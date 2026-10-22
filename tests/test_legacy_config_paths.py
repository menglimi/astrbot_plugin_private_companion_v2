from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.legacy_config import (
    V1_HOST_CONFIG_NAME,
    V1_PLUGIN_DATA_NAME,
    find_v1_data_root,
    v1_host_config_path,
    v1_plugin_config_path,
)


class LegacyConfigPathTests(unittest.TestCase):
    def test_nested_runtime_root_finds_v1_parent(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary)
            v1 = data / "plugin_data" / V1_PLUGIN_DATA_NAME
            runtime = v1 / "companion-7"
            runtime.mkdir(parents=True)
            (v1 / "companions.json").write_text("{}", encoding="utf-8")

            self.assertEqual(find_v1_data_root(runtime), (v1, "nested-parent"))

    def test_nested_runtime_root_finds_astrbot_config_files(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary)
            runtime = data / "plugin_data" / V1_PLUGIN_DATA_NAME / "companion-7"
            runtime.mkdir(parents=True)
            host_config = data / "config" / V1_HOST_CONFIG_NAME
            reality_config = data / "config" / "astrbot_plugin_reality_companion_config.json"
            host_config.parent.mkdir(parents=True)
            host_config.write_text(json.dumps({"version": 1}), encoding="utf-8")
            reality_config.write_text("{}", encoding="utf-8")

            self.assertEqual(v1_host_config_path(runtime), host_config)
            self.assertEqual(v1_plugin_config_path(runtime, "astrbot_plugin_reality_companion"), reality_config)


if __name__ == "__main__":
    unittest.main()
