from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from salon_gateway.config import SalonGatewaySettings
from salon_gateway.models.booking import BookingDraft


class FeishuBitableSink:
    """飞书多维表新增一行记录。"""

    _token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    def __init__(self, settings: SalonGatewaySettings) -> None:
        self._s = settings
        self._token: str | None = None
        self._token_deadline: float = 0.0

    async def _tenant_token(self, client: httpx.AsyncClient) -> str:
        now = time.monotonic()
        if self._token and now < self._token_deadline - 60:
            return self._token
        body = {"app_id": self._s.feishu_app_id, "app_secret": self._s.feishu_app_secret}
        r = await client.post(self._token_url, json=body)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"feishu token error: {data}")
        self._token = data["tenant_access_token"]
        expire = int(data.get("expire", 7200))
        self._token_deadline = now + float(expire)
        return self._token

    async def append_booking(self, draft: BookingDraft) -> None:
        fields = draft.to_feishu_fields(self._s.feishu_field_map)
        if not fields:
            logger.warning("feishu_field_map 为空，跳过写入；请配置 SALON_FEISHU_FIELD_MAP_JSON")
            return
        app = self._s.feishu_bitable_app_token
        tid = self._s.feishu_bitable_table_id
        url = (
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app}/tables/{tid}/records"
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            token = await self._tenant_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            payload: dict[str, Any] = {"fields": fields}
            r = await client.post(url, json=payload, headers=headers)
            try:
                data = r.json()
            except Exception:
                data = {"_parse_error": (r.text or "")[:2000]}
            if r.status_code >= 400:
                logger.error("feishu bitable HTTP {}: {}", r.status_code, data)
                raise RuntimeError(f"feishu HTTP {r.status_code}: {data}") from None
        if data.get("code") != 0:
            logger.error("feishu bitable business error: {}", data)
            raise RuntimeError(f"feishu bitable error: {data}")
        logger.info("feishu_bitable_record_created {}", data.get("data", {}))
