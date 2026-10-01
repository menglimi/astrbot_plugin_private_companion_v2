"""Small V2-only switch store for managed native image actions."""

import json
import os
from pathlib import Path
from uuid import uuid4

from companion_v2.execution.models import TaskError

from .images import IMAGE_ACTIONS


def read_image_settings(path):
    settings = {action: True for action in IMAGE_ACTIONS}
    if path is None or not Path(path).is_file():
        return settings
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8", errors="strict"))
        if (type(data) is not dict or set(data) - IMAGE_ACTIONS
                or any(type(value) is not bool for value in data.values())):
            raise ValueError("invalid image settings")
        return {**settings, **data}
    except (OSError, UnicodeError, ValueError) as error:
        raise TaskError("model_image_settings_invalid", "saved native image switches are invalid") from error


def write_image_settings(path, settings):
    if path is None or set(settings) != IMAGE_ACTIONS or any(type(value) is not bool for value in settings.values()):
        raise ValueError("image settings require every native action")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(settings, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise TaskError("model_image_store_failed", "native image switches could not be saved") from error
    finally:
        temporary.unlink(missing_ok=True)
