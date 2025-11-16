"""FastAPI application entrypoint for the BlueBot extension."""

from fastapi import FastAPI
from app.api.routes import health, teams_incoming, bluefolder_assignments

app = FastAPI(title="BlueBot Extension API", version="0.1.0")

# Register routers
app.include_router(health.router)
app.include_router(teams_incoming.router)
app.include_router(bluefolder_assignments.router)
