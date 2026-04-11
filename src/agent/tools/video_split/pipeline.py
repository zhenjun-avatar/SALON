from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from .cut import cut_clip_ffmpeg
from .metadata_llm import generate_clip_metadata
from .models import FinalClipRecord
from .segment_llm import plan_clips_from_timeline
from .transcribe import segments_to_timeline_text, transcript_for_range, transcribe_video


def probe_duration_sec(video_path: Path) -> float:
    p = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {p.stderr}")
    return float((p.stdout or "0").strip())


@dataclass
class PipelineResult:
    output_dir: Path
    manifest_path: Path
    transcript_path: Path
    clips: list[FinalClipRecord]


def run_shorts_pipeline(
    video_path: Path | str,
    output_dir: Path | str,
    *,
    whisper_model: str = "base",
    whisper_device: str = "cpu",
    whisper_compute_type: str = "int8",
    keep_wav: Path | None = None,
    llm_model: str | None = None,
    min_clip_sec: float = 15.0,
    max_clip_sec: float = 90.0,
) -> PipelineResult:
    """
    1) Transcribe video (faster-whisper + ffmpeg).
    2) LLM plans 15–90s clips (sessions / paragraphs).
    3) ffmpeg cuts each clip.
    4) LLM title + description per clip.
    5) Save manifest.json + transcript.json + clip MP4s.
    """
    video_path = Path(video_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = probe_duration_sec(video_path)
    logger.info("Video duration: {:.2f}s", duration)

    segments = transcribe_video(
        video_path,
        model_size=whisper_model,
        device=whisper_device,
        compute_type=whisper_compute_type,
        keep_wav=keep_wav,
    )
    if not segments:
        raise RuntimeError("Transcription produced no segments (check audio / model).")

    transcript_path = output_dir / "transcript.json"
    transcript_path.write_text(
        json.dumps([s.model_dump() for s in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    timeline = segments_to_timeline_text(segments)
    planned = plan_clips_from_timeline(
        timeline,
        video_duration_sec=duration,
        min_sec=min_clip_sec,
        max_sec=max_clip_sec,
        model_name=llm_model,
    )
    if not planned:
        raise RuntimeError("LLM returned no valid clips; try another model or shorten transcript context.")

    clips_out: list[FinalClipRecord] = []
    for i, plan in enumerate(planned, start=1):
        fname = f"clip_{i:03d}.mp4"
        out_file = output_dir / fname
        cut_clip_ffmpeg(video_path, out_file, plan.start_sec, plan.end_sec)
        excerpt = transcript_for_range(segments, plan.start_sec, plan.end_sec)
        meta = generate_clip_metadata(
            excerpt,
            session_hint=plan.session_hint,
            paragraph_summary=plan.paragraph_summary,
            model_name=llm_model,
        )
        clips_out.append(
            FinalClipRecord(
                index=i,
                file=fname,
                start_sec=plan.start_sec,
                end_sec=plan.end_sec,
                title=meta.title,
                description=meta.description,
                transcript=excerpt,
                session_hint=plan.session_hint,
                paragraph_summary=plan.paragraph_summary,
            )
        )
        logger.info("Wrote {} ({:.1f}s–{:.1f}s): {}", fname, plan.start_sec, plan.end_sec, meta.title)

    manifest: dict[str, Any] = {
        "source_video": str(video_path),
        "duration_sec": duration,
        "whisper_model": whisper_model,
        "clips": [c.model_dump() for c in clips_out],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return PipelineResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        transcript_path=transcript_path,
        clips=clips_out,
    )
