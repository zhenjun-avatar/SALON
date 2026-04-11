#!/usr/bin/env python3
"""Smoke tests for salon_gateway: GET /health and POST /internal/booking.

Run from repo root (or anywhere) with gateway already started:

  python scripts/test_salon_gateway.py

Reads SALON_INTERNAL_BOOKING_TOKEN from env or .env unless --skip-booking.
Base URL: env SALON_TEST_BASE_URL, then same .env file (see --env-file), else http://127.0.0.1:8765.

Env:
  SALON_TEST_BASE_URL   optional; overrides .env
  SALON_INTERNAL_BOOKING_TOKEN  optional; overrides .env for this script
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _value_from_env_file(env_path: Path, key: str) -> str | None:
    if not env_path.is_file():
        return None
    text = env_path.read_text(encoding="utf-8")
    prefix = f"{key}="
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith(prefix):
            v = s.split("=", 1)[1].strip().strip('"').strip("'")
            return v if v else None
    return None


def load_token_from_env_file(env_path: Path) -> str | None:
    return _value_from_env_file(env_path, "SALON_INTERNAL_BOOKING_TOKEN")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test salon_gateway HTTP endpoints.")
    env_file_default = _repo_root() / "src" / "agent" / ".env"

    parser.add_argument(
        "--base-url",
        default=None,
        metavar="URL",
        help="Gateway base URL (default: $SALON_TEST_BASE_URL or from .env or http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for /internal/booking (default: env or src/agent/.env)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Path to .env (default: <repo>/src/agent/.env)",
    )
    parser.add_argument("--skip-booking", action="store_true", help="Only GET /health")
    parser.add_argument(
        "--require-booking",
        action="store_true",
        help="Exit 1 if booking test is skipped due to missing token",
    )
    args = parser.parse_args()

    env_file = args.env_file or env_file_default
    base_url = args.base_url
    if not base_url:
        base_url = (
            os.environ.get("SALON_TEST_BASE_URL")
            or _value_from_env_file(env_file, "SALON_TEST_BASE_URL")
            or "http://127.0.0.1:8765"
        )
    token = args.token or os.environ.get("SALON_INTERNAL_BOOKING_TOKEN")
    if not token:
        token = load_token_from_env_file(env_file)

    base = base_url.rstrip("/")

    # --- GET /health ---
    try:
        req = urllib.request.Request(f"{base}/health", method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8")
            print(f"[health] HTTP {r.status} {body}")
            if r.status != 200:
                return 1
    except urllib.error.HTTPError as e:
        print(f"[health] HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"[health] connection failed: {e.reason!r}", file=sys.stderr)
        return 1

    if args.skip_booking:
        print("[booking] skipped (--skip-booking)")
        return 0

    if not token:
        msg = "[booking] skipped (no token: set SALON_INTERNAL_BOOKING_TOKEN or use --token; .env: %s)" % env_file
        print(msg, file=sys.stderr)
        return 1 if args.require_booking else 0

    payload = {
        "idempotency_key": "test_salon_gateway_script",
        "phone": "13800138000",
        "store": "测试店",
        "service": ["染发", "烫发"],
        "slot_text": "下周六下午",
        "status": "pending",
        "channel": "wecom",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/internal/booking",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = r.read().decode("utf-8")
            print(f"[booking] HTTP {r.status} {out}")
            return 0 if r.status == 200 else 1
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        print(f"[booking] HTTP {e.code} {err_body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"[booking] connection failed: {e.reason!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
