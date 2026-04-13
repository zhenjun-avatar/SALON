from __future__ import annotations

import hashlib
import sys
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse
from loguru import logger

from salon_gateway.ai.dify import DifyChatClient
from salon_gateway.booking.idempotency import IdempotencyCache
from salon_gateway.booking.session import BookingSessionStore
from salon_gateway.config import SalonGatewaySettings, get_settings
from salon_gateway.ingress.wecom import (
    WecomIngress,
    parse_inbound_message,
    parse_sender_recipient,
    render_text_reply,
)
from salon_gateway.ai.wanxiang import WanxiangClient
from salon_gateway.models.booking import BookingDraft
from salon_gateway.models.hairstyle import HairstylePreviewRequest, HairstylePreviewResponse
from salon_gateway.models.messages import WecomImageInbound, WecomTextInbound
from salon_gateway.models.simulate import SimulateWecomTextIn
from salon_gateway.orchestrator.pipeline import SalonPipeline, default_pipeline
from salon_gateway.sink.feishu import FeishuBitableSink
from salon_gateway.sink.null_sink import LoggingSink

_wecom: WecomIngress | None = None
_pipeline: SalonPipeline | None = None
_sink: FeishuBitableSink | LoggingSink | None = None
_idempotency = IdempotencyCache()
_booking_sessions = BookingSessionStore()


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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

    # Session-based accumulation: merge fields from this turn into the
    # conversation session.  Only write to Feishu the first time all required
    # fields (phone + slot_text + store) are present.
    cid = (draft.conversation_id or "").strip()
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

    注意：image_url 须为 DashScope 可公开拉取的 HTTPS URL。
    若图片来自 Dify 内部存储（local_file），请先转存至 OSS 再传入。
    生成耗时约 10–30 秒，Dify HTTP 节点 read_timeout 须设置 ≥ 90s。
    """
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)

    if not settings.dashscope_api_key:
        raise HTTPException(
            status_code=503,
            detail="hairstyle preview disabled: set SALON_DASHSCOPE_API_KEY to enable",
        )
    if not body.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    logger.info(
        "hairstyle_preview: conversation_id={} style_prompt={!r}",
        body.conversation_id or "(none)",
        body.style_prompt[:80] if body.style_prompt else "",
    )
    client = WanxiangClient(settings.dashscope_api_key, settings.wanxiang_model)
    try:
        result = await client.generate_hairstyle(body.image_url, body.style_prompt)
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
