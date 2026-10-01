from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import unittest

from companion_v2.capabilities.native import (
    NativeArtifact, NativeResult, SCHEMA, parse_manifest, parse_result,
)
from companion_v2.execution.models import ProviderBinding, SideEffect, TaskError, encode


def manifest():
    return {
        "schema": SCHEMA,
        "plugin_id": "astrbot_plugin_image_companion",
        "provider_id": "image.native",
        "generation": "instance-1",
        "package": {
            "extension_id": "image",
            "package_id": "astrbot_plugin_image_companion",
            "publisher_id": "publisher",
            "package_version": "0.5.0",
            "artifact_hash": "package-hash",
            "capabilities": ["image.generate"],
            "dataset_owners": ["image.native"],
        },
        "tools": [{
            "action": "image.generate",
            "capability": "image.generate",
            "source_owner": "image.native",
            "description": "Generate an image.",
            "parameters": {"type": "object", "properties": {
                "prompt": {"type": "string"}}, "required": ["prompt"],
                "additionalProperties": False},
            "side_effect": "external_network",
            "timeout_seconds": 60,
        }],
    }


@dataclass(frozen=True)
class FakeContext:
    scope: object
    audience: object

    @property
    def key(self):
        return "context-key"


class NativeProviderContractTests(unittest.TestCase):
    def test_manifest_is_pinned_to_loaded_plugin_and_version(self):
        parsed = parse_manifest(manifest(), plugin_id="astrbot_plugin_image_companion", version="0.5.0")
        self.assertEqual(parsed.provider_id, "image.native")
        self.assertEqual(parsed.tools[0]["action"], "image.generate")
        with self.assertRaises(ValueError):
            parse_manifest(manifest(), plugin_id="astrbot_plugin_image_companion", version="0.4.1")

    def test_artifact_requires_original_sha256_and_bounded_bytes(self):
        content = b"png bytes"
        artifact = NativeArtifact("artifact-1", "operation-1", hashlib.sha256(content).hexdigest(),
                                  "image/png", len(content), content)
        self.assertEqual(artifact.metadata()["size_bytes"], len(content))
        with self.assertRaises(ValueError):
            artifact.with_content(b"changed")

    def test_result_rejects_mismatched_binding_and_unknown_effect(self):
        binding = {"capability": "image.generate", "provider": "image.native",
                   "version": "0.5.0", "generation": "instance-1"}
        request = {"schema": SCHEMA, "invocation_id": "inv-1", "origin_key": "context-key",
                   "arguments_hash": "args-hash", "binding": binding}
        response = {**request, "state": "unknown", "effect": "committed", "operation_id": "op-1",
                    "receipt_ref": None, "result": None, "artifacts": []}
        with self.assertRaises(ValueError):
            parse_result(response, request=request, side_effect=SideEffect.EXTERNAL_NETWORK)
        response["effect"] = "unknown"
        parsed = parse_result(response, request=request, side_effect=SideEffect.EXTERNAL_NETWORK)
        self.assertEqual((parsed.state, parsed.effect), ("unknown", "unknown"))


if __name__ == "__main__":
    unittest.main()
