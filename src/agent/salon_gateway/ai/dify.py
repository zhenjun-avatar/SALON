from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from salon_gateway.config import SalonGatewaySettings


class DifyChatClient:
    """Dify 对话 / Chatflow 应用：`POST /v1/chat-messages`。"""

    def __init__(self, settings: SalonGatewaySettings) -> None:
        self._base = settings.dify_api_base.rstrip("/")
        self._key = settings.dify_api_key
        self._default_inputs = settings.dify_default_inputs

    def _log_error_body(self, r: httpx.Response) -> None:
        try:
            snippet = (r.text or "")[:4000]
        except Exception:
            snippet = "<no body>"
        logger.error("dify POST {} HTTP {}: {}", r.request.url, r.status_code, snippet)

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
        merged_inputs: dict[str, Any] = {**self._default_inputs, **(inputs or {})}
        payload: dict[str, Any] = {
            "inputs": merged_inputs,
            "query": query,
            "user": user,
            "response_mode": "blocking",
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        headers = {"Authorization": f"Bearer {self._key}"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            # Stale or invalid conversation_id often yields 400/404; retry once without it.
            if r.status_code in (400, 404) and conversation_id:
                self._log_error_body(r)
                logger.warning(
                    "dify chat-messages returned {} with conversation_id; retrying as new conversation",
                    r.status_code,
                )
                payload.pop("conversation_id", None)
                r = await client.post(url, json=payload, headers=headers)

            if r.is_error:
                r.raise_for_status()

            data = r.json()

        answer = (data.get("answer") or "").strip()
        new_id = data.get("conversation_id")
        cid = str(new_id) if new_id else conversation_id
        return answer, cid
