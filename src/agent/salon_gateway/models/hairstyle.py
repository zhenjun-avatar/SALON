from __future__ import annotations

from pydantic import BaseModel, Field


class HairstylePreviewRequest(BaseModel):
    image_url: str = Field(description="可公开访问的 HTTPS 图片 URL")
    style_prompt: str = Field(default="", description="发型/发色描述，如「波浪长发 栗色渐变」")
    conversation_id: str = Field(default="", description="Dify 会话 ID，用于日志追踪")


class HairstylePreviewResponse(BaseModel):
    preview_url: str = Field(description="通义万相生成的效果图 URL")
    task_id: str = Field(description="DashScope 任务 ID")
