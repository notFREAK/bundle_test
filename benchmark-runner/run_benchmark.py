#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import secrets
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "benchmark-runner" / "benchmark-report.json"
REPORT_MD = ROOT / "benchmark-runner" / "benchmark-report.md"


@dataclass
class Target:
    name: str
    cwd: str
    cmd: list[str]
    port: int


TARGETS: list[Target] = [
    Target("aspnet-core", "implementations/aspnet-core", ["dotnet", "run", "--urls", "http://0.0.0.0:5101"], 5101),
    Target("go-svc", "implementations/go-svc", ["go", "run", "main.go"], 8080),
    Target("java-spring", "implementations/java-spring", ["./gradlew", "bootRun"], 8081),
    Target("kotlin-spring", "implementations/kotlin-spring", ["./gradlew", "bootRun"], 8082),
    Target("nest-ts", "implementations/nest-ts", ["npm", "run", "start"], 3000),
    Target("express-node", "implementations/express-node", ["node", "index.js"], 3001),
    Target("fastapi-python", "implementations/fastapi-python", ["python3", "-m", "uvicorn", "main:app", "--port", "8000"], 8000),
    Target("django-python", "implementations/django-python", ["python3", "manage.py", "runserver", "0.0.0.0:8001"], 8001),
    Target("laravel-php", "implementations/laravel-php", ["php", "-S", "0.0.0.0:8002", "index.php"], 8002),
    Target("rails-ruby", "implementations/rails-ruby", ["ruby", "app.rb"], 8003),
    Target("rust-axum", "implementations/rust-axum", ["cargo", "run"], 3002),
    Target("phoenix-elixir", "implementations/phoenix-elixir", ["elixir", "server.exs"], 8004),
]


def http_json(method: str, url: str, body: dict[str, Any] | None = None, token: str | None = None) -> tuple[int, dict[str, Any] | None, float]:
    started = time.perf_counter()
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url=url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req, timeout=4) as resp:
            raw = resp.read().decode("utf-8")
            elapsed = (time.perf_counter() - started) * 1000
            return resp.status, (json.loads(raw) if raw else None), elapsed
    except HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        elapsed = (time.perf_counter() - started) * 1000
        return e.code, parsed, elapsed
    except URLError:
        elapsed = (time.perf_counter() - started) * 1000
        return 0, None, elapsed


def wait_ready(base_url: str, timeout_s: float = 20.0) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        code, _, _ = http_json("GET", f"{base_url}/gateway/status")
        if code == 200:
            return True
        time.sleep(0.5)
    return False


def memory_mb(pid: int) -> float | None:
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = float(line.split()[1])
                    return kb / 1024.0
    except Exception:
        return None
    return None


def db_count_user(username: str) -> int | None:
    dsn = os.getenv("BENCHMARK_POSTGRES_DSN", "postgresql://gateway_user:gateway_pass@127.0.0.1:5432/gatewaydb")
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM users WHERE username=%s", (username,))
                return int(cur.fetchone()[0])
    except Exception:
        return None


