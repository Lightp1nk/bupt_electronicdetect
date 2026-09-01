# 《宿舍用电监测与智能提醒系统》

当前仓库已实现并验证北邮 CAS 认证、宿舍电费数据采集客户端和进程内 Session 管理。完整的软件工程文档见 [docs/README.md](docs/README.md)。历史记录、统计预测和前端提醒仍处于规划阶段。

## Setup

```powershell
python -m venv .venv
.\.venv\bin\python.exe -m pip install -r requirements.txt
```

On this MSYS Python installation, upstream Pydantic v2 wheels are not published for its platform. Install the corresponding MSYS packages first (Pydantic, pytest, FastAPI and Uvicorn), then create the virtual environment with system packages enabled, or use a standard CPython environment where `pip install -r requirements.txt` succeeds.

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

The app uses a browser HttpOnly application-session Cookie and one transitional, reusable Runtime `BUPTClient`. Before starting the API, configure a valid Fernet key; the server never generates a fallback key or stores upstream Cookies in plaintext:

```powershell
$env:APP_UPSTREAM_SESSION_KEY = .\.venv\bin\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

After a successful BUPT CAS login, only the app-domain business Cookie payload is encrypted and stored per local user. Passwords, CAS Cookies, tickets, and raw application-session tokens are never persisted. Browser logout revokes only the current local application session; it does not delete the encrypted upstream authorization. Server shutdown closes the transient Runtime Client.

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
