from dataclasses import replace
import unittest

from companion_v2.conversation.segmentation import SegmentationPolicy, LLM_SEGMENT_MARKER as MARKER


class ReplySegmentationTests(unittest.TestCase):
    def setUp(self):
        self.policy = SegmentationPolicy(enabled=True)

    def test_explicit_boundaries_keep_order_and_all_ordinary_text(self):
        self.assertEqual(self.policy.parts(f"第一段\n{MARKER}\n第二段"), ("第一段\n", "第二段"))
        self.assertEqual(self.policy.parts("第一行\n\n第二行"), ("第一行\n\n第二行",))
        for source in ("  原文\r\n第二行\r\n", "emoji 👩‍💻，café。", "普通。句子！"):
            self.assertEqual(self.policy.parts(source), (source,))

    def test_v1_edge_markers_recover_but_inline_markers_only_clean(self):
        for source in (f"甲{MARKER}\n乙", f"甲\n{MARKER}乙", f"甲\n{MARKER}\n乙"):
            self.assertEqual(tuple(p.strip() for p in self.policy.parts(source)), ("甲", "乙"))
        for token in (MARKER, "<< private_companion_split >>", "{{ split_marker }}",
                      "&lt;&lt;PRIVATE_COMPANION_SPLIT&gt;&gt;", r"\<\<PRIVATE_COMPANION_SPLIT\>\>"):
            self.assertEqual(self.policy.parts("hello" + token + "world"), ("hello world",))

    def test_repeated_leading_trailing_markers_never_send_empty_messages(self):
        source = f"{MARKER}\n{MARKER}\n甲\n{MARKER}\n{MARKER}\n乙\n{MARKER}\n"
        self.assertEqual(self.policy.parts(source), ("甲\n", "乙\n"))
        with self.assertRaises(ValueError):
            self.policy.parts(f"{MARKER}\n{MARKER}")

    def test_disabled_and_llm_disabled_still_remove_control_tokens(self):
        for policy in (SegmentationPolicy(), replace(self.policy, llm_controlled=False)):
            self.assertEqual(policy.parts(f"甲\n{MARKER}\n乙"), ("甲\n乙",))
            self.assertEqual(policy.instruction, "")

    def test_maximum_merges_tail_without_truncating(self):
        source = f"\n{MARKER}\n".join(["甲", "乙", "丙", "丁"])
        for maximum in (1, 2, 3):
            parts = replace(self.policy, max_segments=maximum).parts(source)
            self.assertEqual(len(parts), maximum)
            self.assertEqual("".join(parts), "甲\n乙\n丙\n丁")

    def test_fences_quotes_lists_tables_links_and_lazy_lines_stay_atomic(self):
        # Only a fence or a quote keeps the marker as literal text (V1's rule).
        blocks = (f"````text\n```\n{MARKER}\n代码。\n````",
                  f"~~~\n{MARKER}\n代码！\n~~~", f"```\n{MARKER}\n未闭合代码。",
                  f"> 引用。\n> {MARKER}\n懒续行。",
                  "|A|B|\n|---|---|\n|甲。|乙。|", "保留 `a。b` 和 **重点。**。",
                  "[一个链接。](https://example.com/a.b)", "保留 *强调？* 和 _斜体。_。",
                  "A | B\n---|---\n甲。|乙。", "保留 <em>强调。</em> 的格式。")
        policy = replace(self.policy, rules_enabled=True, threshold=1, min_segment_chars=1, max_segments=8)
        for block in blocks:
            with self.subTest(block=block):
                parts = policy.parts(block)
                self.assertEqual(len(parts), 1)
                self.assertNotIn(MARKER, parts[0])
                self.assertEqual(parts[0], block.replace(MARKER, ""))
        source = "开场一。开场二。\n\n" + blocks[0] + "\n\n结尾。"
        parts = policy.parts(source)
        self.assertTrue(any(blocks[0].replace(MARKER, "") in p for p in parts))
        self.assertEqual("".join(parts), source.replace(MARKER, ""))

    def test_a_marker_line_is_a_boundary_unless_fenced_or_quoted(self):
        """V1's rule: indentation never removes a boundary, fences and quotes do."""
        policy = replace(self.policy, threshold=1, min_segment_chars=1, max_segments=8)
        listed = f"- 列表。\n  {MARKER}\n  后续。"
        self.assertEqual(policy.parts(listed), ("- 列表。\n", "  后续。"))
        quoted = f"> 引用。\n> {MARKER}\n懒续行。"
        self.assertEqual(policy.parts(quoted), (quoted.replace(MARKER, ""),))
        fenced = f"```\n{MARKER}\n代码。\n```"
        self.assertEqual(policy.parts(fenced), (fenced.replace(MARKER, ""),))

    def test_rules_respect_threshold_minimum_and_model_priority(self):
        policy = replace(self.policy, rules_enabled=True, threshold=1, min_segment_chars=1, max_segments=3)
        self.assertEqual(policy.parts("甲。乙！丙？丁。"), ("甲。", "乙！", "丙？丁。"))
        self.assertEqual(policy.parts(f"甲\n{MARKER}\n乙一。乙二。乙三。"), ("甲\n", "乙一。", "乙二。乙三。"))
        self.assertEqual(replace(policy, min_segment_chars=3).parts("甲。乙。丙。丁。"), ("甲。乙。", "丙。丁。"))
        self.assertEqual(replace(policy, threshold=100).parts("甲。乙。"), ("甲。乙。",))
        self.assertEqual(replace(policy, rule_mode="paragraphs").parts("甲。乙。\n\n丙。"), ("甲。乙。\n\n", "丙。"))

    def test_explicit_boundary_before_and_after_markdown_without_blank_lines(self):
        for block in ("```python\nprint('x。')\n```", "> 引用。\n> 后续。", "- 第一项\n- 第二项"):
            source = f"开头\n{MARKER}\n{block}\n{MARKER}\n结尾"
            self.assertEqual(self.policy.parts(source), ("开头\n", block + "\n", "结尾"))

    def test_prompt_uses_v1_placeholder_and_policy_validates_types(self):
        policy = replace(self.policy, prompt="只在需要时用 {{ split_marker }}。")
        self.assertIn(f"只在需要时用 {MARKER}。", policy.instruction)
        self.assertNotIn("{{", policy.instruction)
        for changes in ({"enabled": 1}, {"max_segments": True}, {"max_segments": 65},
                        {"threshold": 0}, {"rule_mode": "unknown"}, {"prompt": "x" * 4001}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(policy, **changes)
