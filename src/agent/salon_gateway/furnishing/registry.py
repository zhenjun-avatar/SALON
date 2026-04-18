"""素材库加载与检索。后续可改为 DB / 对象存储：保持 FurnishingRegistry 接口即可。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from salon_gateway.models.furnishing import FurnishingAssetOut


@dataclass(slots=True)
class _Row:
    id: str
    category: str
    name: str
    image_url: str
    tags: list[str]


class FurnishingRegistry:
    """从 JSON 文件加载素材；文件变更时按 mtime 自动重载。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._mtime: float = 0.0
        self._rows: list[_Row] = []

    def _load_if_stale(self) -> None:
        if not self._path.is_file():
            if self._rows:
                logger.warning("furnishing assets file missing: {}", self._path)
            self._rows = []
            self._mtime = 0.0
            return
        try:
            m = self._path.stat().st_mtime
        except OSError:
            return
        if m == self._mtime and self._rows:
            return
        raw = self._path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("furnishing assets JSON invalid {}: {}", self._path, e)
            self._rows = []
            self._mtime = m
            return
        rows = _parse_assets(data)
        self._rows = rows
        self._mtime = m
        logger.info("furnishing assets loaded: {} entries from {}", len(rows), self._path)

    def search(
        self, *, q: str = "", category: str = "", limit: int = 20
    ) -> tuple[list[FurnishingAssetOut], int]:
        """返回 (截断后的列表, 命中总数)。"""
        self._load_if_stale()
        qn = (q or "").strip().lower()
        cat = (category or "").strip().lower()
        lim = max(1, min(limit, 100))
        matched: list[FurnishingAssetOut] = []
        for r in self._rows:
            if not (r.image_url or "").strip():
                continue
            if cat and r.category.lower() != cat:
                continue
            if qn:
                blob = f"{r.name} {' '.join(r.tags)} {r.id}".lower()
                if qn not in blob:
                    continue
            matched.append(
                FurnishingAssetOut(
                    id=r.id,
                    category=r.category,
                    name=r.name,
                    image_url=r.image_url.strip(),
                    tags=list(r.tags),
                )
            )
        total = len(matched)
        return matched[:lim], total


def _parse_assets(data: Any) -> list[_Row]:
    if not isinstance(data, dict):
        return []
    items = data.get("assets")
    if not isinstance(items, list):
        return []
    rows: list[_Row] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        aid = str(it.get("id") or f"asset-{i}").strip()
        if not aid:
            continue
        tags_raw = it.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        rows.append(
            _Row(
                id=aid,
                category=str(it.get("category") or "").strip(),
                name=str(it.get("name") or "").strip(),
                image_url=str(it.get("image_url") or "").strip(),
                tags=tags,
            )
        )
    return rows
