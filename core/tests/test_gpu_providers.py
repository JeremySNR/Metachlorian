import sys
from types import SimpleNamespace
import pytest
from metachlorian import models


@pytest.fixture(autouse=True)
def clear_provider_cache():
    models.ort_providers.cache_clear()
    yield
    models.ort_providers.cache_clear()


def test_cpu_install_does_not_load_cuda(monkeypatch):
    def unexpected():
        pytest.fail('CPU runtime must not attempt to load CUDA DLLs')
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(
        get_available_providers=lambda:['CPUExecutionProvider'], preload_dlls=unexpected))
    assert models.ort_providers() == ['CPUExecutionProvider']


def test_cuda_dlls_are_preloaded_once_and_cpu_fallback_retained(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(
        get_available_providers=lambda:['CUDAExecutionProvider','CPUExecutionProvider'],
        preload_dlls=lambda:calls.append('load')))
    assert models.ort_providers() == ['CUDAExecutionProvider','CPUExecutionProvider']
    models.ort_providers()
    assert calls == ['load']


def test_older_runtime_without_preload_api_remains_supported(monkeypatch):
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(
        get_available_providers=lambda:['DmlExecutionProvider','CPUExecutionProvider']))
    assert models.ort_providers() == ['DmlExecutionProvider','CPUExecutionProvider']


def test_ocr_uses_available_cuda_provider(monkeypatch):
    from metachlorian.analysers import ocr
    ocr._engine.cache_clear()
    monkeypatch.setattr(models,'ort_providers',lambda:['CUDAExecutionProvider','CPUExecutionProvider'])
    monkeypatch.setitem(sys.modules,'rapidocr_onnxruntime',SimpleNamespace(RapidOCR=lambda **kw:kw))
    try:
        engine = ocr._engine()
        assert engine['det_use_cuda'] and engine['rec_use_cuda'] and not engine['det_use_dml']
    finally:
        ocr._engine.cache_clear()
