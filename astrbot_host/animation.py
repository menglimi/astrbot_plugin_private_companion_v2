"""Decode bounded animation cycles and persist composited, deterministic PNG views."""

import hashlib
import io
import math

from PIL import Image

from companion_v2.conversation.media.animation import (
    AnimationDescriptor, CapturedAnimation, FrameDescriptor, MAX_DECODE_FRAMES, MAX_DECODE_PIXELS,
    MAX_FRAME_DURATION_MS, MAX_FRAME_SIDE, selected_indices,
)
from companion_v2.conversation.media.models import CapturedImage, ImageDescriptor, MAX_IMAGE_BYTES, MAX_TURN_BYTES
from companion_v2.execution.models import TaskError

from .animation_container import verify_animation_container


def duration(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= MAX_FRAME_DURATION_MS:
        return None
    return round(value)


def inspect_animation(content, position, mime, width, height):
    expected = verify_animation_container(content, mime)
    elapsed = 0
    frames, manifest = [], []
    retained = len(content)
    with Image.open(io.BytesIO(content)) as image:
        expected = expected if expected is not None else image.n_frames
        poster = bool(getattr(image, "default_image", False))
        if expected < 1:
            raise TaskError("host_image_invalid", "animation has no display frames")
        if expected > MAX_DECODE_FRAMES or width * height * (expected + int(poster)) > MAX_DECODE_PIXELS:
            raise TaskError("host_animation_limit", "animation exceeds the decoded frame or pixel budget")
        selected = selected_indices(expected)
        loop = image.info.get("loop")
        loop = loop if type(loop) is int and 0 <= loop <= 2**32 - 1 else None
        # Do not ask GIF.n_frames: counting an attacker-controlled file can
        # otherwise traverse an unbounded number of frames before any limit.
        # The verified container count lets us render in this same pass. EOF
        # before that count is a decode failure, never a shorter complete cycle.
        for raw_index in range(expected + int(poster)):
            image.seek(raw_index)
            if image.size != (width, height):
                raise TaskError("host_image_invalid", "animation canvas changed during decode")
            image.load()  # Validate every frame, including frames not selected for the model.
            if poster and raw_index == 0:
                continue
            index = raw_index - int(poster)
            ms = duration(image.info.get("duration"))
            start = elapsed
            elapsed = elapsed + ms if elapsed is not None and ms is not None else None
            if index not in selected:
                continue
            # Pillow applies GIF disposal and APNG/WebP blending while seeking.
            # Preserve that composited canvas, including alpha, rather than the
            # raw update rectangle. Original encoded bytes are stored separately.
            canvas = image.convert("RGBA")
            canvas.thumbnail((MAX_FRAME_SIDE, MAX_FRAME_SIDE), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            canvas.save(stream, format="PNG")
            body = stream.getvalue()
            retained += len(body)
            if len(body) > MAX_IMAGE_BYTES or retained > MAX_TURN_BYTES:
                raise TaskError("host_animation_limit", "animation views exceed the retained original budget")
            descriptor = ImageDescriptor(len(frames), "image/png", canvas.width, canvas.height,
                                         len(body), hashlib.sha256(body).hexdigest())
            frames.append(CapturedImage(descriptor, body))
            manifest.append(FrameDescriptor(index, start, ms, descriptor))
    descriptor = AnimationDescriptor(position, mime, width, height, len(content), hashlib.sha256(content).hexdigest(),
        expected, elapsed, loop, poster, tuple(manifest))
    return CapturedAnimation(descriptor, content, tuple(frames))
