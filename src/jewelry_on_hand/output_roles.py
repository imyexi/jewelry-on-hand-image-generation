from __future__ import annotations

from enum import Enum

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType


OUTPUT_ROLE_FILE_NAME = "output_role.json"


class OutputRole(str, Enum):
    HERO = "hero"
    HAND_WORN = "hand_worn"
    LIFESTYLE = "lifestyle"

    @property
    def display_name(self) -> str:
        return {
            OutputRole.HERO: "主图",
            OutputRole.HAND_WORN: "手部佩戴图",
            OutputRole.LIFESTYLE: "生活场景图",
        }[self]


SCENE_REPLACEMENT_OUTPUT_ROLES = frozenset(
    {OutputRole.HAND_WORN, OutputRole.LIFESTYLE}
)


def normalize_output_role(value: OutputRole | str | None) -> OutputRole | None:
    if value is None:
        return None
    try:
        return OutputRole(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("output_role 必须是 hero、hand_worn 或 lifestyle") from exc


def require_scene_replacement_role(
    value: OutputRole | str | None,
    *,
    stage: str,
) -> OutputRole:
    role = normalize_output_role(value)
    if role is None:
        raise ValueError(
            f"{stage} 必须显式提供 output_role=hand_worn 或 lifestyle"
        )
    if role not in SCENE_REPLACEMENT_OUTPUT_ROLES:
        raise ValueError(
            f"{stage} 不支持 hero；主图必须交给独立主图 Skill"
        )
    return role


def output_role_instruction(
    output_role: OutputRole | str | None,
    product_type: ProductType,
    display_mode: DisplayMode,
) -> str:
    if output_role is None:
        return ""
    role = require_scene_replacement_role(output_role, stage="Prompt")
    common = "使用深色背景，产品完整清晰，画面不得出现文字、水印、logo 或平台标识。"
    if role is OutputRole.LIFESTYLE:
        return f"输出用途：{role.display_name}。{common} 保留日常生活环境氛围，但不得遮挡产品主体。"
    if product_type in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}:
        if display_mode is not DisplayMode.HAND_HELD:
            raise ValueError("项链的手部佩戴图必须使用 hand_held 展示模式")
        return f"输出用途：{role.display_name}。{common} 手指轻持链条自然垂落，完整展示链条与吊坠。"
    return f"输出用途：{role.display_name}。{common} 产品自然佩戴在手腕或手指根部，接触和阴影真实。"


__all__ = [
    "OUTPUT_ROLE_FILE_NAME",
    "SCENE_REPLACEMENT_OUTPUT_ROLES",
    "OutputRole",
    "normalize_output_role",
    "output_role_instruction",
    "require_scene_replacement_role",
]
