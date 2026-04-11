# Salon

Repository: **[zhenjun-avatar/SALON](https://github.com/zhenjun-avatar/SALON)** — `https://github.com/zhenjun-avatar/SALON.git`.

**Salon** is a small **FastAPI** gateway for a salon-style workflow: **企业微信** inbound messages → **Dify** chat (conversation continuity) → optional **飞书多维表** for booking drafts, plus a protected **internal booking** callback for Dify HTTP tools.

## What it does

1. **WeCom**「接收消息」callback: verify URL, decrypt (or plaintext dev mode), parse text.  
2. **Dify**: forwards user text, keeps `conversation_id` per WeCom user.  
3. **Sink**: if Feishu credentials and field map are set, writes **BookingDraft** rows; otherwise logs only.  
4. **POST `/internal/booking`**: enabled when `SALON_INTERNAL_BOOKING_TOKEN` is set; used by Dify tool calls.

## Layout

```
├── requirements.txt
├── requirements-salon-gateway.txt    # gateway-only deps (or pyproject [salon-gateway])
├── src/agent/
│   ├── core/                         # shared settings patterns (if used)
│   ├── salon_gateway/
│   │   ├── app.py                    # FastAPI routes
│   │   ├── __main__.py               # uvicorn entry
│   │   ├── config.py
│   │   ├── env.example               # SALON_* template → copy to .env
│   │   ├── ingress/wecom.py
│   │   ├── ai/dify.py
│   │   ├── orchestrator/pipeline.py
│   │   └── sink/                     # Feishu bitable, logging sink
│   └── .env                          # local secrets (do not commit)
└── tests/
```

## Prerequisites

- **Python 3.11+**  
- Dependencies: `pip install -r requirements-salon-gateway.txt` (from repo root), or install the `salon-gateway` optional extra from `pyproject.toml`.

## Quick start

```bash
cd src/agent
python -m venv .venv
# Windows: .venv\Scripts\pip install -r ../../requirements-salon-gateway.txt
# Unix:    .venv/bin/pip install -r ../../requirements-salon-gateway.txt

copy salon_gateway\env.example .env
# Edit .env: WeCom, Dify, optional Feishu and internal booking token.

.venv\Scripts\python -m salon_gateway
# Default bind: 0.0.0.0:8765 — override with SALON_HOST / SALON_PORT
```

## Configuration

- **`src/agent/.env`**: see `src/agent/salon_gateway/env.example` for all `SALON_*` variables (WeCom token/AES key, Dify base URL and API key, Feishu app/table IDs, field map JSON, internal booking token).  
- Do **not** commit `.env`.

## Security

Do not commit API keys, tokens, or `.env`.

## License

MIT License
