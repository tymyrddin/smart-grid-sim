"""
Smart Grid SimLab — Dashboard
Flask + Plotly Dash 2.x
"""

import yaml
import dash
from dash import dcc, html, Input, Output, State, ctx
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from flask import request, jsonify

from dashboard import mqtt_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_attack_options(path: str = "config/attacks.yaml") -> list:
    try:
        with open(path) as f:
            config = yaml.safe_load(f)
        attacks = config.get("attacks", [])
    except Exception:
        return []

    category_labels = {
        "basic":        "── Basic Attacks ──────────────────────",
        "nation-state": "── Nation-State Techniques ─────────────",
    }
    groups: dict[str, list] = {}
    for a in attacks:
        cat = a.get("category", "basic")
        groups.setdefault(cat, []).append(a)

    options = []
    for cat in ("basic", "nation-state"):
        items = groups.get(cat, [])
        if not items:
            continue
        options.append({"label": category_labels.get(cat, cat), "value": f"__sep_{cat}__", "disabled": True})
        for a in items:
            desc = a.get("description") or f"{a['target']} [{a['type']}]"
            display_id = a["id"]
            if a.get("category") == "nation-state":
                display_id = display_id.replace("nation-", "", 1)
            options.append({
                "label": f"  {display_id}  —  {desc}",
                "value": a["id"],
                "title": a.get("info", ""),
            })

    return options


ATTACK_OPTIONS = _load_attack_options()

# homes_per_feeder from config (default 80)
def _load_homes_per_feeder(path: str = "config/devices.yaml") -> dict:
    try:
        with open(path) as f:
            config = yaml.safe_load(f)
        return {
            d["id"]: d.get("homes_per_feeder", 80)
            for d in config.get("devices", [])
            if d["type"] == "substation"
        }
    except Exception:
        return {}


HOMES_PER_FEEDER = _load_homes_per_feeder()

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

STATUS_COLOR = {
    "online":    "#27ae60",
    "offline":   "#c0392b",
    "fault":     "#e74c3c",
    "no_grid":   "#8e44ad",
    "wiped":     "#636e72",
    "encrypted": "#d35400",
    "unknown":   "#7f8c8d",
}
COMPROMISED_COLOR = "#e67e22"

TYPE_ICON  = {"meter": "⚡", "inverter": "☀", "ev_charger": "🔌", "substation": "⬡"}
TYPE_LABEL = {"meter": "Meters", "inverter": "Inverters", "ev_charger": "EV Chargers", "substation": "Substations"}
TYPE_UNIT  = {"meter": "V", "inverter": "kW", "ev_charger": "kW", "substation": "MW"}
TYPE_FIELD = {"meter": "voltage", "inverter": "output_power", "ev_charger": "power", "substation": "load_mw"}

_BG       = "#0f3460"
_PANEL_BG = "#16213e"
_CARD_BG  = "#0d2137"
_MONO     = "'Courier New', monospace"

