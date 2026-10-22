"""REQ-041 migration preserves history without crossing users or reviving work."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from companion_v2.legacy.private_memory import SCHEMA, build_private_memory_plan, fingerprint
from companion_v2.memory.private_legacy_import import import_private_memory
from tests.memory_support import MemoryFixture


def private_source(root, account, actor, *, text="七月二十四日一起看蓝风铃", bad_hash=False):
    identity = {"companion_instance_id": "astrbot_plugin_private_companion",
        "bot_account_id": "aiocqhttp:" + account, "adapter_instance_id": "aiocqhttp:main",
        "subject_namespace": "aiocqhttp:user", "platform_subject_id": actor}
    key = "chat-origin-v1:" + fingerprint(identity)
    content = {"companion_memory": {"items": [{"text": text, "created_at": "2026-07-24T08:00:00+08:00"}]},
        "open_loops": [{"text": "旧提醒不能自动重发", "status": "pending", "created_at": "2026-07-24T09:00:00+08:00"}]}
    payload = {"_req041_private_memory": {"schema": SCHEMA, "records": {"person-a": {
        "schema": SCHEMA, "revision": 1, "content": content, "content_hash": "bad" if bad_hash else fingerprint(content),
        "updated_at": "2026-07-24T10:00:00+08:00"}}}, "unified_person": {
        "profiles": {"person-a": {"profile_status": "active", "identity_keys": [key]}},
        "identity_links": {key: {"person_id": "person-a", "status": "active", "identity": identity}}}}
    path = Path(root) / "companions.json"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def memory_target(context):
    return {"installation_id": context.scope.installation_id, "bot_id": context.scope.bot_id,
        "role_id": context.role_binding.role.subject_id, "actor_id": context.actor.subject.subject_id,
        "platform": context.scope.platform, "account_id": context.scope.account_id,
        "scope_kind": "private", "native_scope_id": context.scope.native_scope_id}


class PrivateMemoryMigrationTests(MemoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory(prefix="companion-v1-private-memory-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = private_source(self.root, self.context.scope.account_id,
                                     self.context.actor.principal.native_account_id)

    def plan(self):
        return build_private_memory_plan(self.root)

    def import_history(self, context=None):
        context = context or self.context
        plan = self.plan()
        records = plan.matching(account_id=context.scope.account_id,
                               native_actor_id=context.actor.principal.native_account_id)
        return import_private_memory(self.recall.legacy, plan, records, memory_target(context))

    def test_preview_is_read_only_and_different_account_or_user_does_not_match(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        plan = self.plan()
        self.assertEqual(plan.document()["material_count"], 2)
        self.assertEqual(plan.matching(account_id="another-account", native_actor_id=self.context.actor.principal.native_account_id), ())
        self.assertEqual(plan.matching(account_id=self.context.scope.account_id, native_actor_id="another-user"), ())
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)
        self.assertFalse((self.runtime.data_root / "legacy-memory-materials.sqlite3").exists())

    def test_invalid_record_hash_and_detached_identity_are_not_importable(self):
        private_source(self.root, self.context.scope.account_id,
                       self.context.actor.principal.native_account_id, bad_hash=True)
        self.assertEqual(self.plan().records, ())
        private_source(self.root, self.context.scope.account_id, self.context.actor.principal.native_account_id)
        payload = json.loads(self.source.read_text(encoding="utf-8"))
        next(iter(payload["unified_person"]["identity_links"].values()))["status"] = "detached"
        self.source.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.plan().records, ())

    def test_import_is_idempotent_and_never_creates_live_facts_or_jobs(self):
        first, repeated = self.import_history(), self.import_history()
        self.assertEqual(first["imported"]["memories"], 2)
        self.assertTrue(repeated["already_present"])
        items = self.recall.legacy.query(self.context).unwrap()["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(all(not item["current_fact"] and not item["execution_restored"] for item in items))
        self.assertEqual(self.runtime.read_all("SELECT * FROM memory_atoms", ()), ())
        self.assertEqual(self.runtime.read_all("SELECT * FROM execution_tasks", ()), ())

    def test_two_role_destinations_are_independent_and_new_snapshot_replaces_only_its_role(self):
        self.import_history()
        other = self.alternate_context(bot_id=self.context.scope.bot_id, role_id="other-memory-role",
                                       session_selector=True)
        self.context = self.context_for(self.context.actor, self.context.scope)
        self.assertEqual(self.recall.legacy.query(other).unwrap()["items"], [])
        self.import_history(other)
        private_source(self.root, self.context.scope.account_id,
                       self.context.actor.principal.native_account_id, text="替换后的新历史")
        self.import_history()
        original = self.recall.legacy.query(self.context, query_intent="替换后").unwrap()["items"]
        preserved = self.recall.legacy.query(other, query_intent="蓝风铃").unwrap()["items"]
        self.assertEqual((len(original), len(preserved)), (1, 1))

    def test_core_reply_recalls_the_migrated_day_through_the_historical_query(self):
        from astrbot_host.core_reply_context import _legacy_memory_materials
        self.import_history()
        owner = SimpleNamespace(query=self.recall, writer=self.memory)
        materials = _legacy_memory_materials(owner, self.context,
            SimpleNamespace(text="七月二十四号我们聊了什么"),
            datetime(2026, 10, 19, tzinfo=timezone.utc), "Asia/Shanghai")
        self.assertTrue(materials)
        self.assertIn("蓝风铃", "\n".join(json.loads(item.payload)["text"] for item in materials))

    def test_date_window_excludes_the_next_local_day(self):
        self.import_history()
        items = self.recall.legacy.query(self.context,
            time_start=datetime(2026, 7, 23, 0, tzinfo=timezone.utc),
            time_end=datetime(2026, 7, 24, 0, tzinfo=timezone.utc)).unwrap()["items"]
        self.assertEqual(items, [])

    def test_core_reply_handles_long_history_and_natural_language_queries(self):
        from astrbot_host.core_reply_context import _legacy_memory_materials
        private_source(self.root, self.context.scope.account_id,
            self.context.actor.principal.native_account_id, text="蓝风铃往事" * 5000)
        self.import_history()
        owner = SimpleNamespace(query=self.recall, writer=self.memory)
        for question in ("还记得蓝风铃吗", "七月二十四号我们聊了什么"):
            with self.subTest(question=question):
                materials = _legacy_memory_materials(owner, self.context,
                    SimpleNamespace(text=question), datetime(2026, 10, 19, tzinfo=timezone.utc),
                    "Asia/Shanghai")
                self.assertTrue(materials)
                self.assertIn("蓝风铃", "\n".join(json.loads(m.payload)["text"] for m in materials))
                self.assertLessEqual(sum(len(m.payload) for m in materials),
                                     self.memory.access.policy_for(self.context).context_chars)


class PrivateMemoryAPIHostTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    async def test_auth_stale_plan_idempotency_and_service_key_identity(self):
        import asyncio
        from astrbot.api.web import PluginRequest, bind_request_context
        from starlette.requests import Request
        from astrbot_host.legacy_api import LegacyMigrationWebAPI
        from astrbot_host.legacy_private_memory_api import PrivateMemoryMigrationAPI
        from astrbot_host.management_identity import dashboard_operator
        from companion_v2.foundation.refs import SubjectKind
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private_source(root, self.context.scope.account_id, self.context.actor.principal.native_account_id)
            session = SimpleNamespace(profile=SimpleNamespace(target=self.context),
                application=SimpleNamespace(semantics=object(), runtime=self.runtime,
                    memory=SimpleNamespace(query=self.recall)))
            legacy = LegacyMigrationWebAPI(SimpleNamespace(runtime=self.runtime,
                session=session, last_session=None, _terminated=False,
                _control_lock=asyncio.Lock(), now=self.clock.now))
            async def migration(*args, **kwargs):
                return SimpleNamespace(v1_configuration={}), root, 'test'
            legacy._migration = migration
            api = PrivateMemoryMigrationAPI(legacy)
            async def call(handler, data=None, username='admin', scoped=False):
                body = json.dumps(data or {}).encode('utf-8')
                async def receive():
                    return {'type':'http.request', 'body':body, 'more_body':False}
                path = '/api/v1/plugins/extensions/test' if scoped else '/test'
                raw = Request({'type':'http','method':'POST' if data else 'GET',
                    'scheme':'http','path':path,'query_string':b'', 'headers':[]}, receive)
                with bind_request_context(PluginRequest(raw, username=username)):
                    return await handler()
            self.assertEqual((await call(api.plan, username=None))['data']['code'], 'dashboard_identity_required')
            self.assertEqual((await call(api.plan, username='api_key:fixture'))['data']['code'], 'dashboard_identity_required')
            planned = (await call(api.plan, username='api_key:fixture', scoped=True))['data']
            self.assertEqual(planned['matched_material_count'], 2)
            changed = {'plan_token':'stale','confirmed':True}
            self.assertEqual((await call(api.apply, changed))['data']['code'], 'legacy_plan_stale')
            body = {'plan_token':planned['plan_token'], 'confirmed':True}
            first, repeated = await call(api.apply, body), await call(api.apply, body)
            self.assertEqual(first['status'], 'ok', first)
            self.assertTrue(repeated['data']['already_present'])
            with self.assertRaises(Exception):
                dashboard_operator(self.runtime, 'api_key:fixture', at=self.clock.now())
            self.assertTrue(self.runtime.read_one("SELECT 1 FROM identity_bindings WHERE host_id=?", ("astrbot-dashboard-api-key",)))
