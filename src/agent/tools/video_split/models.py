from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start_sec: float
    end_sec: float
    text: str


class PlannedClip(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    session_hint: str = ""
    paragraph_summary: str = ""


class ClipMetadata(BaseModel):
    title: str
    description: str


class FinalClipRecord(BaseModel):
    index: int
    file: str
    start_sec: float
    end_sec: float
    title: str
    description: str
    transcript: str
    session_hint: str = ""
    paragraph_summary: str = ""
