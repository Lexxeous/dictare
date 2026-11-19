"""CUDA probing and fallback behavior without GPU libraries."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare import cuda_setup


def test_find_and_preload_libraries(tmp_path, monkeypatch):
    lib = tmp_path / "libcudnn.so.9"
    lib.touch()
    monkeypatch.setattr(cuda_setup.glob, "glob", lambda pattern: [str(lib)] if "libcudnn" in pattern else [str(tmp_path)])
    assert cuda_setup._find_cudnn_path() == str(tmp_path)
    loader = Mock()
    monkeypatch.setattr(cuda_setup.ctypes, "CDLL", loader)
    assert cuda_setup._preload_cudnn_libraries(str(tmp_path)) == (True, None)
    loader.assert_called_once()
    loader.side_effect = OSError("bad library")
    ok, message = cuda_setup._preload_cudnn_libraries(str(tmp_path))
    assert not ok and "bad library" in message
    lib.unlink()
    assert cuda_setup._preload_cudnn_libraries(str(tmp_path)) == (False, "No cuDNN libraries found")
    assert cuda_setup._find_cudnn_path() == str(tmp_path)  # mocked library listing


@pytest.mark.parametrize("available,path,preload,expected", [
    (False, None, (False, "x"), (False, "cpu")),
    (True, None, (False, "x"), (False, "cpu")),
    (True, "/fake", (False, "load failed"), (False, "cpu")),
    (True, "/fake", (True, None), (True, "cuda")),
])
def test_setup_cuda_paths(monkeypatch, available, path, preload, expected):
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: available)))
    monkeypatch.setattr(cuda_setup, "_find_cudnn_path", lambda: path)
    monkeypatch.setattr(cuda_setup, "_preload_cudnn_libraries", lambda _: preload)
    console = Mock()
    assert cuda_setup.setup_cuda(console, verbose=True) == expected
    if available:
        assert console.print.called


def test_gpu_probe_prefers_ctranslate_and_falls_back_to_torch(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 2))
    assert cuda_setup.check_gpu_available() == (True, 2)
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=Mock(side_effect=RuntimeError())))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1)))
    assert cuda_setup.check_gpu_available() == (True, 1)
    monkeypatch.setitem(sys.modules, "torch", None)
    assert cuda_setup.check_gpu_available() == (False, 0)


def test_acceleration_hint_for_mlx(monkeypatch):
    monkeypatch.setattr("dictare.utils.install_info.get_feature_install_message", lambda feature: f"install {feature}")
    console = Mock()
    cuda_setup._print_acceleration_hint(console, "mlx")
    assert any("install mlx" in call.args[0] for call in console.print.call_args_list if call.args)
