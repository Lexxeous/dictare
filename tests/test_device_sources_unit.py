"""Device profiles and input processing without access to physical devices."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.input.device import DeviceInputSource, DeviceProfile, HIDDeviceInputSource


@pytest.fixture
def profile():
    return DeviceProfile("presenter", "Remote", {"KEY_A": "record", "KEY_B": {"command": "switch", "args": {"id": 2}}}, vendor_id=0x1234, product_id=7)


def test_profile_parsing_and_file_loading(tmp_path):
    path = tmp_path / "remote.toml"
    path.write_text('vendor_id = "0x1234"\nproduct_id = "7"\ndebounce_ms = 15\n[bindings]\nKEY_A = "record"\n')
    result = DeviceProfile.load_from_file(path)
    assert (result.name, result.vendor_id, result.product_id, result.debounce_ms) == ("remote", 0x1234, 7, 15)
    assert result.has_hid_ids and result.bindings == {"KEY_A": "record"}
    path.write_text("[invalid")
    assert DeviceProfile.load_from_file(path) is None
    assert not DeviceProfile.from_dict("empty", {}).has_hid_ids
    with pytest.raises(ValueError):
        DeviceProfile.from_dict("bad", {"vendor_id": "nope"})


def test_evdev_discovery_start_and_stop(profile, monkeypatch):
    other = Mock()
    other.name = "Keyboard"
    found = Mock()
    found.name = "Remote control"
    module = SimpleNamespace(list_devices=lambda: ["bad", "other", "found"], InputDevice=Mock(side_effect=[OSError(), other, found]))
    monkeypatch.setitem(sys.modules, "evdev", module)
    monkeypatch.setattr(sys, "platform", "linux")
    thread = Mock()
    monkeypatch.setattr("dictare.input.device.threading.Thread", Mock(return_value=thread))
    source = DeviceInputSource(profile)
    assert source.start(Mock())
    other.close.assert_called_once()
    found.grab.assert_called_once()
    thread.start.assert_called_once()
    assert source.is_running and source.source_name == "Device: presenter"
    source.stop()
    found.ungrab.assert_called_once()
    found.close.assert_called_once()
    assert not source.is_running


def test_evdev_unavailable_and_grab_error(profile, monkeypatch):
    source = DeviceInputSource(profile)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert not source.start(Mock())
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "evdev", None)
    assert not source.start(Mock())
    device = Mock()
    device.name = "Remote"
    device.grab.side_effect = OSError("busy")
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(list_devices=lambda: ["x"], InputDevice=lambda _: device))
    monkeypatch.setattr("dictare.input.device.threading.Thread", Mock())
    assert source.start(Mock())
    device.ungrab.side_effect = OSError()
    device.close.side_effect = OSError()
    source.stop()
    monkeypatch.setattr(source, "_find_device", lambda: None)
    assert not source.start(Mock())


def test_evdev_loop_filters_and_debounces(profile, monkeypatch):
    events = [SimpleNamespace(type=t, value=v, code=c) for t, v, c in [(0, 1, 1), (1, 0, 1), (1, 1, 99), (1, 1, 1), (1, 1, 2), (1, 1, 2)]]
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(ecodes=SimpleNamespace(EV_KEY=1, KEY={1: ("KEY_A", "alternate"), 2: "KEY_B"})))
    monkeypatch.setattr("dictare.input.device.time", SimpleNamespace(time=Mock(side_effect=[1, 1.1, 1.5])))
    source = DeviceInputSource(profile)
    source._device = SimpleNamespace(read_loop=lambda: iter(events))
    received = []
    source._on_input = received.append
    source._listen_loop()
    assert [(e.command, e.args, e.source) for e in received] == [("record", {}, "device:presenter"), ("switch", {"id": 2}, "device:presenter")]


def test_hid_start_report_and_stop(profile, monkeypatch):
    device = Mock()
    module = SimpleNamespace(device=Mock(return_value=device))
    monkeypatch.setitem(sys.modules, "hid", module)
    monkeypatch.setattr("dictare.input.device.threading.Thread", Mock())
    monkeypatch.setattr("dictare.input.device.HID_KEY_MAP", {4: "KEY_A", 5: "KEY_B"})
    monkeypatch.setattr("dictare.input.device.time", SimpleNamespace(time=Mock(side_effect=[1, 1.1, 1.5])))
    source = HIDDeviceInputSource(profile)
    received = []
    assert source.start(received.append)
    device.open.assert_called_once_with(0x1234, 7)
    device.set_nonblocking.assert_called_once_with(True)
    source._handle_report([0, 99, 4, 5])
    source._handle_report([5])
    source._handle_report([5])
    assert [(e.command, e.args, e.source) for e in received] == [("record", {}, "hid:presenter"), ("switch", {"id": 2}, "hid:presenter")]
    assert source.is_running and source.source_name == "HID: presenter"
    source.stop()
    device.close.assert_called_once()
    assert not source.is_running


def test_hid_fallback_errors_and_read_loop(profile, monkeypatch):
    source = HIDDeviceInputSource(profile)
    monkeypatch.setitem(sys.modules, "hid", None)
    monkeypatch.setitem(sys.modules, "hidapi", None)
    assert not source.start(Mock())
    profile.vendor_id = None
    assert not source.start(Mock())
    profile.vendor_id = 1
    device = Mock(manufacturer="Vendor", product="Device")
    monkeypatch.setitem(sys.modules, "hidapi", SimpleNamespace(Device=Mock(return_value=device)))
    monkeypatch.setattr("dictare.input.device.threading.Thread", Mock())
    assert source.start(Mock())
    device.read.side_effect = [bytes([4]), OSError("disconnected")]
    source._handle_report = Mock()
    source._listen_loop()
    source._handle_report.assert_called_once_with([4])
    device.close.side_effect = OSError()
    source.stop()
    monkeypatch.setitem(sys.modules, "hid", SimpleNamespace(device=Mock(side_effect=OSError("open"))))
    assert not source.start(Mock())
