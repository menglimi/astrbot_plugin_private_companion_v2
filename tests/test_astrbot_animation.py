"""Bounded original decoding, frame coverage and disposal/blending semantics."""

import asyncio
from dataclasses import replace
import io
import json
import threading
import unittest
from unittest.mock import patch
import zlib

from PIL import Image

from astrbot_host.media import inspect_image, load_native_image
from companion_v2.adapters.astrbot.native import NativeImageLocator
from companion_v2.conversation.media.animation import AnimationDescriptor, CapturedAnimation, MAX_SELECTED_FRAMES
from companion_v2.conversation.media.codec import image_descriptor
from companion_v2.conversation.media.models import CapturedImage
from companion_v2.execution.models import TaskError, encode
from tests.animation_support import animation_bytes, pixels
from tests.test_conversation_images import FakeImage, image_bytes


class AnimationLoaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gif_apng_and_webp_keep_original_and_every_short_cycle_frame(self):
        for kind in ("GIF", "PNG", "WEBP"):
            with self.subTest(kind=kind):
                content = animation_bytes(kind, durations=[30, 50, 70])
                result = await load_native_image(NativeImageLocator(5, FakeImage(content).file))
                self.assertIsInstance(result, CapturedAnimation)
                self.assertEqual(result.content, content)
                descriptor = result.descriptor
                self.assertEqual((descriptor.position, descriptor.frame_count, descriptor.duration_ms), (5, 3, 150))
                self.assertEqual(descriptor.coverage, "all_frames")
                self.assertEqual([f.start_ms for f in descriptor.frames], [0, 30, 80])
                self.assertEqual([f.duration_ms for f in descriptor.frames], [30, 50, 70])
                self.assertEqual([pixels(f.content) for f in result.frames], [(255, 0, 0, 255), (0, 128, 0, 255), (0, 0, 255, 255)])
                self.assertEqual(image_descriptor(json.loads(encode(descriptor))), descriptor)

    async def test_long_cycle_samples_in_order_including_both_ends(self):
        result = inspect_image(animation_bytes(count=10), 0)
        descriptor = result.descriptor
        self.assertEqual(descriptor.frame_count, 10)
        self.assertEqual(len(result.frames), MAX_SELECTED_FRAMES)
        self.assertEqual(descriptor.coverage, "sampled_frames")
        self.assertEqual([f.index for f in descriptor.frames], [0, 3, 6, 9])
        self.assertEqual([f.start_ms for f in descriptor.frames], [0, 120, 240, 360])
        self.assertEqual(descriptor.duration_ms, 400)

    async def test_apng_default_poster_is_not_an_animation_frame(self):
        result = inspect_image(animation_bytes("PNG", poster=True, durations=[20, 30, 40]), 0)
        self.assertTrue(result.descriptor.default_image)
        self.assertEqual(result.descriptor.frame_count, 3)
        self.assertEqual(result.descriptor.duration_ms, 90)
        self.assertEqual(pixels(result.frames[0].content), (255, 0, 0, 255))
        self.assertEqual([f.index for f in result.descriptor.frames], [0, 1, 2])

    async def test_gif_disposal_restores_background_before_next_update(self):
        palette = [0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (768 - 12)
        frames = [Image.new("P", (4, 4), 1), Image.new("P", (4, 4), 0), Image.new("P", (4, 4), 0)]
        for frame in frames:
            frame.putpalette(palette)
        frames[1].putpixel((0, 0), 2)
        frames[2].putpixel((3, 3), 3)
        output = io.BytesIO()
        frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:], duration=40,
                       transparency=0, background=0, disposal=[1, 2, 1], optimize=False)
        captured = inspect_image(output.getvalue(), 0)
        with Image.open(io.BytesIO(captured.frames[1].content)) as second:
            self.assertEqual(second.getpixel((0, 0)), (0, 255, 0, 255))
            self.assertEqual(second.getpixel((2, 2)), (255, 0, 0, 255))
        with Image.open(io.BytesIO(captured.frames[2].content)) as third:
            self.assertEqual(third.getpixel((0, 0))[3], 0)
            self.assertEqual(third.getpixel((3, 3)), (0, 0, 255, 255))

    async def test_apng_alpha_blend_is_composited_before_frame_extraction(self):
        first = Image.new("RGBA", (4, 4), "red")
        second = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        second.putpixel((0, 0), (0, 0, 255, 255))
        output = io.BytesIO()
        first.save(output, format="PNG", save_all=True, append_images=[second], duration=40,
                   blend=[0, 1], disposal=[0, 0])
        captured = inspect_image(output.getvalue(), 0)
        with Image.open(io.BytesIO(captured.frames[1].content)) as rendered:
            self.assertEqual(rendered.getpixel((0, 0)), (0, 0, 255, 255))
            self.assertEqual(rendered.getpixel((2, 2)), (255, 0, 0, 255))

    async def test_single_frame_gif_and_missing_duration_do_not_invent_animation_time(self):
        captured = inspect_image(image_bytes(kind="GIF"), 0)
        self.assertEqual(captured.descriptor.frame_count, 1)
        self.assertIsNone(captured.descriptor.duration_ms)
        self.assertIsNone(captured.descriptor.frames[0].duration_ms)
        self.assertEqual(captured.descriptor.frames[0].start_ms, 0)

    async def test_frame_views_are_bounded_and_original_dimensions_are_preserved(self):
        content = animation_bytes(count=2, size=(1600, 800))
        captured = inspect_image(content, 0)
        self.assertEqual((captured.descriptor.width, captured.descriptor.height), (1600, 800))
        self.assertEqual((captured.frames[0].descriptor.width, captured.frames[0].descriptor.height), (1024, 512))
        self.assertEqual(captured.content, content)

    async def test_frame_count_and_decoded_pixel_limits_are_checked_before_unbounded_work(self):
        with self.assertRaises(TaskError) as caught:
            inspect_image(animation_bytes(count=257, size=(2, 2)), 0)
        self.assertEqual(caught.exception.code, "host_animation_limit")
        with patch("astrbot_host.animation.MAX_DECODE_PIXELS", 47):
            with self.assertRaises(TaskError) as caught:
                inspect_image(animation_bytes(count=2), 0)
        self.assertEqual(caught.exception.code, "host_animation_limit")

    async def test_corrupt_unselected_frame_is_rejected(self):
        content = bytearray(animation_bytes("PNG", count=10))
        cursor, frame = 8, 0
        while cursor < len(content):
            size = int.from_bytes(content[cursor:cursor + 4], "big")
            if content[cursor + 4:cursor + 8] == b"fcTL":
                frame += 1
            if content[cursor + 4:cursor + 8] == b"fdAT" and frame == 3:
                content[cursor + 12:cursor + 12 + size - 4] = b"\xff" * (size - 4)
                content[cursor + 8 + size:cursor + 12 + size] = zlib.crc32(content[cursor + 4:cursor + 8 + size]).to_bytes(4, "big")
                break
            cursor += 12 + size
        with self.assertRaises(TaskError) as caught:
            inspect_image(bytes(content), 0)
        self.assertEqual(caught.exception.code, "host_image_invalid")

    async def test_truncated_containers_cannot_be_mistaken_for_complete_cycles(self):
        for kind in ("GIF", "PNG", "WEBP"):
            content = animation_bytes(kind, count=6)
            for cut in (1, 2, 12, 20, 37, 38, 43, 45, 46, 81, 82, 87, 89, 90):
                with self.subTest(kind=kind, cut=cut), self.assertRaises(TaskError) as caught:
                    inspect_image(content[:-cut], 0)
                self.assertEqual(caught.exception.code, "host_image_invalid")

    async def test_apng_declared_count_must_match_real_frame_controls(self):
        original = animation_bytes("PNG", count=6)
        for declared in (1, 2, 7):
            content = bytearray(original)
            offset = content.index(b"acTL")
            content[offset + 4:offset + 8] = declared.to_bytes(4, "big")
            content[offset + 12:offset + 16] = zlib.crc32(content[offset:offset + 12]).to_bytes(4, "big")
            with self.subTest(declared=declared), self.assertRaises(TaskError) as caught:
                inspect_image(bytes(content), 0)
            self.assertEqual(caught.exception.code, "host_image_invalid")

    async def test_decoder_runs_in_worker_and_cancellation_never_returns_partial_frames(self):
        entered, release = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        def held(content, position):
            self.assertNotEqual(threading.get_ident(), main_thread)
            entered.set()
            release.wait(3)
            return inspect_image(content, position)
        with patch("astrbot_host.media.inspect_image", side_effect=held):
            pending = asyncio.create_task(load_native_image(NativeImageLocator(0, FakeImage(animation_bytes()).file)))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
            finally:
                release.set()

    async def test_reordered_or_changed_frame_cannot_match_original_manifest(self):
        captured = inspect_image(animation_bytes(), 0)
        with self.assertRaises(TaskError):
            replace(captured, frames=tuple(reversed(captured.frames)))
        with self.assertRaises(TaskError):
            replace(captured.descriptor, frames=tuple(reversed(captured.descriptor.frames)))
        with self.assertRaises(TaskError):
            replace(captured.frames[0], content=b"changed")

    async def test_old_static_descriptor_and_capture_shapes_remain_unchanged(self):
        captured = inspect_image(image_bytes(), 0)
        self.assertIs(type(captured), CapturedImage)
        document = json.loads(encode(captured.descriptor))
        self.assertEqual(set(document), {"position", "mime_type", "width", "height", "byte_count", "content_hash"})
        self.assertNotIsInstance(captured.descriptor, AnimationDescriptor)
        self.assertEqual(image_descriptor(document), captured.descriptor)
