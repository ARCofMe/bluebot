"""Example bot command handlers.

In practice, these would call into services like BlueFolder,
your routing engine, photo compliance checker, etc.
"""


def handle_ping(_: str) -> str:
    return "pong"


def handle_help(_: str) -> str:
    return (
        "Available commands:\n"
        "- ping: basic connectivity check\n"
        "- help: this message"
    )
