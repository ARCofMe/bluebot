"""Routes that receive Teams bot or webhook traffic."""

import logging
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse

from app.services.teams_client import TeamsClient
from app.bot.router import CommandRouter
from app.bot import handlers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["teams"])

# Instantiate once
teams_client = TeamsClient()
command_router = CommandRouter()
command_router.register("ping", handlers.handle_ping)
command_router.register("help", handlers.handle_help)


@router.post("/incoming")
async def teams_incoming(request: Request):
    """
    Entry point for incoming Teams messages or webhook payloads.
    In a real deployment, this would be your bot's endpoint registered with Microsoft.
    """
    payload = await request.json()
    logger.info("Received Teams webhook payload: %s", payload)

    text = payload.get("text", "").strip()
    if not text:
        return JSONResponse(
            {"message": "No text content"}, status_code=status.HTTP_400_BAD_REQUEST
        )

    response_text = command_router.dispatch(text)
    logger.info("Responding with: %s", response_text)

    return {"reply": response_text}


@router.post("/notify")
async def teams_notify(request: Request):
    """
    Send a notification to a Teams channel or user via webhook URL.
    Accepts JSON payload: { "webhook_url": "...", "title": "...", "message": "..." }
    """
    data = await request.json()
    webhook_url = data.get("webhook_url")
    title = data.get("title", "Notification")
    message = data.get("message", "")

    if not webhook_url:
        raise HTTPException(status_code=400, detail="Missing 'webhook_url'")

    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": "0076D7",
        "title": title,
        "text": message,
    }

    ok = await teams_client.send_to_webhook(webhook_url, payload)
    return {"success": ok, "title": title, "message": message}


@router.get("/test")
async def teams_test():
    """
    Quick test route to verify the TeamsClient and bot router.
    """
    sample_message = "This is a test notification from BlueBot."
    logger.info("Sending test message to Teams...")

    # NOTE: You can add a default webhook_url to your .env if desired
    return {"status": "ok", "test_message": sample_message}
