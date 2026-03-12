"""Tests for config-loading functions: load_attacks, load_topology, load_homes."""
from unittest.mock import mock_open, patch
import attacks.engine as engine


ATTACKS_YAML = """
attacks:
  - id: spoof-001
    category: basic
    type: spoofing
    target: meter-001
    description: "test"
    params:
      max_deviation: 50
  - id: cascade-sub
    category: basic
    type: cascading_failure
    target: substation-01
    description: "test"
    params:
      probability: 0.8
"""

DEVICES_YAML = """
devices:
  - id: substation-01
    type: substation
    homes_per_feeder: 80
  - id: substation-02
    type: substation
    homes_per_feeder: 60
  - id: meter-001
    type: meter
    connected_to: substation-01
  - id: meter-002
    type: meter
    connected_to: substation-01
  - id: meter-003
    type: meter
    connected_to: substation-02
"""


def test_load_attacks_returns_dict_keyed_by_id():
    with patch("builtins.open", mock_open(read_data=ATTACKS_YAML)):
        attacks = engine.load_attacks("fake.yaml")
    assert "spoof-001" in attacks
    assert "cascade-sub" in attacks


def test_load_attacks_preserves_all_fields():
    with patch("builtins.open", mock_open(read_data=ATTACKS_YAML)):
        attacks = engine.load_attacks("fake.yaml")
    assert attacks["spoof-001"]["type"] == "spoofing"
    assert attacks["spoof-001"]["target"] == "meter-001"
    assert attacks["spoof-001"]["params"]["max_deviation"] == 50


def test_load_topology_maps_parent_to_children():
    with patch("builtins.open", mock_open(read_data=DEVICES_YAML)):
        topo = engine.load_topology("fake.yaml")
    assert set(topo["substation-01"]) == {"meter-001", "meter-002"}
    assert topo["substation-02"] == ["meter-003"]


def test_load_topology_excludes_devices_without_parent():
    with patch("builtins.open", mock_open(read_data=DEVICES_YAML)):
        topo = engine.load_topology("fake.yaml")
    # Substations have no connected_to — should not appear as children anywhere
    for children in topo.values():
        assert "substation-01" not in children
        assert "substation-02" not in children


def test_load_topology_empty_when_no_connections():
    yaml = "devices:\n  - id: s1\n    type: substation\n"
    with patch("builtins.open", mock_open(read_data=yaml)):
        topo = engine.load_topology("fake.yaml")
    assert topo == {}


def test_load_homes_returns_hpf_per_substation():
    with patch("builtins.open", mock_open(read_data=DEVICES_YAML)):
        homes = engine.load_homes("fake.yaml")
    assert homes["substation-01"] == 80
    assert homes["substation-02"] == 60


def test_load_homes_excludes_non_substation_devices():
    with patch("builtins.open", mock_open(read_data=DEVICES_YAML)):
        homes = engine.load_homes("fake.yaml")
    assert "meter-001" not in homes
    assert "meter-002" not in homes


def test_load_homes_defaults_to_80_when_unspecified():
    yaml = "devices:\n  - id: s1\n    type: substation\n"
    with patch("builtins.open", mock_open(read_data=yaml)):
        homes = engine.load_homes("fake.yaml")
    assert homes["s1"] == 80
