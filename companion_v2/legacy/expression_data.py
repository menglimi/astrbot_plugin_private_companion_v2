"""Read legacy learning results, preserving source ownership and review decisions."""

from __future__ import annotations

from companion_v2.execution.models import digest
from companion_v2.expression.sharing import normalize_pack
from companion_v2.expression.learning import MAX_PROPOSAL_CHARS


RULE_STATES = {"learned_rules": "adopted", "pending_rules": "pending",
               "rejected_rules": "rejected", "retired_rules": "retired"}


def _sample_state(raw, state, ownership, kind):
    binding = raw.get("scope_binding")
    if isinstance(binding, dict):
        if (not isinstance(ownership, dict) or binding.get("owner_type") != kind
                or any(binding.get(name) != ownership.get(name) for name in
                       ("owner_type", "owner_id", "source_namespace", "application_namespace"))):
            return None
        approved = binding.get("approval_state")
        if approved in ("rejected", "revoked"):
            state = "rejected"
        elif state == "approved" and (approved != "approved" or binding.get("approved_by") not in
                ("administrator", "legacy_migration", "automatic_policy")):
            state = "pending"
    if raw.get("review_status") in ("rejected", "revoked", "disabled") or raw.get("enabled") is False:
        state = "rejected"
    return state


def expression_profiles(data, source_persona_id=""):
    profiles = []
    for collection, kind in (("users", "private"), ("groups", "group")):
        values = data.get(collection, {})
        if not isinstance(values, dict):
            continue
        for source_id, subject in values.items():
            if not isinstance(subject, dict) or not isinstance(subject.get("expression_profile"), dict):
                continue
            profile = subject["expression_profile"]
            rules, rejected, seen = [], [], set()
            # A later denial wins when old lists contain the same original rule.
            for field, state in reversed(tuple(RULE_STATES.items())):
                for index, raw in enumerate(profile.get(field, []) if isinstance(profile.get(field), list) else []):
                    if not isinstance(raw, dict):
                        rejected.append({"field": field, "index": index, "reason": "invalid_rule"})
                        continue
                    key = str(raw.get("id") or digest([raw.get("kind"), raw.get("situation"), raw.get("pattern")]))
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        pack = normalize_pack({"schema": "private-companion-expression-pack", "version": 1,
                            "rule_groups": [{"rules": [{**raw, **{name: ["any"] for name in
                                ("relationship_stages", "emotion_gates") if "any" in (raw.get(name) or [])}}]}]})
                        signal = pack["signals"][0]
                    except (ValueError, TypeError):
                        rejected.append({"field": field, "index": index, "reason": "invalid_rule"})
                        continue
                    binding = raw.get("scope_binding")
                    ownership = profile.get("scope_ownership")
                    checked_state = state
                    if isinstance(binding, dict):
                        expected = {"adopted": "approved", "pending": "pending",
                                    "rejected": "rejected", "retired": "revoked"}[state]
                        same_owner = isinstance(ownership, dict) and all(
                            binding.get(name) == ownership.get(name) for name in
                            ("owner_type", "owner_id", "source_namespace", "application_namespace"))
                        if not same_owner or binding.get("owner_type") != kind:
                            rejected.append({"field": field, "index": index, "reason": "ownership_mismatch"})
                            continue
                        if binding.get("approval_state") in ("rejected", "revoked"):
                            checked_state = "rejected" if binding["approval_state"] == "rejected" else "retired"
                        elif binding.get("approval_state") != expected or (state == "adopted" and
                                binding.get("approved_by") not in ("administrator", "legacy_migration")):
                            checked_state = "pending"
                    if raw.get("review_status") in ("rejected", "revoked", "disabled") or raw.get("enabled") is False:
                        checked_state = "retired" if state == "adopted" else "rejected"
                    if raw.get("persona_conflict") and checked_state == "adopted":
                        checked_state = "retired"
                    avoid = raw.get("avoid")
                    if isinstance(avoid, str) and avoid.strip():
                        signal["proposal"] += "；避免：" + avoid.strip()
                    if len(signal["proposal"]) > MAX_PROPOSAL_CHARS:
                        rejected.append({"field": field, "index": index, "reason": "invalid_proposal"})
                        continue
                    examples = raw.get("evidence_examples", [])
                    examples = [item for item in examples if isinstance(item, str) and item.strip()][:16]
                    rules.append({**signal, "source_key": key, "state": checked_state,
                        "examples": examples, "legacy": {name: raw[name] for name in
                            ("use_count", "last_used_ts", "positive_feedback", "negative_feedback",
                             "approved_at", "rejected_at", "created_ts", "family_id") if name in raw}})
            samples, sample_keys = [], set()
            # Denied samples take precedence if an old list contains duplicates.
            for field, state in (("rejected_samples", "rejected"), ("pending_samples", "pending"),
                                 ("samples", "approved")):
                for index, raw in enumerate(profile.get(field, []) if isinstance(profile.get(field), list) else []):
                    if not isinstance(raw, dict):
                        continue
                    key = str(raw.get("id") or digest([raw.get("text"), raw.get("phrase"), raw.get("ts")]))
                    if key in sample_keys:
                        continue
                    sample_keys.add(key)
                    checked = _sample_state(raw, state, profile.get("scope_ownership"), kind)
                    if checked is None:
                        rejected.append({"field": field, "index": index, "reason": "ownership_mismatch"})
                        continue
                    samples.append({"source_key": key, "state": checked,
                                    "value": raw})
            if rules or samples or rejected:
                profiles.append({"source_kind": kind, "source_id": str(source_id),
                    "source_persona_id": source_persona_id, "ownership": profile.get("scope_ownership"),
                    "identity": {name: subject.get(name) for name in ("identity_subject_id",
                        "identity_platform_kind", "identity_adapter_instance_id", "identity_bot_id")},
                    "rules": sorted(rules, key=lambda item: item["source_key"]), "samples": samples,
                    "rejected": rejected})
    return tuple(profiles)


def selected_profile(profiles, context, source_group_id=""):
    kind = context.scope.kind.value
    source_id = source_group_id if kind == "group" else context.actor.principal.native_account_id
    if kind == "group" and source_group_id != context.scope.native_scope_id:
        return None
    for profile in profiles:
        if profile["source_kind"] != kind or profile["source_id"] != source_id:
            continue
        if kind == "private":
            identity = profile["identity"]
            if (identity.get("identity_subject_id") != source_id
                    or identity.get("identity_platform_kind") != "onebot"
                    or identity.get("identity_adapter_instance_id") != context.scope.platform
                    or identity.get("identity_bot_id") != context.scope.account_id):
                continue
        return profile
    return None
