"""Bounded, self-contained MP4 sample tables before opening a native demuxer.

This verifies declared byte ranges and video samples, not codec authenticity or
every bit of an audio stream. Fragmented movies and external data references need
their own decoder contract; they are not silently treated as complete files.
"""

from dataclasses import dataclass
import struct

from companion_v2.conversation.media.video.models import MAX_DECODE_FRAMES, MAX_DECODE_PIXELS, MAX_VIDEO_MS
from companion_v2.execution.models import TaskError


def invalid(code="host_video_invalid"):
    raise TaskError(code, "video container is incomplete, unsupported or outside its declared media budget")


@dataclass(frozen=True)
class Box:
    kind: bytes
    start: int
    end: int


def boxes(data, start, end):
    result = []
    while start < end:
        if start + 8 > end or len(result) >= 4096:
            invalid()
        size, kind = struct.unpack_from(">I4s", data, start)
        header = 8
        if size == 1:
            if start + 16 > end:
                invalid()
            size, = struct.unpack_from(">Q", data, start + 8)
            header = 16
        elif size == 0:
            if kind != b"mdat":
                invalid()
            size = end - start
        if size < header or start + size > end:
            invalid()
        result.append(Box(kind, start + header, start + size))
        start += size
    return tuple(result)


def child(data, parent, kind):
    matches = [b for b in boxes(data, parent.start, parent.end) if b.kind == kind]
    if len(matches) != 1:
        invalid()
    return matches[0]


def u32(data, offset, end):
    if offset + 4 > end:
        invalid()
    return struct.unpack_from(">I", data, offset)[0]


def entries(data, box, width, *, maximum=MAX_DECODE_FRAMES):
    if box.end - box.start < 8 or data[box.start:box.start + 4] != b"\0\0\0\0":
        invalid()
    count = u32(data, box.start + 4, box.end)
    if not 1 <= count <= maximum or box.start + 8 + count * width != box.end:
        invalid()
    return [data[i:i + width] for i in range(box.start + 8, box.end, width)]


def local_track(data, trak):
    mdia = child(data, trak, b"mdia")
    hdlr = child(data, mdia, b"hdlr")
    if hdlr.end - hdlr.start < 12:
        invalid()
    kind = data[hdlr.start + 8:hdlr.start + 12]
    minf = child(data, mdia, b"minf")
    dref = child(data, child(data, minf, b"dinf"), b"dref")
    if dref.end - dref.start < 8 or data[dref.start:dref.start + 4] != b"\0\0\0\0":
        invalid()
    refs = boxes(data, dref.start + 8, dref.end)
    if len(refs) != u32(data, dref.start + 4, dref.end) or not 1 <= len(refs) <= 16:
        invalid()
    # All tracks must be self-contained, including audio we do not inspect.
    if any(r.kind != b"url " or data[r.start:r.end] != b"\0\0\0\1" for r in refs):
        invalid("host_video_external_reference")
    return kind, mdia, child(data, minf, b"stbl"), len(refs)


@dataclass(frozen=True)
class Movie:
    width: int
    height: int
    frame_count: int
    duration_ms: int
    audio_tracks: int


