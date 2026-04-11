#!/usr/bin/env python3
"""
Remove RAG / finance / frontend / API server artifacts, keeping only what
``tools.vedio_split`` needs: ``vedio_split/``, ``llm.py``, ``runtime_logging.py``,
``core/``, ``env.example``, and optional ``tools/data``.

Default: dry-run (prints paths only). Use ``--apply`` to delete.

Never touches: ``.git``, ``venv/``, ``.env``.

Note: Deleting ``src/frontend/`` removes its ``node_modules`` too; on Windows, close
``npm run dev``, IDE file watchers, and antivirus scans on that folder if you see
``WinError 32`` (file in use).

Usage (repo root):
  python scripts/cleanup_non_video_split.py
  python scripts/cleanup_non_video_split.py --apply
  python scripts/cleanup_non_video_split.py --apply --remove-tools-data --remove-outputs
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import time
from pathlib import Path

# Under src/agent/tools/: keep only these names (files or package dirs).
_TOOLS_KEEP = frozenset({"__init__.py", "llm.py", "runtime_logging.py", "vedio_split"})


def _repo_root(script_path: Path) -> Path:
    return script_path.resolve().parent.parent


def _must_be_repo(root: Path) -> None:
    marker = root / "pyproject.toml"
    if not marker.is_file():
        sys.exit(f"Refusing: no pyproject.toml at {root}")
    text = marker.read_text(encoding="utf-8", errors="replace")
    if "vedio-split" not in text and "vedio_split" not in text.lower() and "rag-api" not in text:
        sys.exit(f"Refusing: {marker} does not look like this project")


def _is_safe_target(path: Path, root: Path) -> bool:
    rp = path.resolve()
    if rp == root.resolve():
        return False
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            rp.relative_to(git_dir.resolve())
            return False
        except ValueError:
            pass
    try:
        rp.relative_to(root.resolve())
    except ValueError:
        return False
    parts = rp.parts
    if "venv" in parts or "node_modules" in parts:
        return False
    if path.name == ".env" and path.is_file():
        return False
    return True


def collect_paths(root: Path, *, remove_tools_data: bool, remove_outputs: bool) -> list[Path]:
    targets: list[Path] = []

    rel_dirs = [
        "src/frontend",
        "src/agent/api",
        "tests",
        ".github",
    ]
    for rel in rel_dirs:
        p = root / rel
        if p.exists():
            targets.append(p)

    rel_files = [
        "src/agent/run_server.py",
        "src/start_fastapi.py",
        "docker-compose.yml",
        "docker-compose.rag.yml",
        "Dockerfile.agent",
        "Dockerfile.analytics",
        "analytics_requirements.txt",
        "out.json",
    ]
    for rel in rel_files:
        p = root / rel
        if p.is_file():
            targets.append(p)

    ingest = root / "src/agent/ingest-direct"
    if ingest.exists():
        targets.append(ingest)

    if remove_outputs:
        out_dir = root / "src/agent/outputs"
        if out_dir.exists():
            targets.append(out_dir)

    tools = root / "src/agent/tools"
    if tools.is_dir():
        for child in sorted(tools.iterdir(), key=lambda x: x.name.lower()):
            if child.name in _TOOLS_KEEP:
                continue
            if child.name == "data" and not remove_tools_data:
                continue
            targets.append(child)

    rag_agent_dirs = [
        root / "src/agent/logs",
        root / "src/agent/report",
    ]
    for p in rag_agent_dirs:
        if p.exists():
            targets.append(p)

    # De-duplicate, sort, only under root
    seen: set[Path] = set()
    ordered: list[Path] = []
    for p in sorted(targets, key=lambda x: str(x).lower()):
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        try:
            rp.relative_to(root.resolve())
        except ValueError:
            continue
        if not _is_safe_target(p, root):
            continue
        ordered.append(p)
    return ordered


def _chmod_writable_tree(target: Path) -> None:
    """Best-effort: mark files/dirs writable (helps Windows delete after git/npm)."""
    if not target.exists():
        return
    for walk_root, dirnames, filenames in os.walk(target, topdown=False):
        base = Path(walk_root)
        for name in filenames:
            fp = base / name
            try:
                st = fp.stat()
                fp.chmod(st.st_mode | stat.S_IWRITE)
            except OSError:
                pass
        for name in dirnames:
            dp = base / name
            try:
                st = dp.stat()
                dp.chmod(st.st_mode | stat.S_IWRITE)
            except OSError:
                pass
    try:
        st = target.stat()
        target.chmod(st.st_mode | stat.S_IWRITE)
    except OSError:
        pass


def _is_file_in_use_error(exc: OSError) -> bool:
    winerr = getattr(exc, "winerror", None)
    if winerr == 32:  # ERROR_SHARING_VIOLATION
        return True
    if winerr == 5:  # ACCESS_DENIED (often transient while handles close)
        return True
    if exc.errno in (13, 16):  # EACCES, EBUSY
        return True
    return False


def _rmtree_robust(path: Path, *, attempts: int = 12) -> None:
    """Delete a directory tree; retry with chmod + backoff on Windows file locks."""
    path = path.resolve()
    last: OSError | None = None
    for i in range(attempts):
        try:
            shutil.rmtree(path)
            if not path.exists():
                return
        except OSError as e:
            last = e
            if not _is_file_in_use_error(e):
                raise
        _chmod_writable_tree(path)
        time.sleep(0.2 + 0.25 * i)
    err = RuntimeError(
        f"Could not delete folder (files still in use): {path}\n"
        "  • Stop `npm run dev` / any process using src/frontend\n"
        "  • Close Explorer windows inside that folder\n"
        "  • Retry; or run:  rd /s /q src\\frontend\\node_modules  then re-run this script"
    )
    if last is not None:
        raise err from last
    raise err


def _delete(path: Path) -> None:
    if path.is_dir():
        # Delete node_modules first when removing frontend (shorter lock window for rest).
        if path.name == "frontend":
            nm = path / "node_modules"
            if nm.is_dir():
                try:
                    _rmtree_robust(nm)
                except RuntimeError:
                    _rmtree_robust(path)
                    return
        _rmtree_robust(path)
    elif path.is_file() or path.is_symlink():
        try:
            path.unlink()
        except PermissionError:
            path.chmod(stat.S_IWRITE)
            path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run or delete non–video-split project files.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete; default is dry-run",
    )
    parser.add_argument(
        "--remove-tools-data",
        action="store_true",
        help="Also remove src/agent/tools/data (large EDGAR dumps, sample videos, etc.)",
    )
    parser.add_argument(
        "--remove-outputs",
        action="store_true",
        help="Also remove src/agent/outputs (generated clips / manifests)",
    )
    args = parser.parse_args()

    script = Path(__file__)
    root = (args.repo_root or _repo_root(script)).resolve()
    _must_be_repo(root)

    targets = collect_paths(
        root,
        remove_tools_data=args.remove_tools_data,
        remove_outputs=args.remove_outputs,
    )

    mode = "APPLY (deleting)" if args.apply else "DRY-RUN (no changes)"
    print(f"{mode} — repo root: {root}")
    print(f"Targets ({len(targets)}):")
    for p in targets:
        print(f"  {p.relative_to(root)}")

    if not args.apply:
        print("\nRe-run with --apply to delete. Optional: --remove-tools-data --remove-outputs")
        return

    for p in targets:
        if not p.exists():
            continue
        print(f"  deleting {p.relative_to(root)}")
        _delete(p)

    print("\nDone. Trim pyproject.toml / requirements.txt to only what vedio_split needs, or keep a venv with langchain + faster-whisper + ffmpeg on PATH.")


if __name__ == "__main__":
    main()
