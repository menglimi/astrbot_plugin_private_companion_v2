import unittest

from companion_v2.legacy.image_configuration_migration import convert_image_configuration


class ImageConfigurationMigrationTests(unittest.TestCase):
    def test_online_queue_keeps_order_headers_and_provider_size_labels(self):
        result = convert_image_configuration({"photo_action_config": {
            "photo_generation_backend": "external",
            "enable_photo_reference_image": True,
            "external_image_api_endpoints": [
                {"name": "Agnes", "platform": "agnes", "base_url": "https://api.example.test/v1",
                 "api_key": "secret-one", "model": "agnes-image-2.1-flash", "size": "2K",
                 "timeout_seconds": 120, "custom_headers": "X-Region: cn"},
                {"name": "Second", "platform": "openai", "base_url": "https://api2.example.test/v1",
                 "api_key": "secret-two", "model": "image-v2", "size": "768x1344",
                 "timeout_seconds": 90, "custom_headers": {"X-Route": "fallback"}},
            ],
        }})

        self.assertEqual(result.output_changes["backend"], "online_api")
        endpoints = result.output_changes["endpoints"]
        self.assertEqual([item["name"] for item in endpoints], ["Agnes", "Second"])
        self.assertEqual((endpoints[0]["width"], endpoints[0]["height"], endpoints[0]["size_label"]),
                         (2048, 2048, "2K"))
        self.assertEqual(endpoints[0]["custom_headers"], {"X-Region": "cn"})
        self.assertEqual(endpoints[1]["custom_headers"], {"X-Route": "fallback"})
        self.assertEqual(result.output_changes["operation_routes"]["generate"],
                         ["online:legacy-image-01", "online:legacy-image-02"])
        self.assertTrue(result.output_changes["enabled"])

    def test_non_executable_legacy_modes_and_network_settings_remain_auditable(self):
        result = convert_image_configuration({"photo_action_config": {
            "photo_generation_backend": "tool_call",
            "custom_photo_tool_name": "generate_selfie",
            "custom_photo_tool_prompt_param": "description",
            "custom_photo_tool_kind_param": "kind",
            "custom_photo_tool_reference_param": "image_path",
            "custom_photo_tool_extra_params": "{\"steps\": 24}",
            "COMFYUI_TEXT2IMG_WORKFLOW_NAME": "landscape",
            "COMFYUI_SELFIE_WORKFLOW_NAME": "portrait",
            "external_image_download_proxy": "http://127.0.0.1:7890",
            "external_image_download_use_environment_proxy": True,
        }})

        self.assertEqual(result.output_changes["backend"], "auto")
        self.assertEqual(result.output_changes["legacy_backend"], "tool_call")
        self.assertFalse(result.output_changes["enabled"])
        self.assertEqual(result.output_changes["operation_routes"], {"generate": [], "edit": []})
        self.assertEqual(result.output_changes["legacy_options"], {
            "tool_call": {"name": "generate_selfie", "prompt_param": "description",
                          "kind_param": "kind", "reference_param": "image_path",
                          "extra_params": "{\"steps\": 24}"},
            "comfyui_workflow_names": {"generate": "landscape", "selfie": "portrait"},
        })
        self.assertEqual(result.output_changes["network"], {
            "download_proxy": "http://127.0.0.1:7890", "use_environment_proxy": True,
        })
        difference_fields = {item["field"] for item in result.differences}
        self.assertIn("image.output.legacy_options.tool_call", difference_fields)
        self.assertIn("image.output.legacy_options.comfyui_workflow_names", difference_fields)

    def test_auto_size_label_is_kept_with_a_usable_v2_dimension_fallback(self):
        result = convert_image_configuration({"photo_action_config": {
            "external_image_api_endpoints": [{"name": "Auto size", "platform": "openai",
                "base_url": "https://api.example.test/v1", "model": "image-v1", "size": "auto"}],
        }})

        endpoint = result.output_changes["endpoints"][0]
        self.assertEqual(endpoint["size_label"], "auto")
        self.assertEqual((endpoint["width"], endpoint["height"]), (1024, 1024))

    def test_sdgen_is_not_misidentified_as_native_sd_webui(self):
        result = convert_image_configuration({"photo_action_config": {
            "photo_generation_backend": "sdgen",
        }})

        self.assertEqual(result.output_changes["backend"], "auto")
        self.assertEqual(result.output_changes["legacy_backend"], "sdgen")
        self.assertFalse(result.output_changes["enabled"])
        self.assertEqual(result.output_changes["operation_routes"], {"generate": [], "edit": []})
        self.assertTrue(any(item["kind"] == "manual_mapping" for item in result.differences))

    def test_auto_platform_retains_special_provider_protocol(self):
        result = convert_image_configuration({"photo_action_config": {
            "photo_generation_backend": "external",
            "external_image_api_endpoints": [{"name": "ModelScope", "platform": "auto",
                "base_url": "https://api-inference.modelscope.cn/v1", "model": "sample"}],
        }})
        self.assertEqual(result.output_changes["endpoints"][0]["platform"], "modelscope")
        self.assertFalse(result.output_changes["enabled"])

    def test_local_backend_stays_dormant_until_its_connection_is_bound(self):
        result = convert_image_configuration({"photo_action_config": {
            "photo_generation_backend": "comfyui",
            "COMFYUI_TEXT2IMG_WORKFLOW_NAME": "legacy-flow",
        }})
        self.assertEqual(result.output_changes["operation_routes"]["generate"], ["comfyui"])
        self.assertFalse(result.output_changes["enabled"])
        self.assertTrue(any(item["kind"] == "incomplete_backend" for item in result.differences))


if __name__ == "__main__":
    unittest.main()
