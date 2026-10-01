"""A minimal AstrBot SDK stand-in, so the host test suite can be collected offline.

``astrbot_host`` imports AstrBot's own modules (``astrbot.core.message.components``,
``astrbot.api.web``, ...) at module scope, so without the SDK installed pytest cannot
even collect most of the suite. The real SDK is not on the path inside an isolated
sandbox, and pulling it in would drag a whole application with it.

These stubs are deliberately thin: they exist so imports succeed, not so behaviour can
be exercised through them. Anything that reaches real SDK behaviour is supposed to
fail loudly rather than quietly return a plausible answer, which is why the request
stub raises instead of fabricating a body.

Usage::

    python3 tools/sandbox_sdk.py --run            # stub, then pytest
    python3 tools/sandbox_sdk.py --run -k weather  # extra args pass through
    python3 tools/sandbox_sdk.py --emit           # print the stub root and exit

The stub is written to a temporary directory and put on ``PYTHONPATH`` for the child
process only; nothing is added to the working tree.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp


# (relative path, contents). Directories are created as needed.
MODULES: dict[str, str] = {
    "astrbot/__init__.py": '__version__ = "4.0.0-stub"\n',
    "astrbot/api/__init__.py": "",
    "astrbot/api/web.py": '''"""Request context stand-in.

Handlers read an ambient ``request`` object bound per call. Reading one outside a
bound context is a test bug, so it raises instead of returning invented data.
"""
from contextlib import contextmanager


class PluginMultiDict(dict):
    """A query mapping; AstrBot's own is dict-like with single-value get."""

    def get(self, key, default=None):
        return super().get(key, default)


class PluginRequest:
    def __init__(self, native=None, *, username="", query=None, body=b"", **kwargs):
        self.native = native
        self.username = username
        self.query = PluginMultiDict(query or {})
        self._body = body
        self.kwargs = kwargs

    async def body(self):
        return self._body


class _UnboundRequest:
    query = PluginMultiDict()
    username = ""

    async def body(self):
        raise RuntimeError("stub: no request is bound in this context")


request = _UnboundRequest()


@contextmanager
def bind_request_context(value):
    global request
    previous = request
    request = value
    try:
        yield value
    finally:
        request = previous
''',
    "astrbot/api/message_components.py":
        "from astrbot.core.message.components import (At, Forward, Image, Plain, Record, Reply, Video)\n",
    "astrbot/core/__init__.py": "",
    "astrbot/core/agent/__init__.py": "",
    "astrbot/core/agent/tool.py": '''"""Tool registration stand-in; records what it was handed."""


class FunctionTool:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs


class ToolSet:
    def __init__(self, *args, **kwargs):
        self.tools = list(args)
        self.kwargs = kwargs
''',
    "astrbot/core/config/__init__.py": "",
    "astrbot/core/config/default.py": "CONFIG_METADATA_2 = {}\n",
    "astrbot/core/message/__init__.py": "",
    "astrbot/core/message/components.py": '''"""Message component stand-in; only construction is needed."""


class _Component:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs


class At(_Component): pass
class Forward(_Component): pass
class Image(_Component): pass
class Plain(_Component): pass
class Record(_Component): pass
class Reply(_Component): pass
class Video(_Component): pass
''',
    "astrbot/core/platform/__init__.py": "",
    "astrbot/core/platform/astrbot_message.py": '''class MessageMember:
    def __init__(self, user_id="", nickname=""):
        self.user_id, self.nickname = user_id, nickname


class AstrBotMessage:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
''',
    "astrbot/core/platform/message_type.py": '''from enum import Enum


class MessageType(Enum):
    ALL = "all"
    FRIEND_MESSAGE = "friend"
    GROUP_MESSAGE = "group"
    PRIVATE_MESSAGE = "private"
    OTHER_MESSAGE = "other"
''',
    "astrbot/core/platform/sources/__init__.py": "",
    "astrbot/core/platform/sources/aiocqhttp/__init__.py": "",
    "astrbot/core/platform/sources/aiocqhttp/aiocqhttp_message_event.py":
        "class AiocqhttpMessageEvent:\n    pass\n",
    "astrbot/core/provider/__init__.py": "",
    "astrbot/core/provider/sources/__init__.py": "",
    "astrbot/core/provider/sources/openai_source.py":
        "class ProviderOpenAIOfficial:\n    pass\n",
    "astrbot/core/utils/__init__.py": "",
    "astrbot/core/utils/astrbot_path.py": '''import tempfile
from pathlib import Path


def get_astrbot_temp_path():
    path = Path(tempfile.gettempdir()) / "astrbot"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
''',
}

# Sibling plugins this repository's tests reach into. They are separate installations
# that may not exist next to the plugin under test, so importing them must not abort
# collection of everything else.
SIBLINGS = {
    "astrbot_plugin_game_companion/__init__.py":
        '"""Stub of the sibling game plugin; only importability is required here."""\n',
    "astrbot_plugin_game_companion/native_v2/__init__.py":
        '"""Stub package for the sibling game plugin."""\n',
    "astrbot_plugin_game_companion/blackjack.py": '''"""Stub of the sibling game plugin's blackjack module."""
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("spade", "heart", "diamond", "club")


class BlackjackCard:
    def __init__(self, rank="A", suit="spade"):
        self.rank, self.suit = rank, suit
''',
}

# Tests that need an actual sibling installation on disk, not a stub. They are
# excluded rather than faked, because a stub cannot meaningfully stand in for a
# provider whose file is missing.
NEEDS_SIBLING_CHECKOUT = (
    "tests/test_game_memory_ingestion.py",
    "tests/test_game_native_blackjack.py",
    "tests/test_game_native_pig_dice.py",
    "tests/test_game_native_xiangqi.py",
    "tests/test_live_native_provider.py",
    "tests/test_page_targets_api.py",
    "tests/test_reality_together_native.py",
    "tests/test_w1_fixture_harness.py",
)


def build(root: Path) -> None:
    for relative, contents in {**MODULES, **SIBLINGS}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


def environment(root: Path, repo: Path) -> dict[str, str]:
    values = dict(os.environ)
    existing = values.get("PYTHONPATH", "")
    values["PYTHONPATH"] = os.pathsep.join(part for part in (str(root), str(repo), existing) if part)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="run pytest after stubbing")
    parser.add_argument("--keep", action="store_true",
                        help="reuse a stub root from SANDBOX_SDK_ROOT instead of a fresh one")
    parser.add_argument("--list-excluded", action="store_true")
    parser.add_argument("pytest_args", nargs="*")
    options = parser.parse_args()

    if options.list_excluded:
        for name in NEEDS_SIBLING_CHECKOUT:
            print(name)
        return 0

    repo = Path(__file__).resolve().parents[1]
    root = Path(os.environ.get("SANDBOX_SDK_ROOT") or mkdtemp(prefix="astrbot-sdk-stub-"))
    build(root)
    print(f"stub root {root}")

    if not options.run:
        return 0

    command = [sys.executable, "-m", "pytest", *options.pytest_args]
    ignored = [f"--ignore={name}" for name in NEEDS_SIBLING_CHECKOUT
               if (repo / name).exists() and not any(name in arg for arg in options.pytest_args)]
    command.extend(ignored)
    print("running", " ".join(command))
    return subprocess.call(command, cwd=repo, env=environment(root, repo))


if __name__ == "__main__":
    raise SystemExit(main())
