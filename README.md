# 《宿舍用电监测与智能提醒系统》

当前仓库已实现并验证北邮 CAS 认证、宿舍电费数据采集客户端和进程内 Session 管理。完整的软件工程文档见 [docs/README.md](docs/README.md)。历史记录、统计预测和前端提醒仍处于规划阶段。

## Setup

```powershell
python -m venv .venv
.\.venv\bin\python.exe -m pip install -r requirements.txt
```

On this MSYS Python installation, upstream Pydantic v2 wheels are not published for its platform. Install the corresponding MSYS packages first (Pydantic, pytest, FastAPI and Uvicorn), then create the virtual environment with system packages enabled, or use a standard CPython environment where `pip install -r requirements.txt` succeeds.

## Database migrations

Database structure is versioned with Alembic. Startup creates only missing base tables, then applies versioned migrations. To run migrations manually:

```powershell
.\.venv\bin\alembic.exe upgrade head
```

The C1 migration preserves any former singleton `collection_settings` table as `collection_settings_legacy_unassigned`; it is not automatically assigned to any user.

## Probes

```powershell
.\.venv\bin\python.exe scripts\auth_probe.py
.\.venv\bin\python.exe scripts\electricity_probe.py
```

`electricity_probe.py` is deliberately interactive: it queries only the campus, building, floor and room selected by the user. It never scans rooms or stores credentials, CAS tickets, or Cookie values.

## Public client API

`BUPTClient` extends the verified authentication state machine and exposes `login`, `check_authenticated`, `get_buildings`, `get_floors`, `get_rooms`, `query_electricity`, and `close`. The business methods return `ApiResponse[T]`; upstream IDs are always obtained dynamically from the preceding endpoint.

Run the offline tests with:

```powershell
.\.venv\bin\python.exe -m pytest
```

## In-memory FastAPI session

Start the local API server:

```powershell
.\.venv\bin\python.exe -m uvicorn app.main:app --reload
```

The app uses a browser HttpOnly application-session Cookie and a reusable Runtime `BUPTClient` per local user. Before starting the API, configure a valid Fernet key; the server never generates a fallback key or stores upstream Cookies in plaintext:

```powershell
$env:APP_UPSTREAM_SESSION_KEY = .\.venv\bin\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

After a successful BUPT CAS login, only the app-domain business Cookie payload is encrypted and stored per local user. Passwords, CAS Cookies, tickets, and raw application-session tokens are never persisted. Browser logout revokes only the current local application session; it does not delete the encrypted upstream authorization. Server shutdown closes every transient Runtime Client.

## Multi-user automatic collection

One `AsyncIOScheduler` Cron job runs at `04:00 Asia/Shanghai` by default. It enumerates only enabled, fully configured user collection settings and calls the existing user-scoped collection flow with bounded concurrency. This course-project implementation is intentionally single-process and single-worker; multiple application workers would register duplicate jobs.

Optional environment configuration:

```powershell
$env:COLLECTION_ENABLED = "true"
$env:COLLECTION_HOUR = "4"
$env:COLLECTION_MINUTE = "0"
$env:COLLECTION_MAX_CONCURRENCY = "3"
```

The older `ELECTRICITY_COLLECTION_*` variables remain accepted for compatibility. A missed run is eligible for only a five-minute grace period, so starting the server much later in the morning does not run an obsolete collection job.

## Read-only demonstration data

The production dashboard reads only `electricity_records` by default. To explicitly enable the separate demonstration dataset, set the server-only environment variable below and visit the authenticated dashboard with `?demo=1`:

```powershell
$env:DEMO_MODE_ENABLED = "true"
```

Demo data is loaded from `app/demo_data/demo_electricity_history.json`; it is never written to SQLite and never reaches collection, Alert, Notification, or AstrBot flows. Keep `DEMO_MODE_ENABLED` unset or `false` in normal production operation.

## AstrBot Bridge notifications

The application sends notification bindings' QQ IDs to a trusted internal Bridge; it does not construct or persist AstrBot UMO values and does not call AstrBot's official IM API. Configure the Bridge only through server environment variables:

```powershell
$env:ASTRBOT_BRIDGE_ENDPOINT = "http://bridge.internal:8080"
$env:ASTRBOT_BRIDGE_TOKEN = "..." # optional, if required by the Bridge
```

The application calls `POST {ASTRBOT_BRIDGE_ENDPOINT}/api/send` with `platform`, `target_id`, and plain-text `message`. If configured, the token is sent as a Bearer Authorization header. Keep the Bridge endpoint and token out of source control and browser storage.

Available routes:

- `POST /api/v1/auth/login` with `{"username": "...", "password": "..."}`
- `GET /api/v1/auth/status`
- `POST /api/v1/auth/logout`
- `GET /api/v1/electricity/buildings?area_id=1` (minimal protected route)
- `POST /api/v1/electricity/query` (protected live query and snapshot save)
- `GET /api/v1/electricity/history/{room_id}?area_id=2` (local SQLite history)
- `GET /api/v1/electricity/latest/{room_id}?area_id=2` (local SQLite latest record)

To verify one login supports repeated protected requests, run the server and then:

```powershell
.\.venv\bin\python.exe scripts\session_probe.py
```

To query one selected room and persist a history snapshot:

```powershell
.\.venv\bin\python.exe scripts\database_probe.py
```
