from jewelry_on_hand.ring_attributes import FingerPosition, HandSide, RingWearStyle


def test_ring_attribute_enums_keep_unknown_explicit():
    assert HandSide("unknown") is HandSide.UNKNOWN
    assert HandSide.LEFT.display_name == "左手"
    assert FingerPosition("ring") is FingerPosition.RING
    assert FingerPosition.RING.display_name == "无名指"
    assert RingWearStyle("finger_base") is RingWearStyle.FINGER_BASE
    assert RingWearStyle.FINGER_BASE.display_name == "常规指根佩戴"
