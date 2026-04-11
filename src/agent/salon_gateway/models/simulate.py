from __future__ import annotations

from pydantic import BaseModel, Field


class SimulateWecomTextIn(BaseModel):
    """Dev-only: same path as WeCom text → Dify → reply text (JSON, not XML)."""

    content: str = Field(..., min_length=1, description="User message text")
    from_user: str = Field(default="sim-user-1", max_length=128, description="Stable id for Dify conversation")
    to_user: str = Field(default="corp", max_length=128, description="Placeholder corp id (echo only)")
    msg_id: str | None = Field(default=None, description="Optional; for logging only")
