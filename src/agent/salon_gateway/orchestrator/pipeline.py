from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from loguru import logger

from salon_gateway.ai.dify import DifyChatClient
from salon_gateway.ai.store import ConversationStore
from salon_gateway.config import SalonGatewaySettings
from salon_gateway.ingress.wecom import WecomTextInbound

if TYPE_CHECKING:
    from salon_gateway.ai.protocol import ChatClient


class SalonPipeline:
    def __init__(
        self,
        settings: SalonGatewaySettings,
        chat: ChatClient,
        store: ConversationStore,
    ) -> None:
        self._s = settings
        self._chat = chat
        self._store = store

    def _dify_user(self, wecom_user: str) -> str:
        p = self._s.dify_user_prefix.strip() or "wecom"
        return f"{p}:{wecom_user}"

    async def handle_text(self, msg: WecomTextInbound) -> str:
        user = self._dify_user(msg.from_user)
        cid = await self._store.get(user)
        try:
            answer, new_cid = await self._chat.complete(
                user=user,
                query=msg.content,
                conversation_id=cid,
            )
        except httpx.HTTPStatusError as e:
            try:
                snippet = (e.response.text or "")[:4000]
            except Exception:
                snippet = ""
            logger.error(
                "dify chat-messages HTTP {} body: {}",
                e.response.status_code,
                snippet,
            )
            return "抱歉，系统暂时繁忙，请稍后再试。"
        except Exception as e:
            logger.exception("dify chat failed: {}", e)
            return "抱歉，系统暂时繁忙，请稍后再试。"
        if new_cid:
            await self._store.set(user, new_cid)
        return answer or "（无回复）"


def default_pipeline(settings: SalonGatewaySettings) -> SalonPipeline:
    return SalonPipeline(
        settings=settings,
        chat=DifyChatClient(settings),
        store=ConversationStore.instance(),
    )
