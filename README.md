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
