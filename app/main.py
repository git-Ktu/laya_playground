"""Fixed multilingual service atop Laya's native HTTP lifecycle and worker."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from laya.serve import create_app as native_create_app
from starlette.concurrency import run_in_threadpool
from app.services.laya_service import LayaService, ServiceError
from app.api.policy import PolicyRoute, service_http_error
from app.api.diagnostics import register_diagnostics


class HTTPService:
    def __init__(self, service):
        self.service = service
        self.snapshot = {'loaded': False, 'load_error': None}

    def refresh(self):
        self.snapshot = dict(self.service.info())

    def _call(self, method, *args, **kwargs):
        try:
            return getattr(self.service, method)(*args, **kwargs)
        except ServiceError as error:
            raise service_http_error(error) from error
        finally:
            self.refresh()

    def predict(self, *args, **kwargs):
        return self._call('predict', *args, **kwargs)

    def predict_batch(self, requests):
        return self._call('predict_batch', requests)

    def tokenize(self, state):
        return self._call('tokenize', state)


def create_app(service=None):
    # Reuse Uvicorn's configured output without changing the process root logger.
    application_log = logging.getLogger('app')
    server_log = logging.getLogger('uvicorn.error')
    application_log.handlers = list(server_log.handlers) or [logging.StreamHandler()]
    application_log.setLevel(server_log.getEffectiveLevel())
    application_log.propagate = False
    service = service if service is not None else LayaService()
    adapter = HTTPService(service)
    app = native_create_app(router=adapter)
    native_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with native_lifespan(application):
            await run_in_threadpool(service.load)
            await run_in_threadpool(adapter.refresh)
            yield

    app.router.lifespan_context = lifespan
    for route in list(app.router.routes):
        if getattr(route, 'path', None) == '/health':
            app.router.routes.remove(route)
        elif getattr(route, 'path', None) in ('/v1/systemone', '/v1/systemone/batch'):
            # Rebuild only the two native routes with the same endpoint/signature.
            position = app.router.routes.index(route)
            app.router.routes[position] = PolicyRoute(route.path, route.endpoint,
                methods=route.methods, name=route.name, response_class=route.response_class)
    register_diagnostics(app, service, adapter)
    assets = Path(__file__).resolve().parent
    app.mount("/static", StaticFiles(directory=assets / "static"), name="static")

    @app.get("/", include_in_schema=False)
    async def playground():
        return FileResponse(assets / "templates" / "index.html", media_type="text/html")

    @app.get("/guide", include_in_schema=False)
    async def guide():
        return FileResponse(assets / "templates" / "guide.html", media_type="text/html")

    app.state.service = service
    return app


app = create_app()
