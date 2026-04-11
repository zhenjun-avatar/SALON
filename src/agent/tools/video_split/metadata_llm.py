from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from tools.llm import get_llm

from .models import ClipMetadata

_SYSTEM = """You write short-form video metadata in the same language as the transcript.

Reply with ONLY valid JSON (no markdown):
{
  "title": "catchy title, under 60 characters",
  "description": "1-3 sentences for the caption / video description"
}
"""


def _parse_json_object(raw: str) -> dict[str, Any]:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```\s*$", "", s)
    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def generate_clip_metadata(
    transcript_excerpt: str,
    *,
    session_hint: str = "",
    paragraph_summary: str = "",
    model_name: str | None = None,
) -> ClipMetadata:
    llm = get_llm(model_name=model_name, temperature=0.5)
    ctx_parts = []
    if session_hint:
        ctx_parts.append(f"Session/topic hint: {session_hint}")
    if paragraph_summary:
        ctx_parts.append(f"Summary: {paragraph_summary}")
    ctx = "\n".join(ctx_parts)
    human = f"""{ctx}

Transcript for this clip:
{transcript_excerpt[:8000]}
"""
    msg = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=human)])
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    data = _parse_json_object(content)
    title = str(data.get("title") or "Clip").strip()[:120]
    desc = str(data.get("description") or "").strip()[:2000]
    return ClipMetadata(title=title, description=desc)
