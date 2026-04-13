"""阿里云视觉智能 SegmentHair —— 发区精准分割，生成 mask 供万相 description_edit_with_mask 使用。

流程：
    1. 将用户图片（bytes）压缩到 SegmentHair 限制（≤2000×2000, ≤3MB）
    2. Base64 编码后 POST SegmentHair API
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


def _rgba_to_mask_data_uri(rgba_bytes: bytes) -> str:
    """从 SegmentHair 返回的 RGBA PNG 提取 alpha 通道作为发区 mask data URI。

    万相 description_edit_with_mask 需要：白色 = 编辑区（头发），黑色 = 保留区。
    SegmentHair alpha 通道：255=头发，0=背景，完全对应。
    """
    rgba_img = Image.open(io.BytesIO(rgba_bytes)).convert("RGBA")
    _, _, _, alpha = rgba_img.split()  # 提取 alpha 通道
    buf = io.BytesIO()
    alpha.save(buf, format="PNG")
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _call_segment_hair_sync(
    access_key_id: str,
    access_key_secret: str,
    region: str,
    image_base64: str,
) -> str:
    """同步调用 SegmentHair（在 executor 线程里执行）。返回 mask RGBA PNG URL。"""
    from alibabacloud_imageseg20191230.client import Client
    from alibabacloud_imageseg20191230 import models as seg_models
    from alibabacloud_tea_openapi import models as oa_models

    config = oa_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )
    config.endpoint = f"imageseg.{region}.aliyuncs.com"
    client = Client(config)

    request = seg_models.SegmentHairRequest(image_base64=image_base64)
    response = client.segment_hair(request)
    return response.body.data.image_url  # 30 分钟有效的 RGBA PNG URL


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
        img = _resize_for_segment(img)
        jpeg_bytes = _to_jpeg_bytes(img)
        if len(jpeg_bytes) > _SEGMENT_MAX_BYTES:
            # 降质再试一次
            jpeg_bytes = _to_jpeg_bytes(img, quality=70)

        b64 = base64.standard_b64encode(jpeg_bytes).decode("ascii")
        logger.debug(
            "hair_segment: calling SegmentHair size={}B region={}",
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
            b64,
        )
        mask_url: str = await loop.run_in_executor(None, fn)
        logger.info("hair_segment: mask_url={}", mask_url[:80])

        # 3. 下载 RGBA mask PNG，提取 alpha 通道
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(mask_url)
            r.raise_for_status()
            rgba_bytes = r.content

        mask_uri = _rgba_to_mask_data_uri(rgba_bytes)
        logger.info("hair_segment: mask data URI len={}", len(mask_uri))
        return mask_uri
