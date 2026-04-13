from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _service_to_feishu_multi(value: str | list[str]) -> list[str]:
    """飞书「多选」列需要字符串数组；单字符串视为一个选项。"""
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    return [str(x).strip() for x in value if str(x).strip()]


class BookingDraft(BaseModel):
    """与 Dify HTTP 工具 /internal/booking 对齐；字段可按沙龙表结构扩展。"""

    conversation_id: str | None = Field(
        default=None,
        description="Dify sys.conversation_id；用于跨轮次累积预约字段的会话键",
    )
    idempotency_key: str | None = Field(default=None, description="防重，如企微 MsgId")
    channel: str = Field(default="wecom")
    external_user_id: str | None = None
    phone: str | None = None
    store: str | None = None
    service: str | list[str] | None = Field(
        default=None,
        description="项目；飞书多选列请传 JSON 数组，如 [\"染发\",\"烫发\"]；单字符串仍为单选项",
    )
    slot_text: str | None = Field(default=None, description="意向时间自然语言")
    color_summary: str | None = None
    history_summary: str | None = None
    notes: str | None = None
    status: str = Field(default="pending")
    image_url: str | None = Field(
        default=None,
        description="本轮用户上传的图片 URL（不写飞书；网关用于跨轮次发型效果图生成）",
    )

    @field_validator(
        "phone", "store", "service", "slot_text",
        "color_summary", "history_summary", "notes", "external_user_id",
        "image_url",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        """Dify template variables render as empty string when the slot was never filled;
        convert those to None so they are excluded from to_feishu_fields output."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def to_feishu_fields(self, field_map: dict[str, str]) -> dict[str, Any]:
        """将模型字段映射为飞书多维表 fields；未映射的键跳过。"""
        raw = self.model_dump(exclude_none=True)
        raw.pop("idempotency_key", None)
        out: dict[str, Any] = {}
        for key, value in raw.items():
            col = field_map.get(key)
            if not col:
                continue
            if key == "service":
                tags = _service_to_feishu_multi(value) if value is not None else []
                if not tags:
                    continue
                out[col] = tags
                continue
            out[col] = value
        return out
