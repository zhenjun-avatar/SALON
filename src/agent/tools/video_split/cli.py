"""CLI: python -m tools.vedio_split.cli --input tools/data/Duke.mp4 --out outputs/duke_shorts"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from tools.runtime_logging import configure_runtime_logging

configure_runtime_logging()

from .pipeline import run_shorts_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe video, plan 15–90s shorts, cut + metadata.")
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("tools/data/Duke.mp4"),
        help="Input video path",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        default=Path("outputs/duke_shorts"),
        help="Output directory for clips + manifest",
    )
    parser.add_argument("--whisper-model", default="base", help="faster-whisper model size (tiny/base/small/medium/large-v3)")
    parser.add_argument("--whisper-device", default="cpu", help="cpu or cuda")
    parser.add_argument("--whisper-compute-type", default="int8", help="e.g. int8, float16 (cuda)")
    parser.add_argument("--keep-wav", type=Path, default=None, help="Optional path to save extracted WAV")
    parser.add_argument("--llm-model", default=None, help="Override DEFAULT_MODEL / env for planning + metadata")
    parser.add_argument("--min-sec", type=float, default=15.0)
    parser.add_argument("--max-sec", type=float, default=90.0)
    args = parser.parse_args()

    result = run_shorts_pipeline(
        args.input,
        args.out,
        whisper_model=args.whisper_model,
        whisper_device=args.whisper_device,
        whisper_compute_type=args.whisper_compute_type,
        keep_wav=args.keep_wav,
        llm_model=args.llm_model,
        min_clip_sec=args.min_sec,
        max_clip_sec=args.max_sec,
    )
    logger.info("Done. Manifest: {}", result.manifest_path)


if __name__ == "__main__":
    main()
