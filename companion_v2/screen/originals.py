"""Immutable Screen image bytes under the V2 data root."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import os
from pathlib import Path
from uuid import uuid4
import warnings

from PIL import Image

from companion_v2.foundation.refs import ReferenceValidationError


MAX_SCREEN_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


@dataclass(frozen=True)
class ScreenImage:
    mime_type: str
    content: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (type(self.content) is not bytes or not 0 < len(self.content) <= MAX_SCREEN_IMAGE_BYTES
                or self.mime_type not in IMAGE_SIGNATURES
                or not self.content.startswith(IMAGE_SIGNATURES[self.mime_type])):
            raise ReferenceValidationError("screen image must be a bounded supported image body")
        if self.mime_type == "image/webp" and self.content[8:12] != b"WEBP":
            raise ReferenceValidationError("screen WebP signature is incomplete")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(self.content)) as image:
                    if ({"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(image.format)
                            != self.mime_type or getattr(image, "is_animated", False)
                            or max(image.size) > 8192 or image.width * image.height > 16 * 1024 * 1024):
                        raise ReferenceValidationError("screen image encoding or dimensions are unsupported")
                    image.verify()
                with Image.open(io.BytesIO(self.content)) as decoded:
                    decoded.load()
        except ReferenceValidationError:
            raise
        except Exception as error:
            raise ReferenceValidationError("screen image bytes could not be decoded") from error

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class ScreenOriginalStore:
    """A content-addressed body is inert until a governed Screen capture refers to it."""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "screen" / "originals"

    def _path(self, content_hash: str) -> Path:
        if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
            raise ReferenceValidationError("screen image hash must be SHA-256 hex")
        return self._root / content_hash[:2] / content_hash

    def save(self, image: ScreenImage) -> None:
        path = self._path(image.content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(image.content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if self.read(image.content_hash) != image.content:
                    raise ReferenceValidationError("stored screen original differs from its content hash")
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, content_hash: str) -> bytes:
        path = self._path(content_hash)
        with path.open("rb") as stream:
            content = stream.read(MAX_SCREEN_IMAGE_BYTES + 1)
            if stream.read(1) or not 0 < len(content) <= MAX_SCREEN_IMAGE_BYTES:
                raise ReferenceValidationError("stored screen original exceeds its size budget")
        if hashlib.sha256(content).hexdigest() != content_hash:
            raise ReferenceValidationError("stored screen original differs from its content hash")
        return content
