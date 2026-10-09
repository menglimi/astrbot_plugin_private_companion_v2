from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

from astrbot_host.qzone_transport import build_qzone_transport


class QzoneTransportAvailabilityTests(unittest.TestCase):
    def test_no_account_or_manual_cookie_produces_no_transport(self):
        context = SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=()))
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"QZONE_COOKIE": ""}):
            self.assertIsNone(build_qzone_transport(context, data_root=Path(directory)))

    def test_loaded_aiocqhttp_account_keeps_transport_available(self):
        client = object()
        platform = SimpleNamespace(meta=lambda: SimpleNamespace(name="aiocqhttp"),
                                   get_client=lambda: client)
        context = SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=(platform,)))
        with patch.dict(os.environ, {"QZONE_COOKIE": ""}):
            self.assertIsNotNone(build_qzone_transport(context))

    def test_manual_cookie_keeps_transport_available_without_account(self):
        context = SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=()))
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"QZONE_COOKIE": ""}):
            (Path(directory) / "qzone_cookie.txt").write_text("synthetic-cookie", encoding="utf-8")
            self.assertIsNotNone(build_qzone_transport(context, data_root=Path(directory)))


if __name__ == "__main__":
    unittest.main()
