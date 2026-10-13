from datetime import datetime, timezone
from types import SimpleNamespace as NS
import unittest

from astrbot_host.core_reply_context import build_core_reply_prompt
from companion_v2.foundation.refs import ScopeKind


class CoreReplyTimeContextTests(unittest.TestCase):
    def test_private_prompt_always_includes_local_clock_and_history_boundary(self):
        settings = {"guidance": "", "calendar_timezone": "Asia/Shanghai", "calendar_enabled": False}
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
        )
        application = NS(
            messages=messages,
            perception_settings=NS(capture=lambda *_args: {"settings": settings}),
        )
        context = NS(scope=NS(kind=ScopeKind.PRIVATE))
        native_input = NS(text="才八点", event_id="clock-test")
        at = datetime(2026, 10, 12, 14, 55, tzinfo=timezone.utc)

        prompt = build_core_reply_prompt(application, context, native_input, at=at)

        self.assertIn('"local_time":"22:55"', prompt.instruction)
        self.assertIn('"timezone":"Asia/Shanghai"', prompt.instruction)
        self.assertIn("检索摘要", prompt.instruction)
        self.assertIn("玩笑或反话", prompt.instruction)
        self.assertIn("才八点", prompt.instruction)
        self.assertIn("不要立刻像报时一样纠正", prompt.instruction)


if __name__ == "__main__":
    unittest.main()
