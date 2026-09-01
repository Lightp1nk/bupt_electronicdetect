# BUPT Dormitory Electricity Client

This project implements the verified BUPT CAS flow and the authenticated dormitory-electricity API flow using one `httpx.AsyncClient` for the complete lifecycle.

## Setup

```powershell
python -m venv .venv
.\.venv\bin\python.exe -m pip install -r requirements.txt
```

On this MSYS Python installation, Pydantic v2 and pytest are provided by the corresponding MSYS packages because upstream binary wheels are not published for its platform.

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

The app owns one `AuthSessionManager`, which owns at most one `BUPTClient`. A successful `POST /api/v1/auth/login` retains only that client's in-memory HTTP Cookie Jar. Passwords, Cookie values, and CAS data are never stored on disk or kept as manager attributes. Server shutdown and `POST /api/v1/auth/logout` close the client and discard the session.

Available routes:

- `POST /api/v1/auth/login` with `{"username": "...", "password": "..."}`
- `GET /api/v1/auth/status`
- `POST /api/v1/auth/logout`
- `GET /api/v1/electricity/buildings?area_id=1` (minimal protected route)

To verify one login supports repeated protected requests, run the server and then:

```powershell
.\.venv\bin\python.exe scripts\session_probe.py
```
