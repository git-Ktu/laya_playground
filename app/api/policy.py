"""Validate application policy inside the native admitted, bounded body read."""
import json
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from laya import serve
from app.models.requests import validate_request

class PolicyRequest(Request):
    def __init__(self, original, *, batch):
        super().__init__(original.scope, original.receive)
        self.original = original
        self.batch = batch

    async def stream(self):
        raw = await serve._read_body_capped(self.original)
        try:
            body = json.loads(raw)
        except (ValueError, RecursionError):
            raise HTTPException(400, 'request body must be valid JSON')
        # Reject every upstream routing/budget control the fixed service cannot honor.
        if isinstance(body, dict):
            unsupported = set(body) & (set(serve.BODY_CONTROLS) | set(serve.BODY_REFUSALS)) - {'model', 'max_len'}
            if unsupported:
                raise HTTPException(422, 'unsupported controls: ' + ', '.join(sorted(unsupported)))
        try:
            validate_request(body, batch=self.batch)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        yield raw
        yield b''

class PolicyRoute(APIRoute):
    def get_route_handler(self):
        native = super().get_route_handler()
        async def handler(request):
            return await native(PolicyRequest(request, batch=self.path.endswith('/batch')))
        return handler


def service_http_error(error):
    return HTTPException(500 if error.code == 'inference_error' else 503,
                         {'code': error.code, 'message': str(error)})
