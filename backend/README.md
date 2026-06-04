# Django Ninja backend

This folder contains a minimal Django project configured to expose an API via Django Ninja.

Quick start

1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Run migrations and start the server (Django dev server)

```powershell
python manage.py migrate
python manage.py runserver
```

Or run with ASGI server (recommended for Ninja/async features):

```powershell
uvicorn engine.asgi:application --reload --port 8000
```

API endpoints

- Hello: `GET /api/v1/` — returns a simple message
