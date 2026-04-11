# CLAUDE.md — vedio_split (video shorts)

**Repository:** [github.com/zhenjun-avatar/VIDEO-SPLIT](https://github.com/zhenjun-avatar/VIDEO-SPLIT) · `git clone https://github.com/zhenjun-avatar/VIDEO-SPLIT.git`

Guidance for AI coding agents working in this repository.

## What this project is

A **Python CLI pipeline** under `src/agent/tools/vedio_split/`: transcribe video with **faster-whisper** (+ **ffmpeg**), ask an **LLM** (via `tools/llm.py` + `core/config.py`) to propose **15–90s** clips, **cut** with ffmpeg, generate **title/description** per clip, write **`manifest.json`** + **`transcript.json`**.

## Repository layout

| Path | Role |
|------|------|
| `src/agent/tools/vedio_split/` | Pipeline, CLI (`python -m tools.vedio_split`) |
| `src/agent/tools/llm.py` | OpenAI-compatible chat (DeepSeek / Qwen / OpenAI-style) |
| `src/agent/tools/runtime_logging.py` | loguru setup |
| `src/agent/core/config.py` | pydantic-settings; loads `.env` |
| `src/agent/env.example` | Env var template |
| `src/agent/tools/data/` | Sample inputs (e.g. `Duke.mp4`) — may be large |
| `src/agent/outputs/` | Default render output (often gitignored) |
| `scripts/cleanup_non_video_split.py` | Optional tree cleanup (dry-run by default) |
| Root | `requirements.txt`, `pyproject.toml`, `README.md` |

## Prerequisites

- Python **3.11+**
- **ffmpeg** and **ffprobe** on `PATH`
- API keys for the chosen LLM (see `env.example`)

## Quick start

From `src/agent` with venv active:

```bash
pip install -r ../../requirements.txt
python -m tools.vedio_split --input tools/data/Duke.mp4 --out outputs/duke_shorts
```

See **`README.md`** for CLI flags and troubleshooting (Windows file locks when deleting old `frontend/` trees).

## Configuration

- `src/agent/.env` — never commit; keys like `DEEPSEEK_API_KEY`, `DEFAULT_MODEL`.
- `core/config.py` has many legacy fields (`extra="ignore"`) so old `.env` lines do not crash imports.

## Tests

```bash
pytest
```

Minimal smoke tests live in `tests/` (imports only; no API calls).

## Security and boundaries

- Do not commit `.env` or API keys.
- Avoid reading huge binaries in diff tools; `tools/data/*.mp4` can be large.
- Generated clips under `outputs/` are artifacts.

When changing clip logic or prompts, edit `vedio_split/segment_llm.py` and `metadata_llm.py`; transcription in `transcribe.py`; ffmpeg in `cut.py`.
