from __future__ import annotations

from enum import Enum


class HandSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return {
            HandSide.LEFT: "左手",
            HandSide.RIGHT: "右手",
            HandSide.UNKNOWN: "未知左右手",
        }[self]


class FingerPosition(str, Enum):
    THUMB = "thumb"
    INDEX = "index"
    MIDDLE = "middle"
    RING = "ring"
    LITTLE = "little"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return {
            FingerPosition.THUMB: "拇指",
            FingerPosition.INDEX: "食指",
            FingerPosition.MIDDLE: "中指",
            FingerPosition.RING: "无名指",
            FingerPosition.LITTLE: "小指",
            FingerPosition.UNKNOWN: "未知手指",
        }[self]


class RingWearStyle(str, Enum):
    FINGER_BASE = "finger_base"
    MIDI = "midi"
    CROSS_FINGER = "cross_finger"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return {
            RingWearStyle.FINGER_BASE: "常规指根佩戴",
            RingWearStyle.MIDI: "指关节佩戴",
            RingWearStyle.CROSS_FINGER: "跨指佩戴",
            RingWearStyle.UNKNOWN: "未知佩戴方式",
        }[self]


__all__ = ["FingerPosition", "HandSide", "RingWearStyle"]
