"""Smoke: package imports without running ffmpeg / API."""

from __future__ import annotations

from tools.vedio_split.models import PlannedClip, TranscriptSegment


def test_models_instantiate() -> None:
    s = TranscriptSegment(start_sec=0.0, end_sec=1.0, text="hello")
    assert s.text == "hello"
    c = PlannedClip(start_sec=0.0, end_sec=15.0, session_hint="a", paragraph_summary="b")
    assert c.end_sec - c.start_sec == 15.0
