"""Synthetic PCM / SILK fixtures; never read a user's recordings."""

import base64
import io
import struct

from astrbot_host.audio.decoder import inspect_audio, wave_bytes
from astrbot_host.audio.loader import load_native_audio
from tests.native_adapter_support import FakeEvent
from tests.test_conversation_images import ImageFixture


def audio_bytes(seconds=0.2, rate=24000, value=1000):
    return wave_bytes(struct.pack("<h", value) * int(rate * seconds), rate)


def silk_bytes(*, frames_per_packet=1, packets=2):
    from pysilk.backends.cffi._silk import ffi, lib
    size = ffi.new("int32_t *")
    assert lib.SKP_Silk_SDK_Get_Encoder_Size(size) == 0
    state = ffi.new("char[]", size[0])
    control = ffi.new("SKP_SILK_SDK_EncControlStruct *")
    assert lib.SKP_Silk_SDK_InitEncoder(state, control) == 0
    control.API_sampleRate = control.maxInternalSampleRate = 24000
    control.packetSize, control.bitRate, control.complexity = frames_per_packet * 480, 24000, 2
    pcm, out, count = ffi.new("int16_t[]", 480), ffi.new("uint8_t[]", 5120), ffi.new("int16_t *")
    result = io.BytesIO(b"\x02#!SILK_V3")
    result.seek(0, 2)
    for _ in range(packets * frames_per_packet):
        count[0] = 5120
        assert lib.SKP_Silk_SDK_Encode(state, control, pcm, 480, out, count) == 0
        if count[0]:
            result.write(struct.pack("<h", count[0]))
            result.write(ffi.buffer(out, count[0])[:])
    return result.getvalue()


class FakeRecord:
    type = "Record"

    def __init__(self, content=None):
        self.file = "base64://" + base64.b64encode(content if content is not None else audio_bytes()).decode("ascii")
        self.url = ""
        self.text = "这不是可信转写"
        self.path = "C:/untrusted.wav"


class AudioFixture(ImageFixture):
    def setUp(self):
        super().setUp()
        self.bridge.audio_type = FakeRecord
        self.bridge.audio_loader = load_native_audio

    def audio_event(self, identifier="voice-1", content=None, *, count=1):
        event = FakeEvent(self.native, event_id=identifier)
        event.message_obj.message = [FakeRecord(content) for _ in range(count)]
        return event

    def captured_audio(self, position=0):
        return inspect_audio(audio_bytes(), position)
