from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger

from salon_gateway.ai.dify import DifyChatClient
from salon_gateway.ai.store import ConversationStore
from salon_gateway.config import SalonGatewaySettings
from salon_gateway.models.messages import WecomImageInbound, WecomTextInbound

if TYPE_CHECKING:
    from salon_gateway.ai.protocol import ChatClient


def _remote_url_file(url: str) -> dict[str, Any]:
    return {"type": "image", "transfer_method": "remote_url", "url": url}


def _upload_file_ref(upload_file_id: str) -> dict[str, Any]:
    return {"type": "image", "transfer_method": "local_file", "upload_file_id": upload_file_id}


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

    async def _complete(
        self,
        wecom_user: str,
        query: str,
        files: list[dict[str, Any]] | None = None,
    ) -> str:
        user = self._dify_user(wecom_user)
        cid = await self._store.get(user)
        try:
            answer, new_cid = await self._chat.complete(
                user=user,
                query=query,
                conversation_id=cid,
                files=files,
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

    async def handle_text(self, msg: WecomTextInbound) -> str:
        return await self._complete(msg.from_user, msg.content)

    async def handle_image(self, msg: WecomImageInbound) -> str:
        """Forward image to Dify as remote_url; LLM analyses it and recommends styling."""
        files = [_remote_url_file(msg.pic_url)]
        return await self._complete(
            msg.from_user,
            query="[图片] 请分析这张照片，推荐适合的发型或发色方案。",
            files=files,
        )

    async def handle_message(self, msg: WecomTextInbound | WecomImageInbound) -> str:
        if isinstance(msg, WecomImageInbound):
            return await self.handle_image(msg)
        return await self.handle_text(msg)

    async def handle_with_image(
        self,
        wecom_user: str,
        content: str,
        *,
        image_url: str | None = None,
        upload_file_id: str | None = None,
    ) -> str:
        """Used by /simulate endpoint: text + optional image."""
        files: list[dict[str, Any]] | None = None
        if upload_file_id:
            files = [_upload_file_ref(upload_file_id)]
        elif image_url:
            files = [_remote_url_file(image_url)]
        query = content or "[图片] 请分析这张照片，推荐适合的发型或发色方案。"
        return await self._complete(wecom_user, query, files)

    async def handle_with_image_stream(
        self,
        wecom_user: str,
        content: str,
        *,
        image_url: str | None = None,
        upload_file_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Dify 流式 ``chat-messages``；透传 SSE 字节并在结束后写入会话 id。"""
        files: list[dict[str, Any]] | None = None
        if upload_file_id:
            files = [_upload_file_ref(upload_file_id)]
        elif image_url:
            files = [_remote_url_file(image_url)]
        query = content or "[图片] 请分析这张照片，推荐适合的发型或发色方案。"
        user = self._dify_user(wecom_user)
        cid = await self._store.get(user)
        if not isinstance(self._chat, DifyChatClient):
            raise RuntimeError("streaming requires DifyChatClient")

        holder: list[str | None] = []
        try:
            async for chunk in self._chat.stream_complete(
                user=user,
                query=query,
                conversation_id=cid,
                files=files,
                conversation_id_holder=holder,
            ):
                yield chunk
        except httpx.HTTPStatusError:
            raise
        except Exception:
            logger.exception("handle_with_image_stream failed user={}", wecom_user)
            raise
        finally:
            new_cid = holder[0] if holder else None
            if new_cid:
                await self._store.set(user, new_cid)


def default_pipeline(settings: SalonGatewaySettings) -> SalonPipeline:
    return SalonPipeline(
        settings=settings,
        chat=DifyChatClient(settings),
        store=ConversationStore.instance(),
    )
