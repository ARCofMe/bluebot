"""Entrypoint for running the Discord bot."""

import logging

from app.bot.client import bot
from app.core.config import settings


logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        settings.validate_or_raise()
        bot.run(settings.discord_bot_token)
    except Exception:
        logger.exception("Discord bot terminated during startup or runtime.")
        raise


if __name__ == "__main__":
    main()