def inspect_container(data):
    top = boxes(data, 0, len(data))
    kinds = [b.kind for b in top]
    if kinds.count(b"ftyp") != 1 or kinds.count(b"moov") != 1 or b"mdat" not in kinds or b"moof" in kinds:
        invalid("host_video_format_unsupported")
    ftyp = next(b for b in top if b.kind == b"ftyp")
    if ftyp.end - ftyp.start < 8 or (ftyp.end - ftyp.start) % 4:
        invalid()
    movie = next(b for b in top if b.kind == b"moov")
    movie_boxes = boxes(data, movie.start, movie.end)
    if any(b.kind == b"mvex" for b in movie_boxes):
        invalid("host_video_format_unsupported")
    tracks = [local_track(data, t) for t in movie_boxes if t.kind == b"trak"]
    video = [t for t in tracks if t[0] == b"vide"]
    audio_tracks = sum(t[0] == b"soun" for t in tracks)
    if len(video) != 1 or len(tracks) > 17 or audio_tracks > 16:
        invalid("host_video_format_unsupported")
    _, mdia, table, ref_count = video[0]
    stsd = child(data, table, b"stsd")
    if stsd.end - stsd.start < 8 or u32(data, stsd.start + 4, stsd.end) != 1:
        invalid("host_video_format_unsupported")
    descriptions = boxes(data, stsd.start + 8, stsd.end)
    if len(descriptions) != 1:
        invalid()
    description = descriptions[0]
    if description.kind not in (b"avc1", b"avc3", b"hvc1", b"hev1", b"mp4v") or description.end - description.start < 78:
        invalid("host_video_format_unsupported")
    reference, = struct.unpack_from(">H", data, description.start + 6)
    width, height = struct.unpack_from(">HH", data, description.start + 24)
    if not 1 <= reference <= ref_count or not all(1 <= v <= 4096 for v in (width, height)):
        invalid("host_video_limit")
    mdhd = child(data, mdia, b"mdhd")
    version = data[mdhd.start] if mdhd.start < mdhd.end else -1
    if version not in (0, 1):
        invalid()
    timescale = u32(data, mdhd.start + (12 if version == 0 else 20), mdhd.end)
    if not timescale:
        invalid()
    stts = entries(data, child(data, table, b"stts"), 8)
    times = [struct.unpack(">II", row) for row in stts]
    count = sum(n for n, _ in times)
    ticks = sum(n * duration for n, duration in times)
    duration_ms = (ticks * 1000 + timescale - 1) // timescale
    if (any(n == 0 or duration == 0 for n, duration in times) or not 1 <= count <= MAX_DECODE_FRAMES
            or not 1 <= duration_ms <= MAX_VIDEO_MS or width * height * count > MAX_DECODE_PIXELS):
        invalid("host_video_limit")
    stsz = child(data, table, b"stsz")
    if stsz.end - stsz.start < 12 or data[stsz.start:stsz.start + 4] != b"\0\0\0\0":
        invalid()
    fixed, samples = struct.unpack_from(">II", data, stsz.start + 4)
    if samples != count or stsz.start + 12 + (0 if fixed else count * 4) != stsz.end:
        invalid()
    sizes = [fixed] * count if fixed else [u32(data, stsz.start + 12 + 4 * i, stsz.end) for i in range(count)]
    if any(not size for size in sizes):
        invalid()
    offsets = [b for b in boxes(data, table.start, table.end) if b.kind in (b"stco", b"co64")]
    if len(offsets) != 1:
        invalid()
    offset_table = offsets[0]
    chunks = [struct.unpack(">I" if offset_table.kind == b"stco" else ">Q", row)[0]
              for row in entries(data, offset_table, 4 if offset_table.kind == b"stco" else 8)]
    mapping = [struct.unpack(">III", row) for row in entries(data, child(data, table, b"stsc"), 12)]
    starts = [m[0] for m in mapping]
    if starts[0] != 1 or starts != sorted(set(starts)) or starts[-1] > len(chunks) or any(n < 1 or d != 1 for _, n, d in mapping):
        invalid()
    media = [(b.start, b.end) for b in top if b.kind == b"mdat"]
    sample, mapping_index, ranges = 0, 0, []
    for ordinal, offset in enumerate(chunks, 1):
        if mapping_index + 1 < len(mapping) and mapping[mapping_index + 1][0] == ordinal:
            mapping_index += 1
        n = mapping[mapping_index][1]
        if sample + n > count:
            invalid()
        end = offset + sum(sizes[sample:sample + n])
        if not any(start <= offset < end <= stop for start, stop in media):
            invalid()
        ranges.append((offset, end))
        sample += n
    ordered = sorted(ranges)
    if sample != count or any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        invalid()
    return Movie(width, height, count, duration_ms, audio_tracks)
