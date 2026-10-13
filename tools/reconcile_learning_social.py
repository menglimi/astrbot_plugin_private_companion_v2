"""Review or replay the official V1 social import against a configured V2 store.

Use AstrBot's Python with its backend/app on PYTHONPATH. The default is read-only;
apply requires the preview fingerprint and an SQLite backup destination.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import ScopeKind
from companion_v2.knowledge.catalog import KnowledgeCatalog
from companion_v2.legacy.data_migration import build_data_plan, map_legacy_worldbook
from companion_v2.storage.runtime import StorageRuntime
from companion_v2.storage.schema import SCHEMA_VERSION


class ReadOnlyStore:
    def __init__(self, connection, installation_id):
        self.connection, self.installation_id = connection, installation_id

    def read_one(self, sql, arguments):
        return self.connection.execute(sql, arguments).fetchone()

    def read_all(self, sql, arguments):
        return tuple(self.connection.execute(sql, arguments).fetchall())


def project(args, runtime, installation_id):
    from astrbot_host.legacy_api import LegacyMigrationWebAPI
    from astrbot_host.multi_settings import MultiHostSettings

    settings = MultiHostSettings.parse(json.loads(args.config.read_text(encoding="utf-8-sig")))
    mappings = [p for p in settings.personas if p.role_id == args.role_id]
    if not mappings:
        raise ValueError("role is not configured")
    bot_ids = {p.bot_id for p in mappings}
    data = build_data_plan(args.v1_root, source_persona_id=args.source_persona_id)
    if data.warnings:
        raise ValueError("V1 source warnings require review")
    source_groups = {group for p in data.member_profiles for group in p.group_ids}
    source_groups.update(group for item in data.worldbook_items for group in item.group_ids)
    targets = [t for t in settings.group_targets if t.bot_id in bot_ids and t.group_id in source_groups]
    private_targets = [t for t in settings.targets if t.bot_id in bot_ids]
    if not private_targets:
        raise ValueError("a configured private target is required for the role source")
    def context(target, kind):
        scope = SimpleNamespace(installation_id=installation_id, kind=kind,
            platform=target.platform_id, bot_id=target.bot_id, account_id=target.account_id,
            native_scope_id=target.group_id if kind is ScopeKind.GROUP else target.participant_id)
        return SimpleNamespace(scope=scope, role_binding=SimpleNamespace(role=SimpleNamespace(subject_id=args.role_id)))
    base = context(private_targets[0], ScopeKind.PRIVATE)
    contexts = [("", base), *((t.group_id, context(t, ScopeKind.GROUP)) for t in targets)]
    api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
    api.controller = SimpleNamespace(runtime=runtime, now=lambda: datetime.now(timezone.utc))
    states = [api._worldbook_state(data, current, group) for group, current in contexts]
    if any(s["base_entries_conflict"] or s["base_members_conflict"] or s["group_conflict"] for s in states):
        raise ValueError("an existing knowledge source belongs to another writer")
    bindings = [[g, c.scope.platform, c.scope.bot_id, c.scope.account_id] for g, c in contexts]
    token = digest([data.source_fingerprint, args.role_id, installation_id, bindings, states])
    mapped = map_legacy_worldbook(data, confirm_member_ids=True)
    report = {"plan_token": token, "source_fingerprint": data.source_fingerprint,
        "installation_id": installation_id, "role_id": args.role_id,
        "role_members": len(mapped[1]), "group_bindings": bindings[1:],
        "valid_profiles": len(data.member_profiles),
        "important_memories": sum(len(p.important_memories) for p in data.member_profiles),
        "excluded_profiles": len(data.member_profile_rejected), "states": states, "applied": False}
    return api, data, contexts, report


def run(args):
    database = args.v2_root / StorageRuntime.DATABASE_FILENAME
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        metadata = dict(connection.execute("SELECT key,value FROM runtime_metadata WHERE key IN ('schema_version','installation_id')"))
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("this repair must not upgrade the V2 storage schema")
        installation_id = metadata["installation_id"]
        _, _, _, report = project(args, ReadOnlyStore(connection, installation_id), installation_id)
        if not args.apply:
            return report
        if not args.backup or not args.expected_plan_token or args.expected_plan_token != report["plan_token"]:
            raise ValueError("apply requires the current plan token and a backup path")
        backup = args.backup.resolve()
        if backup.exists() or backup == database.resolve() or backup.is_relative_to(args.v1_root.resolve()):
            raise ValueError("backup must be a new path outside V1")
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as destination:
            connection.backup(destination)
    with StorageRuntime.open(data_root=args.v2_root, installation_id=installation_id) as runtime:
        with runtime.transaction(require_outermost=True):
            api, data, contexts, fresh = project(args, runtime, installation_id)
            if fresh["plan_token"] != args.expected_plan_token:
                raise ValueError("source or V2 records changed after preview")
            results = [api._import_legacy_worldbook(data, context, group, confirm_member_ids=True)
                       for group, context in contexts]
            if any(item.get("errors") for item in results):
                raise ValueError("official import failed; all social changes rolled back")
        report.update(applied=True, backup=str(backup), imports=results,
            source_count=len(KnowledgeCatalog(runtime).active(installation_id, limit=64)))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("v1-root", "v2-root", "config", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--role-id", required=True)
    parser.add_argument("--source-persona-id", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--expected-plan-token")
    args = parser.parse_args()
    report = run(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("applied", "role_members", "valid_profiles", "important_memories", "excluded_profiles")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
