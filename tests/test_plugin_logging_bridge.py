"""Plugin logs reach the host sink once without hijacking other plugin logs."""

import logging
import unittest
from unittest.mock import patch

from astrbot_host.logging_bridge import (
    PLUGIN_NAME, PluginLogBridge, install_logging_bridge, retire_logging_bridge,
)


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class PluginLoggingBridgeTests(unittest.TestCase):
    def setUp(self):
        self.entry = "data.plugins.astrbot_plugin_private_companion.main"
        # A previous real entry test may have installed a bridge in this process.
        # Establish the clean lifecycle state whose restoration is asserted here.
        retire_logging_bridge(self.entry)
        self.capture = Capture()
        self.sink = logging.Logger("astrbot.plugin." + PLUGIN_NAME, logging.INFO)
        self.sink.addHandler(self.capture)
        self.get_sink = patch("astrbot_host.logging_bridge.LogManager.get_plugin_logger", return_value=self.sink)
        self.get_sink_mock = self.get_sink.start()
        self.addCleanup(self.get_sink.stop)
        self.addCleanup(retire_logging_bridge, self.entry)

    def test_source_and_relative_host_logs_use_formal_plugin_identity_once(self):
        install_logging_bridge(self.entry)
        install_logging_bridge(self.entry)
        logging.getLogger("companion_v2.conversation.generation").info("正文 %r", ("甲", "乙"))
        logging.getLogger(self.entry.rsplit(".", 1)[0] + ".astrbot_host.controller").warning("宿主状态")
        self.assertEqual(len(self.capture.records), 2)
        self.assertEqual(self.capture.records[0].getMessage(), "正文 ('甲', '乙')")
        self.assertTrue(all(record.name == self.sink.name for record in self.capture.records))
        self.get_sink_mock.assert_called_with(PLUGIN_NAME)

    def test_live_level_changes_are_respected_and_other_logs_stay_on_original_route(self):
        source = logging.getLogger("companion_v2")
        prior = getattr(source, "_private_companion_v2_log_bridge", None)
        level, propagate = prior[1:3] if prior is not None else (source.level, source.propagate)
        root_capture = Capture()
        root = logging.getLogger()
        root.addHandler(root_capture)
        self.addCleanup(root.removeHandler, root_capture)
        install_logging_bridge(self.entry)
        self.sink.setLevel(logging.ERROR)
        logging.getLogger("companion_v2.conversation.flow").warning("隐藏警告")
        logging.getLogger("companion_v2.conversation.flow").error("显示错误")
        logging.getLogger("another_plugin.example").warning("其他插件")
        self.assertEqual([record.getMessage() for record in self.capture.records], ["显示错误"])
        self.assertEqual([record.getMessage() for record in root_capture.records], ["其他插件"])
        self.sink.setLevel(logging.DEBUG)
        logging.getLogger("companion_v2.conversation.flow").debug("显示调试")
        self.assertEqual(self.capture.records[-1].getMessage(), "显示调试")
        retire_logging_bridge(self.entry)
        self.assertEqual((source.level, source.propagate), (level, propagate))
        self.assertFalse(any(isinstance(handler, PluginLogBridge) for handler in source.handlers))
