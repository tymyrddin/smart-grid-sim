"""Tests for the pure helpers in dashboard.app.

Importing dashboard.app builds the Dash app and reads config/*.yaml at module
scope; it does not start a server, so these run without a broker or browser.
"""
from dash import html

import dashboard.app as app

# _read_yaml / config loaders

def test_read_yaml_parses_real_config():
    cfg = app._read_yaml("config/attacks.yaml")
    assert isinstance(cfg, dict)
    assert "attacks" in cfg


def test_load_attack_options_has_separators_and_entries():
    opts = app._load_attack_options()
    # two disabled category separators, plus one entry per configured attack
    separators = [o for o in opts if o.get("disabled")]
    entries = [o for o in opts if not o.get("disabled")]
    assert len(separators) == 2
    assert len(entries) == 39


def test_load_attack_options_missing_file_returns_empty():
    assert app._load_attack_options("does-not-exist.yaml") == []


def test_load_homes_per_feeder_reads_substations():
    homes = app._load_homes_per_feeder()
    assert homes == {"substation-01": 80, "substation-02": 80}


def test_load_homes_per_feeder_missing_file_returns_empty():
    assert app._load_homes_per_feeder("does-not-exist.yaml") == {}


# _card_color

def test_card_color_online():
    border, label = app._card_color({"status": "online"})
    assert border == app.STATUS_COLOR["online"]
    assert label == "ONLINE"


def test_card_color_safety_system_offline_takes_priority():
    border, label = app._card_color({"status": "online", "safety_system": "offline"})
    assert label == "SIS OFFLINE"


def test_card_color_relay_bypassed():
    _, label = app._card_color({"status": "online", "protection_online": False})
    assert label == "RELAY BYPASSED"


def test_card_color_wiped():
    border, label = app._card_color({"status": "wiped"})
    assert border == app.STATUS_COLOR["wiped"]
    assert label == "WIPED"


def test_card_color_compromised_while_online():
    border, label = app._card_color({"status": "online", "_compromised": True})
    assert border == app.COMPROMISED_COLOR
    assert label == "COMPROMISED"


def test_card_color_no_grid_label_humanised():
    _, label = app._card_color({"status": "no_grid"})
    assert label == "NO GRID"


# _homes_affected

def test_homes_affected_counts_faulted_substation_feeders():
    states = {"s1": {"type": "substation", "status": "fault", "feeders_active": 4, "id": "substation-01"}}
    assert app._homes_affected(states) == 4 * 80


def test_homes_affected_uses_fallback_feeder_count_when_zero():
    states = {"s1": {"type": "substation", "status": "fault", "feeders_active": 0, "id": "substation-01"}}
    assert app._homes_affected(states) == 6 * 80


def test_homes_affected_counts_no_grid_devices_individually():
    states = {"m1": {"type": "meter", "status": "no_grid"}}
    assert app._homes_affected(states) == 1


def test_homes_affected_ignores_online_devices():
    states = {"m1": {"type": "meter", "status": "online"}}
    assert app._homes_affected(states) == 0


# _make_card

def test_make_card_returns_div_with_device_id():
    card = app._make_card({"id": "meter-001", "type": "meter", "status": "online", "voltage": 230.0})
    assert isinstance(card, html.Div)
    rendered = str(card)
    assert "meter-001" in rendered


def test_make_card_shows_cascade_source_line():
    card = app._make_card({"id": "meter-001", "type": "meter", "status": "no_grid",
                           "_cascaded_from": "substation-01"})
    assert "substation-01" in str(card)
