import pytest
from app.services.laya_service import LayaService
from scripts.verification_common import STATE, QUESTIONS, assert_gpu, assert_result

pytestmark = pytest.mark.integration

def test_real_standalone_japanese_gpu_single_and_batch():
    service = LayaService()
    service.load()
    assert_gpu(service.info())
    result = service.predict(STATE, QUESTIONS, max_len=8192)
    assert_result(result)
    results = service.predict_batch([{'state': STATE, 'questions': QUESTIONS}, {'state': {'問い合わせ': STATE}, 'questions': QUESTIONS}])
    assert len(results) == 2
    for result in results: assert_result(result)
    assert_gpu(service.info())
