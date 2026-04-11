from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from tools.llm import get_llm

from .models import PlannedClip

_SYSTEM = """You are a video editor assistant. Given a timestamped transcript, propose clips for short-form video (TikTok/Reels/Shorts).

Rules:
- Each clip must be between 15 and 90 seconds long (inclusive).
- Clips should align with natural session/topic boundaries or complete rhetorical paragraphs (not mid-sentence cuts when avoidable).
- Prefer distinct segments; avoid heavy overlap. You may propose multiple clips across the full video.
- Times must be in seconds, floating point allowed, within the video duration.

Reply with ONLY valid JSON (no markdown fences):
{
  "clips": [
    {
      "start_sec": 12.5,
      "end_sec": 68.0,
      "session_hint": "short label for the session/topic",
      "paragraph_summary": "one line what this clip covers"
    }
  ]
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


def plan_clips_from_timeline(
    timeline_text: str,
    *,
    video_duration_sec: float,
    min_sec: float = 15.0,
    max_sec: float = 90.0,
    model_name: str | None = None,
) -> list[PlannedClip]:
    llm = get_llm(model_name=model_name, temperature=0.2)
    human = f"""Video duration (seconds): {video_duration_sec:.2f}

Transcript (timestamped lines):
{timeline_text}
"""
    msg = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=human)])
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    data = _parse_json_object(content)
    raw_clips = data.get("clips")
    if not isinstance(raw_clips, list):
        raise ValueError("JSON missing clips array")

    planned: list[PlannedClip] = []
    for i, item in enumerate(raw_clips):
        if not isinstance(item, dict):
            continue
        try:
            a = float(item["start_sec"])
            b = float(item["end_sec"])
        except (KeyError, TypeError, ValueError):
            logger.warning("skip clip {}: bad start/end", i)
            continue
        if b <= a:
            continue
        dur = b - a
        if dur < min_sec or dur > max_sec:
            logger.warning("skip clip {}: duration {:.1f}s not in [{},{}]", i, dur, min_sec, max_sec)
            continue
        a = max(0.0, min(a, video_duration_sec))
        b = max(0.0, min(b, video_duration_sec))
        if b - a < min_sec:
            continue
        planned.append(
            PlannedClip(
                start_sec=a,
                end_sec=b,
                session_hint=str(item.get("session_hint") or "")[:200],
                paragraph_summary=str(item.get("paragraph_summary") or "")[:500],
            )
        )

    planned.sort(key=lambda c: c.start_sec)
    return _drop_overlapping(planned)


def _drop_overlapping(clips: list[PlannedClip]) -> list[PlannedClip]:
    """Keep clips in time order; skip any that start before the previous clip ends."""
    if not clips:
        return []
    out: list[PlannedClip] = []
    last_end = -1.0
    for c in clips:
        if c.start_sec < last_end - 1e-6:
            continue
        out.append(c)
        last_end = max(last_end, c.end_sec)
    return out
