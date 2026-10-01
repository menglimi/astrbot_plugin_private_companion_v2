"""Complete PCM WAV / SILK decoding in the disposable audio worker."""

import hashlib
import struct
import sys

from companion_v2.conversation.media.audio.models import (
    AudioDescriptor, CapturedAudio, MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS,
)
from companion_v2.execution.models import TaskError


def fail(code="host_audio_invalid"):
    raise TaskError(code, "audio could not be decoded completely within the intake budget")


def wave_bytes(pcm, rate):
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def decode_wave(content):
    if len(content) < 44 or content[:4] != b"RIFF" or content[8:12] != b"WAVE":
        fail("host_audio_format_unsupported")
    if struct.unpack_from("<I", content, 4)[0] + 8 != len(content):
        fail()
    offset, fmt, pcm = 12, None, None
    while offset < len(content):
        if offset + 8 > len(content):
            fail()
        kind, size = struct.unpack_from("<4sI", content, offset)
        offset += 8
        if offset + size + (size & 1) > len(content):
            fail()
        chunk = content[offset:offset + size]
        if kind == b"fmt ":
            if fmt is not None or size not in (16, 18) or size == 18 and chunk[16:] != b"\0\0":
                fail("host_audio_format_unsupported")
            fmt = struct.unpack_from("<HHIIHH", chunk)
        elif kind == b"data":
            if pcm is not None:
                fail()
            pcm = chunk
        offset += size + (size & 1)
    if fmt is None or not pcm:
        fail()
    codec, channels, rate, byte_rate, alignment, bits = fmt
    if codec != 1 or channels not in (1, 2) or bits != 16 or not 8000 <= rate <= 48000:
        fail("host_audio_format_unsupported")
    if byte_rate != rate * channels * 2 or alignment != channels * 2 or len(pcm) % alignment:
        fail()
    if len(pcm) // alignment > rate * MAX_AUDIO_SECONDS:
        fail("host_audio_limit")
    if channels == 2:
        pcm = b"".join(struct.pack("<h", (left + right) // 2) for left, right in struct.iter_unpack("<hh", pcm))
    return pcm, rate


def silk_packets(content):
    offset = 10 if content.startswith(b"\x02#!SILK_V3") else 9 if content.startswith(b"#!SILK_V3") else 0
    if not offset:
        fail("host_audio_format_unsupported")
    packets = []
    while offset < len(content):
        if offset + 2 > len(content):
            fail()
        size = struct.unpack_from("<h", content, offset)[0]
        offset += 2
        if size == -1 and offset == len(content):
            break
        if not 0 < size <= 5120 or offset + size > len(content):
            fail()
        packets.append(content[offset:offset + size])
        offset += size
        if len(packets) > MAX_AUDIO_SECONDS * 50:
            fail("host_audio_limit")
    if not packets:
        fail()
    return packets


def decode_silk(content):
    packets = silk_packets(content)
    try:
        # Use the bundled CFFI SDK contract directly. The package's convenience
        # decode() emits only one frame per packet and can lose later frames.
        from pysilk.backends.cffi._silk import ffi, lib
    except ImportError:
        fail("host_audio_decoder_unavailable")
    if sys.byteorder != "little":
        fail("host_audio_decoder_unavailable")
    size = ffi.new("int32_t *")
    if lib.SKP_Silk_SDK_Get_Decoder_Size(size) or not 0 < size[0] <= 1024 * 1024:
        fail()
    state = ffi.new("char[]", size[0])
    if lib.SKP_Silk_SDK_InitDecoder(state):
        fail()
    control = ffi.new("SKP_SILK_SDK_DecControlStruct *")
    control.API_sampleRate = 24000
    samples, count = ffi.new("int16_t[]", 2400), ffi.new("int16_t *")
    result = bytearray()
    for packet in packets:
        frames = 0
        while True:
            count[0] = 2400
            status = lib.SKP_Silk_SDK_Decode(state, control, 0, packet, len(packet), samples, count)
            if status or count[0] != 480:
                fail()
            frames += 1
            if frames > 5:
                fail()
            if len(result) + count[0] * 2 > 24000 * MAX_AUDIO_SECONDS * 2:
                fail("host_audio_limit")
            result.extend(ffi.buffer(samples, count[0] * 2)[:])
            if not control.moreInternalDecoderFrames:
                if control.framesPerPacket != frames:
                    fail()
                break
    return bytes(result), 24000


def inspect_audio(content, position):
    if type(content) is not bytes or not 0 < len(content) <= MAX_AUDIO_BYTES:
        fail("host_audio_limit")
    if content.startswith(b"RIFF"):
        pcm, rate = decode_wave(content)
        mime = "audio/wav"
    else:
        pcm, rate = decode_silk(content)
        mime = "audio/silk"
    waveform = wave_bytes(pcm, rate)
    descriptor = AudioDescriptor(position, mime, len(content), hashlib.sha256(content).hexdigest(), rate,
                                 len(pcm) // 2, len(waveform), hashlib.sha256(waveform).hexdigest())
    return CapturedAudio(descriptor, content, waveform)
