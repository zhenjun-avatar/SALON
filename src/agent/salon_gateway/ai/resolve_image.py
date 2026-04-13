"""将用户图片 URL 解析为 DashScope 万相可用的 base_image_url。

通义万相支持：
  - 公网 HTTPS URL
  - data:{mime};base64,{data}

Dify 的 upload.dify.ai / *.dify.ai 预览链通常无法被阿里云侧直接拉取，
需在网关用 Dify API Key 下载后转为 data URI 再提交。
"""

from __future__ import annotations

import base64
from urllib.parse import urlparse

import httpx
from loguru import logger

from salon_gateway.config import SalonGatewaySettings

_DEFAULT_MIME = "image/jpeg"
_MAX_BYTES = 10 * 1024 * 1024  # 与万相文档单图上限一致


def _is_dify_cdn_host(host: str) -> bool:
    h = (host or "").lower()
    return h == "upload.dify.ai" or h.endswith(".dify.ai")


async def resolve_base_image_for_dashscope(url: str, settings: SalonGatewaySettings) -> str:
    """返回公网 URL 或 data URI，供 WanxiangClient 作为 base_image_url 传入。"""
    u = (url or "").strip()
    if not u:
        raise ValueError("empty image url")
    if u.startswith("data:"):
        return u

    parsed = urlparse(u)
    host = (parsed.hostname or "").lower()
    if not _is_dify_cdn_host(host):
        return u

    key = (settings.dify_api_key or "").strip()
    # 先试无头（签名 URL 可能足够），再带 Dify 应用 Key（预览链常需鉴权）
    headers_list: list[dict[str, str]] = [{}]
    if key:
        headers_list.append({"Authorization": f"Bearer {key}"})

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        for headers in headers_list:
            try:
                r = await client.get(u, headers=headers)
                r.raise_for_status()
                break
            except Exception as e:
                last_err = e
                continue
        else:
            logger.error(
                "dify image fetch failed host={} has_dify_key={}: {}",
                host,
                bool(key),
                last_err,
            )
            raise RuntimeError(
                "无法从 Dify 拉取图片：请配置 SALON_DIFY_API_KEY，"
                "或改用公网可访问的图片 URL"
            ) from last_err

        data = r.content
        if len(data) > _MAX_BYTES:
            raise ValueError(f"image too large: {len(data)} bytes (max {_MAX_BYTES})")

        ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not ct.startswith("image/"):
            ct = _DEFAULT_MIME
        b64 = base64.standard_b64encode(data).decode("ascii")
        logger.info(
            "resolved Dify image to data URI: bytes={} mime={}",
            len(data),
            ct,
        )
        return f"data:{ct};base64,{b64}"
