"""家居效果示意图：通义万相图生图 prompt（与发型 prompt 分离）。"""

from __future__ import annotations


def build_home_furnishing_prompt(scheme_description: str) -> str:
    """根据已确认的中文软装方案，生成「空间效果示意」编辑指令。"""
    desc = (scheme_description or "").strip()
    if not desc:
        desc = "现代简约客厅：浅灰布艺沙发、原木茶几、简洁餐桌椅、米白床品风格点缀"
    return (
        "Professional interior staging visualization based on the reference room photo. "
        "Apply the furniture and soft furnishing plan below while keeping the room architecture "
        "(walls, ceiling height, window positions) recognizable unless the plan explicitly requires a layout change. "
        "Photorealistic lighting and materials; coherent color palette; no floating furniture; no text watermarks. "
        "Focus on: sofa, chairs and table, coffee table, bedding look as implied by the plan. "
        f"Plan (Chinese): {desc}. "
        f"软装与家具方案：{desc}。效果为 AI 示意，实际采购与施工以线下为准。"
    )
