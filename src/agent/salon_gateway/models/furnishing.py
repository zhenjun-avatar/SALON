from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

_MAX_PRODUCT_REFS = 4


class FurnishingAssetOut(BaseModel):
    """单条素材（供 Dify / 前端展示与选品）。"""

    id: str
    category: str = ""
    name: str = ""
    image_url: str = ""
    tags: list[str] = Field(default_factory=list)


class FurnishingAssetsListResponse(BaseModel):
    items: list[FurnishingAssetOut]
    total: int


class FurnishingComposePreviewRequest(BaseModel):
    """空间参考图 + 多张产品参考图 → 万相 2.7 多图编辑（仅推荐 wan2.7-*）。"""

    conversation_id: str = Field(default="", description="Dify 会话 ID；room 空时可配合会话缓存")
    room_image_url: str = Field(default="", description="空间参考图 URL；空则用会话缓存")
    product_image_urls: list[str] = Field(
        default_factory=list,
        description="产品参考图 URL 列表，顺序保留；至少 1 张，最多 4 张",
    )
    placement_hint: str = Field(default="", description="如：茶几区域、沙发靠窗侧")
    style_notes: str = Field(default="", description="补充风格/材质说明")

    @field_validator("product_image_urls", mode="before")
    @classmethod
    def _normalize_urls(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for x in v:
            s = str(x).strip()
            if s:
                out.append(s)
            if len(out) >= _MAX_PRODUCT_REFS:
                break
        return out

    @model_validator(mode="after")
    def _need_products(self) -> FurnishingComposePreviewRequest:
        if len(self.product_image_urls) < 1:
            raise ValueError("product_image_urls must contain at least one URL")
        return self
