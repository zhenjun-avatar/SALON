"""python -m salon_gateway — 默认 0.0.0.0:8765"""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("SALON_HOST", "0.0.0.0")
    port = int(os.environ.get("SALON_PORT", "8765"))
    uvicorn.run(
        "salon_gateway.app:app",
        host=host,
        port=port,
        reload=os.environ.get("SALON_RELOAD", "").lower() in ("1", "true", "yes"),
    )
