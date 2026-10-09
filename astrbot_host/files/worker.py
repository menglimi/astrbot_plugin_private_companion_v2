"""One disposable parser process for one incoming document."""

from dataclasses import asdict
import json
import sys

from companion_v2.execution.models import TaskError
from .parsing import extract_document


def main():
    try:
        name, limit, formats = sys.argv[1:]
        content = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        result = asdict(extract_document(content, 0, name, maximum_chars=int(limit), formats=formats))
        code = 0
    except TaskError as error:
        result, code = {"error": error.code}, 1
    except Exception:
        result, code = {"error": "host_file_invalid"}, 1
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
