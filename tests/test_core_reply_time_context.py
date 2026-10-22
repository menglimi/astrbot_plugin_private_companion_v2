from datetime import datetime, timezone
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from astrbot_host.core_reply_context import CURRENT_TIME_INSTRUCTION, build_core_reply_prompt
from companion_v2.foundation.refs import ScopeKind


class CoreReplyTimeContextTests(unittest.TestCase):
    def test_private_prompt_always_includes_local_clock_and_history_boundary(self):
        settings = {"guidance": "", "calendar_timezone": "Asia/Shanghai", "calendar_enabled": False,
                    "platform_enabled": True, "model_route_enabled": True,
                    "configured_modalities_enabled": True}
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
            role_state_context=None,
            expression_style_context=None,
            group_context=NS(authorize=lambda *_args: None),
        )
        application = NS(
            messages=messages,
            perception_settings=NS(capture=lambda *_args: {"settings": settings}),
        )
        context = NS(scope=NS(kind=ScopeKind.PRIVATE))
        native_input = NS(text="才八点", event_id="clock-test")
        at = datetime(2026, 10, 12, 14, 55, tzinfo=timezone.utc)

        prompt = build_core_reply_prompt(application, context, native_input, at=at)

        perception = json.loads(prompt.perception_context)
        self.assertEqual(perception["current_local_time"]["local_time"], "22:55")
        self.assertEqual(perception["current_local_time"]["timezone"], "Asia/Shanghai")
        self.assertNotIn('"local_time":"22:55"', prompt.instruction)
        self.assertIn(CURRENT_TIME_INSTRUCTION, prompt.perception_instructions)
        self.assertEqual(prompt.perception_options, (True, True, True))

        # Native snapshots name their arrival time ``at``. Preparation can run
        # after another reply part has been sent, so its wall time is too late.
        native_input.at = at.replace(minute=54)
        capture = Mock(return_value={})
        interaction = Mock(return_value={})
        application.background_history = NS(capture=capture, interaction=interaction,
                                            read=lambda *_args, **_kwargs: ())
        context.key = "private-time-test"
        build_core_reply_prompt(application, context, native_input, at=at)
        self.assertEqual(capture.call_args.args[1], native_input.at)
        self.assertEqual(interaction.call_args.args[1], native_input.at)

        context.scope.kind = ScopeKind.GROUP
        group_prompt = build_core_reply_prompt(application, context, native_input, at=at)
        self.assertIn("perception", group_prompt.sections)
        self.assertIn("current_local_time", group_prompt.perception_context)
        self.assertEqual(group_prompt.perception_options, (True, True, True))

    def test_stable_role_guidance_is_separate_from_turn_background(self):
        from companion_v2.conversation.reply_settings import GROUP
        from companion_v2.conversation.foreground import ContributionState

        contribution = NS(purpose="relationship_background", state=ContributionState.READY,
                          payload='{"interpretation":"今天一起聊了星星"}')
        messages = NS(
            role_profile_context=NS(capture=lambda *_: {}, instruction=lambda *_: "稳定角色档案"),
            acquaintance=NS(card_contribution=lambda *_args, **_kwargs: None),
            knowledge=None, proactive_inspirations=None, relationship_profile_context=None,
            memory_context=None,
            relationship_context=NS(capture=lambda *_: {}, contributions=lambda *_: (contribution,)),
            life_context=None, role_growth_context=None, role_self_review_context=None,
            open_items_context=None, role_state_context=None, expression_style_context=None,
        )
        settings = {"guidance": "", "calendar_timezone": "Asia/Shanghai", "calendar_enabled": False,
                    "platform_enabled": True, "model_route_enabled": True,
                    "configured_modalities_enabled": True}
        app = NS(messages=messages, perception_settings=NS(capture=lambda *_: {"settings": settings}),
            reply_settings=NS(snapshot=lambda *_: NS(values={
                GROUP + ".style_prompt": "自然地接话",
                GROUP + ".prompt_style_mode": "guided",
                GROUP + ".enable_humanized_expression": True,
                GROUP + ".humanized_expression_prompt": "别像在做汇报",
            })), router=NS(profiles={}), tools=NS())
        context = NS(scope=NS(kind=ScopeKind.PRIVATE), actor=NS(), role_binding=NS(role=NS()), key="context")
        native_input = NS(text="晚上看星星", event_id="split-context-test")

        prompt = build_core_reply_prompt(app, context, native_input, at=datetime(2026, 10, 12, tzinfo=timezone.utc))

        self.assertIn("稳定角色档案", prompt.stable_instruction)
        self.assertIn("自然地接话", prompt.stable_instruction)
        self.assertIn("别像在做汇报", prompt.stable_instruction)
        self.assertNotIn("今天一起聊了星星", prompt.stable_instruction)
        self.assertIn("今天一起聊了星星", prompt.context_instruction)
        self.assertNotIn("稳定角色档案", prompt.context_instruction)


if __name__ == "__main__":
    unittest.main()
