#!/usr/bin/env python3
"""CLI: POST /simulate/wecom-text (same pipeline as WeCom text → Dify).

  python scripts/simulate_wecom.py 你好
  python scripts/simulate_wecom.py -m "下周六想染发"
  python scripts/simulate_wecom.py --chat              # REPL: continuous chat, same from_user
  python scripts/simulate_wecom.py --chat -m "开场白" # send first line, then REPL

  # Image: local file (uploads to Dify first) or public URL
  python scripts/simulate_wecom.py --image /path/to/photo.jpg
  python scripts/simulate_wecom.py --image https://example.com/photo.jpg -m "推荐发色"
  python scripts/simulate_wecom.py --chat --image /path/to/photo.jpg -m "这是我的照片"

Env / .env (src/agent/.env by default):
  SALON_SIMULATE_TOKEN   required (Bearer)
  SALON_TEST_BASE_URL    optional base, default http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
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
            v = s.split("=", 1)[1].strip().strip('"').strip("'").strip("\ufeff")
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


def _normalize_bearer_token(raw: str) -> str:
    """Strip whitespace/BOM; if value looks like 'Bearer xxx', keep only xxx."""
    t = (raw or "").strip().strip("\ufeff")
    parts = t.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return t


def _resolve_simulate_token(env_file: Path) -> str | None:
    t = os.environ.get("SALON_SIMULATE_TOKEN")
    if t:
        v = _normalize_bearer_token(t)
        return v if v else None
    from_file = _value_from_env_file(env_file, "SALON_SIMULATE_TOKEN")
    return _normalize_bearer_token(from_file) if from_file else None


def _multipart_encode(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    """Build a multipart/form-data body (stdlib only)."""
    boundary = f"----SimBoundary{secrets.token_hex(8)}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    for name, (filename, content, mime_type) in files.items():
        parts.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode()
            + content
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _upload_image(
    base: str,
    token: str,
    path: Path,
    timeout: float = 60.0,
) -> tuple[bool, str | None, str]:
    """Upload local image to /simulate/upload-image; returns (ok, upload_file_id, error)."""
    content = path.read_bytes()
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    body, content_type = _multipart_encode({}, {"file": (path.name, content, mime)})
    req = urllib.request.Request(
        f"{base}/simulate/upload-image",
        data=body,
        method="POST",
        headers={"Content-Type": content_type, "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp_body = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return False, None, e.read().decode(errors="replace")
    except urllib.error.URLError as e:
        return False, None, f"connection failed: {e.reason!r}"
    try:
        obj = json.loads(resp_body)
        return True, obj["upload_file_id"], ""
    except Exception:
        return False, None, resp_body


def _post_simulate(
    base: str,
    token: str,
    *,
    content: str,
    from_user: str,
    to_user: str,
    msg_id: str | None,
    image_url: str | None = None,
    upload_file_id: str | None = None,
    timeout: float = 120.0,
) -> tuple[bool, dict | None, str]:
    """Returns (ok, parsed_json_or_none, raw_body_or_error)."""
    payload: dict = {
        "content": content,
        "from_user": from_user,
        "to_user": to_user,
    }
    if msg_id:
        payload["msg_id"] = msg_id
    if upload_file_id:
        payload["upload_file_id"] = upload_file_id
    elif image_url:
        payload["image_url"] = image_url

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


def _resolve_image(
    base: str, token: str, image_arg: str | None
) -> tuple[str | None, str | None, str | None]:
    """Return (image_url, upload_file_id, error).  Uploads local file if needed."""
    if not image_arg:
        return None, None, None
    if image_arg.startswith("http://") or image_arg.startswith("https://"):
        return image_arg, None, None
    p = Path(image_arg).expanduser().resolve()
    if not p.is_file():
        return None, None, f"image file not found: {p}"
    ok, fid, err = _upload_image(base, token, p)
    if not ok:
        return None, None, f"upload failed: {err}"
    print(f"[image] uploaded → upload_file_id={fid}", file=sys.stderr)
    return None, fid, None


def _run_chat_loop(
    base: str,
    token: str,
    *,
    from_user: str,
    to_user: str,
    show_json: bool,
    initial_message: str,
    image_url: str | None = None,
    upload_file_id: str | None = None,
) -> int:
    failed = False
    print(
        f"模拟企微连续对话 (from_user={from_user!r}, base={base})\n"
        "每行一条消息；exit / quit / :q 结束；空行忽略。\n"
        "发送图片：输入 /image <url或本地路径>",
        file=sys.stderr,
    )

    n = 0
    # image state: only attached to the next turn, then cleared
    _img_url: list[str | None] = [image_url]
    _fid: list[str | None] = [upload_file_id]

    def one_turn(text: str) -> None:
        nonlocal n, failed
        n += 1
        msg_id = f"sim-chat-{n}"
        ok, obj, raw = _post_simulate(
            base,
            token,
            content=text,
            from_user=from_user,
            to_user=to_user,
            msg_id=msg_id,
            image_url=_img_url[0],
            upload_file_id=_fid[0],
        )
        _img_url[0] = None
        _fid[0] = None
        if not ok:
            failed = True
            print(raw, file=sys.stderr)
            return
        if show_json and obj is not None:
            print(json.dumps(obj, ensure_ascii=False, indent=2))
        elif obj is not None:
            print(obj.get("reply", raw))
        else:
            print(raw)

    if initial_message or image_url or upload_file_id:
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
        if low.startswith("/image "):
            img_arg = text[7:].strip()
            iu, fid, err = _resolve_image(base, token, img_arg)
            if err:
                print(f"[image] error: {err}", file=sys.stderr)
            else:
                _img_url[0] = iu
                _fid[0] = fid
                print(f"[image] queued, send next message to attach it.", file=sys.stderr)
            continue
        one_turn(text)

    return 1 if failed else 0


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
    parser.add_argument(
        "--image",
        default=None,
        metavar="URL_OR_PATH",
        help="Attach image: public URL (remote_url) or local file path (auto-uploaded to Dify)",
    )
    args = parser.parse_args()

    env_file = args.env_file or env_file_default
    base = (args.base_url or _resolve_base_url(env_file)).rstrip("/")
    token = _normalize_bearer_token(args.token or _resolve_simulate_token(env_file) or "")
    if not token:
        print(
            "Missing SALON_SIMULATE_TOKEN (export it or set in %s)" % env_file,
            file=sys.stderr,
        )
        return 1

    text = (args.message if args.message is not None else " ".join(args.words)).strip()

    # Resolve image once (upload local file if needed)
    img_url, upload_file_id, img_err = _resolve_image(base, token, args.image)
    if img_err:
        print(f"image error: {img_err}", file=sys.stderr)
        return 1

    if args.chat:
        return _run_chat_loop(
            base,
            token,
            from_user=args.from_user,
            to_user=args.to_user,
            show_json=args.json,
            initial_message=text,
            image_url=img_url,
            upload_file_id=upload_file_id,
        )

    if not text and not args.image:
        parser.error("message required: positional words, -m/--message, --image, or use --chat")

    ok, obj, raw = _post_simulate(
        base,
        token,
        content=text,
        from_user=args.from_user,
        to_user=args.to_user,
        msg_id=args.msg_id,
        image_url=img_url,
        upload_file_id=upload_file_id,
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
