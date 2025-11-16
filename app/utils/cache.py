"""In-memory TTL cache for quick bot lookups."""

import time
from typing import Any, Dict, Tuple


class TTLCache:
    """Very small in-memory TTL cache for bot lookups, etc."""

    def __init__(self, ttl_seconds: int = 300):
        """Initialize the cache with the desired expiration interval."""
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Return a cached value if present and not expired."""
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value, overwriting any previous entry."""
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        """Remove all cached entries."""
        self._store.clear()
