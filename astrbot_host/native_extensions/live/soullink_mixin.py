"""Optional Soullink Emotion integration for AstrBot and VTube Studio."""

from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import time
from typing import Any

from astrbot.api import logger


SOULLINK_TAG_PATTERN = re.compile(
    r"<soullink\s*>(.*?)</soullink\s*>",
    re.IGNORECASE | re.DOTALL,
)

DEFAULT_VTS_MAPPING: dict[str, dict[str, Any]] = {
    "poseX": {"ids": ["FaceAngleX"], "scale": 36.0, "min": -24.0, "max": 24.0},
    "poseY": {"ids": ["FaceAngleY"], "scale": 32.0, "min": -18.0, "max": 18.0},
    "poseZ": {"ids": ["FaceAngleZ"], "scale": 34.0, "min": -24.0, "max": 24.0},
    "gazeX": {
        "ids": ["EyeLeftX", "EyeRightX"],
        "scale": 0.9,
        "min": -1.0,
        "max": 1.0,
    },
    "gazeY": {
        "ids": ["EyeLeftY", "EyeRightY"],
        "scale": 0.9,
        "min": -1.0,
        "max": 1.0,
    },
    "eyeOpenLeft": {
        "ids": ["EyeOpenLeft"],
        "scale": 0.526315,
        "min": 0.0,
        "max": 1.0,
    },
    "eyeOpenRight": {
        "ids": ["EyeOpenRight"],
        "scale": 0.526315,
        "min": 0.0,
        "max": 1.0,
    },
    "mouthShape": {
        "ids": ["MouthSmile"],
        "scale": 0.32,
        "offset": 0.78,
        "min": 0.2,
        "max": 1.0,
    },
    "browComposite": {
        "ids": ["Brows"],
        "scale": 0.5,
        "offset": 0.5,
        "min": 0.0,
        "max": 1.0,
    },
}

SOULLINK_COMPOSITE_DEFAULTS: dict[str, float] = {
    "bodyXMix": 0.65,
    "bodyYMix": 0.6,
    "bodyZMix": 0.65,
    "eyeSquintMix": 0.3,
    "mouthNeutral": 0.04,
    "mouthFrownMix": 1.0,
    "browInnerMix": 0.55,
    "browOuterMix": 0.45,
    "browDownMix": 1.0,
}

TYPE_H4_VTS_INPUT_ANCHORS = frozenset(
    {
        "BrowInnerUp",
        "BrowLeftY",
        "BrowRightY",
        "JawOpen",
        "MouthOpen",
        "MouthPucker",
    }
)

TYPE_H4_EXPRESSION_ANCHORS = frozenset(
    {
        "EXP - Angry.exp3.json",
        "EXP - Cry.exp3.json",
        "EXP - Question.exp3.json",
        "EXP - Sparkling.exp3.json",
    }
)

