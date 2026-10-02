import json
from types import SimpleNamespace
import pytest
from app.services.laya_service import (LayaService, ModelUnavailableError, CUDAError, OutOfMemoryError, InferenceError)
from tests.test_validation import QUESTIONS

class Tokenizer:
    mask_token = '[MASK]'
    def __init__(self): self.text = None
    def __call__(self, text, **kwargs):
        assert kwargs == {'add_special_tokens': False}
        self.text = text
        return {'input_ids': list(range(len(text)))}

class Router:
    def __init__(self):
        self.calls = []; self.loads = []; self.error = None; self.fallback = False
        self.agent = SimpleNamespace(tok=Tokenizer(), device='cuda:0', cpu_fallback_count=0,
                                     model=SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device='cuda:0')])))
    def load(self, name): self.loads.append(name); return self.agent
    def predict(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        if self.error: raise self.error
        if self.fallback:
            self.agent.device = 'cpu'; self.agent.cpu_fallback_count = 1
            self.agent.model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device='cpu')]))
        return {'model': 'multilingual', 'answers': {}, 'usage': {'truncated': True, 'state_tokens_dropped': 2}, 'routing': {}}
    def predict_batch(self, requests, batch_size):
        assert batch_size == 1
        return [self.predict(**r) for r in requests]

@pytest.fixture
def setup():
    router = Router(); service = LayaService(router_factory=lambda: router)
    service.load(); return service, router

def test_load_once():
    router = Router(); service = LayaService(router_factory=lambda: router)
    service.load(); service.load()
    assert router.loads == ['multilingual']
    assert service.loaded == ['multilingual']

def test_multilingual_and_8192_for_single_and_batch(setup):
    service, router = setup
    service.predict('日本語', QUESTIONS)
    service.predict_batch([{'state': 'one', 'questions': QUESTIONS}, {'state': 'two', 'questions': QUESTIONS}])
    assert len(router.calls) == 3
    assert all(call[2] == {'model': 'multilingual', 'max_len': 8192} for call in router.calls)

def test_rejects_8193_state_tokens_before_predict(setup):
    service, router = setup
    service.predict('a' * 8192, QUESTIONS)
    with pytest.raises(ValueError): service.predict('a' * 8193, QUESTIONS)
    with pytest.raises(ValueError): service.predict_batch([{'state': 'a' * 8193, 'questions': QUESTIONS}])
    assert len(router.calls) == 1

def test_json_japanese_state(setup):
    service, router = setup
    state = {'名前': '太郎[MASK]'}
    expected = json.dumps(state, ensure_ascii=False).replace('[MASK]', ' ')
    assert service.tokenize(state)['state_tokens'] == len(expected)
    assert router.agent.tok.text == expected
    service.predict(state, QUESTIONS)
    assert router.calls[0][0] == state

def test_preserves_usage_truncation(setup):
    service, _ = setup
    result = service.predict('日本語', QUESTIONS)
    assert result['usage'] == {'truncated': True, 'state_tokens_dropped': 2}
    assert result['diagnostics']['actual_device'] == 'cuda:0'

def test_reports_cpu_fallback(setup):
    service, router = setup; router.fallback = True
    result = service.predict('日本語', QUESTIONS)
    assert result['diagnostics']['actual_device'] == 'cpu'
    assert service.info()['model_parameter_device'] == 'cpu'
    assert service.info()['cpu_fallback_count'] == 1

@pytest.mark.parametrize('error, expected', [(RuntimeError('CUDA failed'), CUDAError), (RuntimeError('CUDA out of memory'), OutOfMemoryError), (RuntimeError('secret input'), InferenceError)])
def test_classifies_inference_errors(setup, error, expected):
    service, router = setup; router.error = error
    with pytest.raises(expected) as exc: service.predict('secret input', QUESTIONS)
    assert 'secret input' not in str(exc.value)

def test_model_unavailable_and_no_load_retry():
    calls = []
    def factory(): calls.append(1); raise RuntimeError('load failure')
    service = LayaService(router_factory=factory)
    service.load(); service.load()
    assert calls == [1]
    assert service.info()['loaded'] is False
    with pytest.raises(ModelUnavailableError): service.predict('x', QUESTIONS)

