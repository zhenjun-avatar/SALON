from __future__ import annotations

import secrets
import time
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidSignatureException

from salon_gateway.models.messages import WecomTextInbound

if TYPE_CHECKING:
    from salon_gateway.config import SalonGatewaySettings


def _t(root: ET.Element, tag: str) -> str | None:
    el = root.find(tag)
    if el is None or el.text is None:
        return None
    return el.text


def parse_sender_recipient(xml_str: str) -> tuple[str | None, str | None]:
    root = ET.fromstring(xml_str)
    return _t(root, "FromUserName"), _t(root, "ToUserName")


def parse_inbound_message(xml_str: str) -> WecomTextInbound | None:
    root = ET.fromstring(xml_str)
    if _t(root, "MsgType") != "text":
        return None
    content = _t(root, "Content") or ""
    from_user = _t(root, "FromUserName") or ""
    to_user = _t(root, "ToUserName") or ""
    agent_id = _t(root, "AgentID")
    msg_id = _t(root, "MsgId")
    return WecomTextInbound(
        from_user=from_user,
        to_user=to_user,
        agent_id=agent_id,
        msg_id=msg_id,
        content=content,
    )


def render_text_reply(to_user: str, from_user: str, content: str) -> str:
    """被动回复 text XML。to_user=客户 id，from_user=企业号 id。"""
    ts = str(int(time.time()))
    return (
        f"<xml><ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{ts}</CreateTime>"
        f"<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content></xml>"
    )


class WecomIngress:
    """企微回调加解密（密文 / 明文）。"""

    def __init__(self, settings: SalonGatewaySettings) -> None:
        self._s = settings
        self._crypto: WeChatCrypto | None = None
        if not settings.wecom_plaintext:
            if not (
                settings.wecom_token
                and settings.wecom_encoding_aes_key
                and settings.wecom_corp_id
            ):
                raise ValueError("密文模式需要 SALON_WECOM_TOKEN / ENCODING_AES_KEY / CORP_ID")
            self._crypto = WeChatCrypto(
                settings.wecom_token,
                settings.wecom_encoding_aes_key,
                settings.wecom_corp_id,
            )

    def verify_url(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        echostr: str,
    ) -> str:
        if self._s.wecom_plaintext:
            return echostr
        assert self._crypto is not None
        try:
            plain = self._crypto.check_signature(msg_signature, timestamp, nonce, echostr)
        except InvalidSignatureException as e:
            raise ValueError("invalid signature") from e
        return plain if isinstance(plain, str) else plain.decode("utf-8")

    def decrypt_body(
        self,
        body: bytes,
        msg_signature: str,
        timestamp: str,
        nonce: str,
    ) -> str:
        if self._s.wecom_plaintext:
            return body.decode("utf-8")
        assert self._crypto is not None
        try:
            xml = self._crypto.decrypt_message(body, msg_signature, timestamp, nonce)
        except InvalidSignatureException as e:
            raise ValueError("invalid signature") from e
        return xml if isinstance(xml, str) else xml.decode("utf-8")

    def encrypt_reply(self, inner_xml: str) -> str:
        if self._s.wecom_plaintext:
            return inner_xml
        assert self._crypto is not None
        nonce = secrets.token_hex(8)
        out = self._crypto.encrypt_message(inner_xml, nonce)
        return out if isinstance(out, str) else out.decode("utf-8")
