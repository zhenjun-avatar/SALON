from __future__ import annotations

from typing import Protocol


class ChatClient(Protocol):
    async def complete(
        self,
        *,
        user: str,
        query: str,
        conversation_id: str | None,
    ) -> tuple[str, str | None]:
        """返回 (answer_text, conversation_id)。"""
