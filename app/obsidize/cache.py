# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                      cache.py                                          #
# ========================================================================================#
"""
LRU-style AST cache for the Obsidize template engine.

Caches ParserResult objects keyed by template text string,
so that identical templates are not re-parsed on every call.
"""

import threading
from collections import OrderedDict
from .types import ParserResult


class TemplateCache:
    """Thread-safe LRU cache for parsed template ASTs.

    Keys are the raw template text; values are ParserResult objects.
    Only successful parses (no errors) should be stored.
    """

    def __init__(self, max_size: int = 128):
        self._max_size = max_size
        self._cache: OrderedDict[str, ParserResult] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, template_text: str) -> ParserResult | None:
        """Return the cached ParserResult for *template_text*, or ``None`` on miss."""
        with self._lock:
            result = self._cache.get(template_text)
            if result is not None:
                # Move to end so it's most-recently-used
                self._cache.move_to_end(template_text)
                self._hits += 1
                return result
            self._misses += 1
            return None

    def put(self, template_text: str, result: ParserResult) -> None:
        """Store a ParserResult in the cache.

        If the cache is at capacity, the least-recently-used entry is evicted.
        """
        with self._lock:
            if template_text in self._cache:
                # Already cached; move to end
                self._cache.move_to_end(template_text)
                return
            self._cache[template_text] = result
            # Evict LRU entry if over capacity
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        """Return cache statistics: hits, misses, and current size."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# Module-level singleton
_default_cache = TemplateCache()
