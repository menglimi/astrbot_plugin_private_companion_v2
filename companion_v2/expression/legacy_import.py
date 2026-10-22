"""Import reviewed legacy expressions into the live expression domain.

Original samples remain evidence, never fabricated conversation events. Stable
source identities make retries preserve subsequent reviews and retirements.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.foundation.refs import RoleOwnerRef

SOURCE = "legacy_expression"


def owner_keys(context):
    owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                         context.role_binding.role.subject_id)
    return digest(owner), digest(context.scope)


def identifiers(profile, context):
    owner, scope = owner_keys(context)
    lineage = [profile["source_persona_id"], profile["source_kind"], profile["source_id"], profile["ownership"]]
    # Ownership revisions change as samples accumulate; they are not identity.
    if isinstance(lineage[-1], dict):
        lineage[-1] = {k: v for k, v in lineage[-1].items() if k != "revision"}
    return owner, scope, "legacy-expression:" + digest([owner, scope, lineage])


def preview(runtime, profile, context):
    if profile is None:
        return {"available": False, "rule_count": 0, "sample_count": 0, "remaining": 0}
    owner, scope, run_id = identifiers(profile, context)
    with runtime.read_snapshot():
        rows = runtime.read_all("""SELECT signal_id, state, decision_key FROM expression_style_signals
            WHERE owner_key = ? AND scope_key = ? AND run_id = ? ORDER BY signal_id""", (owner, scope, run_id))
        run = runtime.read_one("SELECT material_hash, sample_json FROM expression_style_runs WHERE run_id = ?", (run_id,))
    known = {row["signal_id"] for row in rows}
    ready = [rule for rule in profile["rules"] if signal_id(run_id, rule) not in known]
    window = json.loads(run["sample_json"]) if run else {}
    existing_samples = {item["source_key"] for item in window.get("legacy", {}).get("samples", [])}
    new_samples = [item for item in profile["samples"] if item["source_key"] not in existing_samples]
    return {"available": True, "rule_count": len(profile["rules"]),
        "adopted_count": sum(r["state"] == "adopted" for r in profile["rules"]),
        "pending_count": sum(r["state"] == "pending" for r in profile["rules"]),
        "rejected_count": sum(r["state"] in ("rejected", "retired") for r in profile["rules"]),
        "sample_count": len(profile["samples"]), "skipped_count": len(profile["rejected"]),
        "remaining": len(ready) + len(new_samples),
        "token": digest([profile, [dict(row) for row in rows], dict(run) if run else None])}


def signal_id(run_id, rule):
    return "legacy-expression-rule:" + digest([run_id, rule["source_key"]])


def evidence(window, handles):
    values = window.get("legacy", {}).get("evidence", {})
    if not isinstance(values, dict) or any(handle not in values for handle in handles):
        raise TaskError("expression_sample_changed", "legacy expression evidence is unavailable")
    return [values[handle] for handle in handles]


def import_profile(runtime, profile, context, at, *, expected_token):
    if profile is None:
        raise TaskError("legacy_plan_stale", "legacy expression source is unavailable")
    owner, scope, run_id = identifiers(profile, context)
    created = 0
    with runtime.transaction() as connection:
        if preview(runtime, profile, context).get("token") != expected_token:
            raise TaskError("legacy_plan_stale", "legacy expression source or target changed")
        current = connection.execute("SELECT * FROM expression_style_runs WHERE run_id = ?", (run_id,)).fetchone()
        if current is None:
            window = {"opened_at": stamp(at), "closed_at": stamp(at), "handles": [], "characters": 0,
                "source_kind": SOURCE, "legacy": {"source_kind": profile["source_kind"],
                    "source_id": profile["source_id"], "samples": [], "evidence": {}, "rules": {}}}
            connection.execute("""INSERT INTO expression_style_runs
                (run_id, owner_key, scope_key, sample_json, material_hash, summary, state, created_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, 'decided', ?, ?)""",
                (run_id, owner, scope, encode(window), digest(profile), "旧版表达学习成果", stamp(at), stamp(at)))
        else:
            window = json.loads(current["sample_json"])
        known_samples = {item["source_key"] for item in window["legacy"]["samples"]}
        new_samples = [item for item in profile["samples"] if item["source_key"] not in known_samples]
        window["legacy"]["samples"].extend(new_samples)
        ordinal = connection.execute("SELECT COALESCE(MAX(ordinal), -1) FROM expression_style_signals WHERE run_id = ?",
                                     (run_id,)).fetchone()[0] + 1
        for rule in profile["rules"]:
            identifier = signal_id(run_id, rule)
            if connection.execute("SELECT 1 FROM expression_style_signals WHERE signal_id = ?", (identifier,)).fetchone():
                continue
            handles = []
            for index, text in enumerate(rule["examples"]):
                handle = identifier + ":evidence:" + str(index)
                window["legacy"]["evidence"][handle] = text
                handles.append(handle)
            window["legacy"]["rules"][identifier] = rule["legacy"]
            connection.execute("""INSERT INTO expression_style_signals
                (signal_id, run_id, owner_key, scope_key, dimension, observation, proposal, applicability_json,
                 confidence, evidence_json, state, created_at, decided_at, decided_by, decision_key, ordinal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (identifier, run_id, owner, scope, rule["dimension"], rule["observation"], rule["proposal"],
                 encode(rule["applicability"]), rule["confidence"], encode(handles), rule["state"], stamp(at),
                 stamp(at) if rule["state"] != "pending" else None, "legacy_migration",
                 "legacy:" + digest(rule), ordinal))
            ordinal += 1
            created += 1
        window["handles"] = list(window["legacy"]["evidence"])
        window["characters"] = sum(len(text) for text in window["legacy"]["evidence"].values())
        connection.execute("UPDATE expression_style_runs SET sample_json = ? WHERE run_id = ?", (encode(window), run_id))
        _seed_samples(runtime, context, run_id, window, at)
    return {"created": created, "preserved": len(profile["rules"]) - created,
            "sample_count": len(window["legacy"]["samples"]), "samples_created": len(new_samples),
            "remaining": preview(runtime, profile, context)["remaining"]}