_PANEL = {"backgroundColor": _PANEL_BG, "borderRadius": "8px", "padding": "16px", "marginBottom": "16px"}
_H3    = {"color": "#95a5a6", "margin": "0 0 12px 0", "fontSize": "13px",
          "textTransform": "uppercase", "letterSpacing": "1px"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card_color(state: dict) -> tuple[str, str]:
    """Returns (border_color, status_label)."""
    status = state.get("status", "unknown")
    if state.get("safety_system") == "offline":
        return "#9b59b6", "SIS OFFLINE"
    if state.get("protection_online") is False:
        return "#f39c12", "RELAY BYPASSED"
    if status == "wiped":
        return STATUS_COLOR["wiped"], "WIPED"
    if state.get("_compromised") and status == "online":
        return COMPROMISED_COLOR, "COMPROMISED"
    return STATUS_COLOR.get(status, STATUS_COLOR["unknown"]), status.upper().replace("_", " ")


def _make_card(state: dict) -> html.Div:
    device_id   = state.get("id", "?")
    device_type = state.get("type", "?")
    border, label = _card_color(state)

    field = TYPE_FIELD.get(device_type)
    unit  = TYPE_UNIT.get(device_type, "")
    val   = state.get(field)
    metric = f"{field}: {val} {unit}" if val is not None else ""

    cascaded = state.get("_cascaded_from")
    sub_line = html.Div(f"↳ from {cascaded}", style={"color": "#8e44ad", "fontSize": "10px"}) if cascaded else None

    return html.Div(
        style={
            "border": f"2px solid {border}",
            "borderRadius": "6px",
            "padding": "10px 12px",
            "width": "175px",
            "height": "96px",
            "overflow": "hidden",
            "boxSizing": "border-box",
            "backgroundColor": _CARD_BG,
            "fontSize": "12px",
        },
        children=[
            html.Div(f"{TYPE_ICON.get(device_type, '◈')} {device_id}",
                     style={"fontWeight": "bold", "color": "#ecf0f1", "marginBottom": "3px"}),
            html.Div(device_type, style={"color": "#7f8c8d", "fontSize": "10px", "marginBottom": "3px"}),
            html.Div(label, style={"color": border, "fontWeight": "bold", "marginBottom": "3px"}),
            html.Div(metric, style={"color": "#bdc3c7"}),
            sub_line,
        ],
    )


def _homes_affected(states: dict) -> int:
    total = 0
    for s in states.values():
        if s.get("type") == "substation" and s.get("status") in ("fault", "offline"):
            feeders = s.get("feeders_active", 0) or s.get("_last_feeders", 6)
            hpf = HOMES_PER_FEEDER.get(s.get("id", ""), 80)
            total += feeders * hpf
        elif s.get("status") == "no_grid":
            total += 1  # individual device lost
    return total


def _chart_bg() -> dict:
    return dict(paper_bgcolor=_PANEL_BG, plot_bgcolor=_CARD_BG,
                font={"color": "#ecf0f1", "size": 10},
                margin={"l": 44, "r": 8, "t": 30, "b": 40},
                legend={"bgcolor": "rgba(0,0,0,0)", "font": {"size": 9}},
                xaxis={"gridcolor": "#1e3a5f"}, yaxis={"gridcolor": "#1e3a5f"})

# ---------------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------------

app    = dash.Dash(__name__)
server = app.server
app.title = "Smart Grid SimLab"

app.layout = html.Div(
    style={"backgroundColor": _BG, "color": "#ecf0f1", "minHeight": "100vh",
           "padding": "20px 24px", "fontFamily": _MONO},
    children=[

        # Header
        html.Div(
            style={"display": "flex", "justifyContent": "space-between",
                   "alignItems": "flex-start", "marginBottom": "20px"},
            children=[
                html.Div([
                    html.H1("⚡ Smart Grid SimLab",
                            style={"margin": 0, "color": "#00d4aa", "fontSize": "22px"}),
                    html.Div("real-time simulation & attack visualization",
                             style={"color": "#7f8c8d", "fontSize": "11px", "marginTop": "3px"}),
                ]),
                html.Div(style={"display": "flex", "gap": "12px", "alignItems": "flex-start"}, children=[
                    html.Div(id="summary-stats",
                             style={"textAlign": "right", "fontSize": "13px", "lineHeight": "1.8"}),
                    html.Button(
                        "⏸  Pause",
                        id="btn-pause",
                        n_clicks=0,
                        style={
                            "backgroundColor": "#2c3e50", "color": "#ecf0f1",
                            "border": "1px solid #7f8c8d", "padding": "6px 14px",
                            "borderRadius": "4px", "cursor": "pointer",
                            "fontFamily": _MONO, "fontSize": "12px", "whiteSpace": "nowrap",
                        }
                    ),
                ]),
            ],
        ),

        # Alert banner (hidden unless critical)
        html.Div(id="alert-banner"),

        # Attack controls + event log (side by side) — above device grid for better UX
        html.Div(style={"display": "flex", "gap": "16px", "marginBottom": "16px"}, children=[

            html.Div(style={**_PANEL, "flex": "1", "marginBottom": 0}, children=[
                html.H3("Attack Controls", style=_H3),
                dcc.Dropdown(id="attack-select", options=ATTACK_OPTIONS,
                             placeholder="Select an attack...",
                             style={"color": "#111", "fontSize": "12px", "marginBottom": "10px"}),
                html.Div(style={"display": "flex", "gap": "8px", "marginBottom": "8px"}, children=[
                    html.Button("▶  Trigger", id="btn-trigger", n_clicks=0,
                                style={"backgroundColor": "#c0392b", "color": "#fff",
                                       "border": "none", "padding": "8px 16px",
                                       "borderRadius": "4px", "cursor": "pointer",
                                       "fontFamily": _MONO, "fontWeight": "bold"}),
                    html.Button("■  Stop", id="btn-stop", n_clicks=0,
                                style={"backgroundColor": "#555", "color": "#fff",
                                       "border": "none", "padding": "8px 16px",
                                       "borderRadius": "4px", "cursor": "pointer",
                                       "fontFamily": _MONO}),
                ]),
                html.Div(id="attack-feedback", style={"color": "#f39c12", "fontSize": "12px"}),
            ]),

            html.Div(style={**_PANEL, "flex": "2", "marginBottom": 0}, children=[
                html.H3("Event Log", style=_H3),
                html.Div(id="event-log",
                         style={"fontSize": "11px", "maxHeight": "220px", "overflowY": "auto"}),
            ]),
        ]),

        # Device grid
        html.Div(style=_PANEL, children=[
            html.H3("Device Status", style=_H3),
            html.Div(id="device-grid"),
        ]),

        # Charts (2 × 2 subplots)
        html.Div(style=_PANEL, children=[
            html.H3("Live Telemetry", style=_H3),
            dcc.Graph(id="telemetry-chart", style={"height": "380px"},
                      config={"displayModeBar": False}),
        ]),

        dcc.Interval(id="interval", interval=1000, n_intervals=0),
    ],
)

# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

_PAUSE_STYLE  = {"backgroundColor": "#27ae60", "color": "#fff",
                 "border": "none", "padding": "6px 14px", "borderRadius": "4px",
                 "cursor": "pointer", "fontFamily": _MONO, "fontSize": "12px", "whiteSpace": "nowrap"}
_RESUME_STYLE = {"backgroundColor": "#2c3e50", "color": "#ecf0f1",
                 "border": "1px solid #7f8c8d", "padding": "6px 14px", "borderRadius": "4px",
                 "cursor": "pointer", "fontFamily": _MONO, "fontSize": "12px", "whiteSpace": "nowrap"}


@app.callback(
    Output("interval",   "disabled"),
    Output("btn-pause",  "children"),
    Output("btn-pause",  "style"),
    Input("btn-pause",   "n_clicks"),
    State("interval",    "disabled"),
    prevent_initial_call=True,
)
def toggle_pause(_, is_disabled):
    if is_disabled:
        return False, "⏸  Pause",  _RESUME_STYLE
    return True, "▶  Resume", _PAUSE_STYLE


@app.callback(
    Output("summary-stats",  "children"),
    Output("alert-banner",   "children"),
    Output("device-grid",    "children"),
    Input("interval", "n_intervals"),
)
def update_devices(_):
    states = mqtt_client.get_states()

    online      = sum(1 for s in states.values() if s.get("status") == "online" and not s.get("_compromised"))
    compromised = sum(1 for s in states.values() if s.get("_compromised"))
    offline     = sum(1 for s in states.values() if s.get("status") in ("offline", "fault", "no_grid"))
    homes       = _homes_affected(states)

    summary = html.Div([
        html.Div([html.Span("🟢 ", style={"color": "#27ae60"}),
                  html.Span(f"Online: {online}  Compromised: {compromised}  Offline: {offline}",
                            style={"color": "#ecf0f1"})]),
        html.Div(html.Span(f"🏠 Homes affected: {homes:,}",
                           style={"color": "#e74c3c" if homes > 0 else "#27ae60",
                                  "fontWeight": "bold" if homes > 0 else "normal"})),
    ])

    # Alert banner when critical events are active
    if homes > 0 or offline > 0:
        banner = html.Div(
            f"⚠  GRID ALERT — {homes:,} homes affected | {offline} devices down",
            style={
                "backgroundColor": "#c0392b", "color": "#fff",
                "padding": "10px 16px", "borderRadius": "6px",
                "marginBottom": "16px", "fontWeight": "bold",
                "fontSize": "14px", "textAlign": "center",
                "animation": "pulse 1s infinite",
            }
        )
    else:
        banner = html.Div()

    if not states:
        grid = html.Div("No devices visible. Is the simulator and attack engine running?",
                        style={"color": "#7f8c8d"})
    else:
        sorted_states = sorted(states.values(),
                               key=lambda x: (x.get("type", ""), x.get("id", "")))
        grid = html.Div(
            [_make_card(s) for s in sorted_states],
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fill, 175px)",
                "gap": "8px",
            }
        )

    return summary, banner, grid


