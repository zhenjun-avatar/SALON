#!/usr/bin/env python3
"""CLI: POST /simulate/wecom-text (same pipeline as WeCom text → Dify).

  python scripts/simulate_wecom.py 你好
  python scripts/simulate_wecom.py -m "下周六想染发"
  python scripts/simulate_wecom.py --chat              # REPL: continuous chat, same from_user
  python scripts/simulate_wecom.py --chat -m "开场白" # send first line, then REPL

Env / .env (src/agent/.env by default):
  SALON_SIMULATE_TOKEN   required (Bearer)
  SALON_TEST_BASE_URL    optional base, default http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import readline  # noqa: F401 — line editing / history on supported platforms
except ImportError:
    pass


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


def _resolve_base_url(env_file: Path) -> str:
    v = os.environ.get("SALON_TEST_BASE_URL")
    if v:
        return v.rstrip("/")
    from_file = _value_from_env_file(env_file, "SALON_TEST_BASE_URL")
    if from_file:
        return from_file.rstrip("/")
    return "http://127.0.0.1:8765"


def _resolve_simulate_token(env_file: Path) -> str | None:
    t = os.environ.get("SALON_SIMULATE_TOKEN")
    if t:
        return t.strip() or None
    return _value_from_env_file(env_file, "SALON_SIMULATE_TOKEN")


def _post_simulate(
    base: str,
    token: str,
    *,
    content: str,
    from_user: str,
    to_user: str,
    msg_id: str | None,
    timeout: float = 120.0,
) -> tuple[bool, dict | None, str]:
    """Returns (ok, parsed_json_or_none, raw_body_or_error)."""
    payload: dict[str, str] = {
        "content": content,
        "from_user": from_user,
        "to_user": to_user,
    }
    if msg_id:
        payload["msg_id"] = msg_id

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/simulate/wecom-text",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            if r.status != 200:
                return False, None, body
    except urllib.error.HTTPError as e:
        return False, None, e.read().decode(errors="replace")
    except urllib.error.URLError as e:
        return False, None, f"connection failed: {e.reason!r}"

    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return True, None, body
    return True, obj, body


def _run_chat_loop(
    base: str,
    token: str,
    *,
    from_user: str,
    to_user: str,
    show_json: bool,
    initial_message: str,
) -> int:
    print(
        f"模拟企微连续对话 (from_user={from_user!r}, base={base})\n"
        "每行一条消息；exit / quit / :q 结束；空行忽略。",
        file=sys.stderr,
    )

    n = 0

    def one_turn(text: str) -> None:
        nonlocal n
        n += 1
        msg_id = f"sim-chat-{n}"
        ok, obj, raw = _post_simulate(
            base,
            token,
            content=text,
            from_user=from_user,
            to_user=to_user,
            msg_id=msg_id,
        )
        if not ok:
            print(raw, file=sys.stderr)
            return
        if show_json and obj is not None:
            print(json.dumps(obj, ensure_ascii=False, indent=2))
        elif obj is not None:
            print(obj.get("reply", raw))
        else:
            print(raw)

    if initial_message:
        one_turn(initial_message)

    while True:
        try:
            line = input("你> ")
        except EOFError:
            print(file=sys.stderr)
            break
        text = line.strip()
        if not text:
            continue
        low = text.lower()
        if low in ("exit", "quit", ":q"):
            break
        one_turn(text)

    return 0


def main() -> int:
    env_file_default = _repo_root() / "src" / "agent" / ".env"
    parser = argparse.ArgumentParser(description="Call salon_gateway POST /simulate/wecom-text")
    parser.add_argument(
        "words",
        nargs="*",
        metavar="WORD",
        help="User message words (joined with spaces). Or use -m/--message.",
    )
    parser.add_argument(
        "-m",
        "--message",
        default=None,
        help="Full user message (alternative to positional words)",
    )
    parser.add_argument(
        "-c",
        "--chat",
        action="store_true",
        help="Interactive multi-turn chat (same from_user, same Dify conversation)",
    )
    parser.add_argument("--from-user", default="sim-user-1", help="Stable Dify user id")
    parser.add_argument("--to-user", default="corp", help="Placeholder corp id")
    parser.add_argument("--msg-id", default=None, help="Optional msg id (single-shot only)")
    parser.add_argument("--base-url", default=None, help="Override gateway base URL")
    parser.add_argument("--env-file", type=Path, default=None, help="Path to .env")
    parser.add_argument(
        "--token",
        default=None,
        help="SALON_SIMULATE_TOKEN override (default: env or .env)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON response instead of reply text only",
    )
    args = parser.parse_args()

    env_file = args.env_file or env_file_default
    base = (args.base_url or _resolve_base_url(env_file)).rstrip("/")
    token = (args.token or _resolve_simulate_token(env_file) or "").strip()
    if not token:
        print(
            "Missing SALON_SIMULATE_TOKEN (export it or set in %s)" % env_file,
            file=sys.stderr,
        )
        return 1

    text = (args.message if args.message is not None else " ".join(args.words)).strip()

    if args.chat:
        return _run_chat_loop(
            base,
            token,
            from_user=args.from_user,
            to_user=args.to_user,
            show_json=args.json,
            initial_message=text,
        )

    if not text:
        parser.error("message required: positional words, -m/--message, or use --chat")

    ok, obj, raw = _post_simulate(
        base,
        token,
        content=text,
        from_user=args.from_user,
        to_user=args.to_user,
        msg_id=args.msg_id,
    )
    if not ok:
        print(raw, file=sys.stderr)
        return 1

    if args.json and obj is not None:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    elif obj is not None:
        print(obj.get("reply", raw))
    else:
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
