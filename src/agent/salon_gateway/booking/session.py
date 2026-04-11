"""Accumulate BookingDraft fields across Dify turns, keyed by conversation_id.

Design rationale
----------------
Dify is stateless per node execution: the parameter-extractor only sees the
*current* user message, so phone / store / slot_text arrive in separate turns.
Rather than building complex cross-turn logic inside Dify's visual canvas, we
let the gateway be the source of truth: merge each turn's extracted fields into
an in-memory session and only write to Feishu the first time all required
fields are present.

Required fields: phone + slot_text + store
Optional fields: service, color_summary, history_summary, notes, external_user_id

State is held in-process.  For a multi-worker deployment use a shared store
(Redis hash) — swap _SessionStore with a Redis-backed implementation behind the
same interface.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

from loguru import logger

from salon_gateway.models.booking import BookingDraft

_ACCUMULATE: frozenset[str] = frozenset(
    {
        "phone",
        "store",
        "slot_text",
        "service",
        "color_summary",
        "history_summary",
        "notes",
        "external_user_id",
    }
)
_REQUIRED: frozenset[str] = frozenset({"phone", "slot_text", "store"})


def _is_complete(session: dict) -> bool:
    return all(bool(session.get(f, "")) for f in _REQUIRED)


class BookingSessionStore:
    """Thread-safe LRU-bounded accumulator.

    ``merge_and_check`` returns ``(merged_draft, newly_complete)`` where
    ``newly_complete`` is True exactly once — when this merge crosses the
    "all required fields present" threshold for the first time.  Callers
    should write to Feishu only when ``newly_complete`` is True.
    """

    def __init__(self, max_sessions: int = 5_000) -> None:
        self._lock = threading.Lock()
        self._store: OrderedDict[str, dict] = OrderedDict()
        self._max = max_sessions

    # ------------------------------------------------------------------
    def merge_and_check(
        self,
        conversation_id: str,
        draft: BookingDraft,
    ) -> tuple[BookingDraft, bool]:
        """Merge *draft* into the session; return merged draft + newly_complete flag."""
        incoming = {
            k: v
            for k, v in draft.model_dump(exclude_none=True).items()
            if k in _ACCUMULATE and v not in ("", [])
        }

        with self._lock:
            session: dict = dict(self._store.get(conversation_id, {}))
            was_complete = _is_complete(session)

            # merge: non-empty incoming value wins; existing value kept otherwise
            for field, value in incoming.items():
                session[field] = value

            # always carry latest status / channel
            for field in ("status", "channel"):
                val = getattr(draft, field, None)
                if val:
                    session[field] = val

            newly_complete = _is_complete(session) and not was_complete

            # LRU eviction
            self._store.pop(conversation_id, None)
            self._store[conversation_id] = session
            while len(self._store) > self._max:
                self._store.popitem(last=False)

        merged = BookingDraft(**session)
        logger.debug(
            "booking_session cid={} was_complete={} newly_complete={} fields={}",
            conversation_id,
            was_complete,
            newly_complete,
            sorted(session.keys()),
        )
        return merged, newly_complete
