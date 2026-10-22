"""A synthetic role-state snapshot reaches the ordinary AstrBot provider request."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from astrbot_host.core_reply_context import build_core_reply_prompt
from astrbot_host.core_reply_perception import (
    inject_core_reply_perception_context,
    inject_core_reply_perception_policy,
)
from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.conversation.reply_settings import GROUP
from companion_v2.conversation.state_context import ConversationStateContext
from companion_v2.execution.models import TaskError, encode
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.role_work.state.access import RoleStateAccess


AT = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)


class Event:
    def __init__(self):
        self.extra = {}

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)


class CoreReplyRoleStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_snapshot_is_composed_and_sent_as_temporary_provider_context(self):
        simulation = {
            "state": "saved",
            "revision": 4,
            "values": {
                "energy": 15,
                "hunger": "有点饿",
                "health": None,
                "sleep": None,
                "busy": None,
                "mood": None,
                "location": None,
                "cycle": None,
                "conditions": [],
            },
            "mood_dynamics": {"neutral": True},
        }
        intensity_material = ContextContribution(
            "synthetic-role-state-intensity", "role.state", "role_state_intensity",
            ContributionState.READY, encode({"intensity": 80}),
        )
        private_scope = ScopeRef("test-install", "qq-main", ScopeKind.PRIVATE, "member-1",
                                 "bot-1", "account-1", "private-window", "private-session")
        private_source = SourceRef("private-origin-secret", "test.private", private_scope,
                                   VersionRef("private-origin-secret", 1), AT)
        state_material = ContextContribution(
            "synthetic-role-state", "role.state", "role_state", ContributionState.READY,
            encode({"simulation": simulation, "activities": {"items": [], "partial": False}}),
            private_source,
        )
        owner_enabled = {"value": True}
        owner = NS(
            capture=lambda *_args: {"state": "ready"} if owner_enabled["value"] else None,
            contributions=lambda snapshot, *_args: ((state_material, intensity_material)
                if snapshot is not None else ()),
            instruction=ConversationStateContext.instruction,
        )
        messages = NS(
            role_profile_context=None,
            acquaintance=NS(card_contribution=lambda *_args, **_kwargs: None),
            knowledge=None,
            proactive_inspirations=None,
            relationship_profile_context=None,
            memory_context=None,
            relationship_context=None,
            life_context=None,
            role_growth_context=None,
            role_self_review_context=None,
            open_items_context=None,
            role_state_context=owner,
            expression_style_context=None,
            group_context=NS(authorize=lambda *_args: None),
            group_network=NS(contribution=lambda *_args, **_kwargs: None),
            group_memory=NS(context=NS(capture=lambda *_args: {},
                                      contributions=lambda *_args: ())),
        )
        perception_settings = {
            "guidance": "",
            "calendar_timezone": "Asia/Shanghai",
            "calendar_enabled": False,
            "platform_enabled": False,
            "model_route_enabled": False,
            "configured_modalities_enabled": False,
        }
        reply_values = {
            GROUP + ".style_prompt": "",
            GROUP + ".prompt_style_mode": "free",
            GROUP + ".enable_humanized_expression": False,
            GROUP + ".humanized_expression_prompt": "",
        }
        application = NS(
            messages=messages,
            perception_settings=NS(capture=lambda *_args: {"settings": perception_settings}),
            reply_settings=NS(snapshot=lambda *_args: NS(values=reply_values)),
            router=NS(profiles={}),
            tools=NS(),
        )
        application.tools.group_participation = None
        native_input = NS(text="你现在还好吗？", event_id="synthetic-role-state-turn", received_at=AT)

        for scope_kind in (ScopeKind.PRIVATE, ScopeKind.GROUP):
            with self.subTest(scope=scope_kind.value):
                scope = NS(kind=scope_kind, platform="qq-main", native_scope_id="group-1")
                actor = NS(principal=NS(native_account_id="member-1"))
                context = NS(scope=scope, actor=actor, role_binding=NS(role=NS()),
                             key="synthetic-role-state-context")
                prompt = build_core_reply_prompt(application, context, native_input, at=AT)

                self.assertIn("role_state", prompt.sections)
                self.assertIn("角色当前状态", prompt.context_instruction)
                self.assertIn("精力很低", prompt.context_instruction)
                self.assertIn("可感知的状态色彩", prompt.context_instruction)
                # An absent sleep value must not be primed by an insomnia
                # example, and the role's own symptoms are not user symptoms.
                self.assertNotIn("我昨晚没休息好，今天有点困", prompt.context_instruction)
                self.assertIn("没有吃睡记录不等于没吃没睡", prompt.context_instruction)
                self.assertIn("角色自己的状态不表示用户也有同样经历", prompt.context_instruction)
                if scope_kind is ScopeKind.GROUP:
                    self.assertIn("group_speaker", prompt.sections)

                event = Event()
                event.extra[CORE_REPLY_CONTEXT_EXTRA] = {"prepared": {
                    "context": context,
                    "native_input": native_input,
                    "prompt_instruction": prompt.context_instruction,
                    "stable_prompt_instruction": prompt.stable_instruction,
                    "perception_options": prompt.perception_options,
                    "perception_context": prompt.perception_context,
                    "perception_instructions": prompt.perception_instructions,
                    "perception_guidance": prompt.perception_guidance,
                }}
                request = NS(
                    system_prompt="你是当前绑定的人格。",
                    prompt=native_input.text,
                    model=None,
                    image_urls=[],
                    audio_urls=[],
                    func_tool=None,
                    extra_user_content_parts=[],
                )

                inject_core_reply_perception_policy(event, request)
                await inject_core_reply_perception_context(event, request)

                self.assertIn("让它作为持续的人物体验自然影响", request.system_prompt)
                self.assertIn("不要把角色的经历改写成用户的经历", request.system_prompt)
                self.assertIn("不要仅凭角色自己的状态追问用户", request.system_prompt)
                self.assertEqual(len(request.extra_user_content_parts), 1)
                self.assertTrue(request.extra_user_content_parts[0]._no_save)
                payload_text = request.extra_user_content_parts[0].text
                payload = json.loads(payload_text.removeprefix("<companion_v2_context>\n")
                                     .removesuffix("\n</companion_v2_context>"))
                self.assertIn("精力很低", payload["companion_background"])
                self.assertIn("有点饿", payload["companion_background"])

                provider = object.__new__(ProviderOpenAIOfficial)
                assembled = await provider.assemble_context(
                    native_input.text, extra_user_content_parts=request.extra_user_content_parts)
                request_text = "\n".join(part["text"] for part in assembled["content"] if part["type"] == "text")
                self.assertIn("角色当前状态", request_text)
                self.assertIn("精力很低", request_text)
                self.assertNotIn("energy=15", request_text)
                self.assertNotIn("private-origin-secret", request_text)
                if scope_kind is ScopeKind.GROUP:
                    owner_enabled["value"] = False
                    disabled_prompt = build_core_reply_prompt(application, context, native_input, at=AT)
                    self.assertNotIn("role_state", disabled_prompt.sections)
                    self.assertNotIn("角色当前状态", disabled_prompt.context_instruction)
                    owner_enabled["value"] = True

    def test_group_injection_uses_only_the_current_collective_reply_authorization(self):
        scope = ScopeRef("test-install", "qq-main", ScopeKind.GROUP, "group-1",
                         "bot-1", "account-1", "group-window", "group-session")
        subject = SubjectRef("test-install", SubjectKind.HUMAN, "member-1")
        context = NS(scope=scope, actor=NS(subject=subject), audience=group_audience(scope, subject))
        tasks = NS(runtime=Mock(), now=Mock(return_value=AT),
                   check_context_access=Mock(return_value=Outcome.success(True)))
        access = RoleStateAccess(tasks, lambda _context: ({"enabled": True}, "token"))

        access.check_injection(context, at=AT)

        tasks.check_context_access.assert_called_once_with(
            context, action="conversation.reply", observed_at=AT)

        tasks.check_context_access.reset_mock()
        disabled = RoleStateAccess(tasks, lambda _context: ({"enabled": False}, "token"))
        with self.assertRaises(TaskError) as denied:
            disabled.check_injection(context, at=AT)
        self.assertEqual(denied.exception.code, "role_state_disabled")
        tasks.check_context_access.assert_called_once_with(
            context, action="conversation.reply", observed_at=AT)

        tasks.check_context_access.reset_mock()
        wrong_audience = group_audience(scope, SubjectRef("test-install", SubjectKind.HUMAN, "other-member"))
        context.audience = wrong_audience
        with self.assertRaises(TaskError) as denied:
            access.check_injection(context, at=AT)
        self.assertEqual(denied.exception.code, "private_domain_audience")
        tasks.check_context_access.assert_not_called()


if __name__ == "__main__":
    unittest.main()
