# Salon

Repository: **[zhenjun-avatar/SALON](https://github.com/zhenjun-avatar/SALON)** — `https://github.com/zhenjun-avatar/SALON.git`.

**Salon** is a small **FastAPI** gateway for a salon-style workflow: **WeCom (WeChat Work)** inbound messages → **Dify** chat (conversation continuity) → optional **Feishu Bitable** for booking drafts, plus a protected **internal booking** callback for Dify HTTP tools.

## What it does

1. **WeCom** "receive message" callback: URL verification, decrypt (or plaintext dev mode), parse text.  
2. **Dify**: forwards user text, keeps `conversation_id` per WeCom user.  
3. **Sink**: if Feishu credentials and field map are set, writes **BookingDraft** rows; otherwise logs only.  
4. **POST `/internal/booking`**: enabled when `SALON_INTERNAL_BOOKING_TOKEN` is set; used by Dify tool calls.  
5. **POST `/simulate/wecom-text`**: when `SALON_SIMULATE_TOKEN` is set, JSON in/out through the same Dify pipeline (no WeCom XML).

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

# Windows:
copy salon_gateway\env.example .env
# Unix:
# cp salon_gateway/env.example .env
# Edit .env: WeCom, Dify, optional Feishu, internal booking token.

# Windows:
.venv\Scripts\python -m salon_gateway
# Unix:
# .venv/bin/python -m salon_gateway
# Default bind: 0.0.0.0:8765 — override with SALON_HOST / SALON_PORT
```

## Configuration

- **`src/agent/.env`**: see `src/agent/salon_gateway/env.example` for all `SALON_*` variables (WeCom token/AES key, Dify base URL and API key, **`SALON_DIFY_DEFAULT_INPUTS_JSON`** for required Chatflow inputs, Feishu app/table IDs, field map JSON, internal booking token).  
- Do **not** commit `.env`.

## Simulate WeCom + Dify Chatflow (booking and other tools)

**Goal:** You type messages like a user; Dify runs your Chatflow (reply + branches). When the flow needs to persist a booking, a **HTTP Request / Tool** node calls this gateway’s **`/internal/booking`**.

### 1. Gateway `.env`

- `SALON_DIFY_API_BASE` / `SALON_DIFY_API_KEY` — same as production.  
- `SALON_INTERNAL_BOOKING_TOKEN` — non-empty so `/internal/booking` is enabled.  
- `SALON_SIMULATE_TOKEN` — non-empty **only in dev/staging**; enables `/simulate/wecom-text`. Leave **empty in production**.

Dify sees one user per `from_user` (default `sim-user-1`), same as `wecom:<id>` for conversation memory.

### 2. Call the simulate endpoint

Public URL (with Nginx path prefix `/salon/`):

```bash
curl -sS -X POST "https://YOUR_DOMAIN/salon/simulate/wecom-text" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SIMULATE_TOKEN" \
  -d '{"content":"I want to book coloring next Saturday afternoon","from_user":"sim-user-1"}'
```

From repo root (CLI; reads `SALON_SIMULATE_TOKEN` and optional `SALON_TEST_BASE_URL` from env / `src/agent/.env`):

```bash
python scripts/simulate_wecom.py 你好
python scripts/simulate_wecom.py -m "下周六想染发" --from-user alice
python scripts/simulate_wecom.py --json -m "hello"   # full JSON response
python scripts/simulate_wecom.py --chat              # REPL: same user, continuous Dify session
python scripts/simulate_wecom.py -c -m "我想预约"    # optional first message, then REPL
```

Response: `{"reply":"..."}` — the assistant text from Dify (blocking mode).

Use a **stable `from_user`** per tester so `conversation_id` is reused across turns.

### 3. Dify Chatflow wiring

1. **Chat / Chatflow app** — API key must match `SALON_DIFY_API_KEY`.  
2. **Conversation** — Gateway sends `user` as `{SALON_DIFY_USER_PREFIX}:{from_user}` (e.g. `wecom:sim-user-1`).  
3. **Booking** — Add an **HTTP** tool or **HTTP Request** node:  
   - URL: `https://YOUR_DOMAIN/salon/internal/booking` (or your base + path).  
   - Method: `POST`, `Content-Type: application/json`.  
   - Header: `Authorization: Bearer <SALON_INTERNAL_BOOKING_TOKEN>`.  
   - Body: JSON fields aligned with `BookingDraft` (`phone`, `store`, `service`, `slot_text`, `idempotency_key`, etc.); map from LLM-extracted variables.  
4. **Other activities** — Use normal Chatflow nodes (branches, knowledge, other HTTP tools); only the booking step needs this URL.

### 4. Production

- Real users hit **`/webhook/wecom`** (XML); simulate route can stay **disabled** (`SALON_SIMULATE_TOKEN` empty).  
- **Never** expose `SALON_SIMULATE_TOKEN` on a public host without network restriction if you must keep simulate on.

## Security

Do not commit API keys, tokens, or `.env`.

## License

MIT License