def samples(runtime, context, *, opened_at, closed_at):
    """Only original text samples enter learning; aggregate features stay in the migration record."""
    from .style_evidence import StyleSample

    owner, scope = owner_keys(context)
    rows = runtime.read_all("""SELECT run_id, sample_json FROM expression_style_runs
        WHERE owner_key = ? AND scope_key = ? AND json_extract(sample_json, '$.source_kind') = ?""",
        (owner, scope, SOURCE))
    result = []
    for row in rows:
        window = json.loads(row["sample_json"])
        for item in window.get("legacy", {}).get("samples", []):
            raw = item["value"]
            text = raw.get("text") or raw.get("phrase")
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                received_at = datetime.fromtimestamp(float(raw["ts"]), timezone.utc)
            except (KeyError, ValueError, TypeError, OverflowError, OSError):
                continue
            if not opened_at <= received_at <= closed_at:
                continue
            handle = "input:legacy:" + digest([row["run_id"], item["source_key"]])
            result.append(StyleSample(handle, text, window["legacy"]["source_id"]
                if window["legacy"]["source_kind"] == "private" else None,
                received_at, 0, digest(text)))
    return result


def _seed_samples(runtime, context, run_id, window, at):
    from .sample_review import ExpressionSampleReviewStore

    store = ExpressionSampleReviewStore(runtime)
    states = {"input:legacy:" + digest([run_id, item["source_key"]]): item["state"]
              for item in window["legacy"]["samples"]}
    for sample in samples(runtime, context, opened_at=datetime(1970, 1, 1, tzinfo=timezone.utc), closed_at=at):
        if sample.handle not in states or store.read(context, sample.handle) is not None:
            continue
        value = store.observe(context, sample, at)
        store.write(context, {**value, "state": states[sample.handle], "decided_at": stamp(at),
                              "decided_by": "legacy_migration"})
