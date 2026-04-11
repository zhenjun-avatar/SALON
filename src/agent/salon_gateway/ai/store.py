from __future__ import annotations

import asyncio
from typing import ClassVar


class ConversationStore:
    """进程内会话 id；生产环境可替换为 Redis 实现相同接口。"""

    _singleton: ClassVar["ConversationStore | None"] = None

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def instance(cls) -> "ConversationStore":
        if cls._singleton is None:
            cls._singleton = ConversationStore()
        return cls._singleton

    async def get(self, user: str) -> str | None:
        async with self._lock:
            return self._map.get(user)

    async def set(self, user: str, conversation_id: str) -> None:
        async with self._lock:
            self._map[user] = conversation_id
