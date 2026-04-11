from __future__ import annotations

from typing import Any

import httpx

from salon_gateway.config import SalonGatewaySettings


class DifyChatClient:
    """Dify 对话 / Chatflow 应用：`POST /v1/chat-messages`。"""

    def __init__(self, settings: SalonGatewaySettings) -> None:
        self._base = settings.dify_api_base.rstrip("/")
        self._key = settings.dify_api_key

    async def complete(
        self,
        *,
        user: str,
        query: str,
        conversation_id: str | None,
        inputs: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        if not self._key:
            return ("服务未配置 Dify API Key。", None)
        url = f"{self._base}/chat-messages"
        payload: dict[str, Any] = {
            "inputs": inputs or {},
            "query": query,
            "user": user,
            "response_mode": "blocking",
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        answer = (data.get("answer") or "").strip()
        new_id = data.get("conversation_id")
        cid = str(new_id) if new_id else conversation_id
        return answer, cid
