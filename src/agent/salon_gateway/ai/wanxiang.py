"""DashScope 通义万相图像编辑客户端（wanx2.1-imageedit）。

调用流程（异步轮询）：
    1. POST /services/aigc/image2image/image-synthesis  →  获得 task_id
    2. GET  /tasks/{task_id}  轮询，直至 SUCCEEDED / FAILED
    3. 返回 results[0].url

前置要求（base_image_url）：
    公网 HTTPS URL，或 data:{mime};base64,...（网关对 upload.dify.ai 会代为下载并转 data URI）。
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

import httpx
from loguru import logger


def _key_fingerprint(key: str) -> str:
    """SHA-256 前 12 字符，便于与 DashScope 控制台 Key 比对（不暴露原值）。"""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def build_hairstyle_prompt(style_description: str) -> str:
    """将用户确认的发型方案描述包装为万相 description_edit 专用 prompt。

    万相 description_edit 是通用图像编辑，不加约束时容易改动脸部或背景。
    本模板明确约束：只改发型/发色，保留面部特征，确保效果自然真实。
    """
    desc = (style_description or "").strip()
    if not desc:
        return (
            "在保持人物面部五官、肤色、身体比例完全不变的前提下，"
            "对发型和发色进行专业美发造型修改，效果自然真实。"
        )
    return (
        f"请严格按照以下发型方案修改图中人物的头发：{desc}。"
        "要求：①只修改头发部分（发型、发色、发丝质感）；"
        "②保持面部五官、肤色、妆容、衣着和背景完全不变；"
        "③发色过渡自然，发丝细节真实，整体效果符合专业美发造型标准。"
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


class WanxiangClient:
    """通义万相图像编辑（img2img）异步客户端，仅依赖 httpx。"""

    def __init__(
        self,
        api_key: str,
        model: str = "wanx2.1-imageedit",
        base_url: str = _DEFAULT_BASE,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base = base_url.rstrip("/")

    async def generate_hairstyle(self, image_url: str, style_prompt: str) -> HairstyleResult:
        """提交发型重绘任务，轮询至完成，返回效果图 URL。"""
        prompt = build_hairstyle_prompt(style_prompt)
        task_id = await self._submit(image_url, prompt)
        preview_url = await self._poll(task_id)
        return HairstyleResult(preview_url=preview_url, task_id=task_id)

    # ------------------------------------------------------------------ private

    async def _submit(self, image_url: str, style_prompt: str) -> str:
        payload = {
            "model": self._model,
            "input": {
                "function": "description_edit",
                "prompt": style_prompt,
                "base_image_url": image_url,
            },
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
                    "wanxiang _submit HTTP {} key_sha256_12={} body={}",
                    resp.status_code,
                    _key_fingerprint(self._api_key),
                    snippet,
                )
            resp.raise_for_status()
            data = resp.json()

        task_id: str = data["output"]["task_id"]
        logger.info("wanxiang: task submitted task_id={} model={}", task_id, self._model)
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
