from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr

app = FastAPI(title='opcua-gateway-fastapi-compliant')

ACCESS: dict[str, dict] = {}
SNAPSHOT: dict = {}
STATUS = {'service': 'ok', 'opcua': 'disconnected', 'cache': 'empty', 'lastReadAt': None}

POSTGRES_DSN = os.getenv('POSTGRES_DSN', 'postgresql://gateway_user:gateway_pass@127.0.0.1:5432/gatewaydb')
OPCUA_ENDPOINT = os.getenv('OPCUA_ENDPOINT', 'opc.tcp://127.0.0.1:4840/metrics/server/')
OPCUA_NAMESPACE_URI = os.getenv('OPCUA_NAMESPACE_URI', 'urn:argum:demo:metrics')
OPCUA_POLL_INTERVAL_SEC = float(os.getenv('OPCUA_POLL_INTERVAL_SEC', '1'))


class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class RefreshIn(BaseModel):
    refreshToken: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def password_hash(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def db_conn():
    import psycopg
    return psycopg.connect(POSTGRES_DSN, connect_timeout=3)


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail={'error': {'code': 'UNAUTHORIZED'}})
    token = authorization.split(' ', 1)[1]
    claims = ACCESS.get(token)
    if not claims:
        raise HTTPException(status_code=401, detail={'error': {'code': 'UNAUTHORIZED'}})
    return claims


@app.post('/api/v1/auth/register', status_code=201)
def register(payload: RegisterIn):
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (email, username, password_hash, display_name, role, is_active)
                    VALUES (%s,%s,%s,%s,'viewer',true)
                    RETURNING id, username, email, role
                    """,
                    (payload.email, payload.username, password_hash(payload.password), payload.username),
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO audit_log (actor_username, event_type, action, http_method, http_path, http_status, success, details)
                    VALUES (%s,'auth.register','register','POST','/api/v1/auth/register',201,true,%s::jsonb)
                    """,
                    (payload.username, json.dumps({'username': payload.username})),
                )
            conn.commit()
        return {'id': str(row[0]), 'username': row[1], 'email': row[2], 'role': row[3]}
    except Exception as e:
        raise HTTPException(status_code=409, detail={'error': {'code': 'CONFLICT', 'message': str(e)}})


@app.post('/api/v1/auth/login')
def login(payload: LoginIn):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, email, role, password_hash, is_active FROM users WHERE username=%s", (payload.username,))
            row = cur.fetchone()
            if not row or not row[5] or row[4] != password_hash(payload.password):
                raise HTTPException(status_code=401, detail={'error': {'code': 'UNAUTHORIZED'}})
            access_token = secrets.token_hex(24)
            refresh_token = secrets.token_hex(24)
            ACCESS[access_token] = {'userId': str(row[0]), 'username': row[1], 'email': row[2], 'role': row[3]}
            cur.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, token_family_id, expires_at)
                VALUES (%s,%s,gen_random_uuid(), now() + interval '30 days')
                """,
                (row[0], token_hash(refresh_token)),
            )
            cur.execute("UPDATE users SET last_login_at=now() WHERE id=%s", (row[0],))
            cur.execute(
                """
                INSERT INTO audit_log (actor_user_id, actor_username, event_type, action, http_method, http_path, http_status, success)
                VALUES (%s,%s,'auth.login','login','POST','/api/v1/auth/login',200,true)
                """,
                (row[0], row[1]),
            )
        conn.commit()
    return {'accessToken': access_token, 'refreshToken': refresh_token, 'expiresInSec': 900}


@app.post('/api/v1/auth/refresh')
def refresh(payload: RefreshIn):
    t_hash = token_hash(payload.refreshToken)
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rt.id, u.id, u.username, u.email, u.role
                FROM refresh_tokens rt JOIN users u ON u.id=rt.user_id
                WHERE rt.token_hash=%s AND rt.revoked_at IS NULL AND rt.expires_at > now()
                """,
                (t_hash,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail={'error': {'code': 'UNAUTHORIZED'}})
            access_token = secrets.token_hex(24)
            ACCESS[access_token] = {'userId': str(row[1]), 'username': row[2], 'email': row[3], 'role': row[4]}
            cur.execute(
                "INSERT INTO audit_log (actor_user_id, actor_username, event_type, action, success) VALUES (%s,%s,'auth.refresh','refresh',true)",
                (row[1], row[2]),
            )
        conn.commit()
    return {'accessToken': access_token, 'refreshToken': payload.refreshToken, 'expiresInSec': 900}


