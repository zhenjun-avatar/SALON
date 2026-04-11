from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_AGENT_ROOT = Path(__file__).resolve().parents[1]


class SalonGatewaySettings(BaseSettings):
    """Loads `SALON_*` from环境变量与 `src/agent/.env`。"""

    model_config = SettingsConfigDict(
        env_prefix="SALON_",
        env_file=str(_AGENT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = Field(default="INFO", description="loguru level")

    # --- 企业微信（自建应用「接收消息」回调）---
    wecom_token: str = Field(default="", description="回调 Token")
    wecom_encoding_aes_key: str = Field(default="", description="EncodingAESKey")
    wecom_corp_id: str = Field(default="", description="企业 CorpId")
    wecom_plaintext: bool = Field(
        default=False,
        description="True=明文模式（仅本地调试；生产请用密文）",
    )

    # --- Dify Chatflow / 对话应用 API ---
    dify_api_base: str = Field(
        default="http://localhost:5001/v1",
        description="Dify API 根，如 https://api.dify.ai/v1",
    )
    dify_api_key: str = Field(default="", description="应用 API Key")
    dify_user_prefix: str = Field(
        default="wecom",
        description="传给 Dify 的 user id 前缀，如 wecom:userid",
    )

    # --- 内部：Dify HTTP 工具回调写预约 ---
    internal_booking_token: str = Field(
        default="",
        description="Bearer / X-Salon-Token；为空则关闭 /internal/booking",
    )

    # --- 模拟企微文本（仅调试；生产勿设置）---
    simulate_token: str = Field(
        default="",
        description="非空则开启 POST /simulate/wecom-text，需 Bearer / X-Salon-Token 与此相同",
    )

    # --- 飞书多维表（可选；未配置则只打日志）---
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bitable_app_token: str = ""
    feishu_bitable_table_id: str = Field(
        default="",
        description="数据表 table_id，仅 tbl 开头一段；勿把 URL 里的 &view= 粘进来",
    )
    # JSON: {"phone":"手机号","store":"门店",...} 将 BookingDraft 字段映射到飞书列名
    feishu_field_map_json: str = "{}"

    @property
    def feishu_field_map(self) -> dict[str, str]:
        raw = self.feishu_field_map_json.strip() or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    @field_validator("feishu_bitable_table_id")
    @classmethod
    def normalize_feishu_table_id(cls, v: str) -> str:
        """Wiki URL 常为 table=tblXXX&view=...，只保留 tbl 段。"""
        v = (v or "").strip()
        if not v:
            return v
        if "&" in v:
            v = v.split("&", 1)[0].strip()
        if "?" in v:
            v = v.split("?", 1)[0].strip()
        if v.lower().startswith("table="):
            v = v[6:].strip()
        return v

    @field_validator("dify_api_base")
    @classmethod
    def normalize_dify_base(cls, v: str) -> str:
        v = (v or "").strip().rstrip("/")
        if not v:
            return "http://localhost:5001/v1"
        return v if v.endswith("/v1") else f"{v}/v1"


@lru_cache
def get_settings() -> SalonGatewaySettings:
    return SalonGatewaySettings()