TYPE_H4_VTS_MAPPING: dict[str, Any] = {
    "version": 2,
    "composites": {
        "bodyXMix": 0.82,
        "bodyYMix": 0.76,
        "bodyZMix": 0.82,
        "eyeSquintMix": 0.22,
        "mouthNeutral": 0.03,
        "mouthFrownMix": 0.92,
        "browInnerMix": 0.62,
        "browOuterMix": 0.55,
        "browDownMix": 0.9,
    },
    "rules": [
        {
            "id": "type-h4-pose-x",
            "enabled": True,
            "source": "poseX",
            "target": "FaceAngleX",
            "sourceMin": -0.72,
            "sourceNeutral": 0.0,
            "sourceMax": 0.72,
            "outputMin": -24.5,
            "outputNeutral": 0.0,
            "outputMax": 24.5,
            "curve": 0.86,
            "deadzone": 0.01,
            "smoothing": 0.035,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-pose-y",
            "enabled": True,
            "source": "poseY",
            "target": "FaceAngleY",
            "sourceMin": -0.66,
            "sourceNeutral": 0.0,
            "sourceMax": 0.66,
            "outputMin": -22.0,
            "outputNeutral": 0.0,
            "outputMax": 22.0,
            "curve": 0.9,
            "deadzone": 0.01,
            "smoothing": 0.04,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-pose-z",
            "enabled": True,
            "source": "poseZ",
            "target": "FaceAngleZ",
            "sourceMin": -0.74,
            "sourceNeutral": 0.0,
            "sourceMax": 0.74,
            "outputMin": -28.0,
            "outputNeutral": 0.0,
            "outputMax": 28.0,
            "curve": 0.86,
            "deadzone": 0.01,
            "smoothing": 0.035,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-gaze-x-left",
            "enabled": True,
            "source": "gazeX",
            "target": "EyeLeftX",
            "sourceMin": -1.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": -1.0,
            "outputNeutral": 0.0,
            "outputMax": 1.0,
            "curve": 1.0,
            "deadzone": 0.02,
            "smoothing": 0.03,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-gaze-x-right",
            "enabled": True,
            "source": "gazeX",
            "target": "EyeRightX",
            "sourceMin": -1.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": -1.0,
            "outputNeutral": 0.0,
            "outputMax": 1.0,
            "curve": 1.0,
            "deadzone": 0.02,
            "smoothing": 0.03,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-gaze-y-left",
            "enabled": True,
            "source": "gazeY",
            "target": "EyeLeftY",
            "sourceMin": -1.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": -1.0,
            "outputNeutral": 0.0,
            "outputMax": 1.0,
            "curve": 1.0,
            "deadzone": 0.02,
            "smoothing": 0.03,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-gaze-y-right",
            "enabled": True,
            "source": "gazeY",
            "target": "EyeRightY",
            "sourceMin": -1.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": -1.0,
            "outputNeutral": 0.0,
            "outputMax": 1.0,
            "curve": 1.0,
            "deadzone": 0.02,
            "smoothing": 0.03,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-eye-open-left",
            "enabled": True,
            "source": "eyeOpenLeft",
            "target": "EyeOpenLeft",
            "sourceMin": 0.0,
            "sourceNeutral": 1.0,
            "sourceMax": 1.25,
            "outputMin": 0.0,
            "outputNeutral": 0.9,
            "outputMax": 1.0,
            "curve": 0.92,
            "deadzone": 0.0,
            "smoothing": 0.0,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-eye-open-right",
            "enabled": True,
            "source": "eyeOpenRight",
            "target": "EyeOpenRight",
            "sourceMin": 0.0,
            "sourceNeutral": 1.0,
            "sourceMax": 1.25,
            "outputMin": 0.0,
            "outputNeutral": 0.9,
            "outputMax": 1.0,
            "curve": 0.92,
            "deadzone": 0.0,
            "smoothing": 0.0,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-mouth-smile",
            "enabled": True,
            "source": "mouthShape",
            "target": "MouthSmile",
            "sourceMin": -0.8,
            "sourceNeutral": 0.0,
            "sourceMax": 0.8,
            "outputMin": 0.08,
            "outputNeutral": 0.5,
            "outputMax": 1.0,
            "curve": 0.82,
            "deadzone": 0.015,
            "smoothing": 0.035,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-mouth-open",
            "enabled": True,
            "source": "mouthOpen",
            "target": "MouthOpen",
            "sourceMin": 0.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": 0.0,
            "outputNeutral": 0.02,
            "outputMax": 0.75,
            "curve": 0.86,
            "deadzone": 0.05,
            "smoothing": 0.035,
            "weight": 0.72,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-jaw-open",
            "enabled": True,
            "source": "mouthOpen",
            "target": "JawOpen",
            "sourceMin": 0.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": 0.0,
            "outputNeutral": 0.0,
            "outputMax": 0.55,
            "curve": 0.9,
            "deadzone": 0.08,
            "smoothing": 0.04,
            "weight": 0.5,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-brow-inner",
            "enabled": True,
            "source": "browInnerUp",
            "target": "BrowInnerUp",
            "sourceMin": 0.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": 0.0,
            "outputNeutral": 0.0,
            "outputMax": 0.9,
            "curve": 0.92,
            "deadzone": 0.02,
            "smoothing": 0.045,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-brow-left-y",
            "enabled": True,
            "source": "browComposite",
            "target": "BrowLeftY",
            "sourceMin": -0.85,
            "sourceNeutral": 0.0,
            "sourceMax": 0.85,
            "outputMin": -0.55,
            "outputNeutral": 0.0,
            "outputMax": 0.72,
            "curve": 0.95,
            "deadzone": 0.02,
            "smoothing": 0.045,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-brow-right-y",
            "enabled": True,
            "source": "browComposite",
            "target": "BrowRightY",
            "sourceMin": -0.85,
            "sourceNeutral": 0.0,
            "sourceMax": 0.85,
            "outputMin": -0.55,
            "outputNeutral": 0.0,
            "outputMax": 0.72,
            "curve": 0.95,
            "deadzone": 0.02,
            "smoothing": 0.045,
            "weight": 1.0,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
        {
            "id": "type-h4-mouth-pucker",
            "enabled": True,
            "source": "mouthPucker",
            "target": "MouthPucker",
            "sourceMin": 0.0,
            "sourceNeutral": 0.0,
            "sourceMax": 1.0,
            "outputMin": 0.0,
            "outputNeutral": 0.0,
            "outputMax": 0.52,
            "curve": 0.9,
            "deadzone": 0.08,
            "smoothing": 0.05,
            "weight": 0.76,
            "invert": False,
            "clamp": True,
            "blend": "replace",
        },
    ],
    "emotionAccessories": [
        {
            "id": "type-h4-happy-sparkling",
            "name": "Type-H4 开心星光",
            "enabled": True,
            "emotion": "开心",
            "targetType": "expression",
            "target": "EXP - Sparkling.exp3.json",
            "triggerThreshold": 0.42,
            "releaseThreshold": 0.24,
            "fadeIn": 0.16,
            "fadeOut": 0.3,
            "priority": 34,
            "minHold": 0.45,
            "cooldown": 0.12,
            "debounceIn": 0.04,
            "debounceOut": 0.1,
        },
        {
            "id": "type-h4-excited-exclamation",
            "name": "Type-H4 兴奋感叹",
            "enabled": True,
            "emotion": "兴奋，惊讶",
            "targetType": "expression",
            "target": "EXP - Exclamation.exp3.json",
            "triggerThreshold": 0.48,
            "releaseThreshold": 0.26,
            "fadeIn": 0.12,
            "fadeOut": 0.28,
            "priority": 40,
            "minHold": 0.45,
            "cooldown": 0.1,
            "debounceIn": 0.04,
            "debounceOut": 0.08,
        },
        {
            "id": "type-h4-excited-round-eyes",
            "name": "Type-H4 圆眼高能",
            "enabled": True,
            "emotion": "兴奋，惊讶",
            "targetType": "expression",
            "target": "EXP - Round Eyes.exp3.json",
            "triggerThreshold": 0.56,
            "releaseThreshold": 0.32,
            "fadeIn": 0.14,
            "fadeOut": 0.28,
            "priority": 36,
            "minHold": 0.35,
            "cooldown": 0.1,
            "debounceIn": 0.04,
            "debounceOut": 0.08,
        },
        {
            "id": "type-h4-shy-blush",
            "name": "Type-H4 害羞脸红",
            "enabled": True,
            "emotion": "害羞，喜欢",
            "targetType": "expression",
            "target": "EXP - Face Blush.exp3.json",
            "triggerThreshold": 0.42,
            "releaseThreshold": 0.24,
            "fadeIn": 0.18,
            "fadeOut": 0.38,
            "priority": 32,
            "minHold": 0.55,
            "cooldown": 0.12,
            "debounceIn": 0.05,
            "debounceOut": 0.12,
        },
        {
            "id": "type-h4-love",
            "name": "Type-H4 喜爱爱心",
            "enabled": True,
            "emotion": "喜欢，开心",
            "targetType": "expression",
            "target": "EXP - Love.exp3.json",
            "triggerThreshold": 0.62,
            "releaseThreshold": 0.36,
            "fadeIn": 0.16,
            "fadeOut": 0.32,
            "priority": 38,
            "minHold": 0.5,
            "cooldown": 0.12,
            "debounceIn": 0.05,
            "debounceOut": 0.1,
        },
        {
            "id": "type-h4-curious-question",
            "name": "Type-H4 好奇问号",
            "enabled": True,
            "emotion": "好奇，疑惑",
            "targetType": "expression",
            "target": "EXP - Question.exp3.json",
            "triggerThreshold": 0.42,
            "releaseThreshold": 0.24,
            "fadeIn": 0.14,
            "fadeOut": 0.3,
            "priority": 33,
            "minHold": 0.4,
            "cooldown": 0.12,
            "debounceIn": 0.04,
            "debounceOut": 0.1,
        },
        {
            "id": "type-h4-confused-loading",
            "name": "Type-H4 困惑加载",
            "enabled": True,
            "emotion": "困惑",
            "targetType": "expression",
            "target": "EXP - Loading.exp3.json",
            "triggerThreshold": 0.62,
            "releaseThreshold": 0.34,
            "fadeIn": 0.16,
            "fadeOut": 0.32,
            "priority": 34,
            "minHold": 0.45,
            "cooldown": 0.12,
            "debounceIn": 0.05,
            "debounceOut": 0.1,
        },
        {
            "id": "type-h4-concerned-anxious",
            "name": "Type-H4 担心焦虑",
            "enabled": True,
            "emotion": "担心，焦虑",
            "targetType": "expression",
            "target": "EXP - Anxious.exp3.json",
            "triggerThreshold": 0.45,
            "releaseThreshold": 0.26,
            "fadeIn": 0.18,
            "fadeOut": 0.34,
            "priority": 34,
            "minHold": 0.5,
            "cooldown": 0.12,
            "debounceIn": 0.05,
            "debounceOut": 0.12,
        },
        {
            "id": "type-h4-sad-tear",
            "name": "Type-H4 难过泪光",
            "enabled": True,
            "emotion": "难过",
            "targetType": "expression",
            "target": "EXP - Tear.exp3.json",
            "triggerThreshold": 0.43,
            "releaseThreshold": 0.24,
            "fadeIn": 0.18,
            "fadeOut": 0.38,
            "priority": 34,
            "minHold": 0.55,
            "cooldown": 0.12,
            "debounceIn": 0.05,
            "debounceOut": 0.12,
        },
        {
            "id": "type-h4-sad-cry",
            "name": "Type-H4 大哭",
            "enabled": True,
            "emotion": "伤心",
            "targetType": "expression",
            "target": "EXP - Cry.exp3.json",
            "triggerThreshold": 0.68,
            "releaseThreshold": 0.4,
            "fadeIn": 0.18,
            "fadeOut": 0.42,
            "priority": 38,
            "minHold": 0.6,
            "cooldown": 0.14,
            "debounceIn": 0.06,
            "debounceOut": 0.12,
        },
        {
            "id": "type-h4-anger-angry",
            "name": "Type-H4 生气",
            "enabled": True,
            "emotion": "生气",
            "targetType": "expression",
            "target": "EXP - Angry.exp3.json",
            "triggerThreshold": 0.42,
            "releaseThreshold": 0.24,
            "fadeIn": 0.14,
            "fadeOut": 0.34,
            "priority": 38,
            "minHold": 0.5,
            "cooldown": 0.12,
            "debounceIn": 0.04,
            "debounceOut": 0.1,
        },
        {
            "id": "type-h4-anger-shadow",
            "name": "Type-H4 鼻影压迫",
            "enabled": True,
            "emotion": "生气，愤怒",
            "targetType": "expression",
            "target": "EXP - Nose Shadow.exp3.json",
            "triggerThreshold": 0.56,
            "releaseThreshold": 0.32,
            "fadeIn": 0.14,
            "fadeOut": 0.34,
            "priority": 36,
            "minHold": 0.45,
            "cooldown": 0.12,
            "debounceIn": 0.04,
            "debounceOut": 0.1,
        },
        {
            "id": "type-h4-tired",
            "name": "Type-H4 疲惫",
            "enabled": True,
            "emotion": "疲惫",
            "targetType": "expression",
            "target": "EXP - Tired.exp3.json",
            "triggerThreshold": 0.42,
            "releaseThreshold": 0.24,
            "fadeIn": 0.18,
            "fadeOut": 0.38,
            "priority": 30,
            "minHold": 0.5,
            "cooldown": 0.12,
            "debounceIn": 0.05,
            "debounceOut": 0.12,
        },
    ],
    "sceneGroups": [],
}

SOULLINK_EMOTION_ALIASES: dict[str, str] = {
    "中性": "neutral",
    "默认": "neutral",
    "普通": "neutral",
    "无情绪": "neutral",
    "平静": "calm",
    "冷静": "calm",
    "安静": "calm",
    "开心": "happy",
    "快乐": "happy",
    "高兴": "happy",
    "愉快": "happy",
    "欢乐": "happy",
    "喜悦": "happy",
    "兴奋": "excited",
    "激动": "excited",
    "高能": "excited",
    "惊喜": "excited",
    "惊讶": "excited",
    "震惊": "excited",
    "害羞": "shy",
    "羞涩": "shy",
    "脸红": "shy",
    "好奇": "curious",
    "疑问": "curious",
    "提问": "curious",
    "困惑": "confused",
    "疑惑": "confused",
    "迷茫": "confused",
    "不解": "confused",
    "担心": "concerned",
    "关心": "concerned",
    "关切": "concerned",
    "担忧": "concerned",
    "焦虑": "concerned",
    "紧张": "concerned",
    "难过": "sad",
    "伤心": "sad",
    "悲伤": "sad",
    "委屈": "sad",
    "哭": "sad",
    "生气": "anger",
    "愤怒": "anger",
    "恼火": "anger",
    "炸毛": "anger",
    "喜欢": "affectionate",
    "喜爱": "affectionate",
    "爱心": "affectionate",
    "贴贴": "affectionate",
    "疲惫": "tired",
    "疲劳": "tired",
    "累": "tired",
    "困": "tired",
    "所有": "any",
    "全部": "any",
    "任意": "any",
    "angry": "anger",
    "mad": "anger",
    "furious": "anger",
    "anxious": "concerned",
    "anxiety": "concerned",
    "sadness": "sad",
    "sorrow": "sad",
    "grief": "sad",
    "joy": "happy",
    "joyful": "happy",
    "happiness": "happy",
    "delighted": "happy",
    "love": "affectionate",
    "loving": "affectionate",
    "excitation": "excited",
    "surprised": "excited",
    "surprise": "excited",
    "confusion": "confused",
    "puzzled": "confused",
    "questioning": "curious",
    "curiosity": "curious",
    "concern": "concerned",
    "worried": "concerned",
    "worry": "concerned",
    "shyness": "shy",
    "all": "any",
}


def _source_meta(
    label: str,
    group: str,
    minimum: float,
    neutral: float,
    maximum: float,
) -> dict[str, Any]:
    return {
        "label": label,
        "group": group,
        "min": minimum,
        "neutral": neutral,
        "max": maximum,
    }


SOULLINK_SOURCE_META: dict[str, dict[str, Any]] = {
    "poseX": _source_meta("头部与身体 X", "姿态", -1.0, 0.0, 1.0),
    "poseY": _source_meta("头部与身体 Y", "姿态", -1.0, 0.0, 1.0),
    "poseZ": _source_meta("头部与身体 Z", "姿态", -1.0, 0.0, 1.0),
    "headX": _source_meta("头部 X", "姿态", -1.0, 0.0, 1.0),
    "headY": _source_meta("头部 Y", "姿态", -1.0, 0.0, 1.0),
    "headZ": _source_meta("头部 Z", "姿态", -1.0, 0.0, 1.0),
    "bodyX": _source_meta("身体 X", "姿态", -1.0, 0.0, 1.0),
    "bodyY": _source_meta("身体 Y", "姿态", -1.0, 0.0, 1.0),
    "bodyZ": _source_meta("身体 Z", "姿态", -1.0, 0.0, 1.0),
    "gazeX": _source_meta("视线 X", "视线", -1.0, 0.0, 1.0),
    "gazeY": _source_meta("视线 Y", "视线", -1.0, 0.0, 1.0),
    "eyeOpenLeft": _source_meta("左眼开合", "眼睛", 0.0, 1.0, 1.0),
    "eyeOpenRight": _source_meta("右眼开合", "眼睛", 0.0, 1.0, 1.0),
    "eyeOpen": _source_meta("双眼开合", "眼睛", 0.0, 1.0, 1.0),
    "eyeBlinkL": _source_meta("左眼眨眼", "眼睛", 0.0, 0.0, 1.0),
    "eyeBlinkR": _source_meta("右眼眨眼", "眼睛", 0.0, 0.0, 1.0),
    "eyeSmile": _source_meta("笑眼", "眼睛", 0.0, 0.0, 1.0),
    "eyeSquint": _source_meta("眯眼", "眼睛", 0.0, 0.0, 1.0),
    "mouthShape": _source_meta("综合嘴角", "嘴部", -1.0, 0.0, 1.0),
    "mouthSmile": _source_meta("微笑", "嘴部", 0.0, 0.0, 1.0),
    "mouthFrown": _source_meta("嘴角下压", "嘴部", 0.0, 0.0, 1.0),
    "mouthOpen": _source_meta("张嘴", "嘴部", 0.0, 0.0, 1.0),
    "mouthPucker": _source_meta("嘟嘴", "嘴部", 0.0, 0.0, 1.0),
    "browComposite": _source_meta("综合眉形", "眉毛", -1.0, 0.0, 1.0),
    "browInnerUp": _source_meta("内眉抬起", "眉毛", 0.0, 0.0, 1.0),
    "browOuterUp": _source_meta("外眉抬起", "眉毛", 0.0, 0.0, 1.0),
    "browDown": _source_meta("眉毛下压", "眉毛", 0.0, 0.0, 1.0),
    "blush": _source_meta("脸红", "效果", 0.0, 0.0, 1.0),
    "tear": _source_meta("泪光", "效果", 0.0, 0.0, 1.0),
    "sweat": _source_meta("汗滴", "效果", 0.0, 0.0, 1.0),
    "breath": _source_meta("呼吸", "效果", 0.0, 0.5, 1.0),
    "vadValence": _source_meta("VAD 愉悦度", "情绪", -1.0, 0.0, 1.0),
    "vadArousal": _source_meta("VAD 唤醒度", "情绪", -1.0, 0.0, 1.0),
    "vadDominance": _source_meta("VAD 支配度", "情绪", -1.0, 0.0, 1.0),
    "emotionIntensity": _source_meta("情绪强度", "情绪", 0.0, 0.0, 1.0),
}


class SoullinkMixin:
    """Prompt, lifecycle, and VTS mapping glue for the Node emotion engine."""

    def _is_soullink_enabled(self) -> bool:
        return bool(self.config.get("soullink_enabled", False))

    def _soullink_mode(self) -> str:
        mode = str(self.config.get("soullink_mode") or "emotion").strip().lower()
        return mode if mode in {"emotion", "full"} else "emotion"

    def _soullink_runtime_options(self) -> dict[str, Any]:
        style = str(self.config.get("soullink_motion_style") or "natural").strip().lower()
        if style not in {"natural", "lively", "calm", "shy"}:
            style = "natural"
        return {
            "style": style,
            "fps": max(5, min(30, self._safe_parse_int(self.config.get("soullink_fps"), 20))),
            "parameterGain": max(
                0.4,
                min(5.0, self._safe_parse_float(self.config.get("soullink_parameter_gain"), 1.7)),
            ),
            "bodyMotionGain": max(
                0.0,
                min(4.0, self._safe_parse_float(self.config.get("soullink_body_motion_gain"), 1.6)),
            ),
            "vadDecayRate": max(
                0.0,
                min(1.0, self._safe_parse_float(self.config.get("soullink_vad_decay_rate"), 0.075)),
            ),
        }

    async def _start_soullink_runtime(self) -> bool:
        runtime = getattr(self, "_soullink_runtime", None)
        if not self._is_soullink_enabled() or runtime is None:
            return False
        options = self._soullink_runtime_options()
        self._accept_soullink_frames = True
        runtime.fps = int(options["fps"])
        runtime.node_path = str(self.config.get("soullink_node_path") or "").strip()
        scheduler = getattr(self, "_vts_parameter_scheduler", None)
        if scheduler:
            scheduler.set_source_fps("soullink", int(options["fps"]))
            scheduler.start()
        started = await runtime.start(options)
        if not started:
            self._accept_soullink_frames = False
            if scheduler:
                scheduler.clear_layer("soullink")
        return started

    async def _stop_soullink_runtime(self) -> None:
        self._accept_soullink_frames = False
        scheduler = getattr(self, "_vts_parameter_scheduler", None)
        runtime = getattr(self, "_soullink_runtime", None)
        await self._stop_soullink_rule_signal_refresh()
        if runtime:
            await runtime.stop()
        await self._deactivate_soullink_expressions()
        if scheduler:
            scheduler.clear_layer("soullink")

    async def _sync_soullink_runtime(self) -> bool:
        if not self._is_soullink_enabled():
            await self._stop_soullink_runtime()
            return False
        runtime = getattr(self, "_soullink_runtime", None)
        configured_node = str(self.config.get("soullink_node_path") or "").strip()
        if runtime and runtime.running and configured_node != runtime.node_path:
            await runtime.stop()
            runtime.node_path = configured_node
        if runtime and runtime.running:
            options = self._soullink_runtime_options()
            scheduler = getattr(self, "_vts_parameter_scheduler", None)
            if scheduler:
                scheduler.set_source_fps("soullink", int(options["fps"]))
            return await runtime.configure(**options)
        return await self._start_soullink_runtime()

    def _inject_soullink_prompt_instruction(self, req: Any) -> None:
        from ..request_context import set_system_instruction

        if not self._is_soullink_enabled() or not bool(
            self.config.get("soullink_prompt_intent_enabled", True)
        ):
            set_system_instruction(req, "soullink")
            return
        style = self._soullink_runtime_options()["style"]
        lively_hint = ""
        if style == "lively":
            lively_hint = (
                "当前动作风格为 lively，表示允许更鲜明的表演，不要求每句都兴奋。确有开心、玩梗、感谢或好奇时可选 happy、excited、curious 等贴切情绪；普通接话、轻吐槽和短回应仍按角色实际语气，可以保持轻松或 neutral。"
                "intensity 与 VAD 按本次回复的真实情绪和强度填写，不固定抬高 arousal，也不为触发动作改变正文。\n"
            )
        set_system_instruction(req, "soullink", (
            "\n\n## Soullink 实时表演\n"
            "在回复末尾附加一行 Soullink 情绪意图，让 Live2D 动作贴合本次语气。"
            "这是程序消费的控制信息，不向用户解释。每次最多一条；平淡或无法判断时使用 neutral。\n"
            "严格格式：<soullink>{\"emotion\":\"happy\",\"variant\":\"bright_smile\","
            "\"intensity\":0.75,\"vad\":{\"valence\":0.7,\"arousal\":0.45,\"dominance\":0.3}}</soullink>\n"
            "emotion 可使用中文标签（中性、开心、兴奋、害羞、好奇、困惑、担心、伤心、生气）"
            "或稳定短词 neutral、happy、excited、shy、curious、confused、concerned、sad、anger；"
            "模型表情需要时也可使用 affectionate、surprised、anxiety、tired；"
            "确有需要时才使用其他短词；intensity 为 0 到 1；VAD 三轴为 -1 到 1。"
            f"{lively_hint}"
            "填写角色在本次回复中实际表现的情绪，不要把用户的情绪、引用内容或被否定的词当成角色情绪；"
            "例如安慰“别难过”“不用焦虑”“别生气”时，不应仅因这些词输出 sad、anxiety 或 anger。"
            "不要为了触发表演改变正文，不要输出 Markdown 代码块，也不要编造多条控制信息。\n"
        ))

    def _parse_soullink_intent(self, text: str) -> tuple[dict[str, Any] | None, str]:
        match = SOULLINK_TAG_PATTERN.search(text or "")
        cleaned = SOULLINK_TAG_PATTERN.sub("", text or "")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if not match:
            return None, cleaned
        try:
            payload = json.loads(match.group(1).strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.debug("[Soullink] 模型输出的情绪意图不是有效 JSON，改用本地文本分类")
            return None, cleaned
        if not isinstance(payload, dict):
            return None, cleaned
        emotion = self._normalize_soullink_emotion(payload.get("emotion"))[:40]
        if not emotion:
            return None, cleaned
        vad = payload.get("vad") if isinstance(payload.get("vad"), dict) else {}
        return (
            {
                "emotion": emotion,
                "variant": str(payload.get("variant") or "").strip()[:60],
                "intensity": self._clamp_number(payload.get("intensity"), 0.0, 1.0, 0.7),
                "vad": {
                    "valence": self._clamp_number(vad.get("valence"), -1.0, 1.0, 0.0),
                    "arousal": self._clamp_number(vad.get("arousal"), -1.0, 1.0, 0.0),
                    "dominance": self._clamp_number(vad.get("dominance"), -1.0, 1.0, 0.0),
                },
                "contextTags": ["astrbot_llm", "prompt_intent"],
                "sourceMessage": cleaned[:1000],
            },
            cleaned,
        )

    def _handle_soullink_response(self, text: str) -> str:
        if not self._is_soullink_enabled():
            return text
        intent, cleaned = self._parse_soullink_intent(text)
        runtime = getattr(self, "_soullink_runtime", None)
        if not runtime or not runtime.running:
            return cleaned

        async def react() -> None:
            if intent:
                await runtime.trigger(intent)
            elif self._soullink_mode() == "full" or bool(
                self.config.get("soullink_local_fallback_enabled", False)
            ):
                await runtime.react_to_text(cleaned)

        self._create_soullink_task(react())
        return cleaned

    def _create_soullink_task(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        tasks = getattr(self, "_soullink_tasks", None)
        if isinstance(tasks, set):
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def _test_soullink_intent(self, intent: dict[str, Any]) -> bool:
        if not self._is_soullink_enabled():
            return False
        runtime = getattr(self, "_soullink_runtime", None)
        if not runtime or not runtime.running:
            if not await self._start_soullink_runtime():
                return False
        return await runtime.trigger(intent)

    def _on_soullink_frame(self, snapshot: dict[str, Any]) -> None:
        if not self._is_soullink_enabled() or not getattr(
            self, "_accept_soullink_frames", True
        ):
            return
        parameters = self._map_soullink_frame_to_vts(snapshot)
        self._soullink_last_vts_parameters = parameters
        self._queue_soullink_expression_sync()
        scheduler = getattr(self, "_vts_parameter_scheduler", None)
        if scheduler:
            if parameters:
                scheduler.set_layer("soullink", parameters, ttl=1.0)
            else:
                scheduler.clear_layer("soullink")

    def _refresh_soullink_mapping_outputs(self) -> bool:
        """Re-evaluate a mapping edit immediately from the latest runtime frame."""
        if not self._is_soullink_enabled() or not getattr(
            self, "_accept_soullink_frames", True
        ):
            return False
        runtime = getattr(self, "_soullink_runtime", None)
        snapshot = getattr(runtime, "last_snapshot", None)
        if not isinstance(snapshot, dict) or not snapshot:
            return False
        self._on_soullink_frame(snapshot)
        return True

    def _map_soullink_frame_to_vts(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        raw_facs = snapshot.get("facs") if isinstance(snapshot.get("facs"), dict) else {}
        smoothed = (
            snapshot.get("live2dParams")
            if isinstance(snapshot.get("live2dParams"), dict)
            else {}
        )
        facs = smoothed or raw_facs
        mapping = self._soullink_vts_mapping()
        self._queue_soullink_rule_signal_refresh(mapping)
        composites = mapping.get("composites") if isinstance(mapping.get("composites"), dict) else {}
        values = dict(raw_facs)
        values.update(facs)
        values["poseX"] = self._number(values.get("headX")) + self._number(
            values.get("bodyX")
        ) * self._number(composites.get("bodyXMix"), 0.65)
        values["poseY"] = self._number(values.get("headY")) + self._number(
            values.get("bodyY")
        ) * self._number(composites.get("bodyYMix"), 0.6)
        values["poseZ"] = self._number(values.get("headZ")) + self._number(
            values.get("bodyZ")
        ) * self._number(composites.get("bodyZMix"), 0.65)
        eye_open = self._number(facs.get("eyeOpen"), 1.0)
        eye_squint = self._number(facs.get("eyeSquint"))
        values["eyeOpenLeft"] = max(
            0.0,
            eye_open * (1.0 - self._number(facs.get("eyeBlinkL")))
            - eye_squint * self._number(composites.get("eyeSquintMix"), 0.3),
        )
        values["eyeOpenRight"] = max(
            0.0,
            eye_open * (1.0 - self._number(facs.get("eyeBlinkR")))
            - eye_squint * self._number(composites.get("eyeSquintMix"), 0.3),
        )
        values["mouthShape"] = (
            self._number(facs.get("mouthSmile"))
            - self._number(composites.get("mouthNeutral"), 0.04)
            - self._number(facs.get("mouthFrown"))
            * self._number(composites.get("mouthFrownMix"), 1.0)
        )
        values["browComposite"] = (
            self._number(facs.get("browInnerUp"))
            * self._number(composites.get("browInnerMix"), 0.55)
            + self._number(facs.get("browOuterUp"))
            * self._number(composites.get("browOuterMix"), 0.45)
            - self._number(facs.get("browDown"))
            * self._number(composites.get("browDownMix"), 1.0)
        )
        vad = snapshot.get("vad") if isinstance(snapshot.get("vad"), dict) else {}
        current_vad = vad.get("current") if isinstance(vad.get("current"), dict) else {}
        values["vadValence"] = self._number(current_vad.get("valence"))
        values["vadArousal"] = self._number(current_vad.get("arousal"))
        values["vadDominance"] = self._number(current_vad.get("dominance"))
        values["emotionIntensity"] = self._number(vad.get("intensity"))

        outputs: dict[str, dict[str, Any]] = {}
        frame_time = self._number(snapshot.get("time"), time.monotonic())
        rules = (
            mapping.get("rules")
            if facs and isinstance(mapping.get("rules"), list)
            else []
        )
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or not bool(rule.get("enabled", True)):
                continue
            source = str(rule.get("source") or "").strip()
            target = str(rule.get("target") or "").strip()
            if source not in values or not target:
                continue
            valid_inputs = getattr(self, "_soullink_valid_vts_inputs", None)
            if isinstance(valid_inputs, set) and valid_inputs and target not in valid_inputs:
                continue
            value = self._transform_soullink_mapping_value(
                self._number(values.get(source)), rule
            )
            smoothing = max(0.0, self._number(rule.get("smoothing")))
            if smoothing > 0.0:
                value = self._smooth_soullink_mapping_value(
                    f"{rule.get('id') or index}:{target}",
                    value,
                    smoothing,
                    frame_time,
                )
            blend = str(rule.get("blend") or "replace").lower()
            previous = outputs.get(target)
            if previous and blend == "add":
                value = previous["value"] + value - self._number(
                    rule.get("outputNeutral")
                )
            elif previous and blend == "max":
                value = max(previous["value"], value)
            elif previous and blend == "min":
                value = min(previous["value"], value)
            outputs[target] = {
                "id": target,
                "value": value,
                "weight": self._clamp_number(rule.get("weight"), 0.0, 1.0, 1.0),
            }
        accessory_parameters, accessory_expressions = self._soullink_accessory_outputs(
            mapping,
            snapshot,
            frame_time,
        )
        scene_parameters, scene_expressions = self._soullink_scene_outputs(
            mapping,
            snapshot,
            frame_time,
        )
        for target, candidate in accessory_parameters.items():
            self._merge_soullink_output(outputs, target, candidate)
        for target, candidate in scene_parameters.items():
            self._merge_soullink_output(outputs, target, candidate)
        desired_expressions: dict[str, dict[str, Any]] = {}
        for target, candidate in accessory_expressions.items():
            self._merge_soullink_expression_candidate(
                desired_expressions,
                target,
                candidate,
            )
        for target, candidate in scene_expressions.items():
            self._merge_soullink_expression_candidate(
                desired_expressions,
                target,
                candidate,
            )
        self._set_soullink_desired_expressions(desired_expressions)
        return [
            {
                "id": item["id"],
                "value": item["value"],
                "weight": item.get("weight", 1.0),
            }
            for item in outputs.values()
        ]

    def _soullink_accessory_outputs(
        self,
        mapping: dict[str, Any],
        snapshot: dict[str, Any],
        frame_time: float,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        rules = (
            mapping.get("emotionAccessories")
            if isinstance(mapping.get("emotionAccessories"), list)
            else []
        )
        states = getattr(self, "_soullink_accessory_state", None)
        if not isinstance(states, dict):
            states = {}
            self._soullink_accessory_state = states
        parameter_candidates: dict[str, list[dict[str, Any]]] = {}
        expression_candidates: dict[str, list[dict[str, Any]]] = {}
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or not bool(rule.get("enabled", True)):
                continue
            target = str(rule.get("target") or "").strip()
            if not target:
                continue
            target_type = self._soullink_target_type(rule.get("targetType"), target)
            if not self._soullink_target_is_available(target_type, target):
                continue
            rule_id = str(rule.get("id") or f"accessory-{index + 1}")
            state = states.setdefault(rule_id, {})
            active, mix = self._update_soullink_accessory_state(
                state,
                rule,
                snapshot,
                frame_time,
            )
            priority = int(self._finite_number(rule.get("priority"), 0.0))
            common = {
                "active": active,
                "priority": priority,
                "order": index,
                "source": rule_id,
            }
            if target_type == "expression":
                expression_candidates.setdefault(target, []).append(
                    {
                        **common,
                        "fade": self._finite_number(
                            rule.get("fadeIn" if active else "fadeOut"),
                            0.25,
                        ),
                        "force": False,
                    }
                )
                continue
            off_value = self._finite_number(rule.get("offValue"), 0.0)
            on_value = self._finite_number(rule.get("onValue"), 1.0)
            parameter_candidates.setdefault(target, []).append(
                {
                    **common,
                    "value": off_value + (on_value - off_value) * mix,
                    "weight": 1.0,
                }
            )

        parameters: dict[str, dict[str, Any]] = {}
        expressions: dict[str, dict[str, Any]] = {}
        for target, candidates in parameter_candidates.items():
            active = [item for item in candidates if item["active"]]
            pool = active or candidates
            parameters[target] = max(
                pool,
                key=lambda item: (item["priority"], item["order"]),
            )
        for target, candidates in expression_candidates.items():
            active = [item for item in candidates if item["active"]]
            pool = active or candidates
            expressions[target] = max(
                pool,
                key=lambda item: (item["priority"], item["order"]),
            )
        return parameters, expressions

    def _update_soullink_accessory_state(
        self,
        state: dict[str, Any],
        rule: dict[str, Any],
        snapshot: dict[str, Any],
        frame_time: float,
    ) -> tuple[bool, float]:
        stable = bool(state.get("active", False))
        matched = self._soullink_emotion_matches(rule.get("emotion"), snapshot)
        vad = snapshot.get("vad") if isinstance(snapshot.get("vad"), dict) else {}
        intent = snapshot.get("intent") if isinstance(snapshot.get("intent"), dict) else {}
        intensity = max(
            0.0,
            min(1.0, self._number(vad.get("intensity"), self._number(intent.get("intensity")))),
        )
        threshold_key = "releaseThreshold" if stable else "triggerThreshold"
        threshold_default = 0.28 if stable else 0.45
        threshold = self._clamp_number(
            rule.get(threshold_key),
            0.0,
            1.0,
            threshold_default,
        )
        wanted = bool(matched and intensity >= threshold)
        active_since = self._number(state.get("activeSince"), frame_time)
        if stable and not wanted:
            min_hold = max(0.0, self._number(rule.get("minHold"), 0.25))
            if frame_time >= active_since and frame_time - active_since < min_hold:
                wanted = True
        if not stable and wanted and frame_time < self._number(state.get("cooldownUntil")):
            wanted = False

        pending = state.get("pending")
        pending_since = state.get("pendingSince")
        if wanted == stable:
            state["pending"] = None
            state["pendingSince"] = None
        else:
            if pending is not wanted or pending_since is None or frame_time < self._number(pending_since):
                state["pending"] = wanted
                state["pendingSince"] = frame_time
                pending_since = frame_time
            debounce_key = "debounceIn" if wanted else "debounceOut"
            debounce_default = 0.08 if wanted else 0.12
            debounce = max(0.0, self._number(rule.get(debounce_key), debounce_default))
            if debounce <= 0.0 or frame_time - self._number(pending_since, frame_time) >= debounce:
                stable = wanted
                state["active"] = stable
                state["pending"] = None
                state["pendingSince"] = None
                if stable:
                    state["activeSince"] = frame_time
                else:
                    cooldown = max(0.0, self._number(rule.get("cooldown"), 0.1))
                    state["cooldownUntil"] = frame_time + cooldown

        last_time = state.get("lastTime")
        delta = 0.0 if last_time is None else max(0.0, frame_time - self._number(last_time, frame_time))
        mix = max(0.0, min(1.0, self._number(state.get("mix"))))
        target_mix = 1.0 if stable else 0.0
        fade_key = "fadeIn" if target_mix > mix else "fadeOut"
        fade = max(0.0, self._number(rule.get(fade_key), 0.25))
        if fade <= 0.0:
            mix = target_mix
        elif delta > 0.0:
            step = delta / fade
            mix = min(target_mix, mix + step) if target_mix > mix else max(target_mix, mix - step)
        state.update(
            {
                "active": stable,
                "mix": mix,
                "lastTime": frame_time,
                "matched": matched,
                "intensity": intensity,
            }
        )
        return stable, mix

    def _soullink_emotion_matches(self, configured: Any, snapshot: dict[str, Any]) -> bool:
        requested = {
            self._normalize_soullink_emotion(item)
            for item in re.split(r"[,，、;；|/\\\s]+", str(configured or "any"))
            if str(item).strip()
        }
        if not requested or requested.intersection({"any", "*", "all"}):
            return True
        vad = snapshot.get("vad") if isinstance(snapshot.get("vad"), dict) else {}
        intent = snapshot.get("intent") if isinstance(snapshot.get("intent"), dict) else {}
        candidates = {
            self._normalize_soullink_emotion(vad.get("dominantEmotion")),
        }
        # The engine may keep the state label at IDLE while an intent is
        # decaying.  Intensity hysteresis below prevents stale intents from
        # re-triggering a rule, so keep the intent itself as a candidate.
        candidates.update(
            {
                self._normalize_soullink_emotion(intent.get("emotion")),
                self._normalize_soullink_emotion(intent.get("naturalEmotion")),
            }
        )
        candidates.discard("")
        return bool(requested.intersection(candidates))

    @staticmethod
    def _normalize_soullink_emotion(value: Any) -> str:
        name = str(value or "").strip().lower().replace(" ", "_")
        return SOULLINK_EMOTION_ALIASES.get(name, name)

    def _soullink_scene_outputs(
        self,
        mapping: dict[str, Any],
        snapshot: dict[str, Any] | None = None,
        frame_time: float | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        groups = mapping.get("sceneGroups") if isinstance(mapping.get("sceneGroups"), list) else []
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        if frame_time is None:
            frame_time = self._number(snapshot.get("time"), time.monotonic())
        signals = self._soullink_rule_signals_for_frame(snapshot)
        preview_active = mapping is getattr(self, "_soullink_mapping_preview", None)
        parameters: dict[str, dict[str, Any]] = {}
        expressions: dict[str, dict[str, Any]] = {}
        group_states = getattr(self, "_soullink_scene_group_state", None)
        if not isinstance(group_states, dict):
            group_states = {}
            self._soullink_scene_group_state = group_states
        seen_group_ids: set[str] = set()
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict) or not bool(group.get("enabled", True)):
                continue
            group_id = str(group.get("id") or f"scene-group-{group_index + 1}")
            seen_group_ids.add(group_id)
            scenes = group.get("scenes") if isinstance(group.get("scenes"), list) else []
            state = group_states.get(group_id)
            if not isinstance(state, dict):
                state = {}
                group_states[group_id] = state
            selected_id = self._resolve_soullink_scene_selection(
                group,
                scenes,
                state,
                snapshot,
                signals,
                frame_time,
                preview_active=preview_active,
            )
            selected = next(
                (item for item in scenes if isinstance(item, dict) and str(item.get("id")) == selected_id),
                None,
            )
            exclusive = bool(group.get("exclusive", True))
            priority = int(self._finite_number(group.get("priority"), 100.0))
            fade = max(0.0, self._number(group.get("fadeTime"), 0.35))
            all_values = [
                value
                for scene in scenes
                if isinstance(scene, dict)
                for value in (scene.get("values") if isinstance(scene.get("values"), list) else [])
                if isinstance(value, dict)
            ]
            expression_targets = tuple(
                sorted(
                    {
                        str(value.get("target") or "").strip()
                        for value in all_values
                        if str(value.get("target") or "").strip()
                        and self._soullink_target_type(
                            value.get("targetType"),
                            str(value.get("target") or "").strip(),
                        )
                        == "expression"
                    }
                )
            )
            group_signature = (selected_id, exclusive, expression_targets)
            force_resync = state.get("outputSignature") != group_signature
            state["outputSignature"] = group_signature
            if exclusive:
                for value_index, value in enumerate(all_values):
                    target = str(value.get("target") or "").strip()
                    if not target:
                        continue
                    target_type = self._soullink_target_type(value.get("targetType"), target)
                    if not self._soullink_target_is_available(target_type, target):
                        continue
                    candidate = {
                        "active": False,
                        "priority": priority,
                        "order": group_index * 10000 + value_index,
                        "source": group_id,
                    }
                    if target_type == "expression":
                        candidate.update({"fade": fade, "force": force_resync})
                        self._merge_soullink_expression_candidate(expressions, target, candidate)
                    else:
                        candidate.update(
                            {
                                "value": self._finite_number(value.get("offValue"), 0.0),
                                "weight": 1.0,
                            }
                        )
                        self._merge_soullink_output(parameters, target, candidate)
            selected_values = (
                selected.get("values")
                if isinstance(selected, dict) and isinstance(selected.get("values"), list)
                else []
            )
            for value_index, value in enumerate(selected_values):
                if not isinstance(value, dict):
                    continue
                target = str(value.get("target") or "").strip()
                if not target:
                    continue
                target_type = self._soullink_target_type(value.get("targetType"), target)
                if not self._soullink_target_is_available(target_type, target):
                    continue
                candidate = {
                    "active": self._mapping_bool(value.get("active"), True),
                    "priority": priority,
                    "order": group_index * 10000 + 5000 + value_index,
                    "source": group_id,
                }
                if target_type == "expression":
                    candidate.update({"fade": fade, "force": force_resync})
                    self._merge_soullink_expression_candidate(expressions, target, candidate)
                else:
                    candidate.update(
                        {
                            "value": self._finite_number(value.get("value"), 1.0),
                            "weight": 1.0,
                        }
                    )
                    self._merge_soullink_output(parameters, target, candidate)
        for group_id in set(group_states).difference(seen_group_ids):
            group_states.pop(group_id, None)
        return parameters, expressions

    def _resolve_soullink_scene_selection(
        self,
        group: dict[str, Any],
        scenes: list[Any],
        state: dict[str, Any],
        snapshot: dict[str, Any],
        signals: dict[str, Any],
        frame_time: float,
        *,
        preview_active: bool,
    ) -> str:
        scene_by_id = {
            str(scene.get("id")): scene
            for scene in scenes
            if isinstance(scene, dict) and str(scene.get("id") or "")
        }
        default_id = str(group.get("defaultScene") or "")
        if default_id not in scene_by_id:
            default_id = ""
        selection_mode = str(group.get("selectionMode") or "manual").lower()
        if selection_mode not in {"manual", "rules"}:
            selection_mode = "manual"

        # activeScene is an operator choice, not an automatic rule result.  A
        # mapping preview may still override rules so its Preview button stays
        # deterministic without persisting that choice.
        if selection_mode == "manual" or preview_active:
            selected_id = str(
                (
                    group.get("activeScene")
                    if "activeScene" in group
                    else default_id
                )
                or ""
            )
            if selected_id and selected_id not in scene_by_id:
                selected_id = default_id
            if state.get("selected") != selected_id:
                state["selected"] = selected_id
                state["selectedSince"] = frame_time
            state["candidate"] = None
            state["candidateSince"] = None
            return selected_id

        matched: list[tuple[int, int, str]] = []
        for scene_index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("id") or "")
            if not scene_id or not self._soullink_scene_conditions_match(
                scene,
                snapshot,
                signals,
            ):
                continue
            matched.append(
                (
                    int(self._finite_number(scene.get("priority"), 0.0)),
                    scene_index,
                    scene_id,
                )
            )
        desired_id = default_id
        if matched:
            highest_priority = max(item[0] for item in matched)
            top_matches = [item for item in matched if item[0] == highest_priority]
            current_id = str(state.get("selected") or "")
            current_match = next(
                (item for item in top_matches if item[2] == current_id),
                None,
            )
            # Keep an equally ranked current scene stable; otherwise use the
            # first configured rule as the deterministic tie-breaker.
            desired_id = (current_match or min(top_matches, key=lambda item: item[1]))[2]
        return self._stabilize_soullink_scene_selection(
            desired_id,
            default_id,
            scene_by_id,
            state,
            frame_time,
        )

    def _stabilize_soullink_scene_selection(
        self,
        desired_id: str,
        default_id: str,
        scene_by_id: dict[str, dict[str, Any]],
        state: dict[str, Any],
        frame_time: float,
    ) -> str:
        current_value = state.get("selected")
        first_frame = current_value is None
        current_id = str(current_value or "") if not first_frame else default_id
        if current_id and current_id not in scene_by_id:
            current_id = default_id
        selected_since = self._number(state.get("selectedSince"), frame_time)
        if first_frame or frame_time < selected_since:
            selected_since = frame_time
            state["selected"] = current_id
            state["selectedSince"] = selected_since

        if desired_id == current_id:
            state["candidate"] = None
            state["candidateSince"] = None
            return current_id

        candidate_since = state.get("candidateSince")
        if (
            str(state.get("candidate") or "") != desired_id
            or candidate_since is None
            or frame_time < self._number(candidate_since, frame_time)
        ):
            state["candidate"] = desired_id
            state["candidateSince"] = frame_time
            candidate_since = frame_time

        current_scene = scene_by_id.get(current_id, {})
        desired_scene = scene_by_id.get(desired_id, {})
        enter_delay = max(0.0, self._number(desired_scene.get("enterDelay"), 0.0))
        exit_delay = max(0.0, self._number(current_scene.get("exitDelay"), 0.0))
        min_hold = max(0.0, self._number(current_scene.get("minHold"), 0.0))
        candidate_ready = (
            frame_time - self._number(candidate_since, frame_time)
            >= max(enter_delay, exit_delay)
        )
        hold_ready = first_frame or frame_time - selected_since >= min_hold
        if candidate_ready and hold_ready:
            current_id = desired_id
            state["selected"] = current_id
            state["selectedSince"] = frame_time
            state["candidate"] = None
            state["candidateSince"] = None
        return current_id

    def _soullink_scene_conditions_match(
        self,
        scene: dict[str, Any],
        snapshot: dict[str, Any],
        signals: dict[str, Any],
    ) -> bool:
        conditions = scene.get("conditions")
        if not isinstance(conditions, list):
            return False
        enabled = [
            item
            for item in conditions
            if isinstance(item, dict) and bool(item.get("enabled", True))
        ]
        if not enabled:
            return False
        results = [
            self._soullink_scene_condition_matches(item, snapshot, signals)
            for item in enabled
        ]
        return any(results) if str(scene.get("matchMode") or "all").lower() == "any" else all(results)

    def _soullink_scene_condition_matches(
        self,
        condition: dict[str, Any],
        snapshot: dict[str, Any],
        signals: dict[str, Any],
    ) -> bool:
        condition_type = str(condition.get("type") or "manual").strip().lower()
        operator = str(condition.get("operator") or "equals").strip().lower()
        expected = condition.get("value")
        if condition_type == "always":
            return True
        if condition_type == "manual":
            return False
        if condition_type == "emotion":
            if isinstance(expected, list):
                configured = ",".join(str(item) for item in expected)
            else:
                configured = str(expected or "")
            if not configured.strip():
                return False
            matched = self._soullink_emotion_matches(configured, snapshot)
            return not matched if operator in {"not_equals", "not_contains"} else matched
        if condition_type == "obs_scene":
            return self._soullink_text_condition_matches(
                signals.get("obs_scene"),
                operator,
                expected,
            )
        if condition_type == "stream_state":
            actual = self._normalize_soullink_stream_state(signals.get("stream_state"))
            if actual == "unknown":
                return False
            values = expected if isinstance(expected, list) else [expected]
            normalized_expected = [
                self._normalize_soullink_stream_state(item) for item in values
            ]
            return self._soullink_text_condition_matches(
                actual,
                operator,
                normalized_expected,
            )
        return False

    @staticmethod
    def _soullink_text_condition_matches(
        actual: Any,
        operator: str,
        expected: Any,
    ) -> bool:
        actual_text = str(actual or "").strip().casefold()
        values = expected if isinstance(expected, list) else [expected]
        expected_values = [
            str(item or "").strip().casefold()
            for item in values
            if str(item or "").strip()
        ]
        if not actual_text or not expected_values:
            return False
        if operator in {"contains", "not_contains"}:
            matched = any(item in actual_text for item in expected_values)
            return not matched if operator == "not_contains" else matched
        matched = any(actual_text == item for item in expected_values)
        return not matched if operator == "not_equals" else matched

    def _soullink_rule_signals_for_frame(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        cached = getattr(self, "_soullink_rule_signals", None)
        signals = dict(cached) if isinstance(cached, dict) else {}
        containers = [
            snapshot.get("signals"),
            snapshot.get("context"),
            snapshot.get("obs"),
            snapshot,
        ]
        for container in containers:
            if not isinstance(container, dict):
                continue
            for key in ("obs_scene", "obsScene", "current_scene", "currentScene"):
                if key in container and str(container.get(key) or "").strip():
                    signals["obs_scene"] = str(container.get(key)).strip()
                    break
            for key in ("stream_state", "streamState", "live_status", "liveStatus"):
                if key in container:
                    signals["stream_state"] = self._normalize_soullink_stream_state(
                        container.get(key)
                    )
                    break
            if "streaming" in container:
                signals["stream_state"] = "live" if bool(container.get("streaming")) else "offline"
        signals["stream_state"] = self._normalize_soullink_stream_state(
            signals.get("stream_state")
        )
        signals["obs_scene"] = str(signals.get("obs_scene") or "").strip()
        return signals

    @staticmethod
    def _normalize_soullink_stream_state(value: Any) -> str:
        if isinstance(value, bool):
            return "live" if value else "offline"
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {"live", "streaming", "online", "started", "on", "true", "1", "直播中"}:
            return "live"
        if text in {
            "offline",
            "idle",
            "stopped",
            "not_streaming",
            "off",
            "false",
            "0",
            "未直播",
        }:
            return "offline"
        return "unknown"

    def _queue_soullink_rule_signal_refresh(self, mapping: dict[str, Any]) -> None:
        groups = mapping.get("sceneGroups") if isinstance(mapping.get("sceneGroups"), list) else []
        needs_obs = any(
            isinstance(group, dict)
            and str(group.get("selectionMode") or "manual").lower() == "rules"
            and any(
                isinstance(condition, dict)
                and bool(condition.get("enabled", True))
                and str(condition.get("type") or "").lower() in {"obs_scene", "stream_state"}
                for scene in (group.get("scenes") if isinstance(group.get("scenes"), list) else [])
                if isinstance(scene, dict)
                for condition in (scene.get("conditions") if isinstance(scene.get("conditions"), list) else [])
            )
            for group in groups
        )
        if not needs_obs:
            return
        now = time.monotonic()
        if now < self._number(getattr(self, "_soullink_rule_signal_next_refresh", 0.0)):
            return
        task = getattr(self, "_soullink_rule_signal_task", None)
        if task and not task.done():
            return
        helper = getattr(self, "page_api", None)
        if helper is None:
            factory = getattr(self, "_page_api_helper", None)
            if callable(factory):
                try:
                    helper = factory()
                except Exception:
                    helper = None
        requester = getattr(helper, "_obs_requests", None)
        if not callable(requester):
            self._soullink_rule_signals = {
                "obs_scene": "",
                "stream_state": "unknown",
                "available": False,
            }
            self._soullink_rule_signal_next_refresh = now + 3.0
            return
        refresh = self._refresh_soullink_rule_signals(requester)
        try:
            task = asyncio.create_task(refresh)
        except RuntimeError:
            refresh.close()
            self._soullink_rule_signal_next_refresh = now + 3.0
            return
        self._soullink_rule_signal_task = task
        tasks = getattr(self, "_soullink_tasks", None)
        if isinstance(tasks, set):
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def _refresh_soullink_rule_signals(self, requester: Any) -> None:
        available = False
        try:
            responses = await requester(
                [
                    ("GetCurrentProgramScene", {}),
                    ("GetStreamStatus", {}),
                ],
                timeout=1.5,
            )
            scene = responses.get("GetCurrentProgramScene", {}) if isinstance(responses, dict) else {}
            stream = responses.get("GetStreamStatus", {}) if isinstance(responses, dict) else {}
            self._soullink_rule_signals = {
                "obs_scene": str(scene.get("currentProgramSceneName") or "").strip(),
                "stream_state": "live" if bool(stream.get("outputActive")) else "offline",
                "available": True,
                "stale": False,
                "at": time.monotonic(),
            }
            available = True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            now = time.monotonic()
            previous = getattr(self, "_soullink_rule_signals", None)
            previous_at = self._number(previous.get("at")) if isinstance(previous, dict) else 0.0
            if (
                isinstance(previous, dict)
                and bool(previous.get("available"))
                and previous_at > 0.0
                and now - previous_at <= 5.0
            ):
                self._soullink_rule_signals = {
                    **previous,
                    "available": True,
                    "stale": True,
                    "last_error": str(exc)[:180],
                }
                available = True
            else:
                self._soullink_rule_signals = {
                    "obs_scene": "",
                    "stream_state": "unknown",
                    "available": False,
                    "stale": False,
                    "at": now,
                    "last_error": str(exc)[:180],
                }
            logger.debug(f"[Soullink] OBS 场景规则信号暂不可用: {exc}")
        finally:
            self._soullink_rule_signal_next_refresh = time.monotonic() + (1.0 if available else 3.0)

    async def _stop_soullink_rule_signal_refresh(self) -> None:
        task = getattr(self, "_soullink_rule_signal_task", None)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._soullink_rule_signal_task = None
        self._soullink_rule_signal_next_refresh = 0.0
        self._soullink_rule_signals = {
            "obs_scene": "",
            "stream_state": "unknown",
            "available": False,
            "stale": False,
        }

    @staticmethod
    def _soullink_target_type(value: Any, target: str) -> str:
        target_type = str(value or "").strip().lower()
        if target_type in {"parameter", "expression"}:
            return target_type
        return "expression" if str(target).lower().endswith(".exp3.json") else "parameter"

    def _soullink_target_is_available(self, target_type: str, target: str) -> bool:
        attribute = (
            "_soullink_valid_vts_expressions"
            if target_type == "expression"
            else "_soullink_valid_vts_inputs"
        )
        valid = getattr(self, attribute, None)
        return not (isinstance(valid, set) and valid and target not in valid)

    @staticmethod
    def _merge_soullink_output(
        outputs: dict[str, dict[str, Any]],
        target: str,
        candidate: dict[str, Any],
    ) -> None:
        previous = outputs.get(target)
        previous_priority = previous.get("priority", -1000000) if previous else -1000000
        candidate_priority = candidate.get("priority", 0)
        if previous is None or candidate_priority >= previous_priority:
            outputs[target] = {"id": target, **candidate}

    @staticmethod
    def _merge_soullink_expression_candidate(
        outputs: dict[str, dict[str, Any]],
        target: str,
        candidate: dict[str, Any],
    ) -> None:
        previous = outputs.get(target)
        if previous is None:
            outputs[target] = candidate
            return
        previous_key = (
            int(previous.get("priority", 0)),
            bool(previous.get("active", False)),
            int(previous.get("order", 0)),
        )
        candidate_key = (
            int(candidate.get("priority", 0)),
            bool(candidate.get("active", False)),
            int(candidate.get("order", 0)),
        )
        if candidate_key >= previous_key:
            outputs[target] = candidate

    def _set_soullink_desired_expressions(
        self,
        desired: dict[str, dict[str, Any]],
    ) -> None:
        self._soullink_expression_frame_desired = {
            target: {
                "active": bool(item.get("active", False)),
                "fade": max(0.0, min(10.0, self._number(item.get("fade"), 0.25))),
                "force": bool(item.get("force", False)),
            }
            for target, item in desired.items()
            if target
        }

    def _queue_soullink_expression_sync(self) -> None:
        desired = getattr(self, "_soullink_expression_frame_desired", None)
        if not isinstance(desired, dict):
            desired = {}
        controlled = getattr(self, "_soullink_controlled_expressions", None)
        if not isinstance(controlled, set):
            controlled = set()
            self._soullink_controlled_expressions = controlled
        controlled.update(desired)
        self._soullink_expression_desired = {
            target: desired.get(
                target,
                {"active": False, "fade": 0.25, "force": False},
            )
            for target in controlled
        }
        if not self._soullink_expression_desired:
            return
        task = getattr(self, "_soullink_expression_task", None)
        if task and not task.done():
            return
        flush = self._flush_soullink_expression_states()
        try:
            task = asyncio.create_task(flush)
        except RuntimeError:
            flush.close()
            return
        self._soullink_expression_task = task
        tasks = getattr(self, "_soullink_tasks", None)
        if isinstance(tasks, set):
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def _flush_soullink_expression_states(self) -> None:
        applied = getattr(self, "_soullink_expression_applied", None)
        if not isinstance(applied, dict):
            applied = {}
            self._soullink_expression_applied = applied
        failures = getattr(self, "_soullink_expression_retry_at", None)
        if not isinstance(failures, dict):
            failures = {}
            self._soullink_expression_retry_at = failures
        while True:
            desired = getattr(self, "_soullink_expression_desired", None)
            if not isinstance(desired, dict):
                return
            now = time.monotonic()
            changes = [
                (target, item)
                for target, item in desired.items()
                if (
                    bool(item.get("force", False))
                    or bool(applied.get(target, False)) != bool(item.get("active", False))
                )
                and self._number(failures.get(target)) <= now
            ]
            if not changes:
                return
            # Explicit deactivation first prevents two mutually exclusive poses
            # from remaining active after a scene switch.
            changes.sort(key=lambda pair: (bool(pair[1].get("active", False)), pair[0]))
            target, item = changes[0]
            vts = getattr(self, "vts", None)
            if vts is None or not callable(getattr(vts, "set_expression", None)):
                failures[target] = time.monotonic() + 5.0
                return
            checker = getattr(self, "_check_and_reconnect", None)
            if callable(checker):
                try:
                    if not await checker():
                        failures[target] = time.monotonic() + 5.0
                        return
                except Exception:
                    failures[target] = time.monotonic() + 5.0
                    return
            active = bool(item.get("active", False))
            try:
                await vts.set_expression(target, active, self._number(item.get("fade"), 0.25))
                applied[target] = active
                failures.pop(target, None)
                current = getattr(self, "_soullink_expression_desired", {}).get(target)
                if current is item:
                    current["force"] = False
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures[target] = time.monotonic() + 5.0
                logger.debug(f"[Soullink] 设置 VTS 表情 {target} 失败: {exc}")

    async def _deactivate_soullink_expressions(self) -> None:
        self._soullink_accessory_state = {}
        self._soullink_scene_group_state = {}
        controlled = getattr(self, "_soullink_controlled_expressions", None)
        if not isinstance(controlled, set) or not controlled:
            return
        self._soullink_expression_frame_desired = {
            target: {"active": False, "fade": 0.25, "force": True}
            for target in controlled
        }
        self._queue_soullink_expression_sync()
        task = getattr(self, "_soullink_expression_task", None)
        if task and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)
        applied = getattr(self, "_soullink_expression_applied", None)
        failures = getattr(self, "_soullink_expression_retry_at", None)
        if not isinstance(applied, dict):
            applied = {}
            self._soullink_expression_applied = applied
        if not isinstance(failures, dict):
            failures = {}
            self._soullink_expression_retry_at = failures
        retry_now = time.monotonic()
        completed = {
            target
            for target in controlled
            if applied.get(target) is not True
            and self._number(failures.get(target)) <= retry_now
        }
        controlled.difference_update(completed)
        for target in completed:
            applied.pop(target, None)
            failures.pop(target, None)
        desired = getattr(self, "_soullink_expression_desired", None)
        if isinstance(desired, dict):
            for target in completed:
                desired.pop(target, None)
        frame_desired = getattr(self, "_soullink_expression_frame_desired", None)
        if isinstance(frame_desired, dict):
            self._soullink_expression_frame_desired = {
                target: item
                for target, item in frame_desired.items()
                if target in controlled
            }

    def _transform_soullink_mapping_value(
        self,
        source_value: float,
        rule: dict[str, Any],
    ) -> float:
        source_min = self._number(rule.get("sourceMin"), -1.0)
        source_neutral = self._number(rule.get("sourceNeutral"), 0.0)
        source_max = self._number(rule.get("sourceMax"), 1.0)
        if source_value >= source_neutral:
            span = source_max - source_neutral
            normalized = (source_value - source_neutral) / span if span > 1e-9 else 0.0
        else:
            span = source_neutral - source_min
            normalized = (source_value - source_neutral) / span if span > 1e-9 else 0.0
        should_clamp = bool(rule.get("clamp", True))
        if should_clamp:
            normalized = max(-1.0, min(1.0, normalized))
        if bool(rule.get("invert", False)):
            normalized = -normalized
        deadzone = max(0.0, min(0.95, self._number(rule.get("deadzone"))))
        magnitude = abs(normalized)
        if magnitude <= deadzone:
            normalized = 0.0
        elif deadzone > 0.0:
            normalized = math.copysign((magnitude - deadzone) / (1.0 - deadzone), normalized)
        curve = max(0.05, min(8.0, self._number(rule.get("curve"), 1.0)))
        normalized = math.copysign(abs(normalized) ** curve, normalized) if normalized else 0.0
        output_min = self._number(rule.get("outputMin"), -1.0)
        output_neutral = self._number(rule.get("outputNeutral"), 0.0)
        output_max = self._number(rule.get("outputMax"), 1.0)
        if normalized >= 0.0:
            value = output_neutral + normalized * (output_max - output_neutral)
        else:
            value = output_neutral + (-normalized) * (output_min - output_neutral)
        if should_clamp:
            low = min(output_min, output_neutral, output_max)
            high = max(output_min, output_neutral, output_max)
            value = max(low, min(high, value))
        return value

    def _smooth_soullink_mapping_value(
        self,
        key: str,
        value: float,
        smoothing: float,
        frame_time: float,
    ) -> float:
        state = getattr(self, "_soullink_mapping_smoothing", None)
        if not isinstance(state, dict):
            state = {}
            self._soullink_mapping_smoothing = state
        previous = state.get(key)
        if not isinstance(previous, tuple) or len(previous) != 2:
            state[key] = (value, frame_time)
            return value
        previous_value, previous_time = previous
        delta = frame_time - self._number(previous_time, frame_time)
        if delta <= 0.0:
            smoothed = value
        else:
            alpha = 1.0 - math.exp(-delta / max(0.001, smoothing))
            smoothed = self._number(previous_value, value) + (value - self._number(previous_value, value)) * alpha
        state[key] = (smoothed, frame_time)
        return smoothed

    def _soullink_vts_mapping(self) -> dict[str, Any]:
        preview = getattr(self, "_soullink_mapping_preview", None)
        preview_until = self._number(getattr(self, "_soullink_mapping_preview_until", 0.0))
        now = time.monotonic()
        if isinstance(preview, dict) and preview_until > now:
            mapping = preview
            signature = f"preview:{getattr(self, '_soullink_mapping_preview_revision', 0)}"
        else:
            if isinstance(preview, dict):
                self._clear_soullink_mapping_preview()
            raw = self.config.get("soullink_vts_mapping")
            signature = self._soullink_mapping_signature(raw)
            if signature == getattr(self, "_soullink_mapping_cache_signature", None):
                mapping = getattr(self, "_soullink_mapping_cache", None)
            else:
                mapping = self._normalize_soullink_mapping(raw)
                self._soullink_mapping_cache_signature = signature
                self._soullink_mapping_cache = mapping
        if not isinstance(mapping, dict):
            mapping = self._normalize_soullink_mapping({})
        if signature != getattr(self, "_soullink_mapping_active_signature", None):
            self._soullink_mapping_active_signature = signature
            self._soullink_mapping_smoothing = {}
            self._soullink_accessory_state = {}
            self._soullink_scene_group_state = {}
        return mapping

    def _default_soullink_mapping(self) -> dict[str, Any]:
        mapping = self._legacy_soullink_mapping_to_advanced(DEFAULT_VTS_MAPPING)
        if self._soullink_type_h4_inputs_available():
            type_h4_mapping = copy.deepcopy(TYPE_H4_VTS_MAPPING)
            mapping["composites"] = type_h4_mapping["composites"]
            mapping["rules"] = type_h4_mapping["rules"]
        mapping["emotionAccessories"] = self._default_soullink_expression_accessories()
        return mapping

    def _soullink_type_h4_inputs_available(self) -> bool:
        valid_inputs = getattr(self, "_soullink_valid_vts_inputs", None)
        return isinstance(valid_inputs, set) and TYPE_H4_VTS_INPUT_ANCHORS.issubset(valid_inputs)

    def _default_soullink_expression_accessories(self) -> list[dict[str, Any]]:
        accessories = copy.deepcopy(TYPE_H4_VTS_MAPPING["emotionAccessories"])
        valid_expressions = getattr(self, "_soullink_valid_vts_expressions", None)
        if not isinstance(valid_expressions, set) or not valid_expressions:
            return accessories
        return [
            item
            for item in accessories
            if str(item.get("target") or "").strip() in valid_expressions
        ]

    def _invalidate_soullink_mapping_cache(self) -> None:
        self._soullink_mapping_cache_signature = None
        self._soullink_mapping_cache = None
        self._soullink_mapping_active_signature = None

    def _normalize_soullink_mapping(
        self,
        raw: Any,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        payload = self._parse_soullink_mapping(raw)
        if not payload:
            return self._default_soullink_mapping()
        if not isinstance(payload.get("rules"), list):
            converted = self._legacy_soullink_mapping_to_advanced(payload)
            converted["emotionAccessories"] = self._normalize_soullink_accessories(
                payload.get("emotionAccessories")
            )
            converted["sceneGroups"] = self._normalize_soullink_scene_groups(
                payload.get("sceneGroups")
            )
            return converted

        errors: list[str] = []
        composites = dict(SOULLINK_COMPOSITE_DEFAULTS)
        raw_composites = payload.get("composites") if isinstance(payload.get("composites"), dict) else {}
        for key, default in SOULLINK_COMPOSITE_DEFAULTS.items():
            composites[key] = max(
                -10.0,
                min(10.0, self._finite_number(raw_composites.get(key), default)),
            )

        normalized_rules: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for index, raw_rule in enumerate(payload.get("rules", [])[:256]):
            if not isinstance(raw_rule, dict):
                errors.append(f"第 {index + 1} 条规则不是对象")
                continue
            source = str(raw_rule.get("source") or "").strip()[:80]
            targets = raw_rule.get("targets") if isinstance(raw_rule.get("targets"), list) else None
            if targets is None:
                targets = [raw_rule.get("target")]
            targets = [str(item or "").strip()[:120] for item in targets]
            targets = [item for item in targets if item]
            enabled = self._mapping_bool(raw_rule.get("enabled"), True)
            if not source:
                if enabled:
                    errors.append(f"第 {index + 1} 条规则缺少 Soullink 源")
                continue
            if not targets:
                if enabled:
                    errors.append(f"第 {index + 1} 条规则缺少 VTS 目标")
                continue
            meta = SOULLINK_SOURCE_META.get(
                source,
                {"min": -1.0, "neutral": 0.0, "max": 1.0},
            )
            source_min = self._finite_number(raw_rule.get("sourceMin"), meta["min"])
            source_neutral = self._finite_number(raw_rule.get("sourceNeutral"), meta["neutral"])
            source_max = self._finite_number(raw_rule.get("sourceMax"), meta["max"])
            if source_min > source_neutral or source_neutral > source_max:
                errors.append(f"第 {index + 1} 条规则的源范围必须满足 min ≤ 中性 ≤ max")
                continue
            base_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw_rule.get("id") or f"rule-{index + 1}"))[:64]
            for target_index, target in enumerate(targets):
                rule_id = base_id if len(targets) == 1 else f"{base_id}-{target_index + 1}"
                original_id = rule_id
                suffix = 2
                while rule_id in used_ids:
                    rule_id = f"{original_id}-{suffix}"
                    suffix += 1
                used_ids.add(rule_id)
                normalized_rules.append(
                    {
                        "id": rule_id,
                        "enabled": enabled,
                        "source": source,
                        "target": target,
                        "sourceMin": source_min,
                        "sourceNeutral": source_neutral,
                        "sourceMax": source_max,
                        "outputMin": self._finite_number(raw_rule.get("outputMin"), -1.0),
                        "outputNeutral": self._finite_number(raw_rule.get("outputNeutral"), 0.0),
                        "outputMax": self._finite_number(raw_rule.get("outputMax"), 1.0),
                        "curve": max(0.05, min(8.0, self._finite_number(raw_rule.get("curve"), 1.0))),
                        "deadzone": max(0.0, min(0.95, self._finite_number(raw_rule.get("deadzone"), 0.0))),
                        "smoothing": max(0.0, min(5.0, self._finite_number(raw_rule.get("smoothing"), 0.0))),
                        "weight": max(0.0, min(1.0, self._finite_number(raw_rule.get("weight"), 1.0))),
                        "invert": self._mapping_bool(raw_rule.get("invert"), False),
                        "clamp": self._mapping_bool(raw_rule.get("clamp"), True),
                        "blend": str(raw_rule.get("blend") or "replace").lower()
                        if str(raw_rule.get("blend") or "replace").lower() in {"replace", "add", "max", "min"}
                        else "replace",
                    }
                )
        if strict and errors:
            raise ValueError("；".join(errors[:6]))
        return {
            "version": 2,
            "composites": composites,
            "rules": normalized_rules,
            "emotionAccessories": self._normalize_soullink_accessories(
                payload.get("emotionAccessories")
            ),
            "sceneGroups": self._normalize_soullink_scene_groups(
                payload.get("sceneGroups")
            ),
        }

    def _normalize_soullink_accessories(self, raw: Any) -> list[dict[str, Any]]:
        """Normalize discrete emotion actions without rejecting model-specific targets."""
        if not isinstance(raw, list):
            return []
        normalized: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for index, item in enumerate(raw[:256]):
            if not isinstance(item, dict):
                continue
            target = str(
                item.get("target")
                or item.get("expressionFile")
                or item.get("file")
                or ""
            ).strip()[:240]
            target_type = str(item.get("targetType") or "").strip().lower()
            if target_type not in {"parameter", "expression"}:
                target_type = self._soullink_target_type("", target)
            base_id = re.sub(
                r"[^A-Za-z0-9_.-]+",
                "-",
                str(item.get("id") or f"accessory-{index + 1}"),
            )[:64] or f"accessory-{index + 1}"
            rule_id = base_id
            suffix = 2
            while rule_id in used_ids:
                rule_id = f"{base_id}-{suffix}"
                suffix += 1
            used_ids.add(rule_id)
            emotions = item.get("emotions")
            if isinstance(emotions, list):
                emotion = ",".join(
                    str(value).strip().lower()[:40]
                    for value in emotions
                    if str(value).strip()
                )
            else:
                emotion = str(item.get("emotion") or "any").strip().lower()[:160] or "any"
            trigger = self._clamp_number(item.get("triggerThreshold"), 0.0, 1.0, 0.45)
            release = self._clamp_number(item.get("releaseThreshold"), 0.0, 1.0, 0.28)
            # A release threshold above the trigger threshold defeats hysteresis.
            release = min(release, trigger)
            normalized.append(
                {
                    "id": rule_id,
                    "name": str(item.get("name") or rule_id)[:80],
                    "enabled": self._mapping_bool(item.get("enabled"), True),
                    "emotion": emotion,
                    "targetType": target_type,
                    "target": target,
                    "onValue": self._finite_number(item.get("onValue"), 1.0),
                    "offValue": self._finite_number(item.get("offValue"), 0.0),
                    "triggerThreshold": trigger,
                    "releaseThreshold": release,
                    "fadeIn": max(0.0, min(10.0, self._finite_number(item.get("fadeIn"), 0.25))),
                    "fadeOut": max(0.0, min(10.0, self._finite_number(item.get("fadeOut"), 0.35))),
                    "priority": max(-1000, min(1000, int(self._finite_number(item.get("priority"), 20.0)))),
                    "minHold": max(0.0, min(60.0, self._finite_number(item.get("minHold"), 0.25))),
                    "cooldown": max(0.0, min(60.0, self._finite_number(item.get("cooldown"), 0.1))),
                    "debounceIn": max(0.0, min(5.0, self._finite_number(item.get("debounceIn"), 0.08))),
                    "debounceOut": max(0.0, min(5.0, self._finite_number(item.get("debounceOut"), 0.12))),
                }
            )
        return normalized

    def _normalize_soullink_scene_groups(self, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        groups: list[dict[str, Any]] = []
        used_group_ids: set[str] = set()
        for group_index, item in enumerate(raw[:64]):
            if not isinstance(item, dict):
                continue
            base_id = re.sub(
                r"[^A-Za-z0-9_.-]+",
                "-",
                str(item.get("id") or f"scene-group-{group_index + 1}"),
            )[:64] or f"scene-group-{group_index + 1}"
            group_id = base_id
            suffix = 2
            while group_id in used_group_ids:
                group_id = f"{base_id}-{suffix}"
                suffix += 1
            used_group_ids.add(group_id)
            scenes: list[dict[str, Any]] = []
            used_scene_ids: set[str] = set()
            raw_scenes = item.get("scenes") if isinstance(item.get("scenes"), list) else []
            for scene_index, scene in enumerate(raw_scenes[:64]):
                if not isinstance(scene, dict):
                    continue
                scene_base = re.sub(
                    r"[^A-Za-z0-9_.-]+",
                    "-",
                    str(scene.get("id") or f"scene-{scene_index + 1}"),
                )[:64] or f"scene-{scene_index + 1}"
                scene_id = scene_base
                scene_suffix = 2
                while scene_id in used_scene_ids:
                    scene_id = f"{scene_base}-{scene_suffix}"
                    scene_suffix += 1
                used_scene_ids.add(scene_id)
                values: list[dict[str, Any]] = []
                raw_values = scene.get("values") if isinstance(scene.get("values"), list) else []
                for value in raw_values[:256]:
                    if not isinstance(value, dict):
                        continue
                    target = str(
                        value.get("target")
                        or value.get("expressionFile")
                        or value.get("file")
                        or ""
                    ).strip()[:240]
                    target_type = str(value.get("targetType") or "").strip().lower()
                    if target_type not in {"parameter", "expression"}:
                        target_type = self._soullink_target_type("", target)
                    values.append(
                        {
                            "targetType": target_type,
                            "target": target,
                            "value": self._finite_number(value.get("value"), 1.0),
                            "offValue": self._finite_number(value.get("offValue"), 0.0),
                            "active": self._mapping_bool(value.get("active"), True),
                        }
                    )
                raw_conditions = scene.get("conditions")
                if isinstance(raw_conditions, dict):
                    raw_conditions = [raw_conditions]
                if not isinstance(raw_conditions, list):
                    raw_conditions = []
                conditions: list[dict[str, Any]] = []
                condition_type_aliases = {
                    "obsscene": "obs_scene",
                    "obs_scene_name": "obs_scene",
                    "current_scene": "obs_scene",
                    "livestatus": "stream_state",
                    "live_status": "stream_state",
                    "streamstate": "stream_state",
                    "streaming": "stream_state",
                }
                operator_aliases = {
                    "==": "equals",
                    "is": "equals",
                    "exact": "equals",
                    "!=": "not_equals",
                    "is_not": "not_equals",
                    "includes": "contains",
                    "not_includes": "not_contains",
                }
                for condition in raw_conditions[:32]:
                    if not isinstance(condition, dict):
                        continue
                    condition_type = str(
                        condition.get("type") or condition.get("source") or "manual"
                    ).strip().lower().replace("-", "_").replace(" ", "_")[:40]
                    condition_type = condition_type_aliases.get(
                        condition_type,
                        condition_type,
                    )
                    operator = str(condition.get("operator") or "equals").strip().lower()
                    operator = operator_aliases.get(operator, operator)
                    if operator not in {
                        "equals",
                        "not_equals",
                        "contains",
                        "not_contains",
                        "in",
                    }:
                        operator = "equals"
                    value = condition.get("value")
                    if isinstance(value, list):
                        value = [
                            item if isinstance(item, (bool, int, float)) else str(item)[:160]
                            for item in value[:32]
                        ]
                    elif not isinstance(value, (bool, int, float)):
                        value = str(value or "")[:240]
                    conditions.append(
                        {
                            "type": condition_type or "manual",
                            "operator": operator,
                            "value": value,
                            "enabled": self._mapping_bool(condition.get("enabled"), True),
                        }
                    )
                match_mode = str(scene.get("matchMode") or "all").strip().lower()
                if match_mode not in {"all", "any"}:
                    match_mode = "all"
                scenes.append(
                    {
                        "id": scene_id,
                        "name": str(scene.get("name") or scene_id)[:80],
                        "conditions": conditions,
                        "matchMode": match_mode,
                        "priority": max(
                            -1000,
                            min(1000, int(self._finite_number(scene.get("priority"), 0.0))),
                        ),
                        "enterDelay": max(
                            0.0,
                            min(60.0, self._finite_number(scene.get("enterDelay"), 0.0)),
                        ),
                        "exitDelay": max(
                            0.0,
                            min(60.0, self._finite_number(scene.get("exitDelay"), 0.0)),
                        ),
                        "minHold": max(
                            0.0,
                            min(300.0, self._finite_number(scene.get("minHold"), 0.0)),
                        ),
                        "values": values,
                    }
                )
            default_scene = str(item.get("defaultScene") or "").strip()[:64]
            has_active_scene = "activeScene" in item
            active_scene = str(item.get("activeScene") or "").strip()[:64]
            known_scene_ids = {scene["id"] for scene in scenes}
            if default_scene not in known_scene_ids:
                default_scene = scenes[0]["id"] if scenes else ""
            if active_scene and active_scene not in known_scene_ids:
                active_scene = default_scene
            if not has_active_scene:
                active_scene = default_scene
            selection_mode = str(item.get("selectionMode") or "manual").strip().lower()
            if selection_mode in {"auto", "automatic", "rule"}:
                selection_mode = "rules"
            if selection_mode not in {"manual", "rules"}:
                selection_mode = "manual"
            groups.append(
                {
                    "id": group_id,
                    "name": str(item.get("name") or group_id)[:80],
                    "enabled": self._mapping_bool(item.get("enabled"), True),
                    "defaultScene": default_scene,
                    "activeScene": active_scene,
                    "selectionMode": selection_mode,
                    "exclusive": self._mapping_bool(item.get("exclusive"), True),
                    "priority": max(-1000, min(1000, int(self._finite_number(item.get("priority"), 100.0)))),
                    "fadeTime": max(0.0, min(10.0, self._finite_number(item.get("fadeTime"), 0.35))),
                    "scenes": scenes,
                }
            )
        return groups

    def _legacy_soullink_mapping_to_advanced(
        self,
        legacy: dict[str, Any],
    ) -> dict[str, Any]:
        rules: list[dict[str, Any]] = []
        for source, raw_rule in legacy.items():
            if not isinstance(raw_rule, dict):
                continue
            ids = raw_rule.get("ids") or ([raw_rule.get("id")] if raw_rule.get("id") else [])
            if isinstance(ids, str):
                ids = [ids]
            scale = self._finite_number(raw_rule.get("scale"), 1.0)
            offset = self._finite_number(raw_rule.get("offset"), 0.0)
            output_min = self._finite_number(raw_rule.get("min"), -1000000.0)
            output_max = self._finite_number(raw_rule.get("max"), 1000000.0)
            low = min(output_min, output_max)
            high = max(output_min, output_max)
            meta = SOULLINK_SOURCE_META.get(
                str(source),
                {"min": -1.0, "neutral": 0.0, "max": 1.0},
            )
            if abs(scale) < 1e-12:
                source_min = self._number(meta["min"], -1.0)
                source_max = self._number(meta["max"], 1.0)
                invert = False
            elif scale > 0.0:
                source_min = (low - offset) / scale
                source_max = (high - offset) / scale
                invert = False
            else:
                absolute_scale = abs(scale)
                source_min = (offset - high) / absolute_scale
                source_max = (offset - low) / absolute_scale
                invert = True
            source_neutral = max(
                min(source_min, source_max),
                min(max(source_min, source_max), self._number(meta["neutral"])),
            )
            output_neutral = max(low, min(high, source_neutral * scale + offset))
            for target_index, target in enumerate(ids):
                target = str(target or "").strip()
                if not target:
                    continue
                rules.append(
                    {
                        "id": f"legacy-{source}-{target_index + 1}",
                        "enabled": True,
                        "source": str(source),
                        "target": target,
                        "sourceMin": min(source_min, source_max),
                        "sourceNeutral": source_neutral,
                        "sourceMax": max(source_min, source_max),
                        "outputMin": low,
                        "outputNeutral": output_neutral,
                        "outputMax": high,
                        "curve": 1.0,
                        "deadzone": 0.0,
                        "smoothing": 0.0,
                        "weight": self._clamp_number(raw_rule.get("weight"), 0.0, 1.0, 1.0),
                        "invert": invert,
                        "clamp": True,
                        "blend": "replace",
                    }
                )
        return {
            "version": 2,
            "composites": dict(SOULLINK_COMPOSITE_DEFAULTS),
            "rules": rules,
            "emotionAccessories": [],
            "sceneGroups": [],
        }

    def _soullink_mapping_editor_payload(self) -> dict[str, Any]:
        raw = self.config.get("soullink_vts_mapping")
        parsed = self._parse_soullink_mapping(raw)
        saved = self._normalize_soullink_mapping(parsed)
        active = self._soullink_vts_mapping()
        return {
            "version": 2,
            "mode": "default" if not parsed else "custom",
            "previewActive": active is getattr(self, "_soullink_mapping_preview", None),
            "previewExpiresIn": max(
                0.0,
                self._number(getattr(self, "_soullink_mapping_preview_until", 0.0))
                - time.monotonic(),
            ),
            "sources": [
                {"id": source, **meta}
                for source, meta in SOULLINK_SOURCE_META.items()
            ],
            "compositeDefaults": dict(SOULLINK_COMPOSITE_DEFAULTS),
            "defaultMapping": self._normalize_soullink_mapping({}),
            "savedMapping": copy.deepcopy(saved),
            "activeMapping": copy.deepcopy(active),
        }

    def _set_soullink_vts_input_catalog(self, inputs: list[dict[str, Any]]) -> None:
        next_inputs = {
            str(item.get("name") or "").strip()
            for item in inputs
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        if next_inputs != getattr(self, "_soullink_valid_vts_inputs", None):
            self._soullink_valid_vts_inputs = next_inputs
            self._invalidate_soullink_mapping_cache()

    def _set_soullink_vts_expression_catalog(self, expressions: list[dict[str, Any]]) -> None:
        next_expressions = {
            str(
                item.get("target")
                or item.get("file")
                or item.get("expressionFile")
                or item.get("name")
                or ""
            ).strip()
            for item in expressions
            if isinstance(item, dict)
            and str(
                item.get("target")
                or item.get("file")
                or item.get("expressionFile")
                or item.get("name")
                or ""
            ).strip()
        }
        if next_expressions != getattr(self, "_soullink_valid_vts_expressions", None):
            self._soullink_valid_vts_expressions = next_expressions
            self._invalidate_soullink_mapping_cache()

    async def _refresh_soullink_vts_input_catalog(self) -> bool:
        vts = getattr(self, "vts", None)
        if not vts or not bool(getattr(vts, "is_authenticated", False)):
            return False
        try:
            inputs = await vts.get_input_parameters()
            self._set_soullink_vts_input_catalog(inputs)
        except Exception as exc:
            logger.debug(f"[Soullink] 刷新 VTS 输入目录失败: {exc}")
            return False
        try:
            expressions = await vts.get_expressions()
            self._set_soullink_vts_expression_catalog(expressions)
        except Exception as exc:
            logger.debug(f"[Soullink] 刷新 VTS 表情目录失败: {exc}")
        return bool(inputs)

    def _set_soullink_mapping_preview(self, raw: Any) -> dict[str, Any]:
        mapping = self._normalize_soullink_mapping(raw, strict=True)
        self._soullink_mapping_preview = mapping
        self._soullink_mapping_preview_until = time.monotonic() + 120.0
        self._soullink_mapping_preview_revision = int(
            getattr(self, "_soullink_mapping_preview_revision", 0)
        ) + 1
        self._soullink_mapping_smoothing = {}
        self._soullink_accessory_state = {}
        self._soullink_scene_group_state = {}
        self._soullink_expression_frame_desired = {}
        self._queue_soullink_expression_sync()
        return mapping

    def _clear_soullink_mapping_preview(self) -> None:
        self._soullink_mapping_preview = None
        self._soullink_mapping_preview_until = 0.0
        self._soullink_mapping_preview_revision = int(
            getattr(self, "_soullink_mapping_preview_revision", 0)
        ) + 1
        self._soullink_mapping_smoothing = {}
        self._soullink_accessory_state = {}
        self._soullink_scene_group_state = {}
        self._soullink_expression_frame_desired = {}
        self._queue_soullink_expression_sync()

    @staticmethod
    def _parse_soullink_mapping(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _soullink_mapping_signature(raw: Any) -> str:
        if isinstance(raw, str):
            return raw
        try:
            return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return str(raw)

    @staticmethod
    def _mapping_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "off"}
        return bool(value)

    def _finite_number(self, value: Any, default: float = 0.0) -> float:
        number = self._number(value, default)
        return number if math.isfinite(number) else default

    def _soullink_status(self) -> dict[str, Any]:
        runtime = getattr(self, "_soullink_runtime", None)
        scheduler = getattr(self, "_vts_parameter_scheduler", None)
        command_vts = getattr(self, "vts", None)
        parameter_vts = getattr(self, "_parameter_vts", None)
        rule_signals = getattr(self, "_soullink_rule_signals", None)
        rule_signals = dict(rule_signals) if isinstance(rule_signals, dict) else {}
        signal_at = self._number(rule_signals.get("at"))
        signal_age = max(0.0, time.monotonic() - signal_at) if signal_at > 0.0 else None
        mapping = self._soullink_vts_mapping()
        group_states = getattr(self, "_soullink_scene_group_state", None)
        group_states = group_states if isinstance(group_states, dict) else {}
        scene_groups = []
        for index, group in enumerate(
            mapping.get("sceneGroups") if isinstance(mapping.get("sceneGroups"), list) else []
        ):
            if not isinstance(group, dict):
                continue
            group_id = str(group.get("id") or f"scene-group-{index + 1}")
            group_state = group_states.get(group_id)
            group_state = group_state if isinstance(group_state, dict) else {}
            scene_groups.append(
                {
                    "id": group_id,
                    "selectionMode": str(group.get("selectionMode") or "manual"),
                    "selectedScene": str(group_state.get("selected") or ""),
                    "candidateScene": str(group_state.get("candidate") or ""),
                    "defaultScene": str(group.get("defaultScene") or ""),
                }
            )
        status = runtime.status() if runtime else {"running": False, "last_error": "运行时未初始化"}
        status.update(
            {
                "enabled": self._is_soullink_enabled(),
                "mode": self._soullink_mode(),
                "style": self._soullink_runtime_options()["style"],
                "prompt_intent": bool(self.config.get("soullink_prompt_intent_enabled", True)),
                "vts_parameters": list(getattr(self, "_soullink_last_vts_parameters", [])),
                "ruleSignals": {
                    "obsScene": str(rule_signals.get("obs_scene") or ""),
                    "streamState": self._normalize_soullink_stream_state(
                        rule_signals.get("stream_state")
                    ),
                    "available": bool(rule_signals.get("available", False)),
                    "stale": bool(rule_signals.get("stale", False)),
                    "ageSeconds": signal_age,
                },
                "sceneGroups": scene_groups,
                "sceneSelections": {
                    item["id"]: item["selectedScene"] for item in scene_groups
                },
                "scheduler": scheduler.status() if scheduler else {},
                "vts": {
                    "connected": bool(getattr(command_vts, "is_authenticated", False)),
                    "realtime_connected": bool(
                        getattr(parameter_vts, "is_authenticated", False)
                    ),
                    "url": str(getattr(command_vts, "url", "") or ""),
                },
            }
        )
        return status

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _clamp_number(cls, value: Any, minimum: float, maximum: float, default: float) -> float:
        return max(minimum, min(maximum, cls._number(value, default)))
