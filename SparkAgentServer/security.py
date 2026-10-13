"""Shared authentication, without hardware imports."""
import hmac
from starlette.responses import JSONResponse


def authorized(header, token):
    return bool(token) and isinstance(header, str) and hmac.compare_digest(
        header.encode('utf-8'), ('Bearer '+token).encode('utf-8'))


def install_http_auth(app, token):
    @app.middleware('http')
    async def authenticate(request, call_next):
        if not authorized(request.headers.get('Authorization'), token):
            return JSONResponse({'detail': 'Authentication required'}, status_code=401,
                                headers={'WWW-Authenticate': 'Bearer'})
        return await call_next(request)


async def authenticate_device(websocket, token):
    request = getattr(websocket, 'request', None)
    headers = request.headers if request is not None else getattr(websocket, 'request_headers', {})
    if not authorized(headers.get('Authorization'), token):
        await websocket.close(code=1008, reason='Authentication required')
        return False
    return True


def validate_tokens(api_token, device_token):
    if any(not 32 <= len(token) <= 400 or any(not 33 <= ord(c) <= 126 for c in token) for token in (api_token, device_token)):
        raise ValueError('Set SPARKBOT_API_TOKEN and SPARKBOT_DEVICE_TOKEN to random tokens of 32-400 characters')
    if api_token == device_token:
        raise ValueError('Use different API and device tokens')
