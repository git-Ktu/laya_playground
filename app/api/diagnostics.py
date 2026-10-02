"""Fast cached status and worker-thread tokenization."""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from app.models.requests import validate_state
from app.services.laya_service import ServiceError
from app.api.policy import service_http_error
from laya.serve import _read_json_body


def register_diagnostics(app, service, adapter):
    @app.get('/info')
    async def info():
        return dict(adapter.snapshot)

    @app.get('/health')
    async def health():
        snapshot = adapter.snapshot
        ready = bool(snapshot.get('loaded'))
        return JSONResponse(dict(status='ok' if ready else 'unavailable', model_ready=ready,
                                 load_error=snapshot.get('load_error')),
                            status_code=200 if ready else 503)

    @app.post('/tokenize')
    async def tokenize(request: Request):
        body = await _read_json_body(request)
        try:
            state = validate_state(body.get('state') if isinstance(body, dict) else None)
            return await run_in_threadpool(adapter.tokenize, state)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except ServiceError as error:
            raise service_http_error(error) from error
