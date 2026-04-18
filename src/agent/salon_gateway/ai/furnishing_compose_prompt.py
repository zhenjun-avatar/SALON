"""多图家居合成：万相 2.7 messages 文本指令（图序：首张=空间，其后=产品参考）。"""

from __future__ import annotations


def build_furnishing_compose_prompt(
    *,
    n_product_images: int,
    placement_hint: str,
    style_notes: str,
) -> str:
    place = (placement_hint or "").strip()
    notes = (style_notes or "").strip()
    place_block = f" Placement / 摆放偏好: {place}. " if place else " "
    notes_block = f" Extra notes / 补充: {notes}. " if notes else " "

    return (
        "Interior staging from multiple reference images. "
        "IMAGE ORDER: The FIRST image is the room / space base (keep walls, windows, ceiling, "
        "and overall perspective recognizable). The following "
        f"{n_product_images} image(s) are PRODUCT references (sofa, table, etc.): "
        "match their silhouette, material, and color as closely as the scene allows. "
        "Produce ONE photorealistic wide shot of the furnished room. "
        "No text watermarks; no floating furniture; coherent lighting."
        f"{place_block}{notes_block}"
        f"图序说明：第 1 张为空间底图；第 2–{n_product_images + 1} 张为产品参考图，请在空间中合理摆放并统一光影。"
        "效果为 AI 示意，落地以实物与现场测量为准。"
    )
