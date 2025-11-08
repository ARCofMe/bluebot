from typing import Callable

"""Very small placeholder command router for Teams bot messages."""


class CommandRouter:
    def __init__(self):
        self._handlers: dict[str, Callable[[str], str]] = {}

    def register(self, command: str, handler: Callable[[str], str]) -> None:
        self._handlers[command.lower()] = handler

    def dispatch(self, text: str) -> str:
        """Route an incoming text message to a handler.

        Very naive: assumes the first word is a command, rest is arguments.
        """
        if not text:
            return "Empty message."

        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handler = self._handlers.get(cmd)
        if not handler:
            return f"Unknown command: {cmd}"

        return handler(arg)
