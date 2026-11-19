"""Capture lifecycle tests using an isolated PortAudio stream."""
from unittest.mock import Mock

import numpy as np
import pytest

from dictare.audio import capture


def test_recording_buffers_copied_samples_and_closes_stream(monkeypatch):
    stream = Mock()
    factory = Mock(return_value=stream)
    monkeypatch.setattr(capture.sd, 'InputStream', factory)
    recorder = capture.AudioCapture(sample_rate=8000, device='mic')
    recorder.start_recording()
    recorder.start_recording()
    samples = np.array([[1.0], [2.0]], dtype=np.float32)
    recorder._audio_callback(samples, 2, {}, None)
    samples[:] = 0
    assert recorder.is_recording()
    np.testing.assert_array_equal(recorder.stop_recording(), [1.0, 2.0])
    assert not recorder.is_recording()
    assert recorder.stop_recording().size == 0
    factory.assert_called_once()
    assert factory.call_args.kwargs['device'] == 'mic'
    stream.start.assert_called_once()
    stream.stop.assert_called_once()
    stream.close.assert_called_once()


def test_streaming_callbacks_and_shutdown(monkeypatch):
    stream = Mock()
    monkeypatch.setattr(capture.sd, 'InputStream', Mock(return_value=stream))
    monkeypatch.setattr(capture, '_run_with_timeout', lambda func, **kwargs: func())
    recorder = capture.AudioCapture()
    received = Mock()
    recorder.start_streaming(received)
    recorder.start_streaming(received)
    chunk = np.array([[0.5]], dtype=np.float32)
    recorder._streaming_audio_callback(chunk, 1, {}, None)
    np.testing.assert_array_equal(received.call_args.args[0], [0.5])
    recorder.stop_streaming()
    recorder.stop_streaming()
    stream.start.assert_called_once()
    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    assert recorder._streaming_callback is None


def test_failed_stream_open_clears_callback(monkeypatch):
    monkeypatch.setattr(capture, '_run_with_timeout', Mock(side_effect=TimeoutError('open')))
    recorder = capture.AudioCapture()
    with pytest.raises(TimeoutError, match='open'):
        recorder.start_streaming(Mock())
    assert recorder._streaming_callback is None
