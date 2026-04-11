from __future__ import annotations


class IdempotencyCache:
    """内存防重；多实例部署请换 Redis / DB。"""

    def __init__(self, max_keys: int = 50_000) -> None:
        self._seen: set[str] = set()
        self._max = max_keys

    def should_process(self, key: str | None) -> bool:
        if not key:
            return True
        if key in self._seen:
            return False
        self._seen.add(key)
        if len(self._seen) > self._max:
            self._seen.clear()
        return True
