"""One bounded video decode; byte stdin and JSON header plus PNG stdout."""

from dataclasses import asdict
import json
import sys

from companion_v2.conversation.media.video.models import MAX_VIDEO_BYTES
from companion_v2.execution.models import TaskError
from .decoder import inspect_video


def main():
    try:
        video = inspect_video(sys.stdin.buffer.read(MAX_VIDEO_BYTES + 1), 0, scratch=sys.argv[1])
    except Exception as error:
        code = error.code if isinstance(error, TaskError) else "host_video_invalid"
        sys.stdout.buffer.write(json.dumps({"error": code}).encode("ascii") + b"\n")
        return 2
    sys.stdout.buffer.write(json.dumps(asdict(video.descriptor)).encode("ascii") + b"\n")
    for frame in video.frames:
        sys.stdout.buffer.write(frame.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
