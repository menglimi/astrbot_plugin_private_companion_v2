"""One-time promotions for settings whose public scope became broader."""

import json

from .models import ConfigLayer, ConfigTarget, encode


def promote_values_to_installation(runtime, fields, *, source_layers=(ConfigLayer.ROLE,)):
    """Copy legacy values into installation scope without deleting source rows.

    Existing installation values win. When old scopes disagree, the value from
    the most recently updated source target is selected independently per field.
    """
    definitions = {field.field_id: field for field in fields}
    if not definitions:
        return ()
    source_values = {layer.value for layer in source_layers}
    installation = ConfigTarget(runtime.installation_id, ConfigLayer.INSTALLATION)
    field_ids = tuple(definitions)
    placeholders = ",".join("?" for _ in field_ids)
    with runtime.transaction() as connection:
        current = {row["field_id"] for row in connection.execute(
            f"SELECT field_id FROM configuration_values WHERE target_key=? AND field_id IN ({placeholders})",
            (installation.key, *field_ids))}
        rows = connection.execute(
            f"""SELECT t.target_json,t.updated_at,v.field_id,v.value_json
                FROM configuration_targets t JOIN configuration_values v ON v.target_key=t.target_key
                WHERE v.field_id IN ({placeholders}) ORDER BY t.updated_at DESC,t.target_key""",
            field_ids).fetchall()
        candidates = {}
        for row in rows:
            field_id = row["field_id"]
            if field_id in current or field_id in candidates:
                continue
            try:
                target = json.loads(row["target_json"])
                value = json.loads(row["value_json"])
                definitions[field_id].validate(value)
            except (KeyError, TypeError, ValueError):
                continue
            if (type(target) is not dict or target.get("installation_id") != runtime.installation_id
                    or target.get("layer") not in source_values):
                continue
            candidates[field_id] = row
        if not candidates:
            return ()
        target_row = connection.execute(
            "SELECT revision FROM configuration_targets WHERE target_key=?", (installation.key,)).fetchone()
        revision = (target_row["revision"] if target_row else 0) + 1
        updated_at = max(row["updated_at"] for row in candidates.values())
        connection.execute("INSERT OR IGNORE INTO configuration_targets VALUES (?,?,0,?)",
                           (installation.key, encode(installation.document()), updated_at))
        connection.executemany("INSERT INTO configuration_values VALUES (?,?,?,?)",
            ((installation.key, field_id, row["value_json"], revision)
             for field_id, row in candidates.items()))
        connection.execute("UPDATE configuration_targets SET revision=?,updated_at=? WHERE target_key=?",
                           (revision, updated_at, installation.key))
        return tuple(candidates)
