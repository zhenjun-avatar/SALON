from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger


def cut_clip_ffmpeg(
    video_path: Path,
    out_path: Path,
    start_sec: float,
    end_sec: float,
    *,
    reencode: bool = False,
    _retry: bool = True,
) -> None:
    """Extract [start_sec, end_sec] into out_path using ffmpeg."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.01, end_sec - start_sec)
    video_path = Path(video_path).resolve()
    if not video_path.is_file():
        raise FileNotFoundError(video_path)

    if reencode:
        args = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
    else:
        args = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(out_path),
        ]

    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        if not reencode and _retry:
            logger.warning("stream copy failed, retry with re-encode: {}", p.stderr[-800:])
            cut_clip_ffmpeg(video_path, out_path, start_sec, end_sec, reencode=True, _retry=False)
            return
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-2000:]}")
    if not out_path.is_file() or out_path.stat().st_size < 1024:
        raise RuntimeError(f"output too small or missing: {out_path}")
