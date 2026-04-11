from __future__ import annotations

from typing import Protocol

from salon_gateway.models.booking import BookingDraft


class BookingSink(Protocol):
    async def append_booking(self, draft: BookingDraft) -> None: ...
