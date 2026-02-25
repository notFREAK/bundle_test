-- Инициализация БД для web-сервиса OPC UA -> REST Gateway
-- PostgreSQL 16+

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Пользователи API
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    CONSTRAINT users_role_chk CHECK (role IN ('admin', 'operator', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- Refresh-токены / сессии (хранить только hash токена)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    token_family_id UUID,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_token_id UUID REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT refresh_tokens_exp_chk CHECK (expires_at > issued_at)
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_revoked_at ON refresh_tokens(revoked_at);

-- Аудит API (логирование безопасности и бизнес-действий)
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_username TEXT,
    event_type TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    severity TEXT NOT NULL DEFAULT 'info',
    http_method TEXT,
    http_path TEXT,
    http_status INTEGER,
    request_id TEXT,
    ip_address INET,
    user_agent TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT audit_log_severity_chk CHECK (severity IN ('debug', 'info', 'warn', 'error'))
);

CREATE INDEX IF NOT EXISTS idx_audit_log_event_time ON audit_log(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_user_id ON audit_log(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_http_path ON audit_log(http_path);
CREATE INDEX IF NOT EXISTS idx_audit_log_details_gin ON audit_log USING GIN(details);

-- Текущий статус OPC UA источника (1 запись на источник)
CREATE TABLE IF NOT EXISTS opcua_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL UNIQUE,
    endpoint_url TEXT NOT NULL,
    namespace_uri TEXT NOT NULL,
    root_path TEXT NOT NULL DEFAULT 'Objects/DeviceMetrics',
    poll_interval_ms INTEGER NOT NULL DEFAULT 1000,
    status TEXT NOT NULL DEFAULT 'disconnected',
    last_connect_at TIMESTAMPTZ,
    last_read_at TIMESTAMPTZ,
    consecutive_errors INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT opcua_sources_status_chk CHECK (status IN ('connected', 'disconnected', 'degraded', 'error')),
    CONSTRAINT opcua_sources_poll_chk CHECK (poll_interval_ms BETWEEN 100 AND 60000)
);

-- Необязательная история снапшотов метрик (если web-сервис решит сохранять значения)
CREATE TABLE IF NOT EXISTS metric_snapshots (
    id BIGSERIAL PRIMARY KEY,
    source_id UUID REFERENCES opcua_sources(id) ON DELETE SET NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    temperature_c DOUBLE PRECISION,
    cpu_load_percent DOUBLE PRECISION,
    ram_load_percent DOUBLE PRECISION,
    uptime_seconds BIGINT,
    supply_voltage_v DOUBLE PRECISION,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metric_snapshots_ts ON metric_snapshots(timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_metric_snapshots_source_ts ON metric_snapshots(source_id, timestamp_utc DESC);

-- Триггер на updated_at для users/opcua_sources
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_opcua_sources_updated_at ON opcua_sources;
CREATE TRIGGER trg_opcua_sources_updated_at
BEFORE UPDATE ON opcua_sources
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Seed минимального admin пользователя (пароль нужно сменить после старта)
-- Пароль-заглушка: CHANGE_ME (хэш должен быть заменён приложением/миграцией под выбранный алгоритм)
INSERT INTO users (email, username, password_hash, display_name, role)
VALUES (
    'admin@example.local',
    'admin',
    'REPLACE_WITH_ARGON2_OR_BCRYPT_HASH',
    'Gateway Admin',
    'admin'
)
ON CONFLICT (email) DO NOTHING;

-- Seed OPC UA source по умолчанию
INSERT INTO opcua_sources (source_name, endpoint_url, namespace_uri, root_path, poll_interval_ms, status)
VALUES (
    'default-mini-opcua',
    'opc.tcp://opcua-server:4840/metrics/server/',
    'urn:argum:demo:metrics',
    'Objects/DeviceMetrics',
    1000,
    'disconnected'
)
ON CONFLICT (source_name) DO NOTHING;