@app.post('/api/v1/auth/logout')
def logout(payload: RefreshIn, current: dict = Depends(get_current_user)):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE refresh_tokens SET revoked_at=now() WHERE token_hash=%s", (token_hash(payload.refreshToken),))
            cur.execute(
                "INSERT INTO audit_log (actor_user_id, actor_username, event_type, action, success) VALUES (%s,%s,'auth.logout','logout',true)",
                (current['userId'], current['username']),
            )
        conn.commit()
    return {'status': 'ok'}


@app.get('/api/v1/auth/me')
def me(current: dict = Depends(get_current_user)):
    return {'id': current['userId'], 'username': current['username'], 'email': current['email'], 'role': current['role']}


@app.delete('/api/v1/auth/self')
def delete_self(current: dict = Depends(get_current_user)):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id=%s", (current['userId'],))
            cur.execute(
                "INSERT INTO audit_log (actor_user_id, actor_username, event_type, action, success) VALUES (%s,%s,'auth.delete_self','delete_self',true)",
                (current['userId'], current['username']),
            )
        conn.commit()
    return {'status': 'deleted'}


@app.get('/api/v1/metrics/current')
def metrics_current(current: dict = Depends(get_current_user)):
    if not SNAPSHOT:
        raise HTTPException(status_code=503, detail={'error': {'code': 'SOURCE_UNAVAILABLE'}})
    return {**SNAPSHOT, 'requestedBy': current['username']}


@app.get('/api/v1/gateway/status')
def gateway_status():
    return STATUS


async def opcua_poll_loop() -> None:
    from asyncua import Client

    while True:
        try:
            async with Client(url=OPCUA_ENDPOINT) as client:
                ns_idx = await client.get_namespace_index(OPCUA_NAMESPACE_URI)
                base = f"0:Objects/{ns_idx}:DeviceMetrics"
                async def read(name: str):
                    node = await client.nodes.root.get_child([base, f"{ns_idx}:{name}"])
                    return await node.read_value()

                payload = {
                    'temperatureC': float(await read('TemperatureC')),
                    'cpuLoadPercent': float(await read('CpuLoadPercent')),
                    'ramLoadPercent': float(await read('RamLoadPercent')),
                    'uptimeSeconds': int(await read('UptimeSeconds')),
                    'supplyVoltageV': float(await read('SupplyVoltageV')),
                    'timestampUtc': str(await read('TimestampUtc')),
                }
                SNAPSHOT.update(payload)
                STATUS.update({'opcua': 'connected', 'cache': 'ready', 'lastReadAt': now_iso()})

                try:
                    with db_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO metric_snapshots (timestamp_utc, temperature_c, cpu_load_percent, ram_load_percent, uptime_seconds, supply_voltage_v, raw_payload)
                                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                                """,
                                (
                                    payload['timestampUtc'],
                                    payload['temperatureC'],
                                    payload['cpuLoadPercent'],
                                    payload['ramLoadPercent'],
                                    payload['uptimeSeconds'],
                                    payload['supplyVoltageV'],
                                    json.dumps(payload),
                                ),
                            )
                        conn.commit()
                except Exception:
                    pass
        except Exception:
            STATUS.update({'opcua': 'degraded'})

        await asyncio.sleep(OPCUA_POLL_INTERVAL_SEC)


@app.on_event('startup')
async def startup() -> None:
    app.state.poller = asyncio.create_task(opcua_poll_loop())


@app.on_event('shutdown')
async def shutdown() -> None:
    task = getattr(app.state, 'poller', None)
    if task:
        task.cancel()
