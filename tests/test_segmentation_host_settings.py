from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.segmentation_stream_support import host_support, native_provider, ProviderOpenAIOfficial, FunctionTool, ToolSet
from tests.native_adapter_support import FakeEvent, FakeReverseApi, FakeHostContext, final_text
from tests.staging_bootstrap_support import synthetic_configuration, wait_for_batch
from tests.group_host_support import GroupFixture, group_config
from tests.multi_host_support import multi_config
from tests.test_management_access import NOW
from astrbot_host.settings import HostSettings
from astrbot_host.multi_settings import MultiHostSettings
from astrbot_host.controller import AstrBotStagingController
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.adapters.astrbot.staging_config import StagingConfiguration
from companion_v2.conversation.segmentation import SegmentationPolicy, LLM_SEGMENT_MARKER as MARKER
from companion_v2.execution.models import digest


class SegmentationSettingsTests(unittest.TestCase):
    def test_schema_defaults_match_parser_and_existing_fingerprints_are_unchanged(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))
        defaults = {name: value["default"] for name, value in schema["segmentation"]["items"].items()}
        self.assertEqual(defaults, asdict(SegmentationPolicy()))
        self.assertFalse(schema["model"]["items"]["streaming"]["default"])
        common = HostSettings.parse({})
        self.assertEqual(common.segmentation, SegmentationPolicy())
        self.assertFalse(common.streaming)
        old = synthetic_configuration(FakeHostContext())
        self.assertNotIn("segmentation", old.document())
        self.assertNotIn("streaming", old.document()["model"])
        self.assertEqual(StagingConfiguration.parse(json.dumps(old.document())).fingerprint, old.fingerprint)
        multi = MultiHostSettings.parse(multi_config())
        old_multi = asdict(multi)
        for key in ("group_targets", "group_delivery_mode"):
            old_multi.pop(key)
        # Every late field is omitted while it still holds its default, so an already
        # pinned installation keeps its original hash: presentation, segmentation,
        # forward intake, routing and the daily soft ceiling are all adopted outside
        # the identity pin.
        for key in ("streaming", "segmentation", "voice_reply_enabled", "voice_reply_policy", "budget_soft",
                    "additional_providers", "fallback_provider_id", "replacement_rules", "fallback_on_refusal",
                    "forward_intake"):
            old_multi["common"].pop(key)
        self.assertEqual(multi.fingerprint, digest(old_multi))

    def test_enabled_policies_survive_serialization_and_multi_host_assembly(self):
        policy = SegmentationPolicy(enabled=True, rules_enabled=True, max_segments=3, prompt="按需 {{split_marker}}")
        config = replace(synthetic_configuration(FakeHostContext()), streaming=True, segmentation=policy)
        self.assertEqual(StagingConfiguration.parse(json.dumps(config.document(), ensure_ascii=False)), config)
        self.assertNotEqual(config.fingerprint, replace(config, streaming=False).fingerprint)
        self.assertNotEqual(config.fingerprint, replace(config, segmentation=SegmentationPolicy()).fingerprint)
        multi = multi_config()
        multi["model"]["streaming"] = True
        multi["segmentation"] = asdict(policy)
        settings = MultiHostSettings.parse(multi)
        self.assertTrue(settings.common.streaming)
        self.assertEqual(settings.common.segmentation, policy)

    def test_invalid_switches_unknown_fields_and_out_of_range_limits_are_rejected(self):
        for section, changes in (("model", {"streaming": "true"}), ("segmentation", {"max_segments": 0}),
                                 ("segmentation", {"enabled": 1}), ("segmentation", {"unknown": True})):
            with self.subTest(section=section, changes=changes), self.assertRaises(ValueError):
                HostSettings.parse({section: changes})


class SingleHostSegmentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_pinned_settings_load_real_streaming_provider_and_segmented_preview(self):
        temporary = TemporaryDirectory(prefix="companion-segmentation-settings-")
        self.addCleanup(temporary.cleanup)
        native = host_support.WebContext()
        native.provider = native_provider()
        native.provider.client.state.text = final_text(f"甲\n{MARKER}\n乙")
        types = NativeAdapterTypes("4.27.2", FakeEvent, ProviderOpenAIOfficial, FunctionTool, ToolSet, FakeReverseApi)
        config = host_support.host_config(model={"streaming": True})
        config["segmentation"] = {"enabled": True}
        controller = AstrBotStagingController(native, config, Path(temporary.name), native_types=types, now=lambda: NOW)
        self.addAsyncCleanup(controller.terminate)
        (await controller.initialize_profile()).unwrap()
        (await controller.start()).unwrap()
        batch = (await controller.receive_claimed(FakeEvent(native))).unwrap()
        await wait_for_batch(controller.session, batch)
        self.assertEqual([p["text"] for p in (await controller.preview(batch)).unwrap()["parts"]], ["甲\n", "乙"])
        self.assertTrue(native.provider.client.state.calls[0]["stream"])
        self.assertEqual(native.platform.client._api._wsr_api.calls, [])
        await controller.terminate()
        restored = AstrBotStagingController(native, config, Path(temporary.name), native_types=types, now=lambda: NOW)
        self.addAsyncCleanup(restored.terminate)
        (await restored.load_existing()).unwrap()
        self.assertTrue(restored.configuration.streaming)
        self.assertTrue(restored.session.application.generator.segmentation.enabled)
        self.assertEqual([p["text"] for p in (await restored.preview(batch)).unwrap()["parts"]], ["甲\n", "乙"])
        self.assertEqual(len(native.provider.client.state.calls), 1)


class MultiHostSegmentationTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def test_multi_private_and_group_targets_share_policy_without_crossing_routes(self):
        self.native.provider = native_provider()
        self.native.provider.client.state.text = final_text(f"甲\n{MARKER}\n乙")
        self.types = replace(self.types, provider=ProviderOpenAIOfficial, function_tool=FunctionTool, tool_set=ToolSet)
        config = group_config()
        config["model"]["streaming"] = True
        config["segmentation"] = {"enabled": True}
        config["voice_reply"] = {"enabled": True, "private_probability": 0.25, "group_probability": 0.8}
        self.controller = self.make_controller(config)
        app = await self.start_host()
        batches = []
        for event in (self.event("first", "private-first"), self.event("second", "private-second"),
                      self.group_event(identifier="group-first")):
            batch = (await self.controller.receive_claimed(event)).unwrap()
            await wait_for_batch(self.controller.session, batch)
            batches.append(batch)
            rows = app.runtime.read_all("SELECT text FROM conversation_parts WHERE batch_id = ? ORDER BY sequence", (batch,))
            self.assertEqual([r["text"] for r in rows], ["甲\n", "乙"])
            captured = json.loads(app.messages.batch(batch)["contributions_json"])["reply_settings"]["settings"]
            self.assertEqual(captured["voice_probability"], 0.8 if len(batches) == 3 else 0.25)
        scopes = [json.loads(app.messages.batch(batch)["context_json"])["role_binding"]["scope"] for batch in batches]
        self.assertEqual(len({digest(scope) for scope in scopes}), 3)
        self.assertTrue(all(c["stream"] for c in self.native.provider.client.state.calls))
        self.assertEqual(len(self.native.provider.client.state.calls), 3)
        self.assertTrue(all(not p.client._api._wsr_api.calls for p in self.native.platforms.values()))
