import pytest

from jewelry_on_hand.output_roles import (
    OutputRole,
    output_role_instruction,
    require_scene_replacement_role,
)


@pytest.mark.parametrize("role", [OutputRole.HAND_WORN, "lifestyle"])
def test_场景替换角色仅接受受支持角色(role):
    assert require_scene_replacement_role(role, stage="prepare-review") in {
        OutputRole.HAND_WORN,
        OutputRole.LIFESTYLE,
    }


@pytest.mark.parametrize("role", [None, OutputRole.HERO, "hero"])
def test_场景替换角色拒绝缺失值或主图角色(role):
    with pytest.raises(ValueError, match="主图 Skill|hand_worn|lifestyle"):
        require_scene_replacement_role(role, stage="generate")


@pytest.mark.parametrize("role", [OutputRole.HERO, "hero"])
def test_输出用途指令拒绝主图角色(role):
    with pytest.raises(ValueError, match="主图 Skill"):
        output_role_instruction(role)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (OutputRole.HAND_WORN, "输出用途：手部佩戴图。"),
        ("lifestyle", "输出用途：生活场景图。"),
    ],
)
def test_输出用途声明保持品类无关(role, expected):
    assert output_role_instruction(role) == expected
