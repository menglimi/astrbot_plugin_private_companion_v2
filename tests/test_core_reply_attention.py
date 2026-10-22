"""Core request injection: one role's bounded attention note reaches the turn."""

import unittest
from types import SimpleNamespace

from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from astrbot_host.core_reply_perception import inject_core_reply_perception_context
from companion_v2.host.role_attention import RoleAttention
from tests.test_role_awareness import GROUP, PRIVATE, context


class Event:
    def __init__(self, prepared):
        self.extra = {CORE_REPLY_CONTEXT_EXTRA: {"prepared": prepared}}

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)


class CoreReplyAttentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_contended_turn_receives_one_transfer_note(self):
        application = SimpleNamespace(role_attention=RoleAttention(wait_seconds=0.05))
        holder_context = context(GROUP)
        holder = await application.role_attention.acquire(holder_context, "holder", window="group")
        try:
            prepared = {"context": context(PRIVATE), "turn_id": "waiter", "prompt_instruction": "BASE",
                        "perception_options": None}
            event = Event(prepared)
            request = SimpleNamespace(extra_user_content_parts=[], prompt="")
            await inject_core_reply_perception_context(event, request, application=application)
            self.assertIn("注意力转场", prepared["prompt_instruction"])
            self.assertTrue(prepared["role_attention"].contended)
            await inject_core_reply_perception_context(event, request, application=application)
            self.assertEqual(prepared["prompt_instruction"].count("注意力转场"), 1)
        finally:
            application.role_attention.finish(holder)


if __name__ == "__main__":
    unittest.main()
