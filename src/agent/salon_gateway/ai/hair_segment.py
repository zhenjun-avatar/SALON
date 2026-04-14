"""阿里云视觉智能 SegmentHair —— 发区精准分割，生成 mask 供万相 description_edit_with_mask 使用。

流程：
    1. 将用户图片（bytes）压缩到 SegmentHair 限制（≤2000×2000, ≤3MB）
    2. 通过 SDK SegmentHairAdvanceRequest（内存 JPEG 流）调用 segment_hair_advance
    3. 下载返回的 RGBA PNG，提取 alpha 通道作为二值化发区 mask
    4. 返回 data:image/png;base64,... 字符串

所需凭证：阿里云账号的 AccessKeyId + AccessKeySecret
    （与 DashScope API Key 不同，在阿里云 RAM 控制台创建）
"""

from __future__ import annotations

import asyncio
import base64
import io
from functools import partial

import httpx
from loguru import logger
from PIL import Image

_SEGMENT_MAX_DIM = 2000   # SegmentHair 分辨率上限
_SEGMENT_MAX_BYTES = 3 * 1024 * 1024  # SegmentHair 大小上限（原图 JPEG，base64 后 ~4MB）


def _resize_for_segment(img: Image.Image) -> Image.Image:
    """缩小到 SegmentHair 可接受的分辨率（2000×2000）。"""
    w, h = img.size
    if w <= _SEGMENT_MAX_DIM and h <= _SEGMENT_MAX_DIM:
        return img
    scale = _SEGMENT_MAX_DIM / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _to_jpeg_bytes(img: Image.Image, quality: int = 85) -> bytes:
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _rgba_to_mask_data_uri(
    rgba_bytes: bytes,
    target_size: tuple[int, int] | None = None,
) -> str:
    """从 SegmentHair 返回的 RGBA PNG 提取 alpha 通道作为发区 mask data URI。

    万相 description_edit_with_mask 需要：白色 = 编辑区（头发），黑色 = 保留区。
    SegmentHair alpha 通道：255=头发，0=背景，完全对应。

    target_size: 与万相 base_image 一致的 (W, H)。Segment 返回的图可能小于该尺寸或与
    内部分辨率不一致，万相会报 width 须在 512–4096；此处强制对齐到 base 尺寸。
    """
    rgba_img = Image.open(io.BytesIO(rgba_bytes)).convert("RGBA")
    _, _, _, alpha = rgba_img.split()  # 提取 alpha 通道
    if target_size is not None and alpha.size != target_size:
        logger.info(
            "hair_segment: resize mask {} → {} to match base",
            alpha.size,
            target_size,
        )
        alpha = alpha.resize(target_size, Image.NEAREST)
    buf = io.BytesIO()
    alpha.save(buf, format="PNG")
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _extract_segment_hair_image_url(response: object) -> str:
    """从 SegmentHair 响应中取结果图 URL（OpenAPI：Data.Elements[0].ImageURL）。"""
    body = getattr(response, "body", response)
    data = getattr(body, "data", None)
    if data is None:
        raise RuntimeError(f"SegmentHair: missing body.data: {body!r}")

    elements = getattr(data, "elements", None)
    if elements:
        el = elements[0]
        url = getattr(el, "image_url", None) or getattr(el, "imageURL", None)
        if url:
            return str(url)

    # 少数 SDK 版本可能扁平化字段
    flat = getattr(data, "image_url", None)
    if flat:
        return str(flat)

    raise RuntimeError(f"SegmentHair: no result URL in response data: {data!r}")


def _call_segment_hair_sync(
    access_key_id: str,
    access_key_secret: str,
    region: str,
    image_jpeg_bytes: bytes,
) -> str:
    """同步调用 SegmentHair（在 executor 线程里执行）。返回 mask RGBA PNG URL。

    当前 alibabacloud-imageseg20191230 的 SegmentHairRequest 仅支持公网 ImageURL，
    本地/内存图片须用 SegmentHairAdvanceRequest + image_urlobject + segment_hair_advance。
    参考：https://help.aliyun.com/zh/viapi/use-cases/division-of-hair
    """
    from alibabacloud_imageseg20191230.client import Client
    from alibabacloud_imageseg20191230.models import SegmentHairAdvanceRequest
    from alibabacloud_tea_openapi import models as oa_models
    from alibabacloud_tea_util.models import RuntimeOptions

    config = oa_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        endpoint=f"imageseg.{region}.aliyuncs.com",
        region_id=region,
    )
    client = Client(config)

    req = SegmentHairAdvanceRequest()
    req.image_urlobject = io.BytesIO(image_jpeg_bytes)

    runtime = RuntimeOptions()
    response = client.segment_hair_advance(req, runtime)
    return _extract_segment_hair_image_url(response)


class HairSegmentClient:
    """阿里云 SegmentHair 异步封装。"""

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        region: str = "cn-shanghai",
    ) -> None:
        self._ak_id = access_key_id
        self._ak_sec = access_key_secret
        self._region = region

    async def get_mask_data_uri(self, image_bytes: bytes) -> str:
        """输入图片字节，返回发区 mask 的 data URI（可直接作为 mask_image_url 传给万相）。

        失败时抛出异常，调用方应捕获并降级到无 mask 模式。
        """
        # 1. 压缩到 SegmentHair 分辨率/大小限制
        img = Image.open(io.BytesIO(image_bytes))
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
        base_size = img.size  # 与万相 base_image 像素一致，mask 最终须与此对齐
        img = _resize_for_segment(img)
        jpeg_bytes = _to_jpeg_bytes(img)
        if len(jpeg_bytes) > _SEGMENT_MAX_BYTES:
            # 降质再试一次
            jpeg_bytes = _to_jpeg_bytes(img, quality=70)

        logger.debug(
            "hair_segment: calling SegmentHair advance size={}B region={}",
            len(jpeg_bytes),
            self._region,
        )

        # 2. 在线程池中同步调用 SDK（SDK 是同步的）
        loop = asyncio.get_event_loop()
        fn = partial(
            _call_segment_hair_sync,
            self._ak_id,
            self._ak_sec,
            self._region,
            jpeg_bytes,
        )
        mask_url: str = await loop.run_in_executor(None, fn)
        logger.info("hair_segment: mask_url={}", mask_url[:80])

        # 3. 下载 RGBA mask PNG，提取 alpha 通道
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(mask_url)
            r.raise_for_status()
            rgba_bytes = r.content

        mask_uri = _rgba_to_mask_data_uri(rgba_bytes, target_size=base_size)
        logger.info("hair_segment: mask data URI len={}", len(mask_uri))
        return mask_uri
