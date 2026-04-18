from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationImageSnap(BaseModel):
    """与 Dify HTTP 工具 /internal/conversation-image 对齐：仅缓存本轮空间照片 URL。"""

    conversation_id: str = Field(default="", description="Dify 会话 ID")
    image_url: str = Field(default="", description="本轮用户上传的图片 URL；空则跳过")