@app.callback(
    Output("telemetry-chart", "figure"),
    Input("interval", "n_intervals"),
)
def update_chart(_):
    history      = mqtt_client.get_metric_history()
    temp_history = mqtt_client.get_temp_history()
    states       = mqtt_client.get_states()

    # Group device_ids by type
    types_order = ["meter", "inverter", "ev_charger", "substation"]
    type_groups: dict[str, list[str]] = {t: [] for t in types_order}
    for device_id, state in states.items():
        t = state.get("type")
        if t in type_groups:
            type_groups[t].append(device_id)

    titles = [
        f"Smart Meters — voltage (V)",
        f"Inverters — output (kW)",
        f"EV Chargers — power (kW)",
        f"Substations — load (MW)",
    ]
    fig = make_subplots(rows=2, cols=2, subplot_titles=titles,
                        shared_xaxes=False, vertical_spacing=0.18, horizontal_spacing=0.1)

    positions = {"meter": (1, 1), "inverter": (1, 2), "ev_charger": (2, 1), "substation": (2, 2)}

    for device_type, (row, col) in positions.items():
        for device_id in sorted(type_groups.get(device_type, [])):
            data = history.get(device_id, [])
            if not data:
                continue
            times  = [d[0] for d in data]
            values = [d[1] for d in data]

            state  = states.get(device_id, {})
            color  = None
            if state.get("_compromised"):
                color = COMPROMISED_COLOR
            elif state.get("status") in ("offline", "fault", "no_grid"):
                color = STATUS_COLOR["fault"]

            line_style = {"width": 1.8}
            if color:
                line_style["color"] = color

            fig.add_trace(
                go.Scatter(x=times, y=values, mode="lines", name=device_id,
                           line=line_style, showlegend=True),
                row=row, col=col,
            )

    # Transformer temperature overlay on substations subplot (Stuxnet visibility)
    for device_id in sorted(type_groups.get("substation", [])):
        data = temp_history.get(device_id, [])
        if not data:
            continue
        times  = [d[0] for d in data]
        values = [d[1] for d in data]
        # Only show if temperature is elevated (attack active) or briefly after
        if max(values) > 70:
            fig.add_trace(
                go.Scatter(x=times, y=values, mode="lines",
                           name=f"{device_id} °C",
                           line={"width": 1.5, "color": "#e67e22", "dash": "dot"},
                           showlegend=True),
                row=2, col=2,
            )

    # Styling
    fig.update_layout(
        paper_bgcolor=_PANEL_BG,
        plot_bgcolor=_CARD_BG,
        font={"color": "#ecf0f1", "size": 9},
        margin={"l": 44, "r": 8, "t": 44, "b": 8},
        legend={"bgcolor": "rgba(0,0,0,0)", "font": {"size": 9},
                "orientation": "v", "x": 1.02, "y": 1},
        height=380,
    )
    for i in range(1, 3):
        for j in range(1, 3):
            fig.update_xaxes(gridcolor="#1e3a5f", tickfont={"size": 8}, row=i, col=j)
            fig.update_yaxes(gridcolor="#1e3a5f", tickfont={"size": 8}, row=i, col=j)

    return fig


