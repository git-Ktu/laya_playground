"""One locked, fixed-model adapter for Laya's standard HTTP worker."""
import logging
from importlib.metadata import version
from threading import RLock
from time import perf_counter

from app.models.requests import MODEL, MAX_LEN, validate_request, validate_state

log = logging.getLogger(__name__)


class ServiceError(RuntimeError):
    code = 'inference_error'


class ModelUnavailableError(ServiceError):
    code = 'model_unavailable'


class CUDAError(ServiceError):
    code = 'cuda_error'


class OutOfMemoryError(ServiceError):
    code = 'out_of_memory'


class InferenceError(ServiceError):
    pass


def _classify(error):
    message = str(error).lower()
    if 'out of memory' in message or type(error).__name__ == 'OutOfMemoryError':
        return OutOfMemoryError('Inference ran out of memory; shorten the state or restart the application.')
    if 'cuda' in message:
        return CUDAError('CUDA inference failed; check GPU availability and restart the application.')
    return InferenceError('Model inference failed; check the application diagnostics.')


class LayaService:
    def __init__(self, *, router_factory=None, device='cuda'):
        self._factory = router_factory
        self._requested_device = device
        self._lock = RLock()
        self._attempted = False
        self._router = None
        self._agent = None
        self._diagnostics = {'model': MODEL, 'model_id': 'convaiinnovations/laya-multilingual', 'max_len': MAX_LEN, 'requested_device': device,
                             'loaded': False, 'actual_device': None, 'model_parameter_device': None,
                             'cpu_fallback_count': 0, 'load_error': None}

    @property
    def loaded(self):
        with self._lock:
            return [MODEL] if self._agent is not None else []

    @property
    def models(self):
        return {MODEL: 'convaiinnovations/laya-multilingual'}

    def load(self):
        with self._lock:
            if self._attempted:
                return
            self._attempted = True
            log.info('model=%s model_id=%s requested_device=%s loading', MODEL,
                     self._diagnostics['model_id'], self._requested_device)
            try:
                snapshot = self.info()
                log.info('startup model=%s cuda_available=%s gpu_name=%s requested_device=%s '
                         'compute_capability=%s torch_arch_list=%s', MODEL,
                         snapshot['cuda_available'], snapshot['gpu_name'], self._requested_device,
                         snapshot['compute_capability'], snapshot['torch_arch_list'])
            except Exception:
                log.error('startup model=%s error=diagnostic_error', MODEL)
            try:
                if self._factory is None:
                    from laya import Router
                    self._router = Router(models=self.models, device=self._requested_device)
                else:
                    self._router = self._factory()
                self._agent = self._router.load(MODEL)
                self._diagnostics['loaded'] = True
                self._update_device()
                log.info('model=%s device=%s loaded', MODEL, self._diagnostics['actual_device'])
            except Exception as error:
                self._agent = None
                self._diagnostics['load_error'] = _classify(error).code
                log.error('model=%s error=%s', MODEL, self._diagnostics['load_error'])

    def _require_loaded(self):
        if self._agent is None:
            raise ModelUnavailableError('Multilingual model is unavailable; check diagnostics and restart the application.')

    def _update_device(self):
        if self._agent is None:
            return
        self._diagnostics['actual_device'] = str(self._agent.device)
        self._diagnostics['cpu_fallback_count'] = getattr(self._agent, 'cpu_fallback_count', 0)
        parameter = next(self._agent.model.parameters(), None)
        self._diagnostics['model_parameter_device'] = str(parameter.device) if parameter is not None else None

    def info(self):
        with self._lock:
            self._update_device()
            import torch
            snapshot = dict(self._diagnostics)
            available = torch.cuda.is_available()
            snapshot.update(cuda_available=available, gpu_name=torch.cuda.get_device_name(0) if available else None,
                            compute_capability=list(torch.cuda.get_device_capability(0)) if available else None,
                            torch_arch_list=torch.cuda.get_arch_list(), torch_version=torch.__version__,
                            laya_version=version('laya'))
            return snapshot

    def _count(self, state):
        self._require_loaded()
        try:
            from laya.common import encode_text, serialize_state
            text = serialize_state(state).replace(self._agent.tok.mask_token, ' ')
            return len(encode_text(self._agent.tok, text, add_special_tokens=False)['input_ids'])
        except Exception as error:
            classified = _classify(error)
            log.error('model=%s error=%s', MODEL, classified.code)
            raise classified from error

    def tokenize(self, state):
        with self._lock:
            validate_state(state)
            count = self._count(state)
            return {'state_tokens': count, 'max_len': MAX_LEN, 'over_limit': count > MAX_LEN}

    def _check_tokens(self, state):
        if self._count(state) > MAX_LEN:
            raise ValueError('state exceeds the 8192 token limit')

    def _infer(self, operation):
        start = perf_counter()
        try:
            result = operation()
        except Exception as error:
            classified = _classify(error)
            log.error('model=%s error=%s', MODEL, classified.code)
            raise classified from error
        finally:
            self._update_device()
            log.info('model=%s device=%s inference_ms=%.2f', MODEL,
                     self._diagnostics['actual_device'], (perf_counter() - start) * 1000)
        metadata = dict(self._diagnostics)
        metadata['inference_time_ms'] = (perf_counter() - start) * 1000
        if isinstance(result, list):
            return [dict(item, diagnostics=dict(metadata)) for item in result]
        return dict(result, diagnostics=metadata)

    def predict(self, state, questions, model=MODEL, max_len=MAX_LEN):
        with self._lock:
            body = validate_request({'state': state, 'questions': questions, 'model': MODEL if model is None else model, 'max_len': max_len})
            self._require_loaded()
            self._check_tokens(state)
            return self._infer(lambda: self._router.predict(**body))

    def predict_batch(self, requests):
        with self._lock:
            self._require_loaded()
            if not isinstance(requests, (list, tuple)):
                raise ValueError('batch must be an array of requests')
            for request in requests:
                if not isinstance(request, dict):
                    raise ValueError('request must be an object')
            bodies = [validate_request(dict(request, model=MODEL if request.get('model') is None else request['model']))
                      for request in requests]
            if not bodies:
                raise ValueError('batch must be nonempty')
            for body in bodies:
                self._check_tokens(body['state'])
            return self._infer(lambda: self._router.predict_batch(bodies, batch_size=1))
