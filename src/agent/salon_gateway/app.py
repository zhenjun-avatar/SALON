from __future__ import annotations

import asyncio
import hashlib
import sys
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from salon_gateway.ai.dify import DifyChatClient
from salon_gateway.ai.furnishing_compose_prompt import build_furnishing_compose_prompt
from salon_gateway.ai.hair_segment import HairSegmentClient
from salon_gateway.ai.home_furnishing_prompt import build_home_furnishing_prompt
from salon_gateway.ai.resolve_image import resolve_base_image_for_dashscope
from salon_gateway.ai.wan27_image import Wan27ImageClient
from salon_gateway.ai.wanxiang import WanxiangClient
from salon_gateway.booking.hairstyle_session import HairstyleSessionStore
from salon_gateway.booking.idempotency import IdempotencyCache
from salon_gateway.booking.session import BookingSessionStore
from salon_gateway.config import SalonGatewaySettings, get_settings
from salon_gateway.furnishing.registry import FurnishingRegistry
from salon_gateway.ingress.wecom import (
    WecomIngress,
    parse_inbound_message,
    parse_sender_recipient,
    render_text_reply,
)
from salon_gateway.models.booking import BookingDraft
from salon_gateway.models.conversation_image import ConversationImageSnap
from salon_gateway.models.furnishing import (
    FurnishingAssetsListResponse,
    FurnishingComposePreviewRequest,
)
from salon_gateway.models.hairstyle import (
    HairstylePreviewRequest,
    HairstylePreviewResponse,
)
from salon_gateway.models.simulate import SimulateWecomTextIn
from salon_gateway.orchestrator.pipeline import SalonPipeline, default_pipeline
from salon_gateway.sink.feishu import FeishuBitableSink
from salon_gateway.sink.null_sink import LoggingSink

_wecom: WecomIngress | None = None
_pipeline: SalonPipeline | None = None
_sink: FeishuBitableSink | LoggingSink | None = None
_idempotency = IdempotencyCache()
_booking_sessions = BookingSessionStore()
_hairstyle_sessions = HairstyleSessionStore()


@lru_cache(maxsize=8)
def _furnishing_registry_cached(path_key: str) -> FurnishingRegistry:
    return FurnishingRegistry(Path(path_key))

_DEFAULT_HAIR_STYLE_PROMPT = (
    "专业美发效果图：在保持人物面部与五官自然一致的前提下，"
    "根据对话中的发型与发色意向进行真实感发型与染发编辑。"
)


def _get_wecom(settings: SalonGatewaySettings) -> WecomIngress:
    global _wecom
    if _wecom is None:
        _wecom = WecomIngress(settings)
    return _wecom


def _get_pipeline(settings: SalonGatewaySettings) -> SalonPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = default_pipeline(settings)
    return _pipeline


def _get_sink(settings: SalonGatewaySettings) -> FeishuBitableSink | LoggingSink:
    global _sink
    if _sink is None:
        if (
            settings.feishu_app_id
            and settings.feishu_app_secret
            and settings.feishu_bitable_app_token
            and settings.feishu_bitable_table_id
        ):
            _sink = FeishuBitableSink(settings)
        else:
            _sink = LoggingSink()
    return _sink


def _normalize_secret(s: str) -> str:
    return (s or "").strip().strip("\ufeff").strip()


