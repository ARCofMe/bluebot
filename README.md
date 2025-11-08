# Teams Bot Service (FastAPI)

Minimal scaffold for a Microsoft Teams-style bot/webhook service using FastAPI.

## Features

- FastAPI app with health check and placeholder Teams webhook endpoint
- Config via `.env` using Pydantic `BaseSettings`
- Basic logging setup
- Stubs for:
  - Teams client (to send messages to channels/DMs)
  - BlueFolder client integration
  - Simple in-memory/disk-less cache helper

## Quick start

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Then open: http://127.0.0.1:8000/

- `/` – simple status
- `/api/health` – health check endpoint
- `/api/teams/incoming` – placeholder for a Teams incoming webhook / bot endpoint
```
