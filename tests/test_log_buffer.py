import logging
import unittest

from log_buffer import LogRingBuffer, install_log_buffer, snapshot


class LogBufferTests(unittest.TestCase):
    def test_ring_buffer_filters_by_level_and_query(self):
        buffer = LogRingBuffer(capacity=10)
        logger = logging.getLogger("test.companion.logs")
        logger.handlers = [buffer]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.info("群聊 主动联系 已跳过")
        logger.warning("模型调用超时")
        rows, _ = buffer.snapshot(level="WARNING")
        self.assertEqual([row["message"] for row in rows], ["模型调用超时"])
        rows, _ = buffer.snapshot(query="主动")
        self.assertEqual(len(rows), 1)

    def test_install_is_idempotent(self):
        first = install_log_buffer()
        second = install_log_buffer()
        self.assertIs(first, second)
        self.assertGreaterEqual(len(logging.getLogger("astrbot_plugin_private_companion").handlers), 1)

    def test_empty_before_install(self):
        rows, cursor = snapshot(limit=10)
        self.assertIsInstance(rows, list)
        self.assertIsNone(cursor)


if __name__ == "__main__":
    unittest.main()
