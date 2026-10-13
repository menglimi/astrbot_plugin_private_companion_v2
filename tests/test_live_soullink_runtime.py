"""The bundled SoulLink bridge starts and stops with the real local engine."""

import asyncio
import math
import shutil
import unittest

from tests import test_astrbot_staging_host as host_support
from astrbot_host.native_extensions.live.soullink_runtime import SoullinkRuntimeBridge


NODE_PATH = shutil.which("node")


@unittest.skipUnless(NODE_PATH, "Node.js is required for the bundled SoulLink engine")
class LiveSoullinkRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bundled_engine_handshake_frames_reconfigure_and_graceful_stop(self):
        frames = asyncio.Queue()
        bridge = SoullinkRuntimeBridge(node_path=NODE_PATH, on_frame=frames.put_nowait)
        self.addAsyncCleanup(bridge.stop)

        async def next_frame(predicate=lambda frame: True):
            async def receive():
                while True:
                    frame = await frames.get()
                    if predicate(frame):
                        return frame
            return await asyncio.wait_for(receive(), timeout=3)

        started = await bridge.start({"style": "calm", "parameterGain": 1.2,
                                      "bodyMotionGain": 0.9})
        self.assertTrue(started, bridge.last_error)
        process = bridge.process
        self.assertTrue(bridge.running)
        self.assertEqual(bridge.engine_info["engine"], "@soullink-emotion/engine")
        self.assertEqual(bridge.engine_info["version"], bridge.ENGINE_VERSION)
        self.assertIn("lively", bridge.engine_info["styles"])

        frame = await next_frame(lambda frame: frame["parameterGain"] == 1.2)
        self.assertTrue(frame["live2dParams"])
        self.assertTrue(all(math.isfinite(value) for value in frame["live2dParams"].values()))
        self.assertEqual(frame["bodyMotionGain"], 0.9)

        self.assertTrue(await bridge.trigger({"emotion": "开心", "intensity": 0.8}))
        frame = await next_frame(lambda frame: (frame.get("intent") or {}).get("emotion") == "happy")
        self.assertEqual(frame["intent"]["naturalEmotion"], "happy")

        self.assertTrue(await bridge.react_to_text("贴贴，今天玩得很开心"))
        frame = await next_frame(lambda frame: (frame.get("intent") or {}).get("sourceMessage") == "贴贴，今天玩得很开心")
        self.assertEqual(frame["intent"]["emotion"], "shy")

        self.assertTrue(await bridge.configure(style="lively", fps=12, parameterGain=2,
                                               bodyMotionGain=1.5))
        frame = await next_frame(lambda frame: frame["parameterGain"] == 2)
        self.assertEqual(frame["bodyMotionGain"], 1.5)
        self.assertEqual(frame["motionStyle"]["spontaneity"], 2)

        self.assertTrue(await bridge.reset())
        frame = await next_frame(lambda frame: frame["parameterGain"] == 2 and frame["intent"] is None)
        self.assertEqual(frame["state"], "IDLE")
        self.assertGreater(bridge.frames_received, 0)
        self.assertEqual(bridge.last_error, "")

        await bridge.stop()
        self.assertEqual(process.returncode, 0)
        self.assertFalse(bridge.running)
        self.assertIsNone(bridge.process)
        self.assertIsNone(bridge._reader_task)
        self.assertIsNone(bridge._stderr_task)
        await bridge.stop()


if __name__ == "__main__":
    unittest.main()