def scenario(base_url: str, target_name: str) -> tuple[dict[str, bool], dict[str, float], str]:
    suffix = hashlib.sha1(f"{target_name}-{time.time_ns()}".encode()).hexdigest()[:10]
    username = f"bench_{suffix}"
    email = f"{username}@example.local"
    password = f"P@ss-{secrets.token_hex(6)}"
    checks: dict[str, bool] = {}
    timings: dict[str, float] = {}

    before = db_count_user(username)

    code, _, t = http_json("POST", f"{base_url}/auth/register", {"username": username, "email": email, "password": password})
    checks["register"] = code in (200, 201)
    timings["register_ms"] = t

    code, login_payload, t = http_json("POST", f"{base_url}/auth/login", {"username": username, "password": password})
    access_token = (login_payload or {}).get("accessToken") if isinstance(login_payload, dict) else None
    refresh_token = (login_payload or {}).get("refreshToken") if isinstance(login_payload, dict) else None
    checks["login"] = code == 200 and bool(access_token)
    timings["login_ms"] = t

    code, _, t = http_json("GET", f"{base_url}/auth/me", token=access_token)
    checks["me"] = code == 200
    timings["me_ms"] = t

    code, _, t = http_json("GET", f"{base_url}/metrics/current", token=access_token)
    checks["metrics"] = code == 200
    timings["metrics_ms"] = t

    code, _, t = http_json("GET", f"{base_url}/gateway/status", token=access_token)
    checks["status"] = code == 200
    timings["status_ms"] = t

    code, _, t = http_json("POST", f"{base_url}/auth/refresh", {"refreshToken": refresh_token or ""})
    checks["refresh"] = code == 200
    timings["refresh_ms"] = t

    code, _, t = http_json("POST", f"{base_url}/auth/logout", {"refreshToken": refresh_token or ""}, token=access_token)
    checks["logout"] = code in (200, 204)
    timings["logout_ms"] = t

    code, _, t = http_json("DELETE", f"{base_url}/auth/self", token=access_token)
    checks["delete_self"] = code in (200, 204)
    timings["delete_self_ms"] = t

    after = db_count_user(username)
    if before is not None and after is not None:
        checks["db_user_created"] = after >= before
        checks["db_user_deleted"] = after == before
    else:
        checks["db_user_created"] = False
        checks["db_user_deleted"] = False

    return checks, timings, username


def run_target(t: Target) -> dict[str, Any]:
    base_url = f"http://127.0.0.1:{t.port}/api/v1"
    try:
        proc = subprocess.Popen(t.cmd, cwd=ROOT / t.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as e:
        return {"name": t.name, "ready": False, "checks": {}, "passed": False, "startup_error": str(e)}

    mem_samples: list[float] = []
    try:
        ready = wait_ready(base_url)
        if not ready:
            stderr = (proc.stderr.read() or "")[-1200:] if proc.poll() is not None else ""
            return {"name": t.name, "ready": False, "checks": {}, "passed": False, "startup_error": stderr}

        for _ in range(5):
            m = memory_mb(proc.pid)
            if m is not None:
                mem_samples.append(m)
            time.sleep(0.2)

        checks, timings, username = scenario(base_url, t.name)
        passed = all(checks.get(k, False) for k in ["register", "login", "me", "metrics", "status", "refresh", "logout", "delete_self", "db_user_deleted"])
        return {
            "name": t.name,
            "ready": True,
            "checks": checks,
            "timings_ms": timings,
            "memory_avg_mb": round(statistics.mean(mem_samples), 2) if mem_samples else None,
            "passed": passed,
            "benchmark_username": username,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()


def render_md(results: list[dict[str, Any]]) -> str:
    headers = ["implementation", "passed", "avg_mem_mb", "register_ms", "login_ms", "me_ms", "metrics_ms", "status_ms", "refresh_ms", "logout_ms", "delete_self_ms", "db_deleted"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]

    for r in results:
        t = r.get("timings_ms", {})
        c = r.get("checks", {})
        row = [
            r["name"],
            "✅" if r.get("passed") else "❌",
            str(r.get("memory_avg_mb", "-")),
            f"{t.get('register_ms', '-'):.2f}" if "register_ms" in t else "-",
            f"{t.get('login_ms', '-'):.2f}" if "login_ms" in t else "-",
            f"{t.get('me_ms', '-'):.2f}" if "me_ms" in t else "-",
            f"{t.get('metrics_ms', '-'):.2f}" if "metrics_ms" in t else "-",
            f"{t.get('status_ms', '-'):.2f}" if "status_ms" in t else "-",
            f"{t.get('refresh_ms', '-'):.2f}" if "refresh_ms" in t else "-",
            f"{t.get('logout_ms', '-'):.2f}" if "logout_ms" in t else "-",
            f"{t.get('delete_self_ms', '-'):.2f}" if "delete_self_ms" in t else "-",
            "✅" if c.get("db_user_deleted") else "❌",
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    results = [run_target(t) for t in TARGETS]
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed")),
        "failed": [r["name"] for r in results if not r.get("passed")],
        "results": results,
    }
    REPORT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_md(results), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nMarkdown report: {REPORT_MD}")


if __name__ == "__main__":
    main()
