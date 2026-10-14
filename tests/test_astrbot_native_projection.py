import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

# Establish an isolated AstrBot data root before importing the host adapter.
from tests import test_astrbot_staging_host as _support
from astrbot_host.native import (
    installed_native_types,
    load_persona_snapshot_selection,
    resolve_native_persona_selection,
)


class ProjectionSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(one_or_none=lambda: ("persona-1",))


class ProjectionDatabase:
    inited = True

    def __init__(self):
        self.session = ProjectionSession()

    @asynccontextmanager
    async def get_db(self):
        yield self.session


class NativeAdapterProjectionTests(unittest.TestCase):
    def test_native_types_expose_a_lightweight_persona_projection(self):
        native_types = installed_native_types()

        self.assertTrue(callable(native_types.persona_snapshot_lookup))
        self.assertTrue(callable(native_types.session_persona_override_lookup))
        self.assertIs(native_types.persona_selection_lookup, resolve_native_persona_selection)


class ConversationPersonaProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_projection_reads_only_the_persona_column(self):
        database = ProjectionDatabase()
        context = SimpleNamespace(_db=database)

        persona_id = await load_persona_snapshot_selection(context, "qq:FriendMessage:200", "conversation-1")

        self.assertEqual(persona_id, "persona-1")
        self.assertEqual(tuple(database.session.statement.selected_columns.keys()), ("persona_id",))

    async def test_empty_snapshot_uses_astrbot_selected_persona_precedence(self):
        configuration = {"agent_runner": {"runner_type": "local", "config": {"persona": {"persona_id": "runner-default"}}}}
        resolver = AsyncMock(return_value=("window-persona", {"name": "window-persona"}, "window-persona", False))
        platform = SimpleNamespace(meta=lambda: SimpleNamespace(name="aiocqhttp"))
        context = SimpleNamespace(
            persona_manager=SimpleNamespace(resolve_selected_persona=resolver),
            get_config=lambda *, umo: configuration,
            get_platform_inst=lambda platform_id: platform if platform_id == "qq" else None,
        )

        persona_id = await resolve_native_persona_selection(context, "qq:FriendMessage:200", None)

        self.assertEqual(persona_id, "window-persona")
        resolver.assert_awaited_once_with(
            umo="qq:FriendMessage:200",
            conversation_persona_id=None,
            platform_name="aiocqhttp",
            provider_settings={},
        )

    async def test_explicit_none_persona_is_preserved_for_snapshot(self):
        resolver = AsyncMock(return_value=("[%None]", None, None, False))
        platform = SimpleNamespace(meta=lambda: SimpleNamespace(name="aiocqhttp"))
        context = SimpleNamespace(
            persona_manager=SimpleNamespace(resolve_selected_persona=resolver),
            get_config=lambda *, umo: {"provider_settings": {"default_personality": "ignored"}},
            get_platform_inst=lambda platform_id: platform,
        )

        persona_id = await resolve_native_persona_selection(context, "qq:FriendMessage:200", "[%None]")

        self.assertEqual(persona_id, "[%None]")
