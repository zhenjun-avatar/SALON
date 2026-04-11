# Video shorts pipeline (`video_split`)

Upstream repository: **[zhenjun-avatar/VIDEO-SPLIT](https://github.com/zhenjun-avatar/VIDEO-SPLIT)** — clone URL: `https://github.com/zhenjun-avatar/VIDEO-SPLIT.git`.

CLI pipeline that **transcribes** a video, uses an **LLM** to plan **10–100 second** clips (sessions / coherent paragraphs), **cuts** them with **ffmpeg**, and writes **titles + descriptions** plus a **manifest**.

## What it does

1. Extract audio → **faster-whisper** (with VAD) for timestamped segments.  
2. Send a timeline to your configured chat model → JSON clip plan (`start_sec` / `end_sec`).  
3. **ffmpeg** exports each segment (stream copy, with H.264/AAC fallback).  
4. LLM generates **title** and **description** per clip.  
5. Saves `clip_001.mp4`, …, `transcript.json`, `manifest.json` under the output directory.

## Layout

```
├── requirements.txt
├── scripts/cleanup_non_video_split.py   # optional: prune legacy RAG/frontend paths
├── src/agent/
│   ├── core/                 # pydantic-settings (shared with .env)
│   ├── env.example           # API keys + DEFAULT_MODEL
│   ├── tools/
│   │   ├── video_split/      # pipeline, CLI
│   │   ├── llm.py            # OpenAI-compatible providers (DeepSeek / Qwen / OpenAI)
│   │   ├── runtime_logging.py
│   │   └── data/             # e.g. sample input video
│   └── outputs/              # default place for generated shorts (gitignored if listed)
```

## Prerequisites

- **Python 3.11+**  
- **ffmpeg** and **ffprobe** on `PATH`  
- **LLM API** credentials (see `src/agent/env.example`): e.g. `DEEPSEEK_API_KEY` + `DEFAULT_MODEL=deepseek/deepseek-chat`  
- Optional: **CUDA** for faster-whisper (`--whisper-device cuda --whisper-compute-type float16`)

## Quick start

```bash
cd src/agent
python -m venv venv
venv\Scripts\pip install -r ../../requirements.txt
# Unix: venv/bin/pip install -r ../../requirements.txt

copy env.example .env
# Edit .env: at least DEFAULT_MODEL and the matching API key.

venv\Scripts\python -m tools.video_split --input tools/data/Duke.mp4 --out outputs/duke_shorts
```

Use a smaller/faster Whisper model for tests: `--whisper-model tiny`. For quality: `--whisper-model small` or `medium`.

## CLI options (summary)

| Flag | Purpose |
|------|--------|
| `--input` / `-i` | Source video path |
| `--out` / `-o` | Output directory |
| `--whisper-model` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `--whisper-device` | `cpu` or `cuda` |
| `--whisper-compute-type` | e.g. `int8`, `float16` |
| `--llm-model` | Override `DEFAULT_MODEL` for planning + metadata |
| `--min-sec` / `--max-sec` | Clip length bounds (default 15–90) |
| `--keep-wav` | Save extracted WAV next to pipeline |

## Configuration

- **`src/agent/.env`** — loaded by `core.config` (used for logging and defaults). LLM keys are read by `tools/llm.py` from the environment (`DEEPSEEK_API_KEY`, `QWEN_API_KEY`, OpenAI default chain, etc.).  
- Do **not** commit `.env`.

## Optional: repository cleanup script

If this tree still contains leftover paths from the old RAG/frontend stack, inspect and then apply:

```bash
python scripts/cleanup_non_video_split.py
python scripts/cleanup_non_video_split.py --apply
```

On Windows, if deleting `src/frontend` fails with **file in use**, stop `npm run dev` and close handles on `node_modules`, then retry (the script retries with chmod/backoff).

## Security

Do not commit API keys or `.env`.

## License

MIT License
