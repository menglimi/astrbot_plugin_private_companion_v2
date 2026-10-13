from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.execution.models import TaskError, encode
from companion_v2.adapters.astrbot.staging_config import REBINDING_FIELDS, StagingConfiguration
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.model_gateway.models import Amount, BudgetPolicy
from companion_v2.role_work import PersistentRoleLifeLedger, RoleActivity, RoleActivityState
from companion_v2.role_work.journal import JournalContext, JournalKey, JournalKind
from tests.native_adapter_support import FakeEvent, FakeProvider, completion
from tests.staging_bootstrap_support import BootstrapFixture, database_contents
from tests.test_management_access import NOW


class StagingBootstrapTests(BootstrapFixture, unittest.IsolatedAsyncioTestCase):
    async def test_explicit_journal_capability_uses_staging_provider_and_no_platform_delivery(self):
        config = replace(self.config, capabilities=self.config.capabilities + ("role.journal.write",))
        bootstrap = self.make_bootstrap(configuration=config)
        (await bootstrap.initialize()).unwrap()
        session = await self.start_session(self.load_session(bootstrap))
        app, target = session.application, session.profile.target
        captured = (await session.bridge.capture(FakeEvent(self.native))).unwrap()
        event = session.host.inbound.ingest(captured, capability="text").unwrap()
        owner = RoleOwnerRef(config.scope.installation_id, config.scope.bot_id, target.role_binding.role.subject_id)
        journal = JournalContext(JournalKey(owner, JournalKind.DREAM, "2026-09-21"), config.scope, "Asia/Shanghai")
        async def respond(*_):
            return completion(encode({"body": "", "form": "余韵", "recall": "afterglow", "afterglow": "梦已经记不清了。"}))
        self.native.provider.client.state.behavior = respond
        result = (await app.journal_writer.write(target, event, journal, role_instruction=captured.instruction,
                                                request_id="native-journal")).unwrap().task
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(app.role_journal.get(journal.key).draft.afterglow, "梦已经记不清了。")
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        bootstrap.identity.revoke_grant(bootstrap.grant_id("role.journal.write"),
            expected_revision=bootstrap.identity.revision, revoked_at=NOW)
        denied = await app.journal_writer.write(target, event, journal, role_instruction=captured.instruction,
                                                request_id="revoked", expected_revision=1)
        self.assertEqual(denied.failure.code, "authorization_revoked")
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_fresh_initialize_load_and_official_sender_use_exact_standard_grants(self):
        receipt = (await self.bootstrap.initialize()).unwrap()
        self.assertFalse(receipt.replayed)
        self.assertEqual(receipt.configuration_fingerprint, self.config.fingerprint)
        before = database_contents(self.runtime)
        session = self.load_session()
        self.assertEqual(database_contents(self.runtime), before)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.assertEqual(session.inspect().unwrap()["configuration_application"], "consumer_not_started")
        grants = self.bootstrap.identity.snapshot().grants
        self.assertEqual({g.capability for g in grants}, set(self.config.capabilities))
        self.assertTrue(all(g.tier is AuthorizationTier.STANDARD and g.scope == self.config.scope for g in grants))
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM subject_access_tiers", ()))
        policy = ObjectAccessPolicy(self.runtime)
        actor = session.profile.target.actor
        for forbidden in ("configuration.write", "access.policy.set", "memo.create"):
            self.assertFalse(policy.feature_access(actor, scope=self.config.scope, action=forbidden, observed_at=NOW).is_success)
        await self.start_session(session)
        batch = await self.receive(session)
        report = session.inspect(batch).unwrap()
        self.assertEqual(report["configuration_application"], "applied")
        self.assertEqual(report["model"]["calls"][0]["actual_tokens"], 40)
        self.assertTrue(report["confirmed_delivery"])
        self.assertEqual(report["conversation"]["receipt_basis"], "onebot_reverse_websocket")
        self.assertEqual(report["delivery_receipts"][0]["state"], "delivered")
        self.assertFalse(self.bootstrap.delivery_authorization_status()["required"])
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)

    async def test_load_does_not_implicitly_initialize(self):
        before = database_contents(self.runtime)
        self.assertEqual(self.bootstrap.load(runtime_instance_id="new").failure.code, "staging_not_initialized")
        self.assertEqual(database_contents(self.runtime), before)
        self.assertEqual(self.native.role_lookups, 0)

    async def test_initialized_application_assembly_remains_read_only(self):
        (await self.bootstrap.initialize()).unwrap()
        before = database_contents(self.runtime)

        with patch.object(self.runtime, "transaction", side_effect=AssertionError("assembly must stay read-only")):
            self.load_session()

        self.assertEqual(database_contents(self.runtime), before)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_official_sender_needs_no_global_delivery_authorization(self):
        bootstrap = self.make_bootstrap()
        (await bootstrap.initialize()).unwrap()
        session = self.load_session(bootstrap)
        before_grants = bootstrap.identity.snapshot().grants

        (await session.start(expected_task_generation=0, expected_model_generation=0)).unwrap()
        batch = await self.receive(session)
        report = session.inspect(batch).unwrap()

        self.assertTrue(report["confirmed_delivery"])
        self.assertEqual(report["delivery_authorization"]["state"], "not_required")
        self.assertFalse(bootstrap.delivery_authorization_status()["required"])
        self.assertTrue(bootstrap.delivery_authorization_status()["authorized"])
        self.assertEqual(bootstrap.identity.snapshot().grants, before_grants)
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)

    async def test_legacy_delivery_authorization_hook_is_a_noop_before_initialization(self):
        bootstrap = self.make_bootstrap()
        before = database_contents(self.runtime)
        result = bootstrap.authorize_delivery(expires_at=NOW + timedelta(minutes=15))
        self.assertTrue(result.is_success)
        self.assertEqual(result.unwrap().state, "not_required")
        self.assertFalse(bootstrap.delivery_authorization_status()["required"])
        self.assertEqual(database_contents(self.runtime), before)

    async def test_legacy_delivery_authorize_and_revoke_hooks_do_not_change_grants(self):
        bootstrap = self.make_bootstrap()
        (await bootstrap.initialize()).unwrap()
        before_grants = bootstrap.identity.snapshot().grants

        authorized = bootstrap.authorize_delivery(expires_at=NOW + timedelta(minutes=10)).unwrap()
        revoked = bootstrap.revoke_delivery().unwrap()

        self.assertEqual(authorized.state, "not_required")
        self.assertEqual(revoked.state, "not_required")
        self.assertTrue(authorized.replayed)
        self.assertTrue(revoked.replayed)
        self.assertEqual(bootstrap.identity.snapshot().grants, before_grants)
        self.assertEqual(bootstrap.delivery_authorization_status()["state"], "not_required")

    async def test_sender_compatibility_hook_succeeds_without_a_global_grant(self):
        bootstrap = self.make_bootstrap()
        (await bootstrap.initialize()).unwrap()
        self.assertIsNone(bootstrap.require_delivery_authorization())

    async def test_identical_replay_is_read_only_even_after_conversation(self):
        (await self.bootstrap.initialize()).unwrap()
        session = await self.start_session()
        await self.receive(session)
        before = database_contents(self.runtime)
        self.assertTrue((await self.bootstrap.initialize()).unwrap().replayed)
        self.assertEqual(database_contents(self.runtime), before)
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_concurrent_initializers_recheck_after_native_await(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def hold(_):
            entered.set()
            await release.wait()
        self.native.before_resolve = hold
        first = asyncio.create_task(self.bootstrap.initialize())
        await asyncio.wait_for(entered.wait(), 1)
        # A distinct SQLite connection commits while the first host read waits.
        self.native.before_resolve = None
        second = await self.make_bootstrap(runtime=self.open_runtime()).initialize()
        release.set()
        first_result = await first
        self.assertFalse(second.unwrap().replayed)
        self.assertTrue(first_result.unwrap().replayed)
        self.assertEqual(len(self.bootstrap.identity.snapshot().bindings), 1)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM operations", ())), 1)

    async def test_mid_grant_failure_rolls_back_all_authority_and_marker(self):
        before = database_contents(self.runtime)
        original = self.bootstrap.identity.issue_grant
        count = 0
        def fail(**kwargs):
            nonlocal count
            count += 1
            result = original(**kwargs)
            if count == 2:
                raise RuntimeError("sensitive-native-value")
            return result
        with patch.object(self.bootstrap.identity, "issue_grant", side_effect=fail):
            result = await self.bootstrap.initialize()
        self.assertEqual(result.failure.code, "staging_bootstrap_failed")
        self.assertNotIn("sensitive", result.failure.reason)
        self.assertEqual(database_contents(self.runtime), before)
        self.assertFalse((await self.bootstrap.initialize()).unwrap().replayed)

    async def test_cancellation_during_preflight_leaves_no_records(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def hold(_):
            entered.set()
            await release.wait()
        self.native.before_resolve = hold
        before = database_contents(self.runtime)
        task = asyncio.create_task(self.bootstrap.initialize())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(database_contents(self.runtime), before)

    async def test_existing_authority_store_is_rejected_without_native_or_database_changes(self):
        identity = self.bootstrap.identity
        identity.bind(binding_id="unrelated", principal=self.bootstrap.principal, subject=self.config.subject,
                      valid_from=NOW, expected_revision=identity.revision)
        before = database_contents(self.runtime)
        result = await self.bootstrap.initialize()
        self.assertEqual(result.failure.code, "staging_bootstrap_store_in_use")
        self.assertEqual(database_contents(self.runtime), before)
        self.assertEqual(self.native.role_lookups, 0)

    async def test_existing_role_life_store_is_rejected_without_native_or_database_changes(self):
        ledger = PersistentRoleLifeLedger(self.runtime, now=self.clock.now)
        activity = ledger.add_activity(RoleActivity(
            "reading", self.config.persona.role.subject_id, self.config.scope, NOW,
            RoleActivityState.ACTIVE, description="继续阅读", checkpoint="读到第二章",
        ))
        before = database_contents(self.runtime)

        result = await self.bootstrap.initialize()

        self.assertEqual(result.failure.code, "staging_bootstrap_store_in_use")
        self.assertEqual(database_contents(self.runtime), before)
        self.assertEqual(ledger.activity(activity.activity_id, owner=activity.owner), activity)
        self.assertEqual(self.native.role_lookups, 0)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_competing_management_write_during_native_preflight_is_preserved(self):
        async def write(_):
            identity = self.bootstrap.identity
            identity.bind(binding_id="operator", principal=self.bootstrap.principal, subject=self.config.subject,
                          valid_from=NOW, expected_revision=identity.revision)
        self.native.before_resolve = write
        result = await self.bootstrap.initialize()
        self.assertEqual(result.failure.code, "staging_bootstrap_store_in_use")
        self.assertEqual([b.binding_id for b in self.bootstrap.identity.snapshot().bindings], ["operator"])
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM operations", ()))

    async def test_wrong_provider_persona_route_and_disconnected_account_do_not_write(self):
        before = database_contents(self.runtime)
        cases = (
            ("provider", lambda: setattr(self.native.provider, "model_name", "other"), "staging_provider_mismatch"),
            ("persona", lambda: setattr(self.native, "selected", "other"), "host_persona_unmapped"),
            ("route", lambda: setattr(self.native, "cid", "other"), "host_persona_changed"),
            ("account", lambda: self.native.platform.client._wsr_api_clients.pop("100"), "staging_account_unavailable"),
        )
        for name, mutate, code in cases:
            with self.subTest(name=name):
                mutate()
                result = await self.bootstrap.initialize()
                self.assertEqual(result.failure.code, code)
                self.assertEqual(database_contents(self.runtime), before)
                self.native.provider.model_name = "fixture"
                self.native.selected = "original"
                self.native.cid = "conversation-1"
                self.native.platform.client._wsr_api_clients["100"] = object()

    async def test_provider_change_during_preflight_is_rejected_before_commit(self):
        async def change(_):
            self.native.provider.provider_config["model"] = "changed"
        self.native.before_resolve = change
        before = database_contents(self.runtime)
        self.assertEqual((await self.bootstrap.initialize()).failure.code, "host_provider_changed")
        self.assertEqual(database_contents(self.runtime), before)

    async def test_provider_lookup_cannot_substitute_a_different_native_instance_during_initialization(self):
        before = database_contents(self.runtime)
        changed = FakeProvider()
        calls = 0
        def lookup(_):
            nonlocal calls
            calls += 1
            return self.native.provider if calls == 1 else changed
        with patch.object(self.native, "get_provider_by_id", side_effect=lookup):
            self.assertEqual((await self.bootstrap.initialize()).failure.code, "staging_provider_mismatch")
        self.assertEqual(database_contents(self.runtime), before)

    async def test_expired_and_future_configuration_cannot_initialize(self):
        before = database_contents(self.runtime)
        for config in (replace(self.config, valid_from=NOW + timedelta(seconds=1)),
                       replace(self.config, valid_from=NOW - timedelta(days=2), expires_at=NOW)):
            self.assertEqual((await self.make_bootstrap(configuration=config).initialize()).failure.code, "staging_access_inactive")
        self.assertEqual(database_contents(self.runtime), before)

    async def test_a_rebinding_still_requires_a_different_store(self):
        """改指目标、参与人或人格一律拒绝，且不改动库内任何一行。

        固定 profile 的意义就是这个：一条误发的命令、一次手改配置都不能悄悄把角色
        指到别处。这里四个字段正好是 ``REBINDING_FIELDS``。
        """
        (await self.bootstrap.initialize()).unwrap()
        before = database_contents(self.runtime)
        rebindings = {
            "scope": replace(self.config, scope=replace(self.config.scope,
                                                        native_scope_id="201", session_id="201")),
            "subject": replace(self.config, subject=replace(self.config.subject,
                                                            subject_id="another-participant")),
            "persona": replace(self.config, persona=replace(self.config.persona,
                                                           persona_id="someone-else",
                                                           role=replace(self.config.persona.role,
                                                                        subject_id="another-role"))),
        }
        self.assertEqual(set(rebindings), set(REBINDING_FIELDS))
        for name, config in rebindings.items():
            with self.subTest(field=name):
                bootstrap = self.make_bootstrap(configuration=config)
                self.assertEqual((await bootstrap.initialize()).failure.code, "staging_bootstrap_conflict")
                self.assertEqual(bootstrap.load(runtime_instance_id="new").failure.code, "staging_bootstrap_conflict")
        self.assertEqual(database_contents(self.runtime), before)

    async def test_environment_drift_reuses_the_provisioned_store_and_names_the_fields(self):
        """调预算、改提示词上限不该让整台安装离线，但必须留下可读的痕迹。

        收据只存摘要，所以「哪些字段变了」只能靠建库时逐字段记下的摘要回答；报出的
        永远只是字段名——这份文档里有安装标识、人格提示词摘要和 provider 指纹。
        """
        (await self.bootstrap.initialize()).unwrap()
        before = database_contents(self.runtime)
        drifted = replace(self.config,
                          persona=replace(self.config.persona, instruction_hash="b" * 64),
                          task_prompt="另一份提示词", max_output_tokens=999,
                          budget=BudgetPolicy(*(Amount(10 ** 7, 10 ** 8) for _ in range(5))))
        bootstrap = self.make_bootstrap(configuration=drifted)

        with self.assertLogs("companion_v2.adapters.astrbot.staging_bootstrap", level="WARNING") as captured:
            replayed = (await bootstrap.initialize()).unwrap()
            session = self.load_session(bootstrap)

        self.assertTrue(replayed.replayed)
        self.assertEqual(replayed.configuration_fingerprint, drifted.fingerprint)
        trace = "\n".join(captured.output)
        self.assertIn("budget, max_output_tokens, persona, task_prompt", trace)
        self.assertNotIn("另一份提示词", trace)
        self.assertNotIn("999", trace)
        # 漂移后的取值真正生效：加载用的是当前记录，不是建库时那一份。
        self.assertEqual(session.profile.task_prompt, "另一份提示词")
        self.assertEqual(session.profile.max_output_tokens, 999)
        self.assertEqual(database_contents(self.runtime), before)

    def record_first_format_receipt(self, fingerprint):
        """把库内收据改写成第一版格式（只有整文档指纹），模拟已存在的安装。

        真实安装的收据就是这样一个裸摘要：没有身份子指纹，也没有逐字段摘要。
        """
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE operations SET parameter_hash = ? WHERE operation_id = ?",
                               (fingerprint, self.bootstrap.OPERATION_ID))

    async def test_a_receipt_recorded_before_the_identity_sub_hash_still_reopens(self):
        """已存在的库只有整文档指纹：环境漂移照旧加载，能核对的身份改了仍然拒绝。"""
        (await self.bootstrap.initialize()).unwrap()
        self.record_first_format_receipt(self.config.fingerprint)
        before = database_contents(self.runtime)

        drifted = self.make_bootstrap(configuration=replace(self.config, task_prompt="另一份提示词",
                                                           max_output_tokens=999))
        with self.assertLogs("companion_v2.adapters.astrbot.staging_bootstrap", level="WARNING") as captured:
            self.assertTrue((await drifted.initialize()).unwrap().replayed)
            self.load_session(drifted)
        self.assertIn("旧版", "\n".join(captured.output))
        self.assertEqual(database_contents(self.runtime), before)

        rebindings = {
            "subject": replace(self.config, subject=replace(self.config.subject,
                                                            subject_id="another-participant")),
            "persona": replace(self.config, persona=replace(self.config.persona,
                                                           role=replace(self.config.persona.role,
                                                                        subject_id="another-role"))),
        }
        for name, config in rebindings.items():
            with self.subTest(field=name):
                bootstrap = self.make_bootstrap(configuration=config)
                result = await bootstrap.initialize()
                self.assertEqual(result.failure.code, "staging_bootstrap_conflict")
                self.assertTrue(result.failure.reason.endswith(name))
                self.assertEqual(bootstrap.load(runtime_instance_id="new").failure.code, "staging_bootstrap_conflict")
        self.assertEqual(database_contents(self.runtime), before)

    async def test_legacy_runtime_pin_does_not_reject_model_drift_after_bootstrap_validation(self):
        """旧 PIN 哈希无法拆字段；已核验的旧引导收据负责保住身份闸门。"""
        (await self.bootstrap.initialize()).unwrap()
        self.record_first_format_receipt(self.config.fingerprint)
        original = self.load_session()
        started = await original.start(expected_task_generation=0, expected_model_generation=0)
        self.assertTrue(started.is_success, started.failure)
        legacy_hash = original._legacy_profile_hash
        await original.close()

        with self.runtime.transaction() as connection:
            connection.execute("UPDATE operations SET parameter_hash = ? WHERE operation_id = ?",
                               (legacy_hash, original.PIN_ID))

        drifted = self.make_bootstrap(configuration=replace(
            self.config, task_prompt="只改模型任务提示", max_output_tokens=120))
        self.assertEqual(drifted.configuration.identity_fingerprint,
                         self.config.identity_fingerprint)
        self.assertTrue((await drifted.initialize()).unwrap().replayed)
        reopened = self.load_session(drifted)
        resumed = await reopened.start(expected_task_generation=1, expected_model_generation=1)

        self.assertTrue(resumed.is_success, resumed.failure)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        await reopened.close()

    async def test_a_first_format_receipt_with_legacy_preview_reopens_official_sender(self):
        (await self.bootstrap.initialize()).unwrap()
        legacy_document = {**self.config.document(), "delivery_mode": "preview"}
        legacy = StagingConfiguration.parse(json.dumps(legacy_document, ensure_ascii=False))
        self.record_first_format_receipt(legacy.fingerprint)
        promoted = self.make_bootstrap(configuration=legacy)

        session = self.load_session(promoted)
        started = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertTrue(started.is_success, started.failure)
        batch = await self.receive(session)
        report = session.inspect(batch).unwrap()

        self.assertEqual(legacy.delivery_mode, "onebot_private")
        self.assertTrue(report["confirmed_delivery"])
        self.assertEqual(report["delivery_receipts"][0]["state"], "delivered")
        self.assertFalse(promoted.delivery_authorization_status()["required"])
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)

    async def test_provider_drift_is_still_refused_by_the_provider_check(self):
        """provider 指纹不在这道闸门的范围内：收据放行后由原有的 provider 校验拦住。"""
        (await self.bootstrap.initialize()).unwrap()
        drifted = replace(self.config, provider_fingerprint="a" * 64)
        bootstrap = self.make_bootstrap(configuration=drifted)
        self.assertTrue((await bootstrap.initialize()).unwrap().replayed)
        self.assertEqual(bootstrap.load(runtime_instance_id="new").failure.code, "staging_provider_mismatch")

    async def test_revoked_identity_grant_and_persona_are_not_repaired_on_replay_or_load(self):
        (await self.bootstrap.initialize()).unwrap()
        identity = self.bootstrap.identity
        identity.revoke_grant(self.bootstrap.grant_id("text"), revoked_at=NOW, expected_revision=identity.revision)
        before = database_contents(self.runtime)
        for bootstrap in (self.bootstrap, self.make_bootstrap(runtime=self.open_runtime())):
            self.assertEqual((await bootstrap.initialize()).failure.code, "authorization_revoked")
            self.assertEqual(bootstrap.load(runtime_instance_id="new").failure.code, "authorization_revoked")
        self.assertEqual(database_contents(self.runtime), before)
        # Replacing the grant cannot impersonate its original authorization.
        identity.issue_grant(grant_id="replacement", subject=self.config.subject, scope=self.config.scope,
            capability="text", tier=AuthorizationTier.STANDARD, valid_from=NOW, expected_revision=identity.revision)
        self.assertEqual((await self.bootstrap.initialize()).failure.code, "staging_grant_changed")
        self.bootstrap.personas.revoke_binding(self.bootstrap.PERSONA_ID, expected_revision=1, observed_at=NOW)
        before = database_contents(self.runtime)
        self.assertEqual((await self.bootstrap.initialize()).failure.code, "role_binding_missing")
        self.assertEqual(self.bootstrap.load(runtime_instance_id="new").failure.code, "role_binding_missing")
        self.assertEqual(database_contents(self.runtime), before)
        identity.revoke_binding(self.bootstrap.IDENTITY_ID, revoked_at=NOW, expected_revision=identity.revision)
        before = database_contents(self.runtime)
        self.assertEqual((await self.bootstrap.initialize()).failure.code, "binding_revoked")
        self.assertEqual(self.bootstrap.load(runtime_instance_id="new").failure.code, "binding_revoked")
        self.assertEqual(database_contents(self.runtime), before)

    async def test_access_expiry_is_preserved_on_reopen(self):
        config = replace(self.config, expires_at=NOW + timedelta(seconds=1))
        bootstrap = self.make_bootstrap(configuration=config)
        (await bootstrap.initialize()).unwrap()
        self.clock.advance(timedelta(seconds=1))
        before = database_contents(self.runtime)
        reopened = self.make_bootstrap(runtime=self.open_runtime(), configuration=config)
        self.assertEqual((await reopened.initialize()).failure.code, "staging_access_inactive")
        self.assertEqual(reopened.load(runtime_instance_id="new").failure.code, "staging_access_inactive")
        self.assertEqual(database_contents(self.runtime), before)

    async def test_load_sanitizes_native_failure_and_checks_provider_between_lookups(self):
        (await self.bootstrap.initialize()).unwrap()
        before = database_contents(self.runtime)
        with patch.object(self.native, "get_provider_by_id", side_effect=RuntimeError("secret-provider-value")):
            result = self.bootstrap.load(runtime_instance_id="new")
        self.assertEqual(result.failure.code, "staging_load_failed")
        self.assertNotIn("secret-provider", result.failure.reason)
        changed = FakeProvider()
        changed.provider_config["model"] = "changed"
        for boundary, code in ((2, "staging_provider_mismatch"), (3, "host_provider_changed")):
            calls = 0
            def lookup(_):
                nonlocal calls
                calls += 1
                return self.native.provider if calls < boundary else changed
            with self.subTest(boundary=boundary), patch.object(self.native, "get_provider_by_id", side_effect=lookup):
                self.assertEqual(self.bootstrap.load(runtime_instance_id="new").failure.code, code)
        self.assertEqual(database_contents(self.runtime), before)

    async def test_owner_configuration_changes_survive_reload_without_reapplying_file_defaults(self):
        config = replace(self.config, capabilities=tuple(sorted((*self.config.capabilities, "configuration.write"))))
        bootstrap = self.make_bootstrap(configuration=config)
        (await bootstrap.initialize()).unwrap()
        session = await self.start_session(self.load_session(bootstrap))
        actor = session.profile.target.actor
        service = session.application.configuration
        group = session.model_profile.group
        snapshot = service.read(actor, target=session.config_target, group_id=group, observed_at=NOW).unwrap()
        operation = OperationRef("edit-prompt", "configuration", config.scope, VersionRef("edit-prompt", 1), "edit-prompt")
        service.patch(actor, target=session.config_target, group_id=group, expected_edit_token=snapshot.edit_token,
            operation=operation, changes={group + ".prompt": "更新后的任务提示", group + ".max_output_tokens": 60},
            observed_at=NOW).unwrap()
        await session.close()
        reopened = self.make_bootstrap(runtime=self.open_runtime(), configuration=config)
        (await reopened.initialize()).unwrap()
        other = await self.start_session(self.load_session(reopened, instance="runtime-2"), generation=1)
        batch = await self.receive(other, event_id="next-event")
        payload = self.native.provider.client.state.calls[-1][0]
        self.assertEqual(payload["max_tokens"], 60)
        self.assertIn("更新后的任务提示", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(other.inspect(batch).unwrap()["configuration_application"], "applied")


class StagingBootstrapProcessTests(BootstrapFixture, unittest.TestCase):
    def child(self, mode):
        result = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests.staging_bootstrap_process",
            mode, str(self.root)], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, encoding="utf-8", timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_separate_process_recovers_unknown_send_without_retry_and_preserves_revocation(self):
        self.runtime.close()
        before = self.child("seed-and-exit")
        self.assertEqual(before["delivery_receipts"][0]["state"], "unknown")
        self.assertEqual((before["new_model_calls"], before["new_send_calls"]), (1, 1))
        after = self.child("recover")
        for field in ("batch_id", "delivery_receipts", "model_calls"):
            self.assertEqual(after[field], before[field])
        self.assertTrue(after["replayed"])
        self.assertEqual((after["new_model_calls"], after["new_send_calls"]), (0, 0))
        self.assertEqual(after["task_generation"], 2)
        runtime = self.open_runtime()
        identity = self.make_bootstrap(runtime=runtime).identity
        identity.revoke_grant(self.bootstrap.grant_id("text"), revoked_at=NOW, expected_revision=identity.revision)
        runtime.close()
        revoked = self.child("check-revoked")
        self.assertEqual(revoked, {"initialize": "authorization_revoked", "load": "authorization_revoked", "unchanged": True})
