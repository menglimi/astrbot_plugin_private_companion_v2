"""Small synthetic MPEG-4 originals; never download recordings for tests."""

import base64
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.video.decoder import inspect_video
from astrbot_host.video.loader import load_native_video
from tests.audio_support import AudioFixture
from tests.native_adapter_support import FakeEvent


@lru_cache(maxsize=8)
def video_bytes(count=12, fps=10, size=(64, 48), tint=0):
    try:
        import cv2
    except ImportError as error:
        raise unittest.SkipTest("video fixture requires the optional OpenCV decoder") from error
    import numpy as np
    with TemporaryDirectory(prefix="v2-video-fixture-") as directory:
        path = Path(directory) / "fixture.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
        if not writer.isOpened():
            raise AssertionError("bundled OpenCV cannot write synthetic MPEG-4")
        try:
            for index in range(count):
                writer.write(np.full((size[1], size[0], 3), ((index * 20 + tint) % 255, 40, 180), dtype=np.uint8))
        finally:
            writer.release()
        return path.read_bytes()


class FakeVideo:
    type = "Video"

    def __init__(self, content=None):
        self.file = "base64://" + base64.b64encode(content if content is not None else video_bytes()).decode("ascii")
        self.url, self.path, self.cover = "", "C:/untrusted.mp4", "https://untrusted.example/cover.jpg"


class VideoFixture(AudioFixture):
    def setUp(self):
        super().setUp()
        self.bridge.video_type, self.bridge.video_loader = FakeVideo, load_native_video

    def video_event(self, identifier="video-1", content=None, *, count=1):
        event = FakeEvent(self.native, event_id=identifier)
        event.message_obj.message = [FakeVideo(content) for _ in range(count)]
        return event

    def captured_video(self, position=0):
        return inspect_video(video_bytes(), position)
