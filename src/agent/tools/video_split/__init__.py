"""Video transcript → LLM clip plan → ffmpeg shorts (package: vedio_split).

Use ``python -m tools.vedio_split`` or import ``run_shorts_pipeline`` from
``tools.vedio_split.pipeline`` to avoid pulling the full stack on ``import tools.vedio_split``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["run_shorts_pipeline"]


def __getattr__(name: str) -> Any:
    if name == "run_shorts_pipeline":
        return import_module(".pipeline", __package__).run_shorts_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
