"""Framework error leak guard: anchor stripping, dump replacement, and config gating."""

import unittest

from companion_v2.conversation.reply_preparation import prepare_reply
from companion_v2.conversation.segmentation import SegmentationPolicy
from companion_v2.conversation.text_processing import (FRAMEWORK_GUARD_REPLACEMENT, ReplyTextPolicy, text_policy)

TRACEBACK = "Traceback (most recent call last):\n"
FRAME = '  File "C:/host/app.py", line 10, in run\n'


class FrameworkGuardTests(unittest.TestCase):
    def test_anchors_are_stripped_when_enabled(self):
        cleaned, leaked = text_policy({}).framework_guard("在呢[QQ:123456789]，QQ:987654321 怎么啦？")
        self.assertFalse(leaked)
        self.assertEqual(cleaned, "在呢， 怎么啦？")

    def test_disabled_guard_keeps_text_verbatim(self):
        policy = text_policy({"framework_error_guard_enabled": False})
        text = "在呢[QQ:123456789]"
        self.assertEqual(policy.framework_guard(text), (text, False))

    def test_traceback_dump_is_replaced_wholesale(self):
        cleaned, leaked = text_policy({}).framework_guard(TRACEBACK + FRAME + "ValueError: boom")
        self.assertTrue(leaked)
        self.assertEqual(cleaned, FRAMEWORK_GUARD_REPLACEMENT)

    def test_multiple_stack_frames_are_replaced_without_header(self):
        cleaned, leaked = text_policy({}).framework_guard(FRAME + FRAME + "more")
        self.assertTrue(leaked)
        self.assertEqual(cleaned, FRAMEWORK_GUARD_REPLACEMENT)

    def test_single_frame_and_prose_are_kept(self):
        text = '代码里 File "app.py", line 10, in run 这一行是什么意思？'
        self.assertEqual(text_policy({}).framework_guard(text), (text, False))

    def test_prepare_reply_short_circuits_to_single_safe_part(self):
        prepared = prepare_reply(TRACEBACK + FRAME, SegmentationPolicy(), text_policy({}))
        self.assertEqual(prepared.parts, (FRAMEWORK_GUARD_REPLACEMENT,))
        self.assertEqual(prepared.kept_indices, (0,))

    def test_prepare_reply_strips_anchors_without_replacement(self):
        prepared = prepare_reply("好的[QQ:123456789]。", SegmentationPolicy(), text_policy({}))
        self.assertEqual(prepared.parts, ("好的。",))


if __name__ == "__main__":
    unittest.main()
