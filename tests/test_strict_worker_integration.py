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
        manager.acknowledge_strict_interrupt(manager.strict_interrupt_id())
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
        manager.suspend_for_strict()
        assert stopped.wait(timeout=2)
        speaker.join(timeout=2)
        player.join(timeout=2)
        assert result == [False]
        assert not proxy.playback_permitted(message_id)
        manager.resume_after_strict()
        assert not _playback_permitted("http://localhost", "token", message_id)
    finally:
        stopped.set()
        speaker.join(timeout=2)
        if player is not None:
            player.join(timeout=2)
