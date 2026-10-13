import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace

# Establish an isolated AstrBot data root before importing the host adapter.
from tests import test_astrbot_staging_host as _support
from astrbot_host.native import installed_native_types, load_persona_snapshot_selection


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


class ConversationPersonaProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_projection_reads_only_the_persona_column(self):
        database = ProjectionDatabase()
        context = SimpleNamespace(_db=database)

        persona_id = await load_persona_snapshot_selection(context, "qq:FriendMessage:200", "conversation-1")

        self.assertEqual(persona_id, "persona-1")
        self.assertEqual(tuple(database.session.statement.selected_columns.keys()), ("persona_id",))
