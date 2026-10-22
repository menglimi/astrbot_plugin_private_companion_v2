"""Acceptance: import V1 expression-learning material through the formal route.

The process runs in one of two phases against the same isolated V2 data root:

* ``import`` imports every content-bearing V1 expression profile through
  ``LegacyMigrationWebAPI._data_plan`` and ``_data_apply`` and checks the
  stored rules, evidence, review states and scope isolation.
* ``verify`` starts a fresh host process, loads the existing data root and
  checks that every imported scope survived the restart and that another
  import request adds nothing.

Only counts and hashes are printed or written; the source conversation text is
never included in the summary.  No model provider or platform sender is used.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion_v2.execution.models import TaskContext, digest
from companion_v2.expression.legacy_import import identifiers, signal_id
from companion_v2.expression.sample_review import ExpressionSampleReviewStore, PREFIX
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, ScopeKind
from companion_v2.legacy.archive import build_v1_archive_plan
from companion_v2.legacy.expression_data import expression_profiles
from companion_v2.legacy.migration import LegacyMigration

ROLE_ID = "role-a"
BOT_ID = "bot-a"
SOURCE_PERSONA_FALLBACK = "legacy-primary"
UNMAPPED_PRIVATE_ID = "900000000"
UNMAPPED_GROUP_ID = "915052038"
SEND_ACTIONS = {"send_private_msg", "send_group_msg", "send_msg"}
RULE_FIELDS = ("learned_rules", "pending_rules", "rejected_rules", "retired_rules")
SAMPLE_FIELDS = ("samples", "pending_samples", "rejected_samples")


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _source_state(root: Path, config_path: Path) -> dict:
    archive = build_v1_archive_plan(root)
    return {
        "companions_sha256": _sha256(root / "companions.json"),
        "v1_configuration_sha256": _sha256(config_path),
        "archive_inventory_fingerprint": archive.inventory_fingerprint,
        "archive_file_count": len(archive.files),
        "archive_total_bytes": archive.total_bytes,
    }


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _expected_counts(profile):
    rules = Counter(rule["state"] for rule in profile["rules"])
    samples = Counter(sample["state"] for sample in profile["samples"])
    return {"rules": len(profile["rules"]), "rule_states": dict(sorted(rules.items())),
            "samples": len(profile["samples"]), "sample_states": dict(sorted(samples.items()))}


def _validate_profiles(profiles):
    content = [profile for profile in profiles
               if profile["rules"] or profile["samples"]]
    _require(len(content) == 6, "expected_six_expression_profiles")
    private = [profile for profile in content if profile["source_kind"] == "private"]
    group = [profile for profile in content if profile["source_kind"] == "group"]
    _require(len(private) == 4 and len(group) == 2, "unexpected_expression_profile_mix")
    _require(sum(len(profile["rules"]) for profile in content) == 312, "unexpected_rule_count")
    _require(sum(len(profile["samples"]) for profile in content) == 204, "unexpected_sample_count")
    _require(all(not profile["rejected"] for profile in content), "expression_scan_rejected_rows")
    for profile in private:
        identity = profile["identity"]
        _require(identity.get("identity_subject_id") == profile["source_id"],
                 "private_identity_subject_mismatch")
        _require(identity.get("identity_platform_kind") == "onebot",
                 "private_identity_platform_mismatch")
        _require(identity.get("identity_adapter_instance_id"), "private_identity_adapter_missing")
        _require(identity.get("identity_bot_id"), "private_identity_bot_missing")
    return private, group


def _targets(private_profiles):
    platforms = sorted({profile["identity"]["identity_adapter_instance_id"]
                        for profile in private_profiles})
    accounts = sorted({profile["identity"]["identity_bot_id"] for profile in private_profiles})
    _require(len(platforms) == 1 and len(accounts) == 1,
             "acceptance_requires_one_source_platform_and_account")
    targets = [{"target_id": "expression-person-" + str(index),
                "platform_id": platforms[0], "account_id": accounts[0],
                "bot_id": BOT_ID, "participant_id": profile["source_id"]}
               for index, profile in enumerate(private_profiles)]
    return targets, platforms[0], accounts[0]


def _source_persona(config):
    basic = config.get("basic_config") if isinstance(config.get("basic_config"), dict) else {}
    value = basic.get("plugin_specific_persona_id") or config.get(
        "basic_config.plugin_specific_persona_id") or ""
    return value.strip() if isinstance(value, str) and value.strip() else SOURCE_PERSONA_FALLBACK


def _load_source(args):
    config = json.loads(args.v1_config.read_text(encoding="utf-8-sig"))
    data = json.loads((args.v1_root / "companions.json").read_text(encoding="utf-8-sig"))
    profiles = expression_profiles(data)
    private, group = _validate_profiles(profiles)
    return config, profiles, private, group


def _build_runtime(args, config, profiles, private, group):
    from astrbot.core import db_helper
    from astrbot_host.multi_controller import AstrBotMultiController
    from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
    from tests.multi_host_support import MultiNativeContext, multi_config
    from tests.native_adapter_support import (FakeEvent, FakePlatform, FakeProvider,
                                              FakeReverseApi)
    from types import SimpleNamespace as NS

    database = Path(db_helper.db_path).resolve()
    if not database.is_relative_to(args.astrbot_root.resolve()):
        raise RuntimeError("sdk_database_escaped_acceptance_root")

    targets, platform_id, account_id = _targets(private)
    persona = _source_persona(config)
    settings = multi_config(targets=targets, personas=[
        {"bot_id": BOT_ID, "persona_id": persona, "role_id": ROLE_ID},
        {"bot_id": BOT_ID, "persona_id": "acceptance-second", "role_id": "role-b"}])

    native = MultiNativeContext()
    platform = FakePlatform(platform_id)
    platform.client._wsr_api_clients.clear()
    platform.client._wsr_api_clients[account_id] = object()
    native.platforms[platform_id] = platform
    native.selections[platform_id] = persona
    native.conversations[platform_id] = "conversation-" + platform_id
    native.persona = {"name": persona, "prompt": "验收宿主中的旧版角色"}
    native.persona_records = {persona: native.persona,
        "acceptance-second": {"name": "acceptance-second", "prompt": "独立角色"}}
    native.persona_manager.personas_v3 = list(native.persona_records.values())
    native.persona_manager.get_persona_v3_by_id = native.persona_records.get

    async def selected_persona(_umo):
        return persona

    types = NativeAdapterTypes("4.28.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi,
        session_persona_override_lookup=selected_persona)
    controller = AstrBotMultiController(native, settings, args.data_root,
        native_types=types, now=lambda: NOW)
    migration = LegacyMigration(v1_root=args.v1_root, v1_configuration=config)
    return {"native": native, "controller": controller, "migration": migration,
            "targets": targets, "group_ids": [profile["source_id"] for profile in group],
            "platform_id": platform_id, "account_id": account_id, "persona": persona}


def _web_api(controller, data_root):
    from astrbot_host.legacy_api import LegacyMigrationWebAPI
    from types import SimpleNamespace as NS
    api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
    api.controller = NS(runtime=controller.session.runtime, now=lambda: NOW,
                        data_root=data_root)
    return api


def _contexts(controller, targets, group_ids):
    result = {}
    for target in targets:
        context = controller.session.authority.context(target["target_id"], ROLE_ID)
        result[("private", target["participant_id"])] = context
    base = next(iter(result.values()))
    for group_id in group_ids:
        scope = replace(base.scope, kind=ScopeKind.GROUP, native_scope_id=group_id)
        context = TaskContext(base.actor, replace(base.role_binding, scope=scope),
            AudienceRef(scope, (base.actor.subject,)))
        result[("group", group_id)] = context
    return result


def _session(controller, context):
    from types import SimpleNamespace as NS
    return NS(profile=NS(target=context), application=controller.session.application)


def _plan(runtime_api, migration, root, controller, context, source_group_id=""):
    outcome = runtime_api._data_plan(migration, root, _session(controller, context),
        source_group_id=source_group_id, source_persona_id="")
    if not outcome.is_success:
        raise RuntimeError("data_plan:" + str(getattr(outcome.failure, "code", "failed")))
    return outcome.unwrap()


async def _apply(runtime_api, migration, root, controller, context, token, source_group_id=""):
    outcome = await runtime_api._data_apply(migration, root, _session(controller, context),
        plan_token=token, source_group_id=source_group_id, source_persona_id="",
        import_reactions=False, import_group_network=False, confirm_member_ids=False,
        import_journals=False, confirm_persona_mapping=False, import_worldbook=False,
        import_expressions=True, confirm_expression_mapping=True)
    if not outcome.is_success:
        raise RuntimeError("data_apply:" + str(getattr(outcome.failure, "code", "failed")))
    return outcome.unwrap()


def _profile_pairs(profiles, contexts):
    pairs = []
    for profile in profiles:
        key = (profile["source_kind"], profile["source_id"])
        if key not in contexts:
            raise RuntimeError("expression_context_missing")
        pairs.append((profile, contexts[key]))
    return pairs


def _source_group(profile):
    return profile["source_id"] if profile["source_kind"] == "group" else ""


def _sample_handle(run_id, source_key, raw, at):
    text = raw.get("text") or raw.get("phrase")
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        received = datetime.fromtimestamp(float(raw["ts"]), timezone.utc)
    except (KeyError, ValueError, TypeError, OverflowError, OSError):
        return None
    if not datetime(1970, 1, 1, tzinfo=timezone.utc) <= received <= at:
        return None
    return "input:legacy:" + digest([run_id, source_key])


def _verify_profile(runtime, profile, context, at):
    owner, scope, run_id = identifiers(profile, context)
    run = runtime.read_one("SELECT * FROM expression_style_runs WHERE run_id = ?", (run_id,))
    if run is None:
        raise RuntimeError("expression_run_missing")
    if run["owner_key"] != owner or run["scope_key"] != scope:
        raise RuntimeError("expression_run_scope_mismatch")
    if run["state"] != "decided" or run["material_hash"] != digest(profile):
        raise RuntimeError("expression_run_invalid")
    window = json.loads(run["sample_json"])
    legacy = window.get("legacy") if isinstance(window, dict) else None
    if (not isinstance(legacy, dict) or legacy.get("source_kind") != profile["source_kind"]
            or legacy.get("source_id") != profile["source_id"]):
        raise RuntimeError("expression_run_source_mismatch")

    rows = runtime.read_all(
        "SELECT * FROM expression_style_signals WHERE run_id = ? ORDER BY ordinal", (run_id,))
    rules = sorted(profile["rules"], key=lambda item: item["source_key"])
    if len(rows) != len(rules):
        raise RuntimeError("expression_rule_count_mismatch")
    for rule, row in zip(rules, rows):
        expected = signal_id(run_id, rule)
        if row["signal_id"] != expected or row["state"] != rule["state"]:
            raise RuntimeError("expression_rule_identity_or_state_mismatch")
        if (row["dimension"] != rule["dimension"]
                or row["observation"] != rule["observation"]
                or row["proposal"] != rule["proposal"]
                or abs(row["confidence"] - rule["confidence"]) > 1e-12):
            raise RuntimeError("expression_rule_content_mismatch")
        if json.loads(row["applicability_json"]) != rule["applicability"]:
            raise RuntimeError("expression_rule_applicability_mismatch")
        handles = json.loads(row["evidence_json"])
        if len(handles) != len(rule["examples"]):
            raise RuntimeError("expression_rule_evidence_count_mismatch")
        for handle, text in zip(handles, rule["examples"]):
            if legacy.get("evidence", {}).get(handle) != text:
                raise RuntimeError("expression_rule_evidence_mismatch")
        if legacy.get("rules", {}).get(expected) != rule["legacy"]:
            raise RuntimeError("expression_rule_legacy_counters_mismatch")
        if row["decided_by"] != "legacy_migration":
            raise RuntimeError("expression_rule_decider_mismatch")
        if row["state"] == "pending" and row["decided_at"] is not None:
            raise RuntimeError("expression_pending_rule_has_decision_time")
        if row["state"] != "pending" and row["decided_at"] is None:
            raise RuntimeError("expression_decided_rule_lacks_decision_time")
        if row["decision_key"] != "legacy:" + digest(rule):
            raise RuntimeError("expression_rule_decision_key_mismatch")

    entries = legacy.get("samples") or []
    if len(entries) != len(profile["samples"]):
        raise RuntimeError("expression_sample_count_mismatch")
    by_key = {}
    for entry in entries:
        key = entry.get("source_key")
        if not isinstance(key, str) or key in by_key:
            raise RuntimeError("expression_sample_identity_mismatch")
        by_key[key] = entry
    if set(by_key) != {item["source_key"] for item in profile["samples"]}:
        raise RuntimeError("expression_sample_source_mismatch")

    store = ExpressionSampleReviewStore(runtime)
    handles = set()
    review_count = 0
    for item in profile["samples"]:
        entry = by_key[item["source_key"]]
        if entry.get("state") != item["state"]:
            raise RuntimeError("expression_sample_state_mismatch")
        raw = item["value"]
        handle = _sample_handle(run_id, item["source_key"], raw, at)
        if handle is None:
            continue
        value = store.read(context, handle)
        if value is None:
            raise RuntimeError("expression_sample_review_missing")
        text = raw.get("text") or raw.get("phrase")
        if (value["state"] != item["state"] or value["content_hash"] != digest(text)
                or value["decided_by"] != "legacy_migration" or value["decided_at"] is None):
            raise RuntimeError("expression_sample_review_mismatch")
        handles.add(handle)
        review_count += 1

    owner_ref = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                             context.role_binding.role.subject_id)
    prefix = PREFIX + digest([owner_ref, context.scope]) + ":"
    stored = {row["key"] for row in runtime.read_all(
        "SELECT key FROM runtime_metadata WHERE substr(key, 1, ?) = ?", (len(prefix), prefix))}
    expected_keys = {store.key(context, handle) for handle in handles}
    if stored != expected_keys:
        raise RuntimeError("expression_sample_review_scope_mismatch")

    return {"kind": profile["source_kind"], "rules": len(rules),
            "rule_states": dict(sorted(Counter(rule["state"] for rule in rules).items())),
            "samples": len(entries),
            "sample_states": dict(sorted(Counter(item["state"] for item in profile["samples"]).items())),
            "review_samples": review_count}


def _verify_matrix(runtime, pairs):
    expected = []
    for profile, context in pairs:
        owner, scope, run_id = identifiers(profile, context)
        expected.append((owner, scope, run_id, profile))
    expected_pairs = {(owner, scope) for owner, scope, _, _ in expected}
    if len(expected_pairs) != len(expected):
        raise RuntimeError("expression_scopes_are_not_unique")

    runs = runtime.read_all("SELECT run_id, owner_key, scope_key FROM expression_style_runs", ())
    if len(runs) != len(expected) or {(row["owner_key"], row["scope_key"]) for row in runs} != expected_pairs:
        raise RuntimeError("expression_run_matrix_mismatch")

    rows = runtime.read_all("""SELECT owner_key, scope_key, state, COUNT(*) AS n
        FROM expression_style_signals GROUP BY owner_key, scope_key, state""", ())
    actual = {(row["owner_key"], row["scope_key"]): Counter() for row in runs}
    actual_states = Counter()
    for row in rows:
        actual.setdefault((row["owner_key"], row["scope_key"]), Counter())[row["state"]] = row["n"]
        actual_states[row["state"]] += row["n"]
    if set(actual) != expected_pairs:
        raise RuntimeError("expression_signal_matrix_mismatch")
    total = 0
    for owner, scope, run_id, profile in expected:
        counts = Counter(rule["state"] for rule in profile["rules"])
        if actual[(owner, scope)] != counts:
            raise RuntimeError("expression_signal_state_matrix_mismatch")
        total += sum(counts.values())
    if total != 312 or sum(actual_states.values()) != 312:
        raise RuntimeError("expression_signal_total_mismatch")
    return {"runs": len(runs), "signals": total,
            "states": dict(sorted(actual_states.items())),
            "scopes": len(expected_pairs)}


def _verify_unmapped(runtime_api, migration, root, controller, contexts, private, group):
    base = next(context for (kind, _), context in contexts.items() if kind == "private")
    private_scope = replace(base.scope, native_scope_id=UNMAPPED_PRIVATE_ID)
    actor = replace(base.actor, principal=replace(base.actor.principal,
                                                 native_account_id=UNMAPPED_PRIVATE_ID))
    private_context = TaskContext(actor,
        replace(base.role_binding, scope=private_scope),
        AudienceRef(private_scope, (base.actor.subject,)))
    result = {"private_unmapped": False, "group_unmapped": False}
    try:
        plan = _plan(runtime_api, migration, root, controller, private_context)
    except RuntimeError:
        result["private_unmapped"] = True
    else:
        expression = plan["expressions"]
        if expression["available"] or expression["rule_count"] or expression["sample_count"]:
            raise RuntimeError("unmapped_private_reused_another_profile")
        result["private_unmapped"] = True

    if UNMAPPED_GROUP_ID not in {profile["source_id"] for profile in group}:
        group_scope = replace(base.scope, kind=ScopeKind.GROUP,
                              native_scope_id=UNMAPPED_GROUP_ID)
        group_context = TaskContext(base.actor,
            replace(base.role_binding, scope=group_scope),
            AudienceRef(group_scope, (base.actor.subject,)))
        try:
            plan = _plan(runtime_api, migration, root, controller, group_context,
                         source_group_id=UNMAPPED_GROUP_ID)
        except RuntimeError:
            result["group_unmapped"] = True
        else:
            expression = plan["expressions"]
            if expression["available"] or expression["rule_count"] or expression["sample_count"]:
                raise RuntimeError("unmapped_group_reused_another_profile")
            result["group_unmapped"] = True
    return result


def _verify_group_runtime(controller, pairs, at):
    catalog = controller.session.application.expression_style_context
    checked = 0
    for profile, context in pairs:
        if profile["source_kind"] != "group":
            continue
        snapshot = catalog.capture(context, at, channel="group")
        if snapshot["state"] != "ready":
            raise RuntimeError("group_expression_capture_unavailable")
        _, _, run_id = identifiers(profile, context)
        allowed = {signal_id(run_id, rule) for rule in profile["rules"]}
        if not {item["signal_id"] for item in snapshot["references"]} <= allowed:
            raise RuntimeError("group_expression_context_crossed_scope")
        materials = catalog.contributions(snapshot, context, at)
        payloads = [json.loads(item.payload)["proposal"] for item in materials
                    if item.purpose == "expression_style_rule"]
        own = {rule["proposal"] for rule in profile["rules"] if rule["state"] == "adopted"}
        if not set(payloads) <= own:
            raise RuntimeError("group_expression_context_crossed_scope")
        if own and not payloads:
            raise RuntimeError("group_expression_context_did_not_apply")
        checked += 1
    return checked


def _external_calls(native):
    sends = sum(1 for platform in native.platforms.values()
                for action, _ in platform.client._api._wsr_api.calls
                if action in SEND_ACTIONS)
    calls = len(native.provider.client.state.calls)
    return calls, sends


def _summary(profiles, per_profile, matrix, source, external, **extra):
    private = [item for item in profiles if item["source_kind"] == "private"]
    group = [item for item in profiles if item["source_kind"] == "group"]
    return {
        "phase": extra.pop("phase"),
        "source": {
            "profiles": len(profiles), "private_profiles": len(private),
            "group_profiles": len(group),
            "rules": sum(item["rules"] for item in per_profile),
            "rule_states": dict(sorted(sum((Counter(item["rule_states"])
                for item in per_profile), Counter()).items())),
            "samples": sum(item["samples"] for item in per_profile),
            "sample_states": dict(sorted(sum((Counter(item["sample_states"])
                for item in per_profile), Counter()).items())),
            "review_samples": sum(item["review_samples"] for item in per_profile),
            "source_sha256": source["companions_sha256"],
            "configuration_sha256": source["v1_configuration_sha256"],
            "archive_inventory_fingerprint": source["archive_inventory_fingerprint"],
        },
        "stored": per_profile,
        "matrix": matrix,
        "model_calls": external[0], "platform_sends": external[1],
        **extra,
    }


async def run_import(args):
    config, profiles, private, group = _load_source(args)
    source_before = _source_state(args.v1_root, args.v1_config)
    if args.data_root.exists() and any(args.data_root.iterdir()):
        raise RuntimeError("acceptance_data_root_not_empty")
    args.data_root.mkdir(parents=True, exist_ok=True)

    runtime = _build_runtime(args, config, profiles, private, group)
    controller = runtime["controller"]
    try:
        initialized = await controller.initialize_profile()
        _require(initialized.is_success,
                 "initialize:" + str(getattr(initialized.failure, "code", "failed")))
        started = await controller.start()
        _require(started.is_success, "start:" + str(getattr(started.failure, "code", "failed")))
        api = _web_api(controller, args.data_root)
        contexts = _contexts(controller, runtime["targets"], runtime["group_ids"])
        pairs = _profile_pairs(profiles, contexts)
        table = controller.session.runtime.read_one(
            "SELECT COUNT(*) AS n FROM expression_style_runs", ())
        _require(table["n"] == 0, "acceptance_data_root_already_has_expressions")

        imported = []
        for profile, context in pairs:
            source_group_id = _source_group(profile)
            plan = _plan(api, runtime["migration"], args.v1_root, controller,
                         context, source_group_id)
            expression = plan["expressions"]
            expected = _expected_counts(profile)
            _require(expression["available"], "expression_plan_unavailable")
            _require(expression["rule_count"] == expected["rules"]
                     and expression["sample_count"] == expected["samples"],
                     "expression_plan_count_mismatch")
            _require(expression["adopted_count"] == expected["rule_states"].get("adopted", 0)
                     and expression["pending_count"] == expected["rule_states"].get("pending", 0)
                     and expression["rejected_count"] == (expected["rule_states"].get("rejected", 0)
                                                         + expected["rule_states"].get("retired", 0)),
                     "expression_plan_state_mismatch")
            _require(expression["skipped_count"] == 0, "expression_plan_skipped_rows")
            _require(expression["remaining"] == expected["rules"] + expected["samples"],
                     "expression_plan_remaining_mismatch")
            result = await _apply(api, runtime["migration"], args.v1_root,
                                  controller, context, plan["plan_token"], source_group_id)
            value = result["expressions"]
            _require(value["created"] == expected["rules"]
                     and value["samples_created"] == expected["samples"]
                     and value["preserved"] == 0 and value["remaining"] == 0,
                     "expression_import_result_mismatch")

            replay_plan = _plan(api, runtime["migration"], args.v1_root,
                                controller, context, source_group_id)
            _require(replay_plan["expressions"]["remaining"] == 0,
                     "expression_import_left_remaining_rows")
            replay = await _apply(api, runtime["migration"], args.v1_root,
                                  controller, context, replay_plan["plan_token"], source_group_id)
            value = replay["expressions"]
            _require(value["created"] == 0 and value["samples_created"] == 0
                     and value["preserved"] == expected["rules"] and value["remaining"] == 0,
                     "expression_duplicate_import_not_idempotent")
            imported.append({"created": expected["rules"], "samples": expected["samples"]})

        per_profile = [_verify_profile(controller.session.runtime, profile, context, NOW)
                       for profile, context in pairs]
        matrix = _verify_matrix(controller.session.runtime, pairs)
        unmapped = _verify_unmapped(api, runtime["migration"], args.v1_root,
                                    controller, contexts, private, group)
        group_runtime_scopes = _verify_group_runtime(controller, pairs, NOW)
        _require(group_runtime_scopes == len(group), "group_runtime_scope_count_mismatch")

        source_after = _source_state(args.v1_root, args.v1_config)
        _require(source_after == source_before, "v1_source_changed_during_import")
        calls, sends = _external_calls(runtime["native"])
        _require(not calls and not sends, "unexpected_external_call")

        summary = _summary(profiles, per_profile, matrix, source_after, (calls, sends),
            phase="import", duplicate_retries=len(pairs), imported=True,
            source_unchanged=True, unmapped=unmapped,
            group_runtime_scopes=group_runtime_scopes)
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        args.state_file.write_text(json.dumps({"source": source_after},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return summary
    finally:
        await controller.terminate()


async def run_verify(args):
    config, profiles, private, group = _load_source(args)
    _require(args.data_root.is_dir(), "acceptance_data_root_missing")
    state = json.loads(args.state_file.read_text(encoding="utf-8"))
    source_before = _source_state(args.v1_root, args.v1_config)
    _require(source_before == state["source"], "v1_source_changed_before_restart")

    runtime = _build_runtime(args, config, profiles, private, group)
    controller = runtime["controller"]
    try:
        loaded = await controller.load_existing()
        _require(loaded.is_success and loaded.unwrap().get("loaded"), "saved_profile_not_loaded")
        started = await controller.start()
        _require(started.is_success, "restart:" + str(getattr(started.failure, "code", "failed")))
        api = _web_api(controller, args.data_root)
        contexts = _contexts(controller, runtime["targets"], runtime["group_ids"])
        pairs = _profile_pairs(profiles, contexts)

        per_profile = [_verify_profile(controller.session.runtime, profile, context, NOW)
                       for profile, context in pairs]
        matrix = _verify_matrix(controller.session.runtime, pairs)

        retried = 0
        for profile, context in pairs:
            source_group_id = _source_group(profile)
            plan = _plan(api, runtime["migration"], args.v1_root, controller,
                         context, source_group_id)
            expected = _expected_counts(profile)
            _require(plan["expressions"]["available"]
                     and plan["expressions"]["remaining"] == 0,
                     "restarted_expression_preview_not_complete")
            _require(plan["expressions"]["rule_count"] == expected["rules"]
                     and plan["expressions"]["sample_count"] == expected["samples"],
                     "restarted_expression_preview_count_mismatch")
            result = await _apply(api, runtime["migration"], args.v1_root,
                                  controller, context, plan["plan_token"], source_group_id)
            value = result["expressions"]
            _require(value["created"] == 0 and value["samples_created"] == 0
                     and value["preserved"] == expected["rules"] and value["remaining"] == 0,
                     "restarted_duplicate_import_not_idempotent")
            retried += 1

        group_runtime_scopes = _verify_group_runtime(controller, pairs, NOW)
        _require(group_runtime_scopes == len(group), "restarted_group_runtime_scope_mismatch")
        source_after = _source_state(args.v1_root, args.v1_config)
        _require(source_after == source_before, "v1_source_changed_during_restart")
        calls, sends = _external_calls(runtime["native"])
        _require(not calls and not sends, "unexpected_external_call_after_restart")

        return _summary(profiles, per_profile, matrix, source_after, (calls, sends),
            phase="verify", restarted=True, persisted=True,
            duplicate_retries=retried, source_unchanged=True,
            group_runtime_scopes=group_runtime_scopes)
    finally:
        await controller.terminate()


def _prepare_astrbot_root(path: Path):
    """Create the SDK directories step by step on network shares.

    A two-level ``os.makedirs`` below an absent directory can return
    ``WinError 3`` on an SMB share.  Each parent below is created explicitly
    before its child so the acceptance host stays on the requested drive.
    """
    path.mkdir(parents=True, exist_ok=True)
    current = path
    for part in ("data", "temp", "tool_images"):
        current = current / part
        current.mkdir(exist_ok=True)
    for part in ("config", "logs", "plugin_data", "t2i_templates"):
        (path / "data" / part).mkdir(exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("import", "verify"), required=True)
    parser.add_argument("--v1-root", type=Path, required=True)
    parser.add_argument("--v1-config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--astrbot-root", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    _prepare_astrbot_root(args.astrbot_root)
    os.environ["ASTRBOT_ROOT"] = str(args.astrbot_root)
    os.environ["PYTHONUTF8"] = "1"

    global NOW
    NOW = datetime.now(timezone.utc).replace(microsecond=0)
    summary = asyncio.run(run_import(args) if args.phase == "import" else run_verify(args))
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
