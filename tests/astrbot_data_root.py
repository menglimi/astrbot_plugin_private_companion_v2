"""Give SDK subprocesses a private AstrBot root before any SDK import."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory


_temporary_root = TemporaryDirectory(prefix="companion-v2-astrbot-root-")
ASTRBOT_ROOT = Path(_temporary_root.name).resolve()
os.environ["ASTRBOT_ROOT"] = str(ASTRBOT_ROOT)


def assert_sdk_database_isolated(db_helper) -> None:
    database_path = Path(db_helper.db_path).resolve()
    if not database_path.is_relative_to(ASTRBOT_ROOT):
        raise AssertionError("AstrBot SDK database escaped the temporary data root")
