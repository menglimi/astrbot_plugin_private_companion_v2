"""Original animation manifests and the exact composited frames offered to a model."""

from dataclasses import dataclass, field

from companion_v2.execution.models import TaskError

from .models import CapturedImage, ImageDescriptor, ImageConversationEvent, PromptImage, MIME_TYPES, fits_budget


MAX_DECODE_FRAMES = 256
MAX_DECODE_PIXELS = 64 * 1024 * 1024
MAX_SELECTED_FRAMES = 4
MAX_FRAME_SIDE = 1024
MAX_FRAME_DURATION_MS = 2**31 - 1
PROFILE = "pillow-composited-png.v1"


def selected_indices(count):
    size = min(count, MAX_SELECTED_FRAMES)
    return (0,) if size == 1 else tuple(i * (count - 1) // (size - 1) for i in range(size))


def valid_time(value, maximum):
    return value is None or type(value) is int and 0 <= value <= maximum


@dataclass(frozen=True)
class FrameDescriptor:
    index: int
    start_ms: int | None
    duration_ms: int | None
    image: ImageDescriptor

    def __post_init__(self):
        if (type(self.index) is not int or not 0 <= self.index < MAX_DECODE_FRAMES
                or not valid_time(self.start_ms, MAX_FRAME_DURATION_MS * MAX_DECODE_FRAMES)
                or not valid_time(self.duration_ms, MAX_FRAME_DURATION_MS)
                or type(self.image) is not ImageDescriptor or self.image.mime_type != "image/png"
                or max(self.image.width, self.image.height) > MAX_FRAME_SIDE):
            raise TaskError("animation_manifest_invalid", "rendered frame must retain its bounded original position and timing")


@dataclass(frozen=True)
class AnimationDescriptor(ImageDescriptor):
    _mime_types = MIME_TYPES | {"image/gif"}
    frame_count: int
    duration_ms: int | None
    loop_count: int | None
    default_image: bool
    frames: tuple[FrameDescriptor, ...]
    renderer: str = PROFILE

    def __post_init__(self):
        super().__post_init__()
        if (self.mime_type not in {"image/gif", "image/png", "image/webp"}
                or type(self.frame_count) is not int or not 1 <= self.frame_count <= MAX_DECODE_FRAMES
                or self.width * self.height * (self.frame_count + int(self.default_image)) > MAX_DECODE_PIXELS
                or not valid_time(self.duration_ms, MAX_FRAME_DURATION_MS * MAX_DECODE_FRAMES)
                or not valid_time(self.loop_count, 2**32 - 1) or type(self.default_image) is not bool
                or (self.default_image and self.mime_type != "image/png")
                or not isinstance(self.frames, tuple) or any(not isinstance(f, FrameDescriptor) for f in self.frames)
                or tuple(f.index for f in self.frames) != selected_indices(self.frame_count)
                or tuple(f.image.position for f in self.frames) != tuple(range(len(self.frames)))
                or self.renderer != PROFILE or not fits_budget((self,))):
            raise TaskError("animation_manifest_invalid", "animation manifest must preserve bounded coverage and originals")
        starts = [f.start_ms for f in self.frames if f.start_ms is not None]
        last = self.frames[-1]
        if (starts != sorted(starts) or self.frames[0].start_ms != 0
                or (self.duration_ms is not None and (last.start_ms is None or last.duration_ms is None
                    or last.start_ms + last.duration_ms != self.duration_ms))):
            raise TaskError("animation_manifest_invalid", "frame timing does not match its original cycle")

    @property
    def rendered_count(self):
        return len(self.frames)

    @property
    def retained_bytes(self):
        return self.byte_count + sum(f.image.byte_count for f in self.frames)

    @property
    def coverage(self):
        return "all_frames" if len(self.frames) == self.frame_count else "sampled_frames"


@dataclass(frozen=True)
class CapturedAnimation(CapturedImage):
    frames: tuple[CapturedImage, ...] = field(repr=False)

    def __post_init__(self):
        super().__post_init__()
        if (not isinstance(self.descriptor, AnimationDescriptor) or not isinstance(self.frames, tuple)
                or any(type(f) is not CapturedImage for f in self.frames)
                or tuple(f.descriptor for f in self.frames) != tuple(f.image for f in self.descriptor.frames)):
            raise TaskError("animation_content_changed", "animation must retain every selected frame original")


@dataclass(frozen=True)
class PromptAnimation(PromptImage):
    frames: tuple[PromptImage, ...] = field(repr=False)

    def __post_init__(self):
        super().__post_init__()
        if (not isinstance(self.descriptor, AnimationDescriptor) or not isinstance(self.frames, tuple)
                or any(type(f) is not PromptImage or f.parent != self.source for f in self.frames)
                or tuple(f.descriptor for f in self.frames) != tuple(f.image for f in self.descriptor.frames)):
            raise TaskError("animation_prompt_invalid", "model frames must retain the captured originals and animation parent")

    @property
    def rendered_images(self):
        return self.frames

    @property
    def evidence_images(self):
        return (self, *self.frames)


@dataclass(frozen=True)
class AnimationFrameEvent(ImageConversationEvent):
    """Internal parent view for the shared image store, never a new user input."""

    animation: AnimationDescriptor | None = None
    attribution: tuple = ()

    @property
    def image_attribution(self):
        return dict(self.attribution)

    def frame_metadata(self, descriptor):
        frame = self.animation.frames[descriptor.position]
        if frame.image != descriptor:
            raise TaskError("animation_content_changed", "frame no longer matches its original animation")
        return {"coverage": "animation_frame", "frame_index": frame.index, "start_ms": frame.start_ms,
                "duration_ms": frame.duration_ms, "frame_count": self.animation.frame_count,
                "animation_coverage": self.animation.coverage, "renderer": self.animation.renderer}
