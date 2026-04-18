"""万相 2.7 图像编辑（HTTP 同步 multimodal-generation），与 wanx2.1-imageedit 并行。

文档：https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference

单图编辑：messages[0].content 为先 ``image`` 后 ``text``（与官方「图像编辑」示例一致）。
2.7 该接口不按 2.1 的 ``description_edit_with_mask`` 传 mask；发型预览走本后端时不调用 SegmentHair
（``used_mask=False``），避免无效成本。
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import httpx
from loguru import logger
from salon_gateway.ai.wanxiang import HairstyleResult, build_hairstyle_prompt

_DEFAULT_BASE = "https://dashscope.aliyuncs.com/api/v1"
_MULTIMODAL_PATH = "/services/aigc/multimodal-generation/generation"
_TASK_PATH = "/tasks/{task_id}"

_POLL_INTERVAL_S = 3.0
_MAX_POLLS = 40  # 2.7 编辑可能更慢，最多约 120s
_HTTP_TIMEOUT_S = 180.0


def _key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _extract_image_url_from_output(output: dict[str, Any]) -> str | None:
    """从 output 中取首张结果图 URL（同步响应或轮询终态）。"""
    choices = output.get("choices")
    if not choices:
        return None
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        msg = ch.get("message") or {}
        for item in msg.get("content") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "image" and item.get("image"):
                return str(item["image"])
    return None


class Wan27ImageClient:
    """通义万相 2.7（wan2.7-image / wan2.7-image-pro）多模态图像编辑。"""

    def __init__(
        self,
        api_key: str,
        model: str = "wan2.7-image",
        base_url: str = _DEFAULT_BASE,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base = base_url.rstrip("/")

    async def _post_multimodal_user(self, content: list[dict[str, Any]]) -> HairstyleResult:
        if not content:
            raise ValueError("multimodal content must not be empty")
        payload: dict[str, Any] = {
            "model": self._model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "size": "2K",
                "n": 1,
                "watermark": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            resp = await client.post(
                f"{self._base}{_MULTIMODAL_PATH}",
                headers=headers,
                json=payload,
            )
            if not resp.is_success:
                snippet = (resp.text or "")[:2000]
                logger.error(
                    "wan2.7 POST HTTP {} model={} key_sha256_12={} body={}",
                    resp.status_code,
                    self._model,
                    _key_fingerprint(self._api_key),
                    snippet,
                )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code"):
            raise RuntimeError(f"wan2.7 API error: {data}")

        output = data.get("output") or {}
        preview = _extract_image_url_from_output(output)
        if preview:
            rid = str(data.get("request_id") or output.get("task_id") or "")
            logger.info(
                "wan2.7: done model={} request_id/task_id={} preview_url={}",
                self._model,
                rid[:36] if rid else "(none)",
                preview[:80],
            )
            return HairstyleResult(preview_url=preview, task_id=rid or "wan27-sync", used_mask=False)

        task_id = output.get("task_id")
        if task_id and isinstance(task_id, str):
            logger.info("wan2.7: async task_id={} model={}", task_id, self._model)
            preview_url = await self._poll(str(task_id))
            return HairstyleResult(preview_url=preview_url, task_id=str(task_id), used_mask=False)

        raise RuntimeError(f"wan2.7: unexpected response (no image URL): {data}")

    async def edit_with_prompt(self, image_ref: str, prompt: str) -> HairstyleResult:
        """万相 2.7 多模态编辑：单图 + 文本。"""
        return await self._post_multimodal_user([{"image": image_ref}, {"text": prompt}])

    async def edit_with_images(self, image_refs: list[str], prompt: str) -> HairstyleResult:
        """多图 + 文本：图序由调用方约定（如首张空间、后续为产品参考图）。"""
        if not image_refs:
            raise ValueError("image_refs must not be empty")
        parts: list[dict[str, Any]] = [{"image": r} for r in image_refs]
        parts.append({"text": prompt})
        return await self._post_multimodal_user(parts)

    async def generate_hairstyle(self, image_ref: str, style_prompt: str) -> HairstyleResult:
        """基于用户图 + 文本生成发型效果图；不使用 SegmentHair mask。"""
        prompt = build_hairstyle_prompt(style_prompt)
        return await self.edit_with_prompt(image_ref, prompt)

    async def _poll(self, task_id: str) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base}{_TASK_PATH.format(task_id=task_id)}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(1, _MAX_POLLS + 1):
                await asyncio.sleep(_POLL_INTERVAL_S)
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                output = data.get("output") or {}
                status = str(output.get("task_status") or "")
                logger.debug(
                    "wan2.7 poll {}/{} task_id={} status={}",
                    attempt,
                    _MAX_POLLS,
                    task_id,
                    status,
                )
                if status == "SUCCEEDED":
                    preview = _extract_image_url_from_output(output)
                    if preview:
                        return preview
                    raise RuntimeError(f"wan2.7 task {task_id} SUCCEEDED but no image: {data}")
                if status in ("FAILED", "CANCELED"):
                    raise RuntimeError(f"wan2.7 task {task_id} ended with status={status}: {data}")

        raise TimeoutError(
            f"wan2.7 task {task_id} did not complete within "
            f"{_MAX_POLLS * _POLL_INTERVAL_S:.0f}s"
        )
