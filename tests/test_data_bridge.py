"""DataBridge tests."""

import time
from unittest.mock import MagicMock

from lcm_cli.dashboard.data_bridge import DataBridge


def test_bridge_initial_state():
    bridge = DataBridge()
    assert bridge.is_running is False
    assert bridge.get_channels() == []


def test_bridge_subscriber_management():
    bridge = DataBridge()
    bridge.add_subscriber("ws1", ["imu", "motor"], ["accel_x"])
    assert "imu" in bridge.subscriptions
    assert "ws1" in bridge.subscriptions["imu"]
    assert "ws1" in bridge.subscriptions["motor"]

    bridge.remove_subscriber("ws1")
    assert "imu" not in bridge.subscriptions
    assert "motor" not in bridge.subscriptions


def test_bridge_on_packet_with_registry():
    """Simulate a decoded packet flowing through the bridge."""
    bridge = DataBridge()

    # Create a mock type registry that returns a decode class
    mock_registry = MagicMock()
    mock_decode_cls = MagicMock()

    # Create a fake decoded message object
    decoded = type("Msg", (), {"speed": 1.5, "accel": 0.3})()
    mock_decode_cls.decode.return_value = decoded

    mock_registry.find_by_fingerprint.return_value = mock_decode_cls
    bridge.set_type_registry(mock_registry)

    # Create a fake packet
    pkt = MagicMock()
    pkt.has_channel = True
    pkt.channel = "test_ch"
    pkt.payload = b"\x00" * 16  # Fake payload with fingerprint

    bridge.on_packet(pkt)

    assert "test_ch" in bridge.get_channels()
    schema = bridge.get_schema("test_ch")
    assert schema is not None
    paths = [s["path"] for s in schema]
    assert "speed" in paths
    assert "accel" in paths


def test_bridge_get_history():
    bridge = DataBridge()
    mock_registry = MagicMock()
    mock_decode_cls = MagicMock()
    decoded = type("Msg", (), {"val": 42.0})()
    mock_decode_cls.decode.return_value = decoded
    mock_registry.find_by_fingerprint.return_value = mock_decode_cls
    bridge.set_type_registry(mock_registry)

    pkt = MagicMock()
    pkt.has_channel = True
    pkt.channel = "ch1"
    pkt.payload = b"\x00" * 16

    bridge.on_packet(pkt)

    history = bridge.get_history("ch1", ["val"])
    assert len(history["val"]) == 1
    assert history["val"][0][1] == 42.0


def test_bridge_undecodable_packet_skipped():
    bridge = DataBridge()
    mock_registry = MagicMock()
    mock_registry.find_by_fingerprint.return_value = None
    bridge.set_type_registry(mock_registry)

    pkt = MagicMock()
    pkt.has_channel = True
    pkt.channel = "unknown"
    pkt.payload = b"\x00" * 16

    bridge.on_packet(pkt)
    assert bridge.get_channels() == []
