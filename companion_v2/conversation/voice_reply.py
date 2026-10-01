"""Validated voice presentation policy and model-authored spoken spans."""

from dataclasses import dataclass
from datetime import timedelta
import json
import math
import re

from companion_v2.conversation.segment_control import controlled_parts
from companion_v2.execution.models import digest, stamp
from companion_v2.foundation.refs import ScopeKind


_TAG = re.compile(r"(?is)<pc_tts>(.*?)</pc_tts>")
_STRAY_TAG = re.compile(r"(?i)</?pc_tts\s*>")


@dataclass(frozen=True)
class VoiceReplyPolicy:
    trigger_mode: str = "always"
    generation_mode: str = "plain"
    segment_mode: str = "each"
    delivery_mode: str = "voice_and_text"
    position: str = "after_media"
    language: str = "zh"
    foreign_text_mode: str = "original"
    probability: float = 1.0
    private_probability: float = -1.0
    group_probability: float = -1.0
    cooldown_seconds: int = 0
    max_speech_chars: int = 1800
    timeout_seconds: int = 30
    trigger_keywords: str = ""
    provider_id: str = ""
    zh_provider_id: str = ""
    ja_provider_id: str = ""
    en_provider_id: str = ""
    extra_prompt: str = ""

    def __post_init__(self):
        choices = ((self.trigger_mode, {"always", "request", "adaptive"}),
                   (self.generation_mode, {"plain", "model_tag"}),
                   (self.segment_mode, {"each", "first", "last"}),
                   (self.delivery_mode, {"voice_and_text", "voice_only"}),
                   (self.position, {"after_media", "after_text", "before_text"}),
                   (self.language, {"zh", "ja", "en"}),
                   (self.foreign_text_mode, {"original", "translation", "bilingual"}))
        if any(value not in options for value, options in choices):
            raise ValueError("voice reply mode is unsupported")
        for value in (self.probability, self.private_probability, self.group_probability):
            if type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1:
                raise ValueError("voice reply probability must be between zero and one, or -1 for inheritance")
        if not 0 <= self.probability <= 1:
            raise ValueError("voice reply probability must be between zero and one")
        for value, low, high in ((self.cooldown_seconds, 0, 86400),
                                 (self.max_speech_chars, 1, 10000), (self.timeout_seconds, 1, 120)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("voice reply limit is invalid")
        for value, limit in ((self.trigger_keywords, 2000), (self.provider_id, 128),
                             (self.zh_provider_id, 128), (self.ja_provider_id, 128),
                             (self.en_provider_id, 128), (self.extra_prompt, 2000)):
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError("voice reply text setting is invalid")

    @property
    def instruction(self):
        if self.generation_mode != "model_tag" and self.trigger_mode != "adaptive":
            return ""
        prompt = (
            "本轮可自行决定哪些短句适合用语音表达。仅将需要朗读的原文包在 <pc_tts> 与 </pc_tts> 中；"
            "标签内不得放分段标记、代码、链接或图片说明。没有合适内容就不用标签。"
            "语音标签只是内部格式，不要在普通文字中解释它。"
        )
        if self.language != "zh":
            label = "日语" if self.language == "ja" else "英语"
            prompt += f"标签内用自然{label}，"
            if self.foreign_text_mode in ("translation", "bilingual"):
                prompt += "标签外紧接自然中文译文，不加译文标题；译文将作为可见文字。"
            else:
                prompt += "标签外可写补充文字，但不要重复朗读原文。"
        if self.extra_prompt.strip():
            prompt += "\n" + self.extra_prompt.strip()
        return prompt

    def provider_for_language(self):
        return getattr(self, self.language + "_provider_id") or self.provider_id

    def chance(self, kind):
        override = self.group_probability if kind == "group" else self.private_probability
        return float(self.probability if override < 0 else override)

    def keywords(self):
        return tuple(word.strip().casefold() for word in re.split(r"[,，;；\n]+", self.trigger_keywords)
                     if word.strip())


def capability_instruction(policy):
    language = {"zh": "中文", "ja": "日语", "en": "英语"}[policy.language]
    delivery = "优先语音呈现" if policy.delivery_mode == "voice_only" else "语音与文字并行"
    return (f"本轮已启用可选语音呈现策略：目标语种{language}，{delivery}。"
            "对话模型只生成文字；语音在投递时由 TTS Provider 尽力合成，可能因触发条件、频率或合成失败而退回文字。"
            "没有成功投递结果前，不要声称已经发送语音。")


def separate_spoken(text, policy):
    """Return visible text and (offset, speech) pairs before segmentation."""
    if policy.generation_mode != "model_tag" and policy.trigger_mode != "adaptive":
        return text, ()
    translate = policy.language != "zh" and policy.foreign_text_mode == "translation"
    matches = tuple(_TAG.finditer(text))
    visible, spoken, cursor = [], [], 0
    for index, match in enumerate(matches):
        visible.append(text[cursor:match.start()])
        speech = match.group(1).strip()
        if speech:
            spoken.append((len(_STRAY_TAG.sub("", "".join(visible))), speech))
        following = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        translated = translate and bool("".join(controlled_parts(_STRAY_TAG.sub("", following))[0]).strip())
        if not translated:
            visible.append(match.group(1))
        cursor = match.end()
    visible.append(text[cursor:])
    return _STRAY_TAG.sub("", "".join(visible)), tuple(spoken)


def speech_candidates(text, parts, spans, policy):
    """Map authored speech to the original segments before presentation cleanup."""
    if policy.generation_mode != "model_tag" and policy.trigger_mode != "adaptive":
        candidates = tuple(part.strip() for part in parts)
    else:
        buckets = [[] for _ in parts]
        boundaries = []
        total = 0
        for part in parts:
            total += len(part)
            boundaries.append(total)
        for offset, speech in spans:
            prefix, _ = controlled_parts(text[:offset])
            position = min(sum(map(len, prefix)), total)
            index = next((i for i, end in enumerate(boundaries) if position < end), len(parts) - 1)
            buckets[index].append(speech)
        candidates = tuple("\n".join(bucket) for bucket in buckets)
    return candidates


def speech_decisions(text, parts, spans, policy, *, candidates=None):
    """Retain why a final segment was skipped, after any blank parts were removed."""
    if candidates is None:
        candidates = speech_candidates(text, parts, spans, policy)
    if len(candidates) != len(parts):
        raise ValueError("speech candidates must match their visible segments")
    selected = {"each": range(len(parts)), "first": (0,), "last": (len(parts) - 1,)}[policy.segment_mode]
    decisions = []
    for index, candidate in enumerate(candidates):
        if not parts[index].strip():
            decisions.append(("", "empty_part"))
        elif index not in selected:
            decisions.append(("", "segment_skipped"))
        elif not candidate:
            decisions.append(("", "no_speech"))
        elif len(candidate) > policy.max_speech_chars:
            decisions.append(("", "too_long"))
        else:
            decisions.append((candidate, "planned"))
    return tuple(decisions)


def planned_speech(text, parts, spans, policy):
    return tuple(speech for speech, _ in speech_decisions(text, parts, spans, policy))


def eligible(policy, *, input_text, kind, batch_id):
    if policy.trigger_mode == "request":
        keywords = policy.keywords() or ("语音", "说给我听", "念给我听", "读给我听", "voice", "tts")
        if not any(word in input_text.casefold() for word in keywords):
            return False
    chance = policy.chance(kind)
    return chance >= 1 or chance > 0 and int(digest(batch_id)[:12], 16) / 0xFFFFFFFFFFFF < chance


class VoiceReplyDelivery:
    """Durable per-route cooldown; a failed pre-dispatch synthesis releases its claim."""

    def __init__(self, runtime, now):
        self.runtime, self.now = runtime, now

    def claim(self, envelope):
        with self.runtime.transaction() as connection:
            row = connection.execute("""SELECT v.*, p.batch_id FROM conversation_voice_parts v
                JOIN conversation_parts p ON p.part_id = v.part_id WHERE v.part_id = ?""", (envelope.part_id,)).fetchone()
            if row is None:
                return None
            plan = dict(row)
            if not plan["cooldown_seconds"]:
                return plan
            context = envelope.context
            key = digest([context.scope.installation_id, context.scope.platform, context.scope.kind.value,
                          context.scope.bot_id,
                          context.scope.account_id, context.scope.conversation_id, context.role_binding.role])
            old = connection.execute("""SELECT c.*, p.batch_id FROM conversation_voice_cooldowns c
                LEFT JOIN conversation_parts p ON p.part_id = c.part_id WHERE c.route_key = ?""", (key,)).fetchone()
            at = self.now()
            if old is not None and old["until_at"] > stamp(at):
                return plan if old["batch_id"] == plan["batch_id"] else None
            connection.execute("""INSERT INTO conversation_voice_cooldowns(route_key, part_id, until_at)
                VALUES (?, ?, ?) ON CONFLICT(route_key) DO UPDATE SET part_id = excluded.part_id,
                until_at = excluded.until_at""", (key, envelope.part_id, stamp(at + timedelta(seconds=plan["cooldown_seconds"]))))
            plan["cooldown_key"] = key
            return plan

    def release(self, plan, part_id):
        if plan is not None and plan.get("cooldown_key"):
            with self.runtime.transaction() as connection:
                connection.execute("DELETE FROM conversation_voice_cooldowns WHERE route_key = ? AND part_id = ?",
                                   (plan["cooldown_key"], part_id))

    def record(self, part_id, render_state, component_order, text_hidden):
        """Keep the prepared components separate from the platform delivery receipt."""
        order = tuple(component_order)
        if render_state not in {"not_applicable", "cooldown", "unavailable", "failed", "empty", "invalid", "ready"}:
            raise ValueError("voice render state is invalid")
        if any(kind not in {"text", "image", "voice", "at", "face"} for kind in order):
            raise ValueError("voice component order is invalid")
        with self.runtime.transaction() as connection:
            connection.execute("""UPDATE conversation_voice_diagnostics SET
                render_state = CASE WHEN candidate_reason = 'planned' THEN ? ELSE 'not_applicable' END,
                component_order_json = ?, text_hidden = ? WHERE part_id = ?""",
                (render_state, json.dumps(order, ensure_ascii=False), int(text_hidden), part_id))
