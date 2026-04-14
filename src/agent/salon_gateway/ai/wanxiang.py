"""DashScope 通义万相图像编辑客户端（wanx2.1-imageedit）。

调用流程（异步轮询）：
    1. POST /services/aigc/image2image/image-synthesis  →  获得 task_id
    2. GET  /tasks/{task_id}  轮询，直至 SUCCEEDED / FAILED
    3. 返回 results[0].url

两种编辑模式：
    - description_edit：通用编辑，无 mask，精度一般（降级 fallback）
    - description_edit_with_mask：限定发区 mask，仅修改头发，精度高（需配置 AK/SK）

base_image_url / mask_image_url：
    公网 HTTPS URL 或 data:{mime};base64,...（网关对 Dify CDN 图片会代为下载转 data URI）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from loguru import logger

if TYPE_CHECKING:
    from salon_gateway.ai.hair_segment import HairSegmentClient


def _key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12]


# 方案里若出现这些词，模型仍常「保长发只改卷/色」——需额外强调几何剪短。
_SHORT_LENGTH_HINTS_ZH = (
    "齐耳", "短发", "耳上", "耳边", "超短", "寸发", "精灵短", "波波", "bob头", "妹妹头",
)
_SHORT_LENGTH_HINTS_EN = ("bob", "pixie", "ear-length", "short haircut", "above-the-ear")


def _short_length_emphasis(style: str) -> str:
    """当用户明确要短时，加强「必须剪短」指令（图生图默认易保留原长发）。"""
    t = style.strip()
    low = t.lower()
    if any(k in t for k in _SHORT_LENGTH_HINTS_ZH):
        hit = True
    elif any(k in low for k in _SHORT_LENGTH_HINTS_EN):
        hit = True
    else:
        hit = False
    if not hit:
        return ""
    return (
        "LENGTH IS NON-NEGOTIABLE: The text requires SHORT hair (e.g. ear-length bob). "
        "You MUST remove visible length below the jaw/ears—do NOT keep shoulder or chest-length hair. "
        "Treat this as a real haircut: mass and silhouette shrink to match the described length. "
        "若写齐耳/短发，成品必须是明显短发轮廓，禁止仅把长发烫卷或改色。"
    )


def build_hairstyle_prompt(style_description: str) -> str:
    """构造万相发型编辑专用 prompt：英文主体 + 明确约束 + 中文补充。"""
    desc = (style_description or "").strip()
    if not desc:
        return (
            "Professional hair salon transformation: modify ONLY the hair (style, color, texture). "
            "Do NOT change face, skin tone, makeup, eyes, nose, mouth, body, clothing, or background. "
            "Result must look like a real salon photo, natural and realistic."
        )
    length_block = _short_length_emphasis(desc)
    if length_block:
        length_block = length_block + " "
    return (
        "Professional hair salon makeover. "
        "TARGET (change ONLY these): hair length, hair shape, hairstyle, hair color, hair texture, bangs. "
        "PRESERVE (do NOT change anything else): face shape, facial features, skin tone, eye color, "
        "makeup, ears, neck, body, clothing, accessories, background, lighting. "
        f"{length_block}"
        f"Hair style to apply: {desc}. "
        "The transformation must be photorealistic, like a professional before-after salon photo. "
        "Hair color transition should be smooth and natural, not artificial or painted-looking. "
        f"发型方案：{desc}。"
    )


_DEFAULT_BASE = "https://dashscope.aliyuncs.com/api/v1"
_GENERATION_PATH = "/services/aigc/image2image/image-synthesis"
_TASK_PATH = "/tasks/{task_id}"

_POLL_INTERVAL_S = 3.0
_MAX_POLLS = 20  # 最多等待约 60 秒


@dataclass(slots=True)
class HairstyleResult:
    preview_url: str
    task_id: str
    used_mask: bool = False  # 是否使用了 SegmentHair mask


def _extract_bytes_from_data_uri(data_uri: str) -> bytes:
    """从 data URI 中解码出原始字节。"""
    _, b64 = data_uri.split(",", 1)
    return base64.standard_b64decode(b64)


class WanxiangClient:
    """通义万相图像编辑（img2img）异步客户端。

    可选传入 HairSegmentClient；有则自动走 description_edit_with_mask 精准模式，
    无则降级到 description_edit 通用模式。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "wanx2.1-imageedit",
        base_url: str = _DEFAULT_BASE,
        hair_segment_client: "HairSegmentClient | None" = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base = base_url.rstrip("/")
        self._segment = hair_segment_client

    async def generate_hairstyle(self, image_url: str, style_prompt: str) -> HairstyleResult:
        """提交发型重绘任务，轮询至完成，返回效果图 URL。

        若 HairSegmentClient 已配置，先做发区分割再精准重绘；否则通用模式。
        """
        prompt = build_hairstyle_prompt(style_prompt)
        mask_uri: str | None = None
        used_mask = False

        if self._segment and image_url.startswith("data:"):
            try:
                image_bytes = _extract_bytes_from_data_uri(image_url)
                mask_uri = await self._segment.get_mask_data_uri(image_bytes)
                used_mask = True
                logger.info("wanxiang: using hair mask (description_edit_with_mask)")
            except Exception as e:
                logger.warning(
                    "wanxiang: hair segmentation failed, falling back to description_edit: {}", e
                )

        task_id = await self._submit(image_url, prompt, mask_uri)
        preview_url = await self._poll(task_id)
        return HairstyleResult(preview_url=preview_url, task_id=task_id, used_mask=used_mask)

    # ------------------------------------------------------------------ private

    async def _submit(
        self,
        image_url: str,
        style_prompt: str,
        mask_uri: str | None = None,
    ) -> str:
        if mask_uri:
            func = "description_edit_with_mask"
            inp = {
                "function": func,
                "prompt": style_prompt,
                "base_image_url": image_url,
                "mask_image_url": mask_uri,
            }
        else:
            func = "description_edit"
            inp = {
                "function": func,
                "prompt": style_prompt,
                "base_image_url": image_url,
            }

        payload = {
            "model": self._model,
            "input": inp,
            "parameters": {"n": 1},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}{_GENERATION_PATH}",
                headers=headers,
                json=payload,
            )
            if not resp.is_success:
                snippet = (resp.text or "")[:2000]
                logger.error(
                    "wanxiang _submit HTTP {} function={} key_sha256_12={} body={}",
                    resp.status_code,
                    func,
                    _key_fingerprint(self._api_key),
                    snippet,
                )
            resp.raise_for_status()
            data = resp.json()

        task_id: str = data["output"]["task_id"]
        logger.info(
            "wanxiang: task submitted task_id={} model={} function={}",
            task_id, self._model, func,
        )
        return task_id

    async def _poll(self, task_id: str) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base}{_TASK_PATH.format(task_id=task_id)}"

        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(1, _MAX_POLLS + 1):
                await asyncio.sleep(_POLL_INTERVAL_S)
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                status: str = data["output"]["task_status"]
                logger.debug(
                    "wanxiang: poll {}/{} task_id={} status={}",
                    attempt, _MAX_POLLS, task_id, status,
                )
                if status == "SUCCEEDED":
                    return data["output"]["results"][0]["url"]
                if status in ("FAILED", "CANCELED"):
                    raise RuntimeError(
                        f"wanxiang task {task_id} ended with status={status}: {data}"
                    )

        raise TimeoutError(
            f"wanxiang task {task_id} did not complete within "
            f"{_MAX_POLLS * _POLL_INTERVAL_S:.0f}s"
        )
