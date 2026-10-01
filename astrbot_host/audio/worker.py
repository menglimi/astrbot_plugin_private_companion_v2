"""One bounded decode, binary stdin/stdout; no paths, network or host boot."""

from dataclasses import asdict
import json
import sys

from companion_v2.conversation.media.audio.models import MAX_AUDIO_BYTES
from companion_v2.execution.models import TaskError
from .decoder import inspect_audio


def main():
    try:
        audio = inspect_audio(sys.stdin.buffer.read(MAX_AUDIO_BYTES + 1), 0)
    except Exception as error:
        code = error.code if isinstance(error, TaskError) else "host_audio_invalid"
        sys.stdout.buffer.write(json.dumps({"error": code}).encode("ascii") + b"\n")
        return 2
    sys.stdout.buffer.write(json.dumps(asdict(audio.descriptor)).encode("ascii") + b"\n" + audio.waveform)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
