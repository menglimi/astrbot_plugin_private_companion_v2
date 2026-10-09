"""Apply only an explicitly selected V1 reply-segmentation preset to V2."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.reply_settings import (
    GROUP, OWNER, SPACING_DEFAULTS, ReplyConfigurationOwner, configuration_fields, target_for,
)
from companion_v2.conversation.segmentation import SegmentationPolicy
from companion_v2.conversation.text_processing import TEXT_DEFAULTS
from companion_v2.execution.models import TaskContext, digest, encode, require
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.legacy.configuration_migration import (
    configuration_rules, convert_configuration, convert_plugin_configuration, plugin_configuration_rules,
)
from companion_v2.storage.runtime import StorageRuntime
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository


TEXT_FIELDS = frozenset(("content_cleanup_enabled", "content_cleanup_mode", "content_cleanup_scope",
    "content_cleanup_rule", "content_cleanup_words", "content_replacement_enabled", "content_replacements"))
PRESET_FIELDS = frozenset(asdict(SegmentationPolicy())) | TEXT_FIELDS | frozenset(SPACING_DEFAULTS) | {"part_gap_ms"}


def preset(config, window_kind="private", *, cleanup_scope="trailing"):
    """Use the audited converter, selecting no unrelated V1 configuration."""
    allowed_targets = {GROUP + "." + key for key in PRESET_FIELDS}
    sources = {rule["source"] for rule in configuration_rules() if rule["target"] in allowed_targets}
    sources.update(rule["source"] for rule in plugin_configuration_rules()
                   if rule["target"].startswith("segmentation."))
    sources.update("legacy_compat_config." + key for key in (
        "enable_segmented_proactive_chat_profiles", "segmented_proactive_chat_scope",
        "segmented_proactive_interval_method", "segmented_proactive_log_base",
        "segmented_proactive_private_interval_method", "segmented_proactive_group_interval_method",
        "segmented_proactive_private_log_base", "segmented_proactive_group_log_base"))
    nested = config.get("legacy_compat_config", {})
    selected = {}
    for source in sources:
        key = source.partition(".")[2]
        if key in nested:
            selected[key] = nested[key]
        elif source in config:
            selected[key] = config[source]
        elif key in config:
            selected[key] = config[key]
    words = selected.get("segmented_proactive_split_words")
    if isinstance(words, list) and all(type(word) is str for word in words):
        selected["segmented_proactive_split_words"] = list(dict.fromkeys(words))
    source = {"legacy_compat_config": selected}
    registry = FieldRegistry(version="reply-segmentation-preset.v1",
        fields=configuration_fields(SegmentationPolicy(), True, 1.5))
    converted = convert_configuration(source, registry=registry, window_kind=window_kind)
    plugin = convert_plugin_configuration(source, window_kind=window_kind)
    problems = [item.document() for plan in (converted, plugin) for item in plan.differences
                if item.kind in ("conflict", "invalid_value")]
    if problems:
        raise ValueError("V1 segmentation values cannot be migrated: " + json.dumps(problems, ensure_ascii=False))
    values = {**asdict(SegmentationPolicy()), **{key: TEXT_DEFAULTS[key] for key in TEXT_FIELDS},
              **SPACING_DEFAULTS, "part_gap_ms": 1500}
    values.update({key.removeprefix("segmentation."): value for key, value in plugin.changes.items()
                   if key.startswith("segmentation.")})
    values.update({key.removeprefix(GROUP + "."): value for key, value in converted.changes.items()
                   if key in allowed_targets})
    # V1 selected its cleanup algorithm with the split mode; a dormant regex
    # must not override the configured cleanup words.
    values["content_cleanup_mode"] = values["rule_mode"]
    # The user's current preference supersedes the saved V1 cleanup scope.
    if cleanup_scope not in ("all", "trailing"):
        raise ValueError("cleanup scope must be all or trailing")
    values["content_cleanup_scope"] = cleanup_scope
    SegmentationPolicy(**{key: values[key] for key in asdict(SegmentationPolicy())})
    return values


def write_json(path, document):
    temporary = path.with_name(path.name + ".segmentation-tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-config", type=Path, required=True)
    parser.add_argument("--v2-config", type=Path)
    parser.add_argument("--profile-config", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--batch-id")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--cleanup-scope", choices=("all", "trailing"), default="trailing")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    values = preset(json.loads(args.v1_config.read_text(encoding="utf-8-sig")), cleanup_scope=args.cleanup_scope)
    report = {"settings": values, "applied": False}
    if args.apply:
        if not args.v2_config or not args.backup_dir or not args.runtime_root or not args.batch_id:
            parser.error("--apply requires --v2-config, --backup-dir, --runtime-root and --batch-id")
        args.backup_dir.mkdir(parents=True, exist_ok=False)
        plugin_config = json.loads(args.v2_config.read_text(encoding="utf-8-sig"))
        shutil.copy2(args.v2_config, args.backup_dir / "v2-plugin-config.json")
        if args.profile_config:
            shutil.copy2(args.profile_config, args.backup_dir / "v2-profile-config.json")
        # The selected V2 batch determines the exact role and conversation. Use
        # the regular owner and operation ledger for authorized local maintenance.
        # No Dashboard identity is fabricated by this command.
        import sqlite3
        with sqlite3.connect(f"file:{(args.runtime_root / StorageRuntime.DATABASE_FILENAME).resolve().as_posix()}?mode=ro", uri=True) as db:
            row = db.execute("SELECT context_json FROM conversation_batches WHERE batch_id=?", (args.batch_id,)).fetchone()
        if row is None:
            raise ValueError("the selected V2 reply batch is unavailable")
        context = TaskContext.restore(json.loads(row[0]))
        with StorageRuntime.open(data_root=args.runtime_root, installation_id=context.scope.installation_id) as runtime:
            at = datetime.now(timezone.utc)
            registry = FieldRegistry(version="reply-segmentation-migration.v1",
                fields=configuration_fields(SegmentationPolicy(), True, 1.5))
            target = target_for(context)
            owner = ReplyConfigurationOwner(runtime)
            fields = registry.group(GROUP)
            operations = OperationRepository(runtime)
            with runtime.transaction() as db:
                snapshot = owner.read(target, fields)
                report["before"] = {key: snapshot.fields[GROUP + "." + key].value for key in values}
                changes = {GROUP + "." + key: registry.fields[GROUP + "." + key].validate(value)
                           for key, value in values.items()}
                owner.preview_set(target, fields, changes=changes)
                op_id = "v1-segmentation:" + digest([target.key, snapshot.revision, values])
                operation = OperationRef(op_id, OWNER, target.authorization_scope, VersionRef(op_id, 1), op_id)
                reserved = require(operations.reserve(operation, parameter_hash=digest([
                    "authorized_local_segmentation_migration", target.key, values]), observed_at=at))
                if not reserved.replayed:
                    saved = owner.write(target, fields, changes=changes, reset=(),
                        expected_revision=snapshot.revision, observed_at=at)
                    result = {"operation_id": op_id, "target_key": target.key,
                              "revision": saved.revision, "changed_fields": saved.changed_fields}
                    db.execute("""INSERT INTO configuration_changes
                        (operation_id, target_key, group_id, changed, result_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (op_id, target.key, GROUP, int(bool(saved.changed_fields)), encode(result), at.isoformat()))
                    require(operations.transition(op_id, expected_state=OperationState.ACCEPTED,
                        next_state=OperationState.COMPLETED, observed_at=at))
            report["operation_id"] = op_id
            report["target_key"] = target.key
        segmentation = {key: values[key] for key in asdict(SegmentationPolicy())}
        plugin_config["segmentation"] = {key: value for key, value in segmentation.items() if key != "rules_enabled"}
        write_json(args.v2_config, plugin_config)
        if args.profile_config:
            profile = json.loads(args.profile_config.read_text(encoding="utf-8-sig"))
            profile["segmentation"] = segmentation
            write_json(args.profile_config, profile)
        report["applied"] = True
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
