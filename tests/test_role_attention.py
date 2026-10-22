"""One role, one foreground mouth: bounded attention lease behavior."""

import asyncio
import unittest

from companion_v2.host.role_attention import AttentionLease, RoleAttention
from tests.test_role_awareness import GROUP, NOW, PRIVATE, ROLE, FakeSettings, context


class RoleAttentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_window_waits_and_receives_a_transfer_note(self):
        attention = RoleAttention(wait_seconds=0.5)
        first = await attention.acquire(context(PRIVATE), "private-turn", window="private")
        pending = asyncio.create_task(attention.acquire(context(GROUP), "group-turn", window="group"))
        await asyncio.sleep(0.05)
        self.assertFalse(pending.done())
        attention.finish(first)
        second = await pending
        self.assertFalse(second.contended)
        self.assertGreater(second.waited_ms, 0)
        self.assertIn("注意力转场", attention.note(second, min_wait_ms=0))
        self.assertEqual(attention.active(context(GROUP)), second)
        attention.finish(second)

    async def test_timeout_reports_contention_and_does_not_block_forever(self):
        attention = RoleAttention(wait_seconds=0.05)
        first = await attention.acquire(context(GROUP), "group-turn", window="group")
        contended = await attention.acquire(context(PRIVATE), "private-turn", window="private")
        self.assertTrue(contended.contended)
        self.assertEqual(contended.other_window, "group")
        self.assertIn("仍在生成回复", attention.note(contended))
        self.assertIs(attention.active(context(GROUP)), first)
        attention.finish(contended)
        attention.finish(first)
        self.assertIsNone(attention.active(context(GROUP)))
        again = await attention.acquire(context(PRIVATE), "private-again", window="private")
        self.assertFalse(again.contended)
        attention.finish(again)

    async def test_leases_are_role_scoped_and_finish_is_idempotent(self):
        attention = RoleAttention(wait_seconds=0.05)
        first = await attention.acquire(context(PRIVATE), "role-a", window="private")
        other_role = context(PRIVATE, role=type(ROLE)(ROLE.installation_id, ROLE.kind, "role-b"))
        second = await attention.acquire(other_role, "role-b", window="private")
        self.assertFalse(second.contended)
        attention.finish(first)
        attention.finish(first)
        self.assertIsNone(attention.active(context(PRIVATE)))
        self.assertIs(attention.active(other_role), second)
        attention.finish(second)

    async def test_short_wait_does_not_add_a_transfer_note(self):
        attention = RoleAttention(wait_seconds=0.5)
        lease = AttentionLease("k", "t", "private", waited_ms=10)
        self.assertEqual(attention.note(lease), "")
        self.assertIn("注意力转场", attention.note(lease, min_wait_ms=0))

    async def test_wait_seconds_are_read_from_person_settings(self):
        attention = RoleAttention(wait_seconds=0.5, settings=FakeSettings(
            **{"person.cross_window_attention_wait_seconds": 0}))
        first = await attention.acquire(context(GROUP), "holder", window="group")
        second = await attention.acquire(context(PRIVATE), "waiter", window="private")
        self.assertTrue(second.contended)
        attention.finish(second)
        attention.finish(first)


if __name__ == "__main__":
    unittest.main()
