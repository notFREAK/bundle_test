import json
import secrets
from datetime import datetime, timezone
from django.urls import path
from django.http import JsonResponse

USERS = {}
ACCESS = {}
REFRESH = {}
UPTIME = {'value': 0}


def _json(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return {}


def _current_user(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    username = ACCESS.get(auth[7:])
    return USERS.get(username)


def register(request):
    if request.method != 'POST':
        return JsonResponse({}, status=405)
    payload = _json(request)
    username, password = payload.get('username'), payload.get('password')
    if not username or not password:
        return JsonResponse({'error': {'code': 'VALIDATION_ERROR'}}, status=400)
    if username in USERS:
        return JsonResponse({'error': {'code': 'CONFLICT'}}, status=409)
    USERS[username] = {'username': username, 'email': payload.get('email', f'{username}@example.local'), 'password': password, 'role': 'viewer'}
    return JsonResponse({'status': 'registered'}, status=201)


def login(request):
    payload = _json(request)
    user = USERS.get(payload.get('username'))
    if not user or user['password'] != payload.get('password'):
        return JsonResponse({'error': {'code': 'UNAUTHORIZED'}}, status=401)
    access_token = secrets.token_hex(24)
    refresh_token = secrets.token_hex(24)
    ACCESS[access_token] = user['username']
    REFRESH[refresh_token] = user['username']
    return JsonResponse({'accessToken': access_token, 'refreshToken': refresh_token})


def refresh(request):
    payload = _json(request)
    username = REFRESH.get(payload.get('refreshToken'))
    if not username:
        return JsonResponse({'error': {'code': 'UNAUTHORIZED'}}, status=401)
    access_token = secrets.token_hex(24)
    ACCESS[access_token] = username
    return JsonResponse({'accessToken': access_token, 'refreshToken': payload.get('refreshToken')})


def logout(request):
    if not _current_user(request):
        return JsonResponse({'error': {'code': 'UNAUTHORIZED'}}, status=401)
    payload = _json(request)
    REFRESH.pop(payload.get('refreshToken'), None)
    return JsonResponse({'status': 'ok'})


def me(request):
    user = _current_user(request)
    if not user:
        return JsonResponse({'error': {'code': 'UNAUTHORIZED'}}, status=401)
    return JsonResponse({'username': user['username'], 'email': user['email'], 'role': user['role']})


def metrics(request):
    if not _current_user(request):
        return JsonResponse({'error': {'code': 'UNAUTHORIZED'}}, status=401)
    UPTIME['value'] += 1
    return JsonResponse({'temperatureC': 25, 'cpuLoadPercent': 12, 'ramLoadPercent': 24, 'uptimeSeconds': UPTIME['value'], 'supplyVoltageV': 12.0, 'timestampUtc': datetime.now(timezone.utc).isoformat()})


def status(_):
    return JsonResponse({'service': 'ok', 'opcua': 'simulated', 'cache': 'ready'})


urlpatterns = [
    path('api/v1/auth/register', register),
    path('api/v1/auth/login', login),
    path('api/v1/auth/refresh', refresh),
    path('api/v1/auth/logout', logout),
    path('api/v1/auth/me', me),
    path('api/v1/metrics/current', metrics),
    path('api/v1/gateway/status', status),
]
