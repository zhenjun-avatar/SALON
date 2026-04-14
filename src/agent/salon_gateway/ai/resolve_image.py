"""将用户图片 URL 解析为 DashScope 万相可用的 base_image_url。

通义万相支持：
  - 公网 HTTPS URL
  - data:{mime};base64,{data}

Dify 的 upload.dify.ai / *.dify.ai 预览链通常无法被阿里云侧直接拉取，
需在网关用 Dify API Key 下载后转为 data URI 再提交。

万相尺寸要求：宽高均在 512–4096 px 之间，文件 ≤ 10 MB。
图片不符合时自动缩放。
"""

from __future__ import annotations

import base64
import binascii
import io
import math
from urllib.parse import urlparse

import httpx
from loguru import logger
from PIL import Image

from salon_gateway.config import SalonGatewaySettings

_DEFAULT_MIME = "image/jpeg"
_MAX_BYTES = 10 * 1024 * 1024  # 万相单图上限
_MIN_DIM = 512      # 万相要求：宽高 ≥ 512（含）
_SAFE_MIN_DIM = 520  # 实际放大目标：留 8px 余量避免浮点截断后正好落在边界被拒绝
_MAX_DIM = 4096     # 万相要求：宽高 ≤ 4096
_SAFE_MAX_DIM = 4090  # 实际缩小目标：留 6px 余量


def _is_dify_cdn_host(host: str) -> bool:
    h = (host or "").lower()
    return h == "upload.dify.ai" or h.endswith(".dify.ai")


def _parse_data_uri(data_uri: str) -> tuple[bytes, str]:
    """Decode data:[mime][;base64],payload → (bytes, mime). Only base64 payloads are supported."""
    u = (data_uri or "").strip()
    if not u.startswith("data:"):
        raise ValueError("not a data URI")
    rest = u[5:]
    if "," not in rest:
        raise ValueError("invalid data URI: missing comma")
    meta, payload = rest.split(",", 1)
    meta = meta.strip()
    if ";base64" not in meta.lower():
        raise ValueError("invalid data URI: expected ;base64")
    mime = (meta.split(";")[0].strip() or _DEFAULT_MIME).lower()
    if not mime.startswith("image/"):
        mime = _DEFAULT_MIME
    raw = base64.standard_b64decode(payload)
    return raw, mime


def _ensure_valid_dimensions(data: bytes, mime: str) -> tuple[bytes, str]:
    """规范化图片：修正 EXIF 旋转、确保尺寸在万相可接受范围、JPEG 统一转 RGB baseline。

    放大时用 _SAFE_MIN_DIM + math.ceil：避免 int() 截断导致短边变成 511 或正好 512 被服务端拒绝。
    缩小时用 _SAFE_MAX_DIM + math.floor：避免长边压在 4096 边界上偶发失败。
    JPEG 始终经过 Pillow 重新编码，避免 CMYK / 旋转 / 非标准编码导致万相拒绝。
    PNG 若尺寸已合法则返回原始字节（跳过重编码）。
    """
    from PIL import ImageOps  # lazy import，避免顶层循环依赖

    img = Image.open(io.BytesIO(data))
    # 应用 EXIF 旋转（手机竖拍 JPEG 宽高会被翻转，不修正会误判尺寸）
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    original = (w, h)

    # 按需放大（任一边 < 512）：目标略高于下限，避免浮点误差 + 截断落在无效区间
    if w < _MIN_DIM or h < _MIN_DIM:
        scale = _SAFE_MIN_DIM / min(w, h)
        w = max(_SAFE_MIN_DIM, math.ceil(w * scale))
        h = max(_SAFE_MIN_DIM, math.ceil(h * scale))

    # 按需缩小（任一边 > 4096）：目标略低于上限
    if w > _MAX_DIM or h > _MAX_DIM:
        scale = _SAFE_MAX_DIM / max(w, h)
        w = min(_SAFE_MAX_DIM, math.floor(w * scale))
        h = min(_SAFE_MAX_DIM, math.floor(h * scale))

    fmt = "JPEG" if mime in ("image/jpeg", "image/jpg") else "PNG"
    out_mime = "image/jpeg" if fmt == "JPEG" else "image/png"

    # PNG 且尺寸合法 → 原样返回，跳过重编码
    if fmt == "PNG" and (w, h) == original:
        return data, out_mime

    if (w, h) != original:
        img = img.resize((w, h), Image.LANCZOS)

    # JPEG 不支持 alpha 通道；任何非 RGB 模式统一转换
    if fmt == "JPEG":
        if img.mode != "RGB":
            img = img.convert("RGB")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=92)
    result = buf.getvalue()

    if (w, h) != original:
        logger.info(
            "image resized: {}x{} → {}x{} mime={} bytes {} → {}",
            original[0], original[1], w, h, out_mime, len(data), len(result),
        )
    else:
        logger.info(
            "image re-encoded (JPEG normalize): {}x{} bytes {} → {}",
            w, h, len(data), len(result),
        )
    return result, out_mime


async def resolve_base_image_for_dashscope(url: str, settings: SalonGatewaySettings) -> str:
    """返回公网 URL 或 data URI，供 WanxiangClient 作为 base_image_url 传入。"""
    u = (url or "").strip()
    if not u:
        raise ValueError("empty image url")
    if u.startswith("data:"):
        try:
            data, ct = _parse_data_uri(u)
        except (ValueError, binascii.Error) as e:
            raise ValueError(f"invalid data URI: {e}") from e
        if len(data) > _MAX_BYTES:
            raise ValueError(f"image too large: {len(data)} bytes (max {_MAX_BYTES})")
        data, ct = _ensure_valid_dimensions(data, ct)
        b64 = base64.standard_b64encode(data).decode("ascii")
        return f"data:{ct};base64,{b64}"

    parsed = urlparse(u)
    host = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    # 公网 HTTPS 若直接交给万相拉取，小图仍会触发 InvalidParameter（宽/高 512–4096）。
    # 能成功下载则转为规范化后的 data URI，避免与 mask 路径不一致。
    if scheme in ("http", "https") and not _is_dify_cdn_host(host):
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                r = await client.get(u)
                r.raise_for_status()
                data = r.content
        except Exception as e:
            logger.warning(
                "resolve_base_image: could not fetch non-Dify URL host={} (pass-through): {}",
                host,
                e,
            )
            return u
        if len(data) > _MAX_BYTES:
            raise ValueError(f"image too large: {len(data)} bytes (max {_MAX_BYTES})")
        ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not ct.startswith("image/"):
            ct = _DEFAULT_MIME
        data, ct = _ensure_valid_dimensions(data, ct)
        b64 = base64.standard_b64encode(data).decode("ascii")
        logger.info(
            "resolved HTTPS image to data URI: host={} bytes={} mime={}",
            host,
            len(data),
            ct,
        )
        return f"data:{ct};base64,{b64}"

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

        data, ct = _ensure_valid_dimensions(data, ct)

        b64 = base64.standard_b64encode(data).decode("ascii")
        logger.info(
            "resolved Dify image to data URI: bytes={} mime={}",
            len(data),
            ct,
        )
        return f"data:{ct};base64,{b64}"
