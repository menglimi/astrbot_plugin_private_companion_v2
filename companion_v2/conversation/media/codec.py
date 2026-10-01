"""Restore additive animation manifests without changing old static documents."""

from .animation import AnimationDescriptor, FrameDescriptor
from .models import ImageDescriptor


def image_descriptor(data):
    if "frames" not in data:
        return ImageDescriptor(**data)
    frames = tuple(FrameDescriptor(**{**frame, "image": ImageDescriptor(**frame["image"])}) for frame in data["frames"])
    return AnimationDescriptor(**{**data, "frames": frames})
