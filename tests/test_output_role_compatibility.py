import pytest

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.output_roles import (
    OutputRole,
    output_role_instruction,
    require_scene_replacement_role,
)
from jewelry_on_hand.product_types import ProductType


@pytest.mark.parametrize("role", [OutputRole.HAND_WORN, "lifestyle"])
def test_scene_replacement_role_accepts_only_supported_roles(role):
    assert require_scene_replacement_role(role, stage="prepare-review") in {
        OutputRole.HAND_WORN,
        OutputRole.LIFESTYLE,
    }


@pytest.mark.parametrize("role", [None, OutputRole.HERO, "hero"])
def test_scene_replacement_role_rejects_missing_or_hero(role):
    with pytest.raises(ValueError, match="主图 Skill|hand_worn|lifestyle"):
        require_scene_replacement_role(role, stage="generate")


@pytest.mark.parametrize("role", [OutputRole.HERO, "hero"])
def test_output_role_instruction_rejects_hero(role):
    with pytest.raises(ValueError, match="主图 Skill"):
        output_role_instruction(
            role,
            ProductType.BRACELET,
            DisplayMode.WORN,
        )
