"""Bounded index reads of immutable versions and metadata-only journal receipts."""

from companion_v2.execution.models import digest, encode


SCAN_LIMIT = 64
STREAMS = {
    "activity": ("role_activity_revisions r", "r.updated_at", "'activity'", "r.activity_id", "r.revision",
                 "json_extract(r.record_json, '$.scope')", "1"),
    "growth": ("role_growth_revisions r", "json_extract(r.record_json, '$.updated_at')", "'growth'", "r.growth_id",
               "r.revision", "json_extract(r.record_json, '$.scope')", "1"),
    "journal": ("role_journal_operations r JOIN role_journals j ON j.owner_key = r.owner_key "
                "AND j.kind = json_extract(r.result_json, '$.head.key.kind') "
                "AND j.local_date = json_extract(r.result_json, '$.head.key.local_date')",
                "json_extract(r.result_json, '$.head.updated_at')", "json_extract(r.result_json, '$.head.key.kind')",
                "r.operation_id", "json_extract(r.result_json, '$.head.revision')",
                "json_extract(j.context_json, '$.scope')", "json_extract(r.result_json, '$.action') IN ('save', 'delete', 'restore')"),
}


def streams(kinds):
    return tuple(name for name in STREAMS if name in kinds or name == "journal" and {"diary", "dream"}.intersection(kinds))


def ceilings(runtime, owner, scope, kinds):
    result = {}
    for name in streams(kinds):
        table, _, _, _, _, scope_sql, condition = STREAMS[name]
        row = runtime.read_one(f"SELECT COALESCE(MAX(r.rowid), 0) AS ceiling FROM {table} "
            f"WHERE r.owner_key = ? AND {scope_sql} = json(?) AND {condition}", (digest(owner), encode(scope)))
        result[name] = row["ceiling"]
    return result


def candidates(runtime, owner, scope, snapshot):
    query, included = snapshot["query"], snapshot["included_kinds"]
    end = min(query["time_end"], snapshot["captured_at"]) if query["time_end"] else snapshot["captured_at"]
    combined = []
    for name in streams(included):
        table, time_sql, kind_sql, id_sql, revision_sql, scope_sql, condition = STREAMS[name]
        sql = (f"SELECT {time_sql} AS occurred_at, {kind_sql} AS kind, {id_sql} AS identifier, {revision_sql} AS revision "
               f"FROM {table} WHERE r.owner_key = ? AND {scope_sql} = json(?) AND {condition} AND r.rowid <= ? "
               f"AND {time_sql} <= ?")
        args = [digest(owner), encode(scope), snapshot["ceilings"][name], end]
        if query["time_start"] is not None:
            sql += f" AND {time_sql} >= ?"
            args.append(query["time_start"])
        if name == "journal":
            kinds = [k for k in included if k in ("diary", "dream")]
            sql += f" AND {kind_sql} IN ({','.join('?' for _ in kinds)})"
            args.extend(kinds)
        if snapshot.get("after") is not None:
            sql += f" AND ({time_sql}, {kind_sql}, {revision_sql}, {id_sql}) < (?, ?, ?, ?)"
            args.extend(snapshot["after"])
        sql += " ORDER BY occurred_at DESC, kind DESC, revision DESC, identifier DESC LIMIT ?"
        combined.extend(runtime.read_all(sql, (*args, SCAN_LIMIT + 1)))
    return sorted(combined, key=position, reverse=True)[:SCAN_LIMIT + 1]


def position(row):
    return (row["occurred_at"], row["kind"], row["revision"], row["identifier"])
