from __future__ import annotations

from typing import Any, Protocol


class ChatClient(Protocol):
    async def complete(
        self,
        *,
        user: str,
        query: str,
        conversation_id: str | None,
        files: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str | None]:
        """返回 (answer_text, conversation_id)。"""
