"""Exercise revocation across proxy, worker permit, and native playback."""

import json
import threading
from unittest.mock import MagicMock

from dictare.config import Config
from dictare.core.tts_manager import TTSManager
from dictare.tts import base
from dictare.tts.proxy import WorkerTTSEngine
from dictare.tts.worker import _playback_permitted


def test_strict_mute_revokes_worker_and_terminates_active_playback(monkeypatch):
    delivered = threading.Event()
    started = threading.Event()
    stopped = threading.Event()
    messages = []
    server = MagicMock()
    def put(agent_id, message):
        messages.append(message)
        delivered.set()
        return True
    server.put_message.side_effect = put
    proxy = WorkerTTSEngine(server)
    manager = TTSManager(Config())
    manager._tts_proxy = proxy
    manager._tts_worker_process = MagicMock(pid=123)
    manager._worker_ready = True
    def signal_worker(pid, sig):
        base.stop_audio_native()
        manager.acknowledge_mute_interrupt(manager.mute_interrupt_id())
    monkeypatch.setattr("os.kill", signal_worker)
    monkeypatch.setattr(base.sys, "platform", "darwin")
    process = MagicMock()
    process.wait.side_effect = lambda **kwargs: stopped.wait(timeout=2)
    process.terminate.side_effect = stopped.set
    def popen(*args, **kwargs):
        started.set()
        return process
    monkeypatch.setattr(base.subprocess, "Popen", popen)
    def urlopen(request, timeout):
        message_id = request.full_url.rsplit("/", 1)[-1]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"allowed": proxy.playback_permitted(message_id)}).encode()
        return response
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    result = []
    speaker = threading.Thread(target=lambda: result.append(proxy.speak("private")))
    player = None
    try:
        speaker.start()
        assert delivered.wait(timeout=2)
        message_id = messages[0]["id"]
        def playback():
            with base.native_playback_permit(lambda: _playback_permitted("http://localhost", "token", message_id)):
                base.play_audio_native("cached.wav")
        player = threading.Thread(target=playback)
        player.start()
        assert started.wait(timeout=2)
        manager.suspend_for_mute()
        assert stopped.wait(timeout=2)
        speaker.join(timeout=2)
        player.join(timeout=2)
        assert result == [False]
        assert not proxy.playback_permitted(message_id)
        manager.resume_after_mute()
        assert not _playback_permitted("http://localhost", "token", message_id)
    finally:
        stopped.set()
        speaker.join(timeout=2)
        if player is not None:
            player.join(timeout=2)


def test_worker_ack_waits_for_player_spawn_racing_with_mute(monkeypatch):
    """A player starting during interruption is stopped before acknowledgement."""
    from fastapi.testclient import TestClient

    from dictare.core.engine import DictareEngine
    from dictare.core.http_server import OpenVIPServer
    from dictare.tts import worker as tts_worker

    engine = DictareEngine(Config(), hotkey_enabled=False)
    server = OpenVIPServer(engine, auth_tokens={"register_tts": "token"})
    client = TestClient(server._app)
    delivered = threading.Event()
    entered_spawn = threading.Event()
    allow_spawn = threading.Event()
    stopped = threading.Event()
    messages = []
    def put(agent_id, message):
        messages.append(message)
        delivered.set()
        return True
    server.put_message = put
    proxy = WorkerTTSEngine(server)
    engine.tts_mgr._tts_proxy = proxy
    engine.tts_mgr._tts_worker_process = MagicMock(pid=123)
    engine.tts_mgr._worker_ready = True
    monkeypatch.setattr("dictare.audio.beep.suspend_feedback", lambda **kwargs: None)
    monkeypatch.setattr(base, "suspend_native_audio", lambda: None)
    process = MagicMock()
    process.terminate.side_effect = stopped.set
    process.wait.side_effect = lambda **kwargs: stopped.wait(timeout=2)
    def popen(*args, **kwargs):
        entered_spawn.set()
        assert allow_spawn.wait(timeout=2)
        return process
    monkeypatch.setattr(base.subprocess, "Popen", popen)
    def urlopen(request, timeout):
        path = request.full_url.split("localhost", 1)[1]
        response = client.request(request.get_method(), path, content=request.data, headers=dict(request.header_items()))
        if response.status_code != 200:
            raise OSError("request rejected")
        wrapper = MagicMock()
        wrapper.__enter__.return_value.read.return_value = response.content
        return wrapper
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    signal_threads = []
    def send_signal(pid, sig):
        def deliver():
            tts_worker._handle_stop_signal(sig, None)
            tts_worker._acknowledge_interruption("http://localhost", "token")
        thread = threading.Thread(target=deliver)
        signal_threads.append(thread)
        thread.start()
    monkeypatch.setattr("os.kill", send_signal)
    speaker = threading.Thread(target=lambda: proxy.speak("hello"))
    player = None
    muter = None
    try:
        speaker.start()
        assert delivered.wait(timeout=2)
        message_id = messages[0]["id"]
        def playback():
            with base.native_playback_permit(lambda: _playback_permitted("http://localhost", "token", message_id)):
                base.play_audio_native("test.wav")
        player = threading.Thread(target=playback)
        player.start()
        assert entered_spawn.wait(timeout=2)
        muter = threading.Thread(target=engine.strict_mute)
        muter.start()
        # Revocation happens before the mute operation can be acknowledged.
        for _ in range(1000):
            if not proxy.playback_permitted(message_id):
                break
            threading.Event().wait(0.001)
        assert not proxy.playback_permitted(message_id)
        assert muter.is_alive()
        allow_spawn.set()
        muter.join(timeout=3)
        assert not muter.is_alive()
        assert stopped.is_set()
        assert engine._strict_audio_error is None
    finally:
        allow_spawn.set()
        stopped.set()
        for thread in [speaker, player, muter, *signal_threads]:
            if thread is not None:
                thread.join(timeout=3)
        tts_worker._stop_requested = False
        tts_worker._interrupt_ack_requested = False