_SEV_COLOR = {
    "CRITICAL": "#e74c3c",
    "WARNING":  "#e67e22",
    "INFO":     "#3498db",
}


@app.callback(
    Output("event-log", "children"),
    Input("interval", "n_intervals"),
)
def update_events(_):
    events = mqtt_client.get_events()
    if not events:
        return html.Div("No events yet.", style={"color": "#7f8c8d"})

    items = []
    for e in reversed(events):
        sev   = e.get("severity", "WARNING")
        color = _SEV_COLOR.get(sev, "#7f8c8d")
        items.append(html.Div(
            style={"marginBottom": "6px", "padding": "5px 8px",
                   "borderLeft": f"3px solid {color}", "backgroundColor": _CARD_BG},
            children=[
                html.Div(style={"display": "flex", "gap": "6px", "alignItems": "baseline"}, children=[
                    html.Span(f"[{e['time']}]", style={"color": "#7f8c8d", "fontSize": "10px"}),
                    html.Span(sev,              style={"color": color, "fontWeight": "bold", "fontSize": "10px"}),
                    html.Span(e.get("source", ""), style={"color": "#ecf0f1", "fontWeight": "bold", "fontSize": "11px"}),
                ]),
                html.Div(e.get("message", ""), style={"color": "#bdc3c7", "fontSize": "11px", "marginTop": "2px"}),
            ],
        ))
    return items


@app.callback(
    Output("attack-feedback", "children"),
    Input("btn-trigger", "n_clicks"),
    Input("btn-stop",    "n_clicks"),
    State("attack-select", "value"),
    prevent_initial_call=True,
)
def handle_attack_button(_t, _s, attack_id):
    if not attack_id:
        return "⚠  Select an attack first."
    action = "trigger" if ctx.triggered_id == "btn-trigger" else "stop"
    mqtt_client.publish(f"control/attacks/{attack_id}", {"action": action, "attack_id": attack_id})
    verb = "TRIGGERED" if action == "trigger" else "STOPPED"
    return f"✓  {attack_id}  {verb}"


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------

@server.route("/attack/trigger", methods=["POST"])
def rest_trigger():
    data = request.get_json(silent=True) or {}
    attack_id = data.get("attack_id")
    action    = data.get("action", "trigger")
    if not attack_id:
        return jsonify({"error": "attack_id required"}), 400
    mqtt_client.publish(f"control/attacks/{attack_id}", {"action": action, "attack_id": attack_id})
    return jsonify({"status": "ok", "attack_id": attack_id, "action": action})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    mqtt_client.start(
        host=os.environ.get("MQTT_HOST", "localhost"),
        port=int(os.environ.get("MQTT_PORT", 1883)),
    )
    app.run(debug=False, host="0.0.0.0", port=8050)
