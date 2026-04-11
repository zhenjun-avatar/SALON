from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WecomTextInbound:
    """企微解密后的文本消息。"""

    from_user: str
    to_user: str
    agent_id: str | None
    msg_id: str | None
    content: str


@dataclass(frozen=True)
class WecomImageInbound:
    """企微解密后的图片消息。pic_url 为公开临时 URL（通常有效数天）。"""

    from_user: str
    to_user: str
    agent_id: str | None
    msg_id: str | None
    pic_url: str
    media_id: str
