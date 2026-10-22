"""Upgrades retain approved expressions and review state without inventing turns."""

from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from companion_v2.execution.models import TaskContext, TaskError
from companion_v2.expression.legacy_import import import_profile, preview
from companion_v2.expression.style_management import ExpressionStyleManagement
from companion_v2.foundation.refs import AudienceRef, ScopeKind
from companion_v2.legacy.data_migration import build_data_plan
from companion_v2.legacy.expression_data import expression_profiles, selected_profile
from companion_v2.legacy.migration import LegacyMigration
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE


def legacy_data(context):
    user = context.actor.principal.native_account_id
    rule = {"id": "old-rule", "kind": "grammar", "situation": "收束话题",
        "pattern": "简短地结束", "instruction": "保留轻巧的句末停顿", "channels": ["private", "proactive"],
        "relationship_stages": ["familiar", "any"], "evidence_examples": ["好，等会见。"]}
    return {"users": {user: {"identity_subject_id": user, "identity_platform_kind": "onebot",
        "identity_adapter_instance_id": context.scope.platform, "identity_bot_id": context.scope.account_id,
        "expression_profile": {"learned_rules": [rule],
            "pending_rules": [{**rule, "id": "pending"}], "rejected_rules": [{**rule, "id": "rejected"}],
            "pending_samples": [{"id": "sample", "text": "稍后聊呀。", "ts": NOW.timestamp()}]}}}}


class LegacyExpressionTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def context(self):
        binding = self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap()
        return TaskContext(self.important, binding, AudienceRef(SCOPE, (self.important.subject,)))

    async def test_real_data_route_keeps_states_samples_and_injects_the_approved_rule(self):
        host = await self.start()
        context = self.context()
        with TemporaryDirectory(prefix="legacy-expression-") as directory:
            root = Path(directory)
            data = legacy_data(context)
            # The original timestamp is retained, rather than replayed as a fresh message.
            data["users"][context.actor.principal.native_account_id]["expression_profile"]["pending_samples"][0]["ts"] = self.clock.now().timestamp()
            path = root / "companions.json"
            path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
            migration = LegacyMigration(v1_root=root, v1_configuration={})
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=self.runtime, now=self.clock.now, data_root=self.root)
            service = SimpleNamespace(ensure_reaction_catalog=lambda _: "fixture-role",
                                      reaction_owner=lambda _: "fixture-role")
            api._data_context = lambda _: (context, service)
            api._reaction_ids = lambda *_: set()
            session = SimpleNamespace(profile=SimpleNamespace(target=context), application=host.application)
            plan = api._data_plan(migration, root, session).unwrap()
            self.assertEqual(plan["expressions"]["adopted_count"], 1)
            args = dict(plan_token=plan["plan_token"], source_group_id="", source_persona_id="",
                import_reactions=False, import_group_network=False, confirm_member_ids=False,
                import_journals=False, confirm_persona_mapping=False, import_worldbook=False,
                import_expressions=True)
            denied = await api._data_apply(migration, root, session, **args)
            self.assertEqual(denied.failure.code, "legacy_expression_mapping_required")
            result = (await api._data_apply(migration, root, session, **args, confirm_expression_mapping=True)).unwrap()
            self.assertEqual(result["expressions"]["created"], 3)
            styles = ExpressionStyleManagement(host.application)
            adopted = styles.list(operator=self.core, context=context, state="adopted").unwrap()["items"]
            self.assertEqual(len(adopted), 1)
            self.assertEqual(adopted[0]["evidence"], ["好，等会见。"])
            self.assertEqual(adopted[0]["source_kind"], "legacy_expression")
            self.assertIsNone(adopted[0]["unavailable_reason"])
            catalog = host.application.expression_style_context
            snapshot = catalog.capture(context, self.clock.now())
            material = catalog.contributions(snapshot, context, self.clock.now())
            self.assertTrue(any("保留轻巧的句末停顿" in item.payload for item in material))
            samples = styles.list_samples(operator=self.core, context=context).unwrap()
            self.assertEqual(samples["counts"]["pending"], 1)
            sample = samples["items"][0]
            styles.sample_command(operator=self.core, context=context, handle=sample["handle"],
                action="approve", view_token=sample["view_token"], operation_key="approve-migrated-sample").unwrap()
            style = adopted[0]
            styles.command(operator=self.core, context=context, signal_id=style["signal_id"], action="retire",
                view_token=style["view_token"], operation_key="retire-migrated-expression").unwrap()
            newplan = api._data_plan(migration, root, session).unwrap()
            args["plan_token"] = newplan["plan_token"]
            replay = (await api._data_apply(migration, root, session, **args, confirm_expression_mapping=True)).unwrap()
            self.assertEqual(replay["expressions"]["created"], 0)
            self.assertEqual(styles.list(operator=self.core, context=context, state="adopted").unwrap()["items"], [])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), fingerprint)
            self.assertEqual(self.called, [])
            self.assertEqual(self.sent, [])

    async def test_wrong_account_and_other_person_are_not_mapped(self):
        context = self.context()
        data = legacy_data(context)
        profiles = expression_profiles(data)
        self.assertIsNotNone(selected_profile(profiles, context))
        other = TaskContext(self.standard, context.role_binding, AudienceRef(SCOPE, (self.standard.subject,)))
        self.assertIsNone(selected_profile(profiles, other))
        data["users"][context.actor.principal.native_account_id]["identity_bot_id"] = "another-login"
        self.assertIsNone(selected_profile(expression_profiles(data), context))

    async def test_retirement_newer_data_and_changed_source_do_not_reactivate_old_rules(self):
        context = self.context()
        data = legacy_data(context)
        profiles = expression_profiles(data)
        profile = profiles[0]
        token = preview(self.runtime, profile, context)["token"]
        data["users"][context.actor.principal.native_account_id]["expression_profile"]["learned_rules"][0]["instruction"] = "新的表达"
        changed = expression_profiles(data)[0]
        with self.assertRaises(TaskError):
            import_profile(self.runtime, changed, context, self.clock.now(), expected_token=token)
        import_profile(self.runtime, profile, context, self.clock.now(), expected_token=token)
        self.assertEqual(preview(self.runtime, profile, context)["remaining"], 0)

    async def test_context_does_not_share_legacy_private_rules_with_other_people(self):
        host = await self.start()
        context = self.context()
        profile = expression_profiles(legacy_data(context))[0]
        import_profile(self.runtime, profile, context, self.clock.now(),
                       expected_token=preview(self.runtime, profile, context)["token"])
        scope = replace(SCOPE, native_scope_id="other-window")
        other = TaskContext(self.standard, replace(context.role_binding, scope=scope),
                            AudienceRef(scope, (self.standard.subject,)))
        captured = host.application.expression_style_context.capture(other, self.clock.now())
        self.assertEqual(captured["references"], [])

    async def test_later_samples_merge_without_restoring_a_newer_review(self):
        from companion_v2.expression.legacy_import import samples
        from companion_v2.expression.sample_review import ExpressionSampleReviewStore

        context = self.context()
        data = legacy_data(context)
        profile = expression_profiles(data)[0]
        import_profile(self.runtime, profile, context, self.clock.now(),
                       expected_token=preview(self.runtime, profile, context)["token"])
        bounds = dict(opened_at=NOW - timedelta(days=1), closed_at=self.clock.now())
        old_sample = samples(self.runtime, context, **bounds)[0]
        reviews = ExpressionSampleReviewStore(self.runtime)
        value = reviews.read(context, old_sample.handle)
        reviews.write(context, {**value, "state": "rejected"})
        raw_profile = next(iter(data["users"].values()))["expression_profile"]
        raw_profile["pending_samples"].append({"id": "later", "text": "明天接着聊。", "ts": NOW.timestamp()})
        profile = expression_profiles(data)[0]
        plan = preview(self.runtime, profile, context)
        self.assertEqual(plan["remaining"], 1)
        result = import_profile(self.runtime, profile, context, self.clock.now(), expected_token=plan["token"])
        self.assertEqual((result["created"], result["samples_created"], result["remaining"]), (0, 1, 0))
        self.assertEqual(len(samples(self.runtime, context, **bounds)), 2)
        self.assertEqual(reviews.read(context, old_sample.handle)["state"], "rejected")

    async def test_sample_scope_conflicts_and_denials_are_kept_out_of_learning(self):
        context = self.context()
        data = legacy_data(context)
        raw = next(iter(data["users"].values()))["expression_profile"]
        owner = {"owner_type": "private", "owner_id": "original",
                 "source_namespace": "source", "application_namespace": "source"}
        raw["scope_ownership"] = owner
        sample = raw["pending_samples"][0]
        raw["samples"] = [{**sample, "scope_binding": {**owner, "owner_id": "other-owner",
                          "approval_state": "approved", "approved_by": "administrator"}}]
        # The pending duplicate stays pending; a conflicting approved copy must never win.
        self.assertEqual(expression_profiles(data)[0]["samples"][0]["state"], "pending")
        raw["pending_samples"] = []
        parsed = expression_profiles(data)[0]
        self.assertFalse(parsed["samples"])
        self.assertTrue(any(item["reason"] == "ownership_mismatch" for item in parsed["rejected"]))
        raw["samples"] = [sample]
        raw["rejected_samples"] = [sample]
        self.assertEqual(expression_profiles(data)[0]["samples"][0]["state"], "rejected")

    async def test_group_rule_and_sample_history_stay_in_the_selected_group_and_role(self):
        from companion_v2.expression.legacy_import import samples

        base = self.context()
        scope = replace(SCOPE, kind=ScopeKind.GROUP, native_scope_id="group-one")
        context = TaskContext(base.actor, replace(base.role_binding, scope=scope), AudienceRef(scope, (base.actor.subject,)))
        raw = next(iter(legacy_data(base)["users"].values()))["expression_profile"]
        raw["learned_rules"][0]["channels"] = ["group"]
        raw["samples"] = [{"id": "aggregate", "ts": NOW.timestamp(), "features": {"short": 4}}]
        data = {"groups": {"group-one": {"expression_profile": raw}}}
        profile = selected_profile(expression_profiles(data), context, "group-one")
        self.assertIsNotNone(profile)
        self.assertIsNone(selected_profile(expression_profiles(data), context, "group-two"))
        import_profile(self.runtime, profile, context, self.clock.now(),
                       expected_token=preview(self.runtime, profile, context)["token"])
        other_role = replace(context.role_binding.role, subject_id="another-role")
        other = TaskContext(context.actor, replace(context.role_binding, role=other_role), context.audience)
        self.assertEqual(preview(self.runtime, profile, other)["remaining"], 5)
        available = samples(self.runtime, context, opened_at=NOW - timedelta(days=1), closed_at=self.clock.now())
        self.assertEqual(len(available), 1)  # Only the original text sample, not the aggregate features.


if __name__ == "__main__":
    unittest.main()
