from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from loguru import logger

from salon_gateway.booking.idempotency import IdempotencyCache
from salon_gateway.config import SalonGatewaySettings, get_settings
from salon_gateway.ingress.wecom import (
    WecomIngress,
    parse_inbound_message,
    parse_sender_recipient,
    render_text_reply,
)
from salon_gateway.models.booking import BookingDraft
from salon_gateway.orchestrator.pipeline import SalonPipeline, default_pipeline
from salon_gateway.sink.feishu import FeishuBitableSink
from salon_gateway.sink.null_sink import LoggingSink

_wecom: WecomIngress | None = None
_pipeline: SalonPipeline | None = None
_sink: FeishuBitableSink | LoggingSink | None = None
_idempotency = IdempotencyCache()


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


def _auth_internal(
    settings: SalonGatewaySettings,
    authorization: str | None,
    x_salon_token: str | None,
) -> None:
    expected = (settings.internal_booking_token or "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="internal booking disabled")
    got = (x_salon_token or "").strip()
    if not got and authorization and authorization.startswith("Bearer "):
        got = authorization.removeprefix("Bearer ").strip()
    if got != expected:
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
        tip = "目前仅支持文字咨询，请直接发送您的问题或需求。"
        reply = render_text_reply(to_user=fu, from_user=tu, content=tip)
        out = wecom.encrypt_reply(reply)
        return PlainTextResponse(content=out, media_type="application/xml; charset=utf-8")

    pipe = _get_pipeline(settings)
    text = await pipe.handle_text(msg)
    reply = render_text_reply(to_user=msg.from_user, from_user=msg.to_user, content=text)
    out = wecom.encrypt_reply(reply)
    return PlainTextResponse(content=out, media_type="application/xml; charset=utf-8")


@app.post("/internal/booking")
async def internal_booking(
    draft: BookingDraft,
    authorization: Annotated[str | None, Header()] = None,
    x_salon_token: Annotated[str | None, Header(alias="X-Salon-Token")] = None,
) -> dict[str, bool]:
    settings = get_settings()
    _auth_internal(settings, authorization, x_salon_token)
    if not _idempotency.should_process(draft.idempotency_key):
        return {"ok": True, "dedup": True}
    sink = _get_sink(settings)
    try:
        await sink.append_booking(draft)
    except Exception as e:
        logger.exception("append_booking failed: {}", e)
        raise HTTPException(status_code=502, detail="sink failed") from e
    return {"ok": True, "dedup": False}
