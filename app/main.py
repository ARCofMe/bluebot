"""Entrypoint for running the Discord bot."""

from app.bot.client import bot
from app.core.config import settings


def main() -> None:
    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
