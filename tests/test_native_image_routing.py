"""The model catalog follows the operations enabled by V2 image routes."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.builtins import BundledNativeLease
from astrbot_host.native_extensions.image_native.adapter import PLUGIN_ID
from astrbot_host.native_extensions.image_native.backends import NativeTransportBackend
from astrbot_host.native_extensions.image_native.extension import ImageExtensionAPI
from astrbot_host.native_extensions.image_native.output_configuration import settings as image_settings
from astrbot_host.native_extensions.image_native.types import ImageInvocation, NativeImageError, ReferenceImage
from companion_v2.capabilities.models import FurnitureDescriptor
from companion_v2.product import PRODUCT_VERSION


class NativeImageRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.api = ImageExtensionAPI(data_root=root, config_path=root / "image-config.json",
                                     version=PRODUCT_VERSION)
        lease = BundledNativeLease(PLUGIN_ID, self.api.companion_v2_native(), api=self.api,
            furniture=FurnitureDescriptor("image", "image", "画面工作室", "image"))
        self.registry = NativeExtensionRegistry(NS(get_all_stars=lambda: ()), bundled_extensions=(lease,))
        self.registry._enforcing_image_settings = True
        self.declarations = {item.descriptor.tool.action: item for item in self.registry.declarations()}

    def tearDown(self):
        self.api.close()
        self.temporary.cleanup()

    def save_online(self, platform):
        current = self.api.output_configuration()
        return self.api.save_output_configuration(current["revision"], {
            "enabled": True,
            "backend": "online_api",
            "endpoints": [{"id": "primary", "name": "Primary", "enabled": True,
                           "platform": platform, "model": "image-model", "width": 1024, "height": 1024,
                           "base_url": "https://api.example.test/v1", "timeout_seconds": 60}],
        })

    @staticmethod
    def endpoint(identifier, model):
        return {"id": identifier, "name": identifier, "enabled": True,
                "platform": "openai", "model": model, "width": 1024, "height": 1024,
                "base_url": "https://api.example.test/v1", "timeout_seconds": 60}

    def test_legacy_image_configuration_gets_independent_default_queues(self):
        plugin = NS(config={"native_v2": {"output": {
            "enabled": True, "backend": "auto", "endpoints": [{"id": "legacy"}],
            "sd_webui": {}, "comfyui": {},
        }}})
        routes = image_settings(plugin)["operation_routes"]
        self.assertEqual(routes["generate"], ["online:legacy", "comfyui", "sd_webui"])
        self.assertEqual(routes["edit"], routes["generate"])

        plugin.config["native_v2"]["output"]["operation_routes"] = {
            "generate": ["online:missing", None, "sd_webui"], "edit": []}
        routes = image_settings(plugin)["operation_routes"]
        self.assertEqual(routes["generate"], ["sd_webui"])
        self.assertEqual(routes["edit"], [])

    def test_generation_and_edit_use_independent_priorities_and_mask_edit_shares_edit_queue(self):
        current = self.api.output_configuration()
        saved = self.api.save_output_configuration(current["revision"], {
            "enabled": True,
            "backend": "online_api",
            "endpoints": [self.endpoint("primary", "image-v1"), self.endpoint("secondary", "image-v2")],
            "operation_routes": {
                "generate": ["online:primary", "online:secondary"],
                "edit": ["online:secondary", "online:primary"],
            },
        })
        self.assertEqual(saved["settings"]["operation_routes"]["generate"], ["online:primary", "online:secondary"])
        self.assertEqual(saved["settings"]["operation_routes"]["edit"], ["online:secondary", "online:primary"])

        backend = self.api.companion_v2_native().owner.backend
        route_ids = lambda operation: [item.config["id"] for item in backend._routes(operation)]
        self.assertEqual(route_ids("generate"), ["primary", "secondary"])
        self.assertEqual(route_ids("edit"), ["secondary", "primary"])
        self.assertEqual(route_ids("mask_edit"), route_ids("edit"))

    def test_unknown_model_route_is_rejected_on_save(self):
        current = self.api.output_configuration()
        with self.assertRaises(NativeImageError):
            self.api.save_output_configuration(current["revision"], {
                "enabled": False,
                "backend": "auto",
                "operation_routes": {"generate": ["online:missing"], "edit": []},
            })

    def test_sd_webui_uses_generate_and_edit_parameter_overrides(self):
        backend = NativeTransportBackend("sd_webui", {
            "base_url": "http://127.0.0.1:7860", "timeout_seconds": 60,
            "parameters": {"steps": 18, "generate": {"steps": 28},
                           "edit": {"steps": 42, "cfg_scale": 5.5}},
        }, Path(self.temporary.name))
        generate = ImageInvocation("scope", "generate", "generate", "origin", "generate", "prompt")
        reference = ReferenceImage("ref", b"test-reference", "test-source", "0" * 64)
        edit = ImageInvocation("scope", "edit", "edit", "origin", "edit", "prompt", reference_ids=("ref",))

        self.assertEqual(backend._plan(generate)["parameters"]["steps"], 28)
        edit_parameters = backend._plan(edit, (reference,))["parameters"]
        self.assertEqual(edit_parameters["steps"], 42)
        self.assertEqual(edit_parameters["cfg_scale"], 5.5)

    def test_dormant_provider_keeps_management_api_but_exposes_no_unconfigured_action(self):
        self.assertEqual(self.api.companion_v2_native().manifest()["package"]["capabilities"], [
            "image.generate", "image.edit", "image.mask_edit",
        ])
        self.assertEqual(self.api.companion_v2_native().owner.backend.operations, ())
        self.assertIs(self.registry.image_extension_api(), self.api)
        self.assertTrue(all(self.registry.current_declaration(action) is None for action in self.declarations))

    def test_online_backend_exposes_only_operations_supported_by_its_platform(self):
        self.save_online("minimax")
        self.assertEqual(self.api.companion_v2_native().owner.backend.operations, ("generate",))
        self.assertIsNotNone(self.registry.current_declaration("native:" + PLUGIN_ID + ":image.generate"))
        self.assertIsNone(self.registry.current_declaration("native:" + PLUGIN_ID + ":image.edit"))
        self.assertIsNone(self.registry.current_declaration("native:" + PLUGIN_ID + ":image.mask_edit"))
        self.assertEqual(self.registry.declaration_readiness("native:" + PLUGIN_ID + ":image.mask_edit"),
                         "unsupported")

        self.save_online("openai")
        self.assertEqual(self.api.companion_v2_native().owner.backend.operations, ("generate", "edit"))
        self.assertIsNotNone(self.registry.current_declaration("native:" + PLUGIN_ID + ":image.edit"))
        self.assertIsNone(self.registry.current_declaration("native:" + PLUGIN_ID + ":image.mask_edit"))
        self.assertEqual(self.registry.declaration_readiness("native:" + PLUGIN_ID + ":image.mask_edit"),
                         "unsupported")

    def test_sd_webui_enables_masked_edit_after_a_real_endpoint_is_configured(self):
        current = self.api.output_configuration()
        self.api.save_output_configuration(current["revision"], {
            "enabled": True,
            "backend": "sd_webui",
            "endpoints": [],
            "sd_webui": {"base_url": "http://127.0.0.1:7860", "timeout_seconds": 60,
                          "parameters": {}},
            "comfyui": {},
        })
        self.assertEqual(self.api.companion_v2_native().owner.backend.operations,
                         ("generate", "edit", "mask_edit"))
        self.assertIsNotNone(self.registry.current_declaration("native:" + PLUGIN_ID + ":image.mask_edit"))


if __name__ == "__main__":
    unittest.main()
