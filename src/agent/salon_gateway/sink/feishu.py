from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from salon_gateway.config import SalonGatewaySettings
from salon_gateway.models.booking import BookingDraft

_SINGLE_SELECT_UI = frozenset({"SingleSelect"})
_MULTI_SELECT_UI = frozenset({"MultiSelect"})


class FeishuBitableSink:
    """飞书多维表新增一行记录。"""

    _token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    # class-level: avoid hammering list-fields API (20/s limit)
    _fields_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
    _fields_cache_ttl_sec = 300.0

    def __init__(self, settings: SalonGatewaySettings) -> None:
        self._s = settings
        self._token: str | None = None
        self._token_deadline: float = 0.0

    def _fields_base_url(self) -> str:
        app = self._s.feishu_bitable_app_token
        tid = self._s.feishu_bitable_table_id
        return f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app}/tables/{tid}/fields"

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

    def _fields_cache_key(self) -> str:
        return f"{self._s.feishu_bitable_app_token}|{self._s.feishu_bitable_table_id}"

    async def list_table_fields(self) -> list[dict[str, Any]]:
        """All bitable field definitions (paginated)."""
        key = self._fields_cache_key()
        now = time.monotonic()
        hit = FeishuBitableSink._fields_cache.get(key)
        if hit and now - hit[0] < FeishuBitableSink._fields_cache_ttl_sec:
            return list(hit[1])

        items: list[dict[str, Any]] = []
        page_token: str | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            token = await self._tenant_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            while True:
                params: dict[str, str | int] = {"page_size": 100}
                if page_token:
                    params["page_token"] = page_token
                r = await client.get(self._fields_base_url(), headers=headers, params=params)
                r.raise_for_status()
                data = r.json()
                if data.get("code") != 0:
                    raise RuntimeError(f"feishu list fields error: {data}")
                block = data.get("data") or {}
                batch = block.get("items") or []
                items.extend(batch)
                if not block.get("has_more"):
                    break
                page_token = block.get("page_token")
                if not page_token:
                    break
        FeishuBitableSink._fields_cache[key] = (now, list(items))
        return items

    @staticmethod
    def _filter_option_names(
        options: list[dict[str, Any]],
        q: str,
    ) -> list[dict[str, Any]]:
        qn = (q or "").strip().lower()
        out: list[dict[str, Any]] = []
        for opt in options:
            name = str(opt.get("name") or "").strip()
            if not name:
                continue
            oid = str(opt.get("id") or "")
            if not qn or qn in name.lower():
                out.append({"id": oid, "name": name})
        return out

    async def booking_field_options(
        self,
        *,
        store_search: str = "",
        service_search: str = "",
    ) -> dict[str, Any]:
        """Options for store (SingleSelect) and service (MultiSelect) per feishu_field_map column names."""
        fmap = self._s.feishu_field_map
        store_col = (fmap.get("store") or "").strip()
        service_col = (fmap.get("service") or "").strip()
        result: dict[str, Any] = {
            "store": {"field_name": store_col, "ui_type": None, "options": []},
            "service": {"field_name": service_col, "ui_type": None, "options": []},
        }
        if not store_col and not service_col:
            result["warning"] = "feishu_field_map 缺少 store 或 service 列名映射"
            return result

        fields = await self.list_table_fields()
        by_name = {str(f.get("field_name") or ""): f for f in fields}

        def _resolve_ui(fdef: dict[str, Any]) -> str:
            ui = str(fdef.get("ui_type") or "").strip()
            if ui:
                return ui
            t = fdef.get("type")
            if t == 3:
                return "SingleSelect"
            if t == 4:
                return "MultiSelect"
            return ""

        def fill(key: str, col: str, search: str, allowed_ui: frozenset[str]) -> None:
            if not col:
                return
            fdef = by_name.get(col)
            if not fdef:
                result[key]["error"] = f"表中未找到名为「{col}」的列"
                return
            ui = _resolve_ui(fdef)
            result[key]["ui_type"] = ui
            if ui not in allowed_ui:
                result[key]["error"] = f"列「{col}」类型为 {ui}，需要 {allowed_ui}"
                return
            prop = fdef.get("property") or {}
            raw_opts = prop.get("options") or []
            if not isinstance(raw_opts, list):
                raw_opts = []
            result[key]["options"] = self._filter_option_names(raw_opts, search)

        fill("store", store_col, store_search, _SINGLE_SELECT_UI)
        fill("service", service_col, service_search, _MULTI_SELECT_UI)
        return result

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
