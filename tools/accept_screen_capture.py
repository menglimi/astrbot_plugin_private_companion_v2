"""Opt-in local Screen capture through the V2 host with temporary data only."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

if __name__ == "__main__" and sys.argv[1:] != ["--capture-once"]:
    raise SystemExit("Explicit consent required: pass --capture-once to capture the local desktop once")

_sdk_root = TemporaryDirectory(prefix="companion-v2-screen-sdk-")
os.environ["ASTRBOT_ROOT"] = _sdk_root.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_native_screen_flow import NativeScreenFlowTests, provider_module


class RealScreenCapture(NativeScreenFlowTests):
    def capture(self):
        self.captures += 1
        self.jpeg = provider_module()._capture_local()
        return self.jpeg

    async def test_one_real_capture(self):
        host, batch, context = await self.complete_screen()
        self.assertEqual(self.captures, 1)
        self.assertEqual(len(self.screen_images(host, batch, context)), 1)
        image = self.called[-1].original.images[0]
        self.assertEqual(base64.b64decode(image.data_base64), self.jpeg)
        self.assertEqual(image.descriptor.content_hash, hashlib.sha256(self.jpeg).hexdigest())
        self.assertFalse(getattr(self.sent[0], "images", ()))
        self.assertEqual(host.receive(self.event()).unwrap(), batch)
        self.assertEqual(self.captures, 1)
        row = self.runtime.read_one("SELECT state, effect, receipt_ref FROM extension_tool_invocations", ())
        self.assertEqual((row["state"], row["effect"]), ("succeeded", "committed"))
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM screen_captures", ())[0], 1)
        with Image.open(io.BytesIO(self.jpeg)) as decoded:
            dimensions = list(decoded.size)
        self.report = {
            "capture_count": self.captures,
            "image_size": dimensions,
            "bytes": len(self.jpeg),
            "original_sha256": image.descriptor.content_hash,
            "receipt_ref": row["receipt_ref"],
            "model_image_inputs": len(self.called[-1].original.images),
            "outbound_images": len(getattr(self.sent[0], "images", ())),
            "data_root": "temporary",
            "model_and_sender": "local doubles",
        }


def main():
    if sys.argv[1:] != ["--capture-once"]:
        raise SystemExit("Explicit consent required: pass --capture-once to capture the local desktop once")
    case = RealScreenCapture("test_one_real_capture")
    result = unittest.TextTestRunner().run(unittest.TestSuite([case]))
    if not result.wasSuccessful():
        raise SystemExit(1)
    print(json.dumps(case.report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    finally:
        _sdk_root.cleanup()
