"""Device backend contracts without physical devices or privileged access."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.input.backends import evdev_backend, hidapi_backend, karabiner_backend


class IdleThread:
    def __init__(self, **kwargs):
        self.target = kwargs['target']

    def start(self):
        pass


def test_karabiner_config_and_start(tmp_path, monkeypatch):
    monkeypatch.setattr(karabiner_backend, 'KARABINER_COMPLEX_MODS', tmp_path)
    monkeypatch.setattr(karabiner_backend, '_get_socket_path', lambda: str(tmp_path / 'control.sock'))
    backend = karabiner_backend.KarabinerBackend()
    monkeypatch.setattr(backend, '_start_socket_server', lambda: True)
    assert not backend.start('invalid', {}, Mock())
    assert backend.start('1234:abcd', {'KEY_PAGEUP': 'next', 'unknown': 'skip'}, Mock())
    data = json.loads((tmp_path / 'dictare.json').read_text())
    assert len(data['rules']) == 1
    manipulator = data['rules'][0]['manipulators'][0]
    assert manipulator['from']['key_code'] == 'page_up'
    assert manipulator['conditions'][0]['identifiers'] == [{'vendor_id': 0x1234, 'product_id': 0xabcd}]
    assert "echo 'next'" in manipulator['to'][0]['shell_command']
    assert backend.name == 'karabiner' and backend.supports_grab and backend.is_running
    backend.stop()
    assert not backend.is_running


def test_karabiner_socket_dispatch_and_cleanup(monkeypatch, tmp_path):
    path = tmp_path / 'control.sock'
    path.touch()
    monkeypatch.setattr(karabiner_backend, '_get_socket_path', lambda: str(path))
    sock = Mock()
    conn = Mock()
    conn.recv.return_value = b' next \n'
    backend = karabiner_backend.KarabinerBackend()
    callback = Mock(side_effect=lambda *_: setattr(backend, '_running', False))
    backend._on_command = callback
    sock.accept.return_value = (conn, None)
    backend._socket = sock
    backend._running = True
    backend._socket_loop()
    callback.assert_called_once_with('next', {})
    conn.close.assert_called_once()
    backend.stop()
    sock.close.assert_called_once()
    assert not path.exists()


def test_karabiner_server_setup_and_failure(monkeypatch, tmp_path):
    path = tmp_path / 'sock'
    path.touch()
    monkeypatch.setattr(karabiner_backend, '_get_socket_path', lambda: str(path))
    sock = Mock()
    monkeypatch.setattr(karabiner_backend.socket, 'socket', lambda *_: sock)
    monkeypatch.setattr(karabiner_backend.threading, 'Thread', IdleThread)
    backend = karabiner_backend.KarabinerBackend()
    assert backend._start_socket_server()
    sock.bind.assert_called_once_with(str(path))
    sock.listen.assert_called_once_with(1)
    assert not path.exists()
    sock.bind.side_effect = OSError('denied')
    assert not backend._start_socket_server()


def test_hidapi_enumerate_start_and_report(monkeypatch):
    device = Mock(manufacturer='Vendor', product='Remote')
    module = SimpleNamespace(Device=Mock(return_value=device), enumerate=lambda: [
        SimpleNamespace(vendor_id=0, product_id=0, manufacturer_string=None, product_string=None),
        SimpleNamespace(vendor_id=1, product_id=2, manufacturer_string=None, product_string='Remote'),
    ])
    monkeypatch.setitem(sys.modules, 'hidapi', module)
    monkeypatch.setattr(hidapi_backend.threading, 'Thread', IdleThread)
    monkeypatch.setattr(hidapi_backend.time, 'time', lambda: 10)
    backend = hidapi_backend.HIDAPIBackend()
    assert backend.is_available()
    assert backend.list_devices() == [{'vendor_id': 1, 'product_id': 2, 'manufacturer': '', 'product': 'Remote', 'path': '0001:0002'}]
    assert not backend.start('bad', {}, Mock())
    key, name = next(iter(hidapi_backend.HID_KEY_MAP.items()))
    callback = Mock()
    assert backend.start('0001:0002', {name: 'press'}, callback)
    backend._handle_report([0, 255, key, key])
    backend._handle_report([key])
    callback.assert_called_once_with('press', {})
    assert backend.name == 'hidapi' and not backend.supports_grab and backend.is_running
    backend.stop()
    device.close.assert_called_once()
    assert not backend.is_running


def test_hid_fallback_and_open_failure(monkeypatch):
    monkeypatch.setitem(sys.modules, 'hidapi', None)
    device = Mock()
    module = SimpleNamespace(device=lambda: device, enumerate=lambda: [{'vendor_id': 4, 'product_id': 5}])
    monkeypatch.setitem(sys.modules, 'hid', module)
    monkeypatch.setattr(hidapi_backend.threading, 'Thread', IdleThread)
    backend = hidapi_backend.HIDAPIBackend()
    assert backend.list_devices()[0]['path'] == '0004:0005'
    assert backend.start('4:5', {}, Mock())
    device.open.assert_called_once_with(4, 5)
    device.set_nonblocking.assert_called_once_with(True)
    backend.stop()
    device.open.side_effect = OSError('unavailable')
    assert not backend.start('4:5', {}, Mock())
    monkeypatch.setitem(sys.modules, 'hid', None)
    assert not backend.is_available()
    assert backend.list_devices() == []
    assert not backend.start('4:5', {}, Mock())


def test_hid_listen_loop_dispatches_and_handles_read_error():
    backend = hidapi_backend.HIDAPIBackend()
    backend._device = Mock()
    backend._running = True
    backend._device.read.side_effect = [b'\x01\x02', OSError('disconnected')]
    backend._handle_report = Mock()
    backend._listen_loop()
    backend._handle_report.assert_called_once_with([1, 2])


def test_evdev_discovery_start_events_and_stop(monkeypatch):
    events = [SimpleNamespace(type=1, value=1, code=3), SimpleNamespace(type=1, value=0, code=3)]
    device = Mock(name='device')
    device.name = 'Remote'
    device.info = SimpleNamespace(vendor=1, product=2)
    device.read_loop.return_value = events
    module = SimpleNamespace(list_devices=lambda: ['/dev/input/event0'], InputDevice=lambda _: device,
                             ecodes=SimpleNamespace(EV_KEY=1, KEY={3: ('KEY_A', 'alternate')}))
    monkeypatch.setitem(sys.modules, 'evdev', module)
    monkeypatch.setattr(evdev_backend.sys, 'platform', 'linux')
    monkeypatch.setattr(evdev_backend.threading, 'Thread', IdleThread)
    monkeypatch.setattr(evdev_backend.time, 'time', lambda: 10)
    backend = evdev_backend.EvdevBackend()
    assert backend.is_available()
    assert backend.list_devices()[0]['product'] == 'Remote'
    callback = Mock()
    assert backend.start('0001:0002', {'KEY_A': 'press'}, callback)
    backend._listen_loop()
    callback.assert_called_once_with('press', {})
    device.grab.assert_called_once()
    assert backend.name == 'evdev' and backend.supports_grab and backend.is_running
    backend.stop()
    device.ungrab.assert_called_once()
    assert not backend.is_running


def test_evdev_missing_device_and_import(monkeypatch):
    monkeypatch.setattr(evdev_backend.sys, 'platform', 'linux')
    monkeypatch.setitem(sys.modules, 'evdev', SimpleNamespace(list_devices=lambda: []))
    backend = evdev_backend.EvdevBackend()
    assert not backend.start('missing', {}, Mock())
    monkeypatch.setitem(sys.modules, 'evdev', None)
    assert not backend.is_available()
    assert backend.list_devices() == []
    assert not backend.start('missing', {}, Mock())


@pytest.mark.parametrize(
    ('platform', 'prefer_grab', 'available', 'expected'),
    [
        ('linux', True, {'evdev', 'hidapi'}, 'evdev'),
        ('darwin', True, {'karabiner', 'hidapi'}, 'karabiner'),
        ('darwin', False, {'karabiner', 'hidapi'}, 'hidapi'),
        ('linux', True, {'hidapi'}, 'hidapi'),
        ('linux', True, set(), None),
    ],
)
def test_backend_selection(monkeypatch, platform, prefer_grab, available, expected):
    from dictare.input import backends

    monkeypatch.setattr(sys, 'platform', platform)
    for cls in (evdev_backend.EvdevBackend, hidapi_backend.HIDAPIBackend,
                karabiner_backend.KarabinerBackend):
        monkeypatch.setattr(cls, 'is_available', lambda self: self.name in available)
    assert set(backends.get_available_backends()) == available
    result = backends.get_best_backend(prefer_grab)
    assert (result.name if result else None) == expected
