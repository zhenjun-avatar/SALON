from __future__ import annotations

import xml.etree.ElementTree as ET

from salon_gateway.booking.idempotency import IdempotencyCache
from salon_gateway.config import SalonGatewaySettings
from salon_gateway.ingress.wecom import parse_inbound_message, render_text_reply
from salon_gateway.models.booking import BookingDraft


def test_parse_inbound_text() -> None:
    xml = (
        "<xml><MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[你好]]></Content>"
        "<FromUserName><![CDATA[u1]]></FromUserName>"
        "<ToUserName><![CDATA[corp]]></ToUserName>"
        "<MsgId>1</MsgId></xml>"
    )
    m = parse_inbound_message(xml)
    assert m is not None
    assert m.content == "你好"
    assert m.from_user == "u1"
    assert m.to_user == "corp"


def test_parse_non_text() -> None:
    xml = "<xml><MsgType><![CDATA[event]]></MsgType></xml>"
    assert parse_inbound_message(xml) is None


def test_render_roundtrip_xml() -> None:
    s = render_text_reply("u1", "corp", "ok")
    root = ET.fromstring(s)
    assert root.find("MsgType").text == "text"
    assert root.find("Content").text == "ok"


def test_idempotency() -> None:
    c = IdempotencyCache(max_keys=1000)
    assert c.should_process("a") is True
    assert c.should_process("a") is False
    assert c.should_process(None) is True


def test_booking_service_str_to_feishu_multi() -> None:
    d = BookingDraft(service="染发")
    assert d.to_feishu_fields({"service": "项目"}) == {"项目": ["染发"]}


def test_booking_service_list_to_feishu_multi() -> None:
    d = BookingDraft(service=["染发", "烫发"])
    assert d.to_feishu_fields({"service": "项目"}) == {"项目": ["染发", "烫发"]}


def test_feishu_table_id_strips_url_suffix() -> None:
    s = SalonGatewaySettings(
        feishu_bitable_table_id="tbl7kKyFKOd8vYDs&view=vewyQfgtfz",
    )
    assert s.feishu_bitable_table_id == "tbl7kKyFKOd8vYDs"


def test_internal_booking_tokens_pipe_and_quotes() -> None:
    s = SalonGatewaySettings(internal_booking_token="  'a'|b  \n|c ")
    assert s.internal_booking_tokens_accepted == frozenset({"a", "b", "c"})


def test_booking_service_empty_omitted() -> None:
    assert BookingDraft(service="   ").to_feishu_fields({"service": "项目"}) == {}
    assert BookingDraft(service=[]).to_feishu_fields({"service": "项目"}) == {}


def test_booking_session_accumulation() -> None:
    from salon_gateway.booking.session import BookingSessionStore

    store = BookingSessionStore()
    cid = "conv-test-1"

    # turn 1: slot_text + store only
    d1 = BookingDraft(conversation_id=cid, slot_text="周五晚7点", store="东门店", channel="dify")
    merged, newly = store.merge_and_check(cid, d1)
    assert not newly  # phone missing

    # turn 2: phone arrives
    d2 = BookingDraft(conversation_id=cid, phone="18310607536", channel="dify")
    merged, newly = store.merge_and_check(cid, d2)
    assert newly  # all three now present
    assert merged.phone == "18310607536"
    assert merged.store == "东门店"
    assert merged.slot_text == "周五晚7点"

    # turn 3: same conversation — no longer newly_complete
    d3 = BookingDraft(conversation_id=cid, color_summary="黄色", channel="dify")
    _, newly = store.merge_and_check(cid, d3)
    assert not newly  # already was complete
