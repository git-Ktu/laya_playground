import pytest
from fastapi.testclient import TestClient
from app.services.laya_service import ModelUnavailableError, CUDAError, OutOfMemoryError, InferenceError
from app.main import create_app

QUESTIONS = {'選択': {'type': 'choice', 'instructions': '分類', 'criteria': {'a': '良い'}}, '評価': {'type': 'score', 'instructions': '評価', 'criteria': ['低', '高']}, '抽出': {'type': 'noul', 'instructions': '要約'}}
class FakeService:
    def __init__(self, ready=True):
        self.ready = ready
        self.loads = 0
        self.calls = []
        self.error = None
    def load(self): self.loads += 1
    def info(self):
        return dict(loaded=self.ready, load_error=None if self.ready else 'cuda_error', model='multilingual', max_len=8192, actual_device='cuda:0', cuda_available=True, gpu_name='GTX 1070', laya_version='0.3.22')
    def predict(self, state, questions, model=None, max_len=8192):
        if not self.ready: raise ModelUnavailableError('unavailable')
        if self.error: raise self.error('safe explanation')
        self.calls.append((state, questions, model, max_len))
        return {'model': 'multilingual', 'answers': {k: {'value': 'a'} for k in questions}, 'usage': {'input_tokens': 3, 'output_tokens': 0}, 'routing': {}, 'diagnostics': self.info()}
    def predict_batch(self, requests):
        return [self.predict(**dict(r, max_len=8192)) for r in requests]
    def tokenize(self, state):
        if self.error: raise self.error('safe explanation')
        if not self.ready: raise ModelUnavailableError('unavailable')
        return dict(state_tokens=3, max_len=8192, over_limit=False)

@pytest.fixture
def service(): return FakeService()
@pytest.fixture
def client(service):
    with TestClient(create_app(service=service)) as client: yield client

def test_health_ready(client, service):
    assert client.get('/health').json()['model_ready'] is True
    assert service.loads == 1

def test_health_unavailable():
    with TestClient(create_app(service=FakeService(False))) as c:
        assert c.get('/health').status_code == 503
        assert c.get('/health').json()['load_error'] == 'cuda_error'
        assert c.get('/info').status_code == 200
        assert c.post('/v1/systemone', json=dict(state='日本語', questions=QUESTIONS)).status_code == 503

def test_info(client):
    info = client.get('/info').json()
    for key in ('model','max_len','actual_device','cuda_available','gpu_name','laya_version'): assert key in info

def test_three_question_types_and_japanese(client):
    r = client.post('/v1/systemone', json=dict(state={'日本語': '文章'}, questions=QUESTIONS))
    assert r.status_code == 200
    assert set(r.json()['answers']) == set(QUESTIONS)
    assert 'routing' in r.json()
    assert 'inference;dur=' in r.headers['server-timing']
    assert float(r.headers['x-inference-time-ms']) >= 0

def test_batch_format_and_fixed_budget(client, service):
    r = client.post('/v1/systemone/batch', json=dict(states=['文章', {'文': '日本語'}], questions=QUESTIONS))
    assert r.status_code == 200
    assert len(r.json()['results']) == 2
    assert r.json()['total_usage']['input_tokens'] == 6
    assert all(call[3] == 8192 for call in service.calls)

@pytest.mark.parametrize('path,base', [('/v1/systemone', {'state':'文章'}), ('/v1/systemone/batch', {'states':['文章']})])
@pytest.mark.parametrize('extra', [{'max_len':4096}, {'max_len':None}, {'model':'english'}, {'model':None}, {'task':'score'}, {'lang':'ja'}, {'head_max_len':1}, {'min_confidence':0.5}, {'hooks':None}])
def test_rejects_overrides(client, path, base, extra):
    assert client.post(path,json=dict(base,questions=QUESTIONS,**extra)).status_code == 422