def _secret_fingerprint(s: str) -> str:
    """Short SHA-256 prefix for logs (compare locally to .env without pasting the secret)."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _bearer_or_header(
    authorization: str | None,
    x_salon_token: str | None,
) -> str:
    got = _normalize_secret(x_salon_token or "")
    if got:
        return got
    if not authorization:
        return ""
    raw = _normalize_secret(authorization)
    # Any whitespace after scheme (RFC-style); avoids Tab-only gap breaking partition(" ").
    parts = raw.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return _normalize_secret(parts[1])
    return raw


def _auth_internal(
    settings: SalonGatewaySettings,
    authorization: str | None,
    x_salon_token: str | None,
) -> None:
    allowed = settings.internal_booking_tokens_accepted
    if not allowed:
        raise HTTPException(status_code=404, detail="internal booking disabled")
    got = _bearer_or_header(authorization, x_salon_token)
    if got not in allowed:
        lens = sorted({len(x) for x in allowed})
        afps = sorted({_secret_fingerprint(x) for x in allowed})
        logger.error(
            "internal_booking unauthorized: has_authorization_header={} has_x_salon_token={} parsed_token_len={} parsed_token_sha256_12={} accepted_token_lengths={} accepted_token_sha256_12={}",
            bool(_normalize_secret(authorization or "")),
            bool(_normalize_secret(x_salon_token or "")),
            len(got),
            _secret_fingerprint(got),
            lens,
            afps,
        )
        raise HTTPException(status_code=401, detail="unauthorized")


def _auth_simulate(
    settings: SalonGatewaySettings,
    authorization: str | None,
    x_salon_token: str | None,
) -> None:
    expected = _normalize_secret(settings.simulate_token or "")
    if not expected:
        raise HTTPException(status_code=404, detail="simulate disabled")
    if _bearer_or_header(authorization, x_salon_token) != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=(settings.log_level or "INFO").upper())
    yield


app = FastAPI(title="Salon gateway (WeCom -> Dify -> Feishu)", lifespan=_lifespan)

# 家居素材库本地 JPG → 公网 HTTPS（与反代前缀一致，如 https://quizmesh.tech/salon/furnishing-asset-files/…）
_FURNISHING_IMAGES_DIR = Path(__file__).resolve().parent / "data" / "furnishing_images"
if _FURNISHING_IMAGES_DIR.is_dir():
    app.mount(
        "/furnishing-asset-files",
        StaticFiles(directory=str(_FURNISHING_IMAGES_DIR)),
        name="furnishing_asset_files",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/internal/hairstyle-diag")
async def hairstyle_diag(
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> dict[str, object]:
    """诊断：检查 DashScope Key 是否有效（提交一个极小的测试任务）。

    鉴权同 /internal/booking（Bearer 或 X-Salon-Token）。
    返回 key_sha256_12 供与控制台 Key 指纹比对。
    """
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)
    key = (settings.dashscope_api_key or "").strip()
    info: dict[str, object] = {
        "dashscope_key_configured": bool(key),
        "dashscope_key_len": len(key),
        "dashscope_key_sha256_12": hashlib.sha256(key.encode()).hexdigest()[:12] if key else "",
        "wanxiang_model": settings.wanxiang_model,
        "dashscope_base": settings.dashscope_base_url,
    }
    if not key:
        return {**info, "status": "error", "detail": "SALON_DASHSCOPE_API_KEY not set"}

    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://dashscope.aliyuncs.com/api/v1/tasks",
                headers={"Authorization": f"Bearer {key}"},
                params={"page_no": 1, "page_size": 1},
            )
        body_snippet = (r.text or "")[:500]
        return {
            **info,
            "status": "ok" if r.is_success else "error",
            "http_status": r.status_code,
            "body_snippet": body_snippet,
        }
    except Exception as e:
        return {**info, "status": "exception", "detail": str(e)}


@app.get("/webhook/wecom")
async def wecom_verify(
    msg_signature: str = Query(..., alias="msg_signature"),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
) -> PlainTextResponse:
    settings = get_settings()
    try:
        plain = _get_wecom(settings).verify_url(msg_signature, timestamp, nonce, echostr)
    except ValueError:
        raise HTTPException(status_code=403, detail="verify failed") from None
    return PlainTextResponse(content=plain, media_type="text/plain; charset=utf-8")


@app.post("/webhook/wecom")
async def wecom_message(
    request: Request,
    msg_signature: str = Query(..., alias="msg_signature"),
    timestamp: str = Query(...),
    nonce: str = Query(...),
) -> PlainTextResponse:
    settings = get_settings()
    body = await request.body()
    wecom = _get_wecom(settings)
    try:
        inner_xml = wecom.decrypt_body(body, msg_signature, timestamp, nonce)
    except ValueError:
        raise HTTPException(status_code=403, detail="decrypt failed") from None

    msg = parse_inbound_message(inner_xml)
    if msg is None:
        fu, tu = parse_sender_recipient(inner_xml)
        if not fu or not tu:
            return PlainTextResponse(content="success", media_type="text/plain")
        tip = "目前仅支持文字和图片咨询，请直接发送您的问题或照片。"
        reply = render_text_reply(to_user=fu, from_user=tu, content=tip)
        out = wecom.encrypt_reply(reply)
        return PlainTextResponse(content=out, media_type="application/xml; charset=utf-8")

    pipe = _get_pipeline(settings)
    text = await pipe.handle_message(msg)
    reply = render_text_reply(to_user=msg.from_user, from_user=msg.to_user, content=text)
    out = wecom.encrypt_reply(reply)
    return PlainTextResponse(content=out, media_type="application/xml; charset=utf-8")


@app.post("/internal/booking")
async def internal_booking(
    request: Request,
    draft: BookingDraft,
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> dict[str, bool]:
    settings = get_settings()
    raw_auth = request.headers.get("authorization")
    logger.info(
        "internal_booking: raw_Authorization_present={} fastapi_Header_authorization_present={} X-Salon-Token_present={}",
        raw_auth is not None,
        authorization is not None,
        (x_salon_token or "").strip() != "",
    )
    _auth_internal(settings, authorization, x_salon_token)

    # 存储本轮图片 URL，供后续轮次发型效果图生成使用（image_url 非空时才更新）
    cid = (draft.conversation_id or "").strip()
    if cid and draft.image_url:
        _hairstyle_sessions.save(cid, draft.image_url)

    # Session-based accumulation: merge fields from this turn into the
    # conversation session.  Only write to Feishu the first time all required
    # fields (phone + slot_text + store) are present.
    if cid:
        merged, newly_complete = _booking_sessions.merge_and_check(cid, draft)
        if not newly_complete:
            return {"ok": True, "dedup": False, "complete": False}
        draft = merged
    else:
        # No conversation_id: fall back to legacy single-turn idempotency.
        if not _idempotency.should_process(draft.idempotency_key):
            return {"ok": True, "dedup": True, "complete": True}

    sink = _get_sink(settings)
    try:
        await sink.append_booking(draft)
    except Exception as e:
        logger.exception("append_booking failed: {}", e)
        raise HTTPException(status_code=502, detail="sink failed") from e
    return {"ok": True, "dedup": False, "complete": True}


@app.post("/internal/hairstyle-preview")
async def internal_hairstyle_preview(
    body: HairstylePreviewRequest,
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> HairstylePreviewResponse:
    """调用通义万相对用户照片进行发型效果重绘，返回效果图 URL。

    鉴权与 POST /internal/booking 相同（Bearer 或 X-Salon-Token）。

    image_url 可为公网 HTTPS，或 Dify 的 upload.dify.ai 预览链（网关会用
    SALON_DIFY_API_KEY 下载并转为 data URI 再提交万相）。
    生成耗时约 10–30 秒，Dify HTTP 节点 read_timeout 须设置 ≥ 90s。

    SALON_WANXIANG_MODEL=wan2.7-image 或 wan2.7-image-pro 时走万相 2.7 多模态编辑（无 mask）；
    默认 wanx2.1-imageedit 可走 SegmentHair + description_edit_with_mask。
    """
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)

    if not settings.dashscope_api_key:
        raise HTTPException(
            status_code=503,
            detail="hairstyle preview disabled: set SALON_DASHSCOPE_API_KEY to enable",
        )
    style_prompt = (body.style_prompt or "").strip() or _DEFAULT_HAIR_STYLE_PROMPT
    logger.info(
        "hairstyle_preview: conversation_id={} style_prompt={!r}",
        body.conversation_id or "(none)",
        style_prompt[:80],
    )
    # 解析有效图片 URL：当前轮提供则存入 session；否则从 session 取上一轮的
    effective_url = _hairstyle_sessions.resolve(body.conversation_id, body.image_url)
    if not effective_url:
        raise HTTPException(
            status_code=400,
            detail="image_url is required (no image in current or previous turns of this conversation)",
        )

    try:
        base_image = await resolve_base_image_for_dashscope(effective_url, settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    model_id = (settings.wanxiang_model or "").strip()
    use_wan27 = model_id.lower() in ("wan2.7-image", "wan2.7-image-pro")

    try:
        if use_wan27:
            logger.info(
                "hairstyle_preview: Wan 2.7 multimodal edit model={} (no SegmentHair mask)",
                model_id,
            )
            client27 = Wan27ImageClient(
                settings.dashscope_api_key,
                model_id,
                settings.dashscope_base_url,
            )
            result = await client27.generate_hairstyle(base_image, style_prompt)
        else:
            segment_client: HairSegmentClient | None = None
            if settings.aliyun_access_key_id and settings.aliyun_access_key_secret:
                segment_client = HairSegmentClient(
                    settings.aliyun_access_key_id,
                    settings.aliyun_access_key_secret,
                    settings.aliyun_imageseg_region,
                )
                logger.info("hairstyle_preview: SegmentHair enabled (mask mode)")
            else:
                logger.info(
                    "hairstyle_preview: SegmentHair not configured, using description_edit fallback"
                )

            client = WanxiangClient(
                settings.dashscope_api_key,
                model_id,
                settings.dashscope_base_url,
                hair_segment_client=segment_client,
            )
            result = await client.generate_hairstyle(base_image, style_prompt)
    except TimeoutError as e:
        logger.warning("hairstyle_preview: timeout conversation_id={}: {}", body.conversation_id, e)
        raise HTTPException(status_code=504, detail="image generation timed out") from e
    except Exception as e:
        logger.exception("hairstyle_preview: failed conversation_id={}: {}", body.conversation_id, e)
        raise HTTPException(status_code=502, detail="image generation failed") from e

    logger.info(
        "hairstyle_preview: done task_id={} preview_url={}",
        result.task_id,
        result.preview_url,
    )
    return HairstylePreviewResponse(preview_url=result.preview_url, task_id=result.task_id)


@app.post("/internal/conversation-image")
async def internal_conversation_image(
    body: ConversationImageSnap,
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> dict[str, bool]:
    """缓存本轮会话的空间/人物参考图 URL，供后续轮次 HTTP 节点 image_url 为空时补全。

    家居 Chatflow 首轮不经过 booking，需单独调用本接口写入 HairstyleSessionStore。
    鉴权与 POST /internal/booking 相同。
    """
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)
    cid = (body.conversation_id or "").strip()
    url = (body.image_url or "").strip()
    if cid and url:
        _hairstyle_sessions.save(cid, url)
    return {"ok": True}


@app.get("/internal/conversation-room-image")
async def internal_conversation_room_image(
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
    conversation_id: str = Query(
        default="",
        max_length=200,
        description="Dify 会话 ID；返回此前 POST /internal/conversation-image 写入的 room URL（无则空）",
    ),
) -> dict[str, str]:
    """供 Dify Code 前一轮拉取「已缓存的空间图 URL」，便于请求体里带上非空的 room_image_url。"""
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)
    cid = (conversation_id or "").strip()
    url = _hairstyle_sessions.get(cid) if cid else ""
    return {"image_url": url or ""}


@app.post("/internal/home-furnishing-preview")
async def internal_home_furnishing_preview(
    body: HairstylePreviewRequest,
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> HairstylePreviewResponse:
    """根据已确认的软装方案，对房间参考图做「效果示意」重绘（通义万相）。

    请求体与 /internal/hairstyle-preview 相同：image_url、style_prompt（此处为整套方案中文描述）、conversation_id。
    image_url 为空时从会话缓存读取（须先由 POST /internal/conversation-image 或含图的首轮请求写入）。

    推荐使用 wan2.7-image / wan2.7-image-pro；wanx2.1-imageedit 走 description_edit 无 mask。
    鉴权与发型接口相同；Dify HTTP 节点 read_timeout 建议 ≥ 90s。
    """
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)

    if not settings.dashscope_api_key:
        raise HTTPException(
            status_code=503,
            detail="home furnishing preview disabled: set SALON_DASHSCOPE_API_KEY to enable",
        )
    scheme = (body.style_prompt or "").strip()
    if not scheme:
        raise HTTPException(status_code=400, detail="style_prompt (confirmed scheme) is required")

    logger.info(
        "home_furnishing_preview: conversation_id={} scheme_len={}",
        body.conversation_id or "(none)",
        len(scheme),
    )
    effective_url = _hairstyle_sessions.resolve(body.conversation_id, body.image_url)
    if not effective_url:
        raise HTTPException(
            status_code=400,
            detail="image_url is required (no image in current or previous turns of this conversation)",
        )

    try:
        base_image = await resolve_base_image_for_dashscope(effective_url, settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    model_id = (settings.wanxiang_model or "").strip()
    use_wan27 = model_id.lower() in ("wan2.7-image", "wan2.7-image-pro")

    try:
        if use_wan27:
            full_prompt = build_home_furnishing_prompt(scheme)
            client27 = Wan27ImageClient(
                settings.dashscope_api_key,
                model_id,
                settings.dashscope_base_url,
            )
            result = await client27.edit_with_prompt(base_image, full_prompt)
        else:
            client = WanxiangClient(
                settings.dashscope_api_key,
                model_id,
                settings.dashscope_base_url,
                hair_segment_client=None,
            )
            result = await client.generate_interior_preview(base_image, scheme)
    except TimeoutError as e:
        logger.warning("home_furnishing_preview: timeout conversation_id={}: {}", body.conversation_id, e)
        raise HTTPException(status_code=504, detail="image generation timed out") from e
    except Exception as e:
        logger.exception("home_furnishing_preview: failed conversation_id={}: {}", body.conversation_id, e)
        raise HTTPException(status_code=502, detail="image generation failed") from e

    logger.info(
        "home_furnishing_preview: done task_id={} preview_url={}",
        result.task_id,
        result.preview_url,
    )
    return HairstylePreviewResponse(preview_url=result.preview_url, task_id=result.task_id)


@app.get("/internal/furnishing-assets", response_model=FurnishingAssetsListResponse)
async def internal_furnishing_assets(
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
    q: str = Query(default="", description="名称 / 标签 / id 子串（不区分大小写）"),
    category: str = Query(default="", description="category 精确匹配；空=不限"),
    limit: int = Query(default=20, ge=1, le=100),
) -> FurnishingAssetsListResponse:
    """素材库检索（默认 JSON，可换路径见 SALON_FURNISHING_ASSETS_FILE）。鉴权同 internal/booking。"""
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)
    reg = _furnishing_registry_cached(settings.furnishing_assets_path.as_posix())
    items, total = reg.search(q=q, category=category, limit=limit)
    return FurnishingAssetsListResponse(items=items, total=total)


@app.post("/internal/furnishing-compose-preview")
async def internal_furnishing_compose_preview(
    body: FurnishingComposePreviewRequest,
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> HairstylePreviewResponse:
    """空间参考图 + 多张产品参考图 → 万相 2.7 多图编辑效果图。

    图序：第 1 张为空间底图（room_image_url 或会话缓存）；其后为 product_image_urls。
    仅支持 ``wan2.7-image`` / ``wan2.7-image-pro``；read_timeout 建议 ≥ 90s。
    """
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)

    if not settings.dashscope_api_key:
        raise HTTPException(
            status_code=503,
            detail="compose preview disabled: set SALON_DASHSCOPE_API_KEY to enable",
        )
    model_id = (settings.wanxiang_model or "").strip()
    use_wan27 = model_id.lower() in ("wan2.7-image", "wan2.7-image-pro")
    if not use_wan27:
        raise HTTPException(
            status_code=400,
            detail="furnishing compose requires SALON_WANXIANG_MODEL=wan2.7-image or wan2.7-image-pro",
        )

    room_effective = _hairstyle_sessions.resolve(body.conversation_id, body.room_image_url)
    if not room_effective:
        raise HTTPException(
            status_code=400,
            detail=(
                "room_image_url is required (or use POST /internal/conversation-image first "
                "with the same conversation_id)"
            ),
        )

    all_urls = [room_effective, *body.product_image_urls]
    logger.info(
        "furnishing_compose_preview: conversation_id={} n_images={}",
        body.conversation_id or "(none)",
        len(all_urls),
    )
    try:
        refs = await asyncio.gather(
            *[resolve_base_image_for_dashscope(u, settings) for u in all_urls]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    prompt = build_furnishing_compose_prompt(
        n_product_images=len(body.product_image_urls),
        placement_hint=body.placement_hint,
        style_notes=body.style_notes,
    )
    client27 = Wan27ImageClient(
        settings.dashscope_api_key,
        model_id,
        settings.dashscope_base_url,
    )
    try:
        result = await client27.edit_with_images(list(refs), prompt)
    except TimeoutError as e:
        logger.warning("furnishing_compose_preview: timeout: {}", e)
        raise HTTPException(status_code=504, detail="image generation timed out") from e
    except Exception as e:
        logger.exception("furnishing_compose_preview: failed: {}", e)
        raise HTTPException(status_code=502, detail="image generation failed") from e

    logger.info(
        "furnishing_compose_preview: done task_id={} preview_url={}",
        result.task_id,
        result.preview_url,
    )
    return HairstylePreviewResponse(preview_url=result.preview_url, task_id=result.task_id)


@app.get("/internal/booking-options")
async def internal_booking_options(
    request: Request,
    store_q: str = Query(default="", description="门店单选：按名称子串过滤（不区分大小写）"),
    service_q: str = Query(default="", description="项目多选：按名称子串过滤"),
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> dict[str, object]:
    """飞书多维表中「门店」单选、「项目」多选的可选值，供前端/Dify 做下拉与搜索。

    列名来自 SALON_FEISHU_FIELD_MAP_JSON 的 store / service 键对应飞书列名。
    鉴权与 POST /internal/booking 相同（Bearer 或 X-Salon-Token）。
    """
    settings = get_settings()
    logger.info(
        "internal_booking_options: raw_Authorization_present={}",
        request.headers.get("authorization") is not None,
    )
    _auth_internal(settings, authorization, x_salon_token)
    sink = _get_sink(settings)
    if not isinstance(sink, FeishuBitableSink):
        raise HTTPException(status_code=404, detail="feishu not configured")
    try:
        return await sink.booking_field_options(store_search=store_q, service_search=service_q)
    except Exception as e:
        logger.exception("booking_field_options failed: {}", e)
        raise HTTPException(status_code=502, detail="feishu fields failed") from e


@app.post("/simulate/wecom-text")
async def simulate_wecom_text(
    body: SimulateWecomTextIn,
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> dict[str, str]:
    """Same pipeline as WeCom → Dify; supports optional image (image_url / upload_file_id)."""
    settings = get_settings()
    _auth_simulate(settings, authorization, x_salon_token)
    pipe = _get_pipeline(settings)
    reply = await pipe.handle_with_image(
        body.from_user.strip(),
        body.content,
        image_url=body.image_url,
        upload_file_id=body.upload_file_id,
    )
    return {"reply": reply}


@app.post("/simulate/upload-image")
async def simulate_upload_image(
    file: Annotated[UploadFile, File(description="Image file to upload to Dify")],
    from_user: str = Query(default="sim-user-1", description="Must match from_user in subsequent simulate call"),
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> dict[str, str]:
    """Upload an image to Dify /files/upload; returns upload_file_id for use in simulate.

    The upload_file_id is scoped to the Dify user that uploads it.  Pass the same
    from_user here as in the subsequent POST /simulate/wecom-text call, otherwise
    Dify silently drops the file and the LLM never sees the image.
    """
    settings = get_settings()
    _auth_simulate(settings, authorization, x_salon_token)
    # Build the same Dify user string that the pipeline / chat uses.
    prefix = (settings.dify_user_prefix or "wecom").strip()
    dify_user = f"{prefix}:{from_user.strip()}"
    content = await file.read()
    mime = file.content_type or "image/jpeg"
    fname = file.filename or "image.jpg"
    client = DifyChatClient(settings)
    try:
        fid = await client.upload_file_from_bytes(
            user=dify_user,
            filename=fname,
            content=content,
            mime_type=mime,
        )
    except Exception as e:
        logger.exception("upload_file_from_bytes failed: {}", e)
        raise HTTPException(status_code=502, detail="dify upload failed") from e
    return {"upload_file_id": fid, "filename": fname, "dify_user": dify_user}
