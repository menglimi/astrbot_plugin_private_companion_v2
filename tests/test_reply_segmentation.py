from dataclasses import replace
import json
import unittest

from companion_v2.conversation.segmentation import SegmentationPolicy, LLM_SEGMENT_MARKER as MARKER


class ReplySegmentationTests(unittest.TestCase):
    def setUp(self):
        self.policy = SegmentationPolicy(enabled=True, llm_controlled=True, rules_enabled=False)

    def test_explicit_boundaries_keep_order_and_all_ordinary_text(self):
        self.assertEqual(self.policy.parts(f"第一段\n{MARKER}\n第二段"), ("第一段\n", "第二段"))
        self.assertEqual(self.policy.parts("第一行\n\n第二行"), ("第一行\n\n第二行",))
        for source in ("  原文\r\n第二行\r\n", "emoji 👩‍💻，café。", "普通。句子！"):
            self.assertEqual("".join(self.policy.parts(source)), source)

    def test_v1_edge_markers_recover_but_inline_markers_only_clean(self):
        for source in (f"甲{MARKER}\n乙", f"甲\n{MARKER}乙", f"甲\n{MARKER}\n乙"):
            self.assertEqual(tuple(p.strip() for p in self.policy.parts(source)), ("甲", "乙"))
        for token in (MARKER, "<< private_companion_split >>", "{{ split_marker }}",
                      "&lt;&lt;PRIVATE_COMPANION_SPLIT&gt;&gt;", "&#x3C;&#x3C;PRIVATE_COMPANION_SPLIT&#x3E;&#x3E;",
                      r"\<\<PRIVATE_COMPANION_SPLIT\>\>"):
            self.assertEqual(self.policy.parts("hello" + token + "world"), ("hello world",))

    def test_repeated_leading_trailing_markers_never_send_empty_messages(self):
        source = f"{MARKER}\n{MARKER}\n甲\n{MARKER}\n{MARKER}\n乙\n{MARKER}\n"
        self.assertEqual(self.policy.parts(source), ("甲\n", "乙\n"))
        with self.assertRaises(ValueError):
            self.policy.parts(f"{MARKER}\n{MARKER}")

    def test_disabled_and_llm_disabled_still_remove_control_tokens(self):
        for policy in (SegmentationPolicy(), replace(self.policy, llm_controlled=False)):
            self.assertEqual(policy.parts(f"甲\n{MARKER}\n乙"), ("甲\n乙",))

    def test_rule_only_prompt_guides_coherence_without_model_boundary_protocol(self):
        policy = replace(self.policy, llm_controlled=False,
                         prompt="只在需要时用 {{ split_marker }}。")
        self.assertIn("回应与理由保持连贯", policy.instruction)
        self.assertNotIn(MARKER, policy.instruction)
        self.assertNotIn("split_marker", policy.instruction)
        self.assertEqual(replace(policy, enabled=False).instruction, "")

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
        policy = replace(self.policy, rules_enabled=True, threshold=500, min_segment_chars=1, max_segments=8)
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
        policy = replace(self.policy, rules_enabled=True, threshold=500, min_segment_chars=1, max_segments=3)
        self.assertEqual(policy.parts("甲。乙！丙？丁。"), ("甲。", "乙！", "丙？丁。"))
        self.assertEqual(policy.parts(f"开场一。\n{MARKER}\n乙一。乙二。乙三。"),
                         ("开场一。\n", "乙一。", "乙二。乙三。"))
        self.assertEqual(replace(policy, min_segment_chars=3).parts("甲。乙。丙。丁。"), ("甲。乙。", "丙。丁。"))
        self.assertEqual(replace(policy, threshold=3).parts("甲。乙。"), ("甲。乙。",))
        self.assertEqual(replace(policy, rule_mode="paragraphs").parts("甲。乙。\n\n丙。"), ("甲。乙。\n\n", "丙。"))

    def test_legacy_rules_switch_cannot_disable_rule_completion(self):
        legacy = replace(self.policy, rules_enabled=False, threshold=500,
                         min_segment_chars=1, max_segments=3)
        self.assertEqual(legacy.parts("第一句。第二句！第三句？"),
                         ("第一句。", "第二句！", "第三句？"))

    def test_v1_rule_length_ceiling_short_reply_merging_and_lossless_content(self):
        words = json.dumps(["，", "。", "\n"], ensure_ascii=False)
        policy = replace(self.policy, rules_enabled=True, threshold=500,
                         split_words=words, min_segment_chars=5, max_segments=5)
        source = "我刚才趴在窗边看了一会儿雨，玻璃上全是细细的水线。忽然想起你说今天会很忙，所以来轻轻报个到。"
        parts = policy.parts(source)
        self.assertEqual(tuple(part.strip() for part in parts), (
            "我刚才趴在窗边看了一会儿雨，", "玻璃上全是细细的水线。",
            "忽然想起你说今天会很忙，", "所以来轻轻报个到。"))
        self.assertEqual("".join(parts), source)
        self.assertEqual(replace(policy, threshold=20).parts(source), (source,))

        marked = f"嗯。\n{MARKER}\n我刚才去买咖啡了。\n{MARKER}\n哈哈！\n{MARKER}\n还有点小蛋糕。"
        merged = replace(self.policy, llm_controlled=False, rules_enabled=True, threshold=500).parts(marked)
        self.assertEqual(tuple(part.strip() for part in merged),
                         ("嗯。\n我刚才去买咖啡了。", "哈哈！\n还有点小蛋糕。"))
        self.assertEqual("".join(merged), marked.replace(f"\n{MARKER}\n", "\n"))

    def test_explicit_boundary_before_and_after_markdown_without_blank_lines(self):
        for block in ("```python\nprint('x。')\n```", "> 引用。\n> 后续。", "- 第一项\n- 第二项"):
            source = f"开头\n{MARKER}\n{block}\n{MARKER}\n结尾"
            self.assertEqual(self.policy.parts(source), ("开头\n", block + "\n", "结尾"))

    def test_prompt_uses_v1_placeholder_and_policy_validates_types(self):
        policy = replace(self.policy, prompt="只在需要时用 {{ split_marker }}。")
        self.assertIn(f"只在需要时用 {MARKER}。", policy.instruction)
        self.assertNotIn("{{", policy.instruction)
        self.assertIn("各自读得通", self.policy.instruction)
        self.assertIn("称呼要和所在的完整句子放在一起", self.policy.instruction)
        self.assertIn("简短不等于只说几个字或一句就结束", self.policy.instruction)
        self.assertIn("不能借此删改、概括或重排原文", self.policy.instruction)
        self.assertIn("代码、引用、列表、表格、链接", self.policy.instruction)
        for changes in ({"enabled": 1}, {"max_segments": True}, {"max_segments": 65},
                        {"threshold": 0}, {"rule_mode": "unknown"}, {"prompt": "x" * 4001}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(policy, **changes)