@pytest.mark.parametrize('body', [[], {}, {'state':' ', 'questions':QUESTIONS}, {'state':'文','questions':{}}, {'state':'文','questions':{'q':{'type':'bad','instructions':'文'}}}])
def test_invalid_input_422(client, body):
    assert client.post('/v1/systemone',json=body).status_code == 422

@pytest.mark.parametrize('error,status', [(ModelUnavailableError,503),(CUDAError,503),(OutOfMemoryError,503),(InferenceError,500)])
@pytest.mark.parametrize('path', ['/v1/systemone','/v1/systemone/batch','/tokenize'])
def test_classified_service_errors(client,service,error,status,path):
    service.error=error
    r=client.post(path,json=dict(state='文',states=['文'],questions=QUESTIONS))
    assert r.status_code == status
    assert r.json()['detail']['code'] == error.code

def test_tokenize(client):
    assert client.post('/tokenize',json={'state':'文章'}).json() == dict(state_tokens=3,max_len=8192,over_limit=False)
    assert client.post('/tokenize',json={'state':None}).status_code == 422

def test_native_limits(client):
    assert client.post('/v1/systemone',content='x'*(2*1024*1024+1)).status_code == 413
    assert client.post('/v1/systemone',content='{').status_code == 400
    assert client.post('/v1/systemone',json=dict(state='文'*50001,questions=QUESTIONS)).status_code == 413

def test_real_service_adapter_fixed_budget_and_load_failure():
    from app.services.laya_service import LayaService
    from tests.test_service import Router
    router = Router()
    with TestClient(create_app(service=LayaService(router_factory=lambda: router))) as c:
        for path, state in [('/v1/systemone', {'state':'日本語'}), ('/v1/systemone/batch', {'states':['日本語']})]:
            assert c.post(path, json=dict(state, questions=QUESTIONS)).status_code == 200
        assert c.post('/v1/systemone',json=dict(state='a'*8193,questions=QUESTIONS)).status_code == 422
        assert c.post('/tokenize',json={'state':'a'*8193}).json()['over_limit'] is True
        assert router.loads == ['multilingual']
        assert all(call[2] == {'model':'multilingual','max_len':8192} for call in router.calls)
    calls=[]
    def fail():
        calls.append(1)
        raise RuntimeError('CUDA load failure')
    with TestClient(create_app(service=LayaService(router_factory=fail))) as c:
        assert c.get('/info').json()['load_error'] == 'cuda_error'
        assert c.post('/tokenize',json={'state':'文'}).status_code == 503
        assert c.get('/health').status_code == 503
    assert calls == [1]

def test_info_does_not_wait_for_inference(client, service):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, release = Event(), Event()
    original = service.predict
    def blocking(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    service.predict = blocking
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(client.post, '/v1/systemone', json=dict(state='文',questions=QUESTIONS))
        assert entered.wait(5)
        try:
            assert client.get('/info').status_code == 200
            assert client.get('/health').status_code == 200
        finally:
            release.set()
        assert pending.result().status_code == 200

def test_streaming_body_stops_at_cap():
    import asyncio
    from starlette.requests import Request
    from fastapi import HTTPException
    from app.api.policy import PolicyRequest
    consumed=[]
    chunks=iter([b'x'*(1024*1024), b'x'*(1024*1024+1), b'never read'])
    async def receive():
        chunk=next(chunks)
        consumed.append(len(chunk))
        return {'type':'http.request','body':chunk,'more_body':True}
    request=Request({'type':'http','headers':[],'method':'POST','path':'/v1/systemone'},receive)
    async def read():
        async for _ in PolicyRequest(request,batch=False).stream(): pass
    with pytest.raises(HTTPException) as error: asyncio.run(read())
    assert error.value.status_code == 413
    assert len(consumed) == 2


def test_playground_and_assets(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert 'charset=utf-8' in response.headers['content-type']
    assert '状態' in response.text
    for asset, content_type in [('playground.css', 'text/css'), ('playground.js', 'javascript')]:
        asset_response = client.get('/static/' + asset)
        assert asset_response.status_code == 200
        assert content_type in asset_response.headers['content-type']
