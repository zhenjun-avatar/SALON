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
from dataclasses import dataclass

import httpx
from loguru import logger

_BASE = "https://dashscope.aliyuncs.com/api/v1"
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

    def __init__(self, api_key: str, model: str = "wanx2.1-imageedit") -> None:
        self._api_key = api_key
        self._model = model

    async def generate_hairstyle(self, image_url: str, style_prompt: str) -> HairstyleResult:
        """提交发型重绘任务，轮询至完成，返回效果图 URL。"""
        task_id = await self._submit(image_url, style_prompt)
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
                f"{_BASE}{_GENERATION_PATH}",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        task_id: str = data["output"]["task_id"]
        logger.info("wanxiang: task submitted task_id={} model={}", task_id, self._model)
        return task_id

    async def _poll(self, task_id: str) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{_BASE}{_TASK_PATH.format(task_id=task_id)}"

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
