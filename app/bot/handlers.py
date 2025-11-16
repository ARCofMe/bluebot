"""Example bot command handlers.

In practice, these would call into services like BlueFolder,
your routing engine, photo compliance checker, etc.
"""


def handle_ping(_: str) -> str:
    """Return a basic heartbeat response for connectivity checks."""
    return "pong"


def handle_help(_: str) -> str:
    """Return a help message listing available demo commands."""
    return (
        "Available commands:\n"
        "- ping: basic connectivity check\n"
        "- help: this message"
    )
