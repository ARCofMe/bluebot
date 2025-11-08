import os
import json
import time
import logging

logger = logging.getLogger(__name__)

# Create a hidden cache folder within utils
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_TTL_MINUTES = 30


class CacheManager:
    """
    Simple key–value cache with JSON persistence.
    Supports TTL expiration and in-memory + on-disk caching.
    """

    def __init__(self, name: str, ttl_minutes: int = DEFAULT_TTL_MINUTES):
        self.name = name
        self.ttl = ttl_minutes * 60
        self.file_path = os.path.join(CACHE_DIR, f"{name}.json")
        self.data = self._load()

    def _load(self):
        """Load cache data from disk (if available)."""
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                return raw.get("data", {})
        except Exception as e:
            logger.warning(f"[CACHE] Failed to load {self.name}: {e}")
            return {}

    def _save(self):
        """Persist cache data to disk."""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({"data": self.data, "timestamp": time.time()}, f, indent=2)
        except Exception as e:
            logger.warning(f"[CACHE] Failed to save {self.name}: {e}")

    def get(self, key):
        """Retrieve cached value if not expired."""
        entry = self.data.get(str(key))
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > self.ttl:
            del self.data[str(key)]
            return None
        return value

    def set(self, key, value):
        """Store a value and save to disk."""
        self.data[str(key)] = (time.time(), value)
        self._save()

    def clear(self):
        """Clear all cache data."""
        self.data = {}
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
        logger.info(f"[CACHE] Cleared cache: {self.name}")
# --- Auto-create .gitignore inside cache directory ---
gitignore_path = os.path.join(CACHE_DIR, ".gitignore")
if not os.path.exists(gitignore_path):
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("*\n!.gitignore\n")
