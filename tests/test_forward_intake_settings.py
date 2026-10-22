"""转发设置：schema → HostSettings → StagingConfiguration → StagingProfile → Bridge。

三个数量设置不能超过结构边界（MAX_FORWARDS 4 / MAX_NODES 300 / MAX_DEPTH 4），
节点设置默认仍为 32；旧版合并节点上限 1–300 可无损保留。嵌套展开开关只影响新输入，
已落库的转发事件永远仍可读。

正因为是「只收紧」，接线断了不会报错——下游用默认值，也就是结构上限，
于是 schema 里那三个字段调了等于没调。所以两条都得断言：
**字段存在**（不然 dataclass 构造直接 TypeError，插件加载失败）
与**值真的透到底**（不然是静默失效，比崩溃更难发现）。

注意：本模块只导入插件自身的模块，不导入 `astrbot_host.controller`，
后者会拉进真实 AstrBot SDK。宿主端到端装配在 AstrBot 自带 Python 下另跑。
"""

from dataclasses import asdict
import json
from pathlib import Path
import unittest

from astrbot_host.settings import HostSettings
from companion_v2.adapters.astrbot.staging_config import StagingConfiguration
from companion_v2.conversation.forwards.models import (
    DEFAULT_MAX_NODES, MAX_DEPTH, MAX_FORWARDS, MAX_NODES, ForwardIntakePolicy)


class ForwardIntakeSettingsTests(unittest.TestCase):
    def test_schema_defaults_match_the_policy(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))
        items = schema["runtime"]["items"]
        # 默认值必须与 V2 原有 intake 默认一致；迁移映射另可保留 V1 的自定义值。
        self.assertEqual(items["forward_max_forwards"]["default"], MAX_FORWARDS)
        self.assertEqual(items["forward_max_nodes"]["default"], DEFAULT_MAX_NODES)
        self.assertEqual(items["forward_max_nodes"]["max"], MAX_NODES)
        self.assertEqual(items["forward_max_depth"]["default"], MAX_DEPTH)
        self.assertTrue(items["forward_parse_nested"]["default"])
        self.assertEqual(asdict(ForwardIntakePolicy()),
                         {"max_forwards": MAX_FORWARDS, "max_nodes": DEFAULT_MAX_NODES,
                          "max_depth": MAX_DEPTH, "parse_nested": True})

    def test_default_configuration_parses_and_exposes_the_policy(self):
        # 崩溃点：parse() 早就在构造 ForwardIntakePolicy，但 dataclass 没这个字段。
        settings = HostSettings.parse({})
        self.assertEqual(settings.forward_intake, ForwardIntakePolicy())

    def test_narrowed_limits_survive_the_parser(self):
        settings = HostSettings.parse({"runtime": {
            "forward_max_forwards": 2, "forward_max_nodes": 80, "forward_max_depth": 2,
            "forward_parse_nested": False}})
        self.assertEqual(settings.forward_intake,
                         ForwardIntakePolicy(max_forwards=2, max_nodes=80, max_depth=2, parse_nested=False))

    def test_out_of_range_and_wrong_typed_limits_are_rejected(self):
        # 超过结构上限的值要在配置边界被拒，而不是留到落库时才炸。
        for changes in ({"forward_max_forwards": MAX_FORWARDS + 1}, {"forward_max_nodes": 0},
                        {"forward_max_depth": MAX_DEPTH + 1}, {"forward_max_forwards": "2"},
                        {"forward_max_forwards": True}, {"forward_max_nodes": MAX_NODES + 1},
                        {"forward_parse_nested": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                HostSettings.parse({"runtime": changes})


class ForwardIntakeFingerprintTests(unittest.TestCase):
    """与 streaming / segmentation 同一条 late-field 规则。

    从没表达过的字段不能改变文档哈希，否则升级会让已固定的 profile
    在下一次 probe 时报 `staging_profile_conflict`，插件起不来。
    表达过（收紧过）则必须进哈希，让 profile 真正按新上限重建。
    """

    def _configuration(self, **overrides):
        from tests.staging_bootstrap_support import synthetic_configuration
        from tests.native_adapter_support import FakeHostContext
        from dataclasses import replace
        return replace(synthetic_configuration(FakeHostContext()), **overrides)

    def test_a_default_policy_stays_out_of_the_fingerprint_document(self):
        document = self._configuration().document()
        self.assertNotIn("forward_intake", document)
        # 存读一轮后指纹不变。
        restored = StagingConfiguration.parse(json.dumps(document, ensure_ascii=False))
        self.assertEqual(restored.fingerprint, self._configuration().fingerprint)
        self.assertEqual(restored.forward_intake, ForwardIntakePolicy())

    def test_nondefault_limits_and_nested_switch_enter_the_document_and_round_trip(self):
        narrowed = ForwardIntakePolicy(max_forwards=2, max_nodes=80, max_depth=2, parse_nested=False)
        document = self._configuration(forward_intake=narrowed).document()
        self.assertEqual(document["forward_intake"],
                         {"max_forwards": 2, "max_nodes": 80, "max_depth": 2, "parse_nested": False})
        restored = StagingConfiguration.parse(json.dumps(document, ensure_ascii=False))
        self.assertEqual(restored.forward_intake, narrowed)
        self.assertEqual(restored.fingerprint, self._configuration(forward_intake=narrowed).fingerprint)
        # 任何有效变化都必须改变哈希，否则旧 profile 不会重建。
        self.assertNotEqual(restored.fingerprint, self._configuration().fingerprint)

    def test_an_invalid_policy_is_rejected_at_the_configuration_boundary(self):
        with self.assertRaises(Exception):
            self._configuration(forward_intake={"max_forwards": 2})


if __name__ == "__main__":
    unittest.main()
