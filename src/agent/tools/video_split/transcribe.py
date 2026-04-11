from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from .models import TranscriptSegment


def _run_ffmpeg(args: list[str]) -> None:
    p = subprocess.run(
        ["ffmpeg", "-y", *args],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-2000:]}")


def extract_audio_wav(video_path: Path, wav_path: Path, sample_rate: int = 16000) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "wav",
            str(wav_path),
        ]
    )


def transcribe_with_faster_whisper(
    wav_path: Path,
    *,
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
) -> list[TranscriptSegment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ImportError(
            "faster-whisper is required for local transcription. "
            'Install with: pip install "faster-whisper>=1.0.0"'
        ) from e

    logger.info("Loading Whisper model {} (device={})", model_size, device)
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(str(wav_path), beam_size=5, vad_filter=True)
    out: list[TranscriptSegment] = []
    for seg in segments:
        t = (seg.text or "").strip()
        if not t:
            continue
        out.append(TranscriptSegment(start_sec=float(seg.start), end_sec=float(seg.end), text=t))
    return out


def transcribe_video(
    video_path: Path,
    *,
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
    keep_wav: Path | None = None,
) -> list[TranscriptSegment]:
    video_path = Path(video_path).resolve()
    if not video_path.is_file():
        raise FileNotFoundError(video_path)

    if keep_wav:
        wav = Path(keep_wav).resolve()
        extract_audio_wav(video_path, wav)
        return transcribe_with_faster_whisper(
            wav, model_size=model_size, device=device, compute_type=compute_type
        )

    with tempfile.TemporaryDirectory(prefix="vedio_split_") as tmp:
        wav = Path(tmp) / "audio.wav"
        extract_audio_wav(video_path, wav)
        return transcribe_with_faster_whisper(
            wav, model_size=model_size, device=device, compute_type=compute_type
        )


def segments_to_timeline_text(segments: list[TranscriptSegment], max_chars: int = 120_000) -> str:
    lines: list[str] = []
    n = 0
    for s in segments:
        line = f"[{s.start_sec:.2f}-{s.end_sec:.2f}] {s.text}"
        if n + len(line) > max_chars:
            lines.append("… [transcript truncated for LLM context]")
            break
        lines.append(line)
        n += len(line) + 1
    return "\n".join(lines)


def transcript_for_range(segments: list[TranscriptSegment], start: float, end: float) -> str:
    parts: list[str] = []
    for s in segments:
        if s.end_sec < start or s.start_sec > end:
            continue
        parts.append(s.text.strip())
    return " ".join(parts).strip()