@pytest.mark.parametrize('kwargs', [{'model': 'base'}, {'max_len': 1}])
def test_fixed_overrides_rejected(setup, kwargs):
    service, router = setup
    with pytest.raises(ValueError): service.predict('x', QUESTIONS, **kwargs)
    assert router.calls == []

def test_standard_server_omitted_model_is_multilingual(setup):
    service, router = setup
    service.predict('日本語', QUESTIONS, model=None)
    service.predict_batch([{'state': '日本語', 'questions': QUESTIONS, 'model': None}])
    assert all(call[2]['model'] == 'multilingual' for call in router.calls)

@pytest.mark.parametrize('path', ['single', 'batch', 'tokenize'])
@pytest.mark.parametrize('error, expected', [
    (RuntimeError('tokenizer failed with secret input'), InferenceError),
    (RuntimeError('CUDA tokenizer failed'), CUDAError),
    (RuntimeError('CUDA out of memory'), OutOfMemoryError),
])
def test_classifies_tokenizer_errors(setup, path, error, expected):
    service, router = setup
    class BrokenTokenizer:
        mask_token = '[MASK]'
        def __call__(self, *args, **kwargs):
            raise error
    router.agent.tok = BrokenTokenizer()
    with pytest.raises(expected) as exc:
        if path == 'single':
            service.predict('secret input', QUESTIONS)
        elif path == 'batch':
            service.predict_batch([{'state': 'secret input', 'questions': QUESTIONS}])
        else:
            service.tokenize('secret input')
    assert 'secret input' not in str(exc.value)
    assert router.calls == []

@pytest.mark.parametrize('item', [None, 'text', 4, []])
def test_rejects_malformed_batch_items(setup, item):
    service, router = setup
    with pytest.raises(ValueError, match='request must be an object'):
        service.predict_batch([item])
    assert router.calls == []

def test_default_factory_uses_requested_standalone_checkpoint(monkeypatch):
    import laya
    calls = []
    router = Router()
    def factory(**kwargs):
        calls.append(kwargs)
        return router
    monkeypatch.setattr(laya, 'Router', factory)
    service = LayaService()
    service.load()
    assert calls == [{'models': {'multilingual': 'convaiinnovations/laya-multilingual'}, 'device': 'cuda'}]
    assert service.info()['model_id'] == 'convaiinnovations/laya-multilingual'


def test_default_uvicorn_logs_safe_startup_loading_inference_and_errors():
    """Catch disabled application INFO output under the documented server config."""
    import subprocess
    import sys
    script = """
import uvicorn
uvicorn.Config('app.main:app')
from tests.test_service import Router, QUESTIONS
from app.main import create_app
from app.services.laya_service import LayaService, InferenceError
router = Router()
service = LayaService(router_factory=lambda: router)
create_app(service)
service.load()
service.predict('PRIVATE_REQUEST_BODY', QUESTIONS)
router.error = RuntimeError('PRIVATE_EXCEPTION_CONTENT')
try:
    service.predict('PRIVATE_REQUEST_BODY', QUESTIONS)
except InferenceError:
    pass
def broken_factory():
    raise RuntimeError('PRIVATE_LOADING_EXCEPTION')
failed = LayaService(router_factory=broken_factory)
failed.load()
"""
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert 'startup' in output
    assert 'loading' in output
    assert 'model=multilingual' in output
    assert 'cuda_available=' in output
    assert 'gpu_name=' in output
    assert 'compute_capability=' in output
    assert 'torch_arch_list=' in output
    assert 'requested_device=cuda' in output
    assert 'device=cuda:0 loaded' in output
    assert 'inference_ms=' in output
    assert 'error=inference_error' in output
    assert 'PRIVATE_' not in output


def test_startup_diagnostic_failure_does_not_prevent_model_loading(monkeypatch):
    router = Router()
    service = LayaService(router_factory=lambda: router)
    def unavailable_probe():
        raise RuntimeError('PRIVATE_DIAGNOSTIC_FAILURE')
    monkeypatch.setattr(service, 'info', unavailable_probe)
    service.load()
    assert service.loaded == ['multilingual']
    assert service.predict('ordinary text', QUESTIONS)['diagnostics']['actual_device'] == 'cuda:0'
