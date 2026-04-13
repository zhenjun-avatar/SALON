"""每个对话的图片 URL 存储，供跨轮次发型效果图生成使用。

第一轮：用户上传照片 → hairstyle-preview 收到 image_url，存入 session。
第二轮：用户确认方案 → hairstyle-preview image_url 为空，从 session 取出。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


_TTL_SECONDS = 3600  # 图片 URL 保留 1 小时


@dataclass
class _Entry:
    image_url: str
    updated_at: float = field(default_factory=time.monotonic)


class HairstyleSessionStore:
    """线程安全的内存存储，key = conversation_id，value = image_url。"""

    def __init__(self, ttl: float = _TTL_SECONDS) -> None:
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._ttl = ttl

    def save(self, conversation_id: str, image_url: str) -> None:
        """存储或更新 conversation_id 对应的图片 URL。"""
        if not conversation_id or not image_url:
            return
        with self._lock:
            self._store[conversation_id] = _Entry(image_url=image_url)

    def get(self, conversation_id: str) -> str:
        """返回存储的图片 URL，不存在或已过期则返回空字符串。"""
        if not conversation_id:
            return ""
        with self._lock:
            entry = self._store.get(conversation_id)
            if entry is None:
                return ""
            if time.monotonic() - entry.updated_at > self._ttl:
                del self._store[conversation_id]
                return ""
            return entry.image_url

    def resolve(self, conversation_id: str, current_image_url: str) -> str:
        """返回有效图片 URL：优先使用 current_image_url，否则取 session 中存储的。"""
        url = (current_image_url or "").strip()
        if url:
            self.save(conversation_id, url)
            return url
        return self.get(conversation_id)
