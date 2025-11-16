"""Placeholder Teams client.

This is where you'd implement calls to the Microsoft Graph API or
incoming webhooks to send messages into Teams channels / chats.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TeamsClient:
    """Wrapper around the HTTP client used to talk to Microsoft Teams."""

    def __init__(self):
        """Create an async HTTP client session."""
        # For true bot / Graph integration, you'd store tokens / app ids here.
        self._session = httpx.AsyncClient(timeout=10)

    async def send_to_webhook(self, webhook_url: str, payload: dict[str, Any]) -> bool:
        """Send a simple JSON payload to a Teams incoming webhook."""
        try:
            resp = await self._session.post(webhook_url, json=payload)
            if resp.status_code >= 200 and resp.status_code < 300:
                logger.info("Sent message to Teams webhook.")
                return True
            logger.error("Failed to send message: %s %s", resp.status_code, resp.text)
            return False
        except Exception as exc:
            logger.exception("Error sending message to Teams webhook: %s", exc)
            return False

    async def send_channel_message(self, team_id: str, channel_id: str, text: str) -> None:
        """Stub for sending a channel message via Microsoft Graph.

        TODO: implement actual Graph API call once app registration exists.
        """
        logger.info(
            "[STUB] Would send channel message to team=%s channel=%s: %s",
            team_id,
            channel_id,
            text,
        )

    async def send_dm(self, user_aad_id: str, text: str) -> None:
        """Stub for sending a direct message to a user via Graph."""
        logger.info("[STUB] Would send DM to user=%s: %s", user_aad_id, text)
