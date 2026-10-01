"""Remove newer tables when constructing historical upgrade fixtures."""

from companion_v2.storage.schema import MEMORY_TABLES, V10_MIGRATION_STATEMENTS, V15_MIGRATION_STATEMENTS


def remove_v45(connection):
    """Undo the persona draft ledger so a v44 fixture can be rebuilt."""
    for name in ("persona_draft_versions_append_only_update",
                 "persona_draft_versions_append_only_delete"):
        connection.execute(f'DROP TRIGGER IF EXISTS "{name}"')
    connection.execute('DROP INDEX IF EXISTS "persona_draft_versions_order_idx"')
    connection.execute('DROP TABLE IF EXISTS "persona_draft_versions"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v44-to-v45'")


def remove_v44(connection):
    """Undo the reading-archive trigger cursors so a v43 fixture can be rebuilt."""
    remove_v45(connection)
    connection.execute('DROP TABLE IF EXISTS "reading_archive_triggers"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v43-to-v44'")


def remove_v43(connection):
    """Undo the reference-asset tables so a v42 fixture can be rebuilt."""
    remove_v44(connection)
    for index in ("reference_assets_kind_idx", "reference_assets_hash_idx",
                  "reference_asset_roles_role_idx", "wardrobe_items_state_idx"):
        connection.execute(f'DROP INDEX IF EXISTS "{index}"')
    # Children before parents: wardrobe_items and reference_asset_roles both carry
    # a foreign key into reference_assets.
    for table in ("reference_asset_roles", "wardrobe_items", "reference_assets"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v42-to-v43'")


def remove_v42(connection):
    remove_v43(connection)
    for index in ("reading_archive_entries_state_idx", "reading_archive_entries_origin_idx",
                  "reading_archive_reviews_entry_idx"):
        connection.execute(f'DROP INDEX IF EXISTS "{index}"')
    for table in ("reading_archive_reviews", "reading_archive_progress",
                  "reading_archive_consents", "reading_archive_entries"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v41-to-v42'")


def remove_v41(connection):
    remove_v42(connection)
    connection.execute('DROP INDEX IF EXISTS "group_member_safety_hits_time_idx"')
    connection.execute('DROP INDEX IF EXISTS "group_member_safety_hits_member_idx"')
    connection.execute('DROP TABLE IF EXISTS "group_member_safety_hits"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v40-to-v41'")


def remove_v40(connection):
    remove_v41(connection)
    connection.execute('DROP INDEX IF EXISTS "expression_style_signal_adopted_idx"')
    connection.execute('DROP INDEX IF EXISTS "expression_style_signal_queue_idx"')
    connection.execute('DROP TABLE IF EXISTS "expression_style_signals"')
    connection.execute('DROP TABLE IF EXISTS "expression_style_runs"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v39-to-v40'")


def remove_v39(connection):
    remove_v40(connection)
    connection.execute('DROP INDEX IF EXISTS "role_self_review_item_active_idx"')
    connection.execute('DROP INDEX IF EXISTS "role_self_review_item_queue_idx"')
    connection.execute('DROP TABLE IF EXISTS "role_self_review_items"')
    connection.execute('DROP TABLE IF EXISTS "role_self_review_runs"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v38-to-v39'")


def remove_v38(connection):
    remove_v39(connection)
    connection.execute('DROP TABLE IF EXISTS "proactive_news_polls"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v37-to-v38'")


def remove_v37(connection):
    remove_v38(connection)
    connection.execute('DROP TABLE IF EXISTS "proactive_balance_polls"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v36-to-v37'")


def remove_v36(connection):
    remove_v37(connection)
    if connection.execute(
        "SELECT 1 FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v35-to-v36'"
    ).fetchone() is None:
        return
    connection.execute("CREATE TEMP TABLE fixture_failures AS SELECT * FROM model_call_failures")
    connection.execute('DROP TABLE "model_call_failures"')
    connection.execute(V15_MIGRATION_STATEMENTS[0])
    connection.execute("INSERT INTO model_call_failures SELECT * FROM fixture_failures")
    connection.execute("DROP TABLE fixture_failures")
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v35-to-v36'")


def remove_v35(connection):
    remove_v36(connection)
    connection.execute('DROP TABLE IF EXISTS "conversation_voice_diagnostics"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v34-to-v35'")


def remove_v34(connection):
    remove_v35(connection)
    connection.execute('DROP INDEX IF EXISTS "proactive_official_alert_chain_idx"')
    connection.execute('DROP TABLE IF EXISTS "proactive_official_alerts"')
    connection.execute('DROP TABLE IF EXISTS "proactive_official_alert_polls"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v33-to-v34'")


def remove_v33(connection):
    remove_v34(connection)
    connection.execute('DROP TABLE IF EXISTS "proactive_weather_samples"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v32-to-v33'")


def remove_v32(connection):
    remove_v33(connection)
    connection.execute('DROP TABLE IF EXISTS "conversation_voice_cooldowns"')
    connection.execute('DROP TABLE IF EXISTS "conversation_voice_parts"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v31-to-v32'")


def remove_v31(connection):
    remove_v32(connection)
    connection.execute('DROP INDEX IF EXISTS "role_growth_progress_queue_idx"')
    connection.execute('DROP TABLE IF EXISTS "role_growth_progress_reviews"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v30-to-v31'")


def remove_v30(connection):
    remove_v31(connection)
    connection.execute('DROP TABLE IF EXISTS "conversation_video_payloads"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v29-to-v30'")


def remove_v29(connection):
    remove_v30(connection)
    connection.execute('DROP TABLE IF EXISTS "conversation_audio_payloads"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v28-to-v29'")


def remove_v28(connection):
    remove_v29(connection)
    connection.execute('DROP TABLE IF EXISTS "memory_reflection_jobs"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v27-to-v28'")


def remove_v27(connection):
    remove_v28(connection)
    for name in ("reflection_inputs_insert", "reflection_inputs_update"):
        connection.execute(f'DROP TRIGGER IF EXISTS "{name}"')
    connection.execute('DROP INDEX IF EXISTS "memory_pending_selection_idx"')
    connection.execute('DROP TABLE IF EXISTS "memory_reflection_inputs"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v26-to-v27'")


def remove_v26(connection):
    remove_v27(connection)
    for kind in ("human", "reply", "experience", "fact"):
        for action in ("insert", "update", "delete"):
            connection.execute(f'DROP TRIGGER IF EXISTS "recall_{kind}_{action}"')
    connection.execute('DROP INDEX IF EXISTS "memory_guard_evidence_idx"')
    connection.execute('DROP TABLE IF EXISTS "memory_recall_changes"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v25-to-v26'")


def remove_v25(connection):
    remove_v26(connection)
    connection.execute('DROP TABLE IF EXISTS "conversation_image_payloads"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v24-to-v25'")


def remove_v24(connection):
    remove_v25(connection)
    from companion_v2.storage.state_schema import STATE_TABLES
    for table in sorted(STATE_TABLES, key=lambda name: name.endswith("_records")):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v23-to-v24'")


def remove_v23(connection):
    remove_v24(connection)
    connection.execute('DROP TABLE IF EXISTS "role_activity_revisions"')
    connection.execute('DROP INDEX IF EXISTS "role_growth_history_time_idx"')
    connection.execute('DROP INDEX IF EXISTS "role_journal_history_time_idx"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v22-to-v23'")


def remove_v22(connection):
    remove_v23(connection)
    for table in ("role_growth_operations", "role_growth_revisions", "role_growth_items"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v21-to-v22'")


def remove_v21(connection):
    remove_v22(connection)
    for table in sorted(MEMORY_TABLES):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v20-to-v21'")


def remove_v20(connection):
    remove_v21(connection)
    connection.execute('DROP TABLE IF EXISTS "proactive_contacts"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v19-to-v20'")


def remove_v19(connection):
    remove_v20(connection)
    for table in ("agenda_dispatches", "background_delivery_receipts", "background_deliveries"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v18-to-v19'")


def remove_v18(connection):
    remove_v19(connection)
    for table in ("relationship_memory_operations", "relationship_memory_revisions", "relationship_memories"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v17-to-v18'")


def remove_v17(connection):
    remove_v18(connection)
    for table in ("role_journal_operations", "role_journal_derivatives", "role_journals"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v16-to-v17'")


def remove_v16(connection):
    remove_v17(connection)
    for table in ("role_life_operations", "role_artifacts", "role_activities"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v15-to-v16'")


def remove_v15(connection):
    remove_v16(connection)
    connection.execute('DROP TABLE IF EXISTS "model_call_failures"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v14-to-v15'")


def remove_v14(connection):
    remove_v15(connection)
    connection.execute('DROP TABLE IF EXISTS "conversation_flows"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v13-to-v14'")


def remove_v13(connection):
    remove_v14(connection)
    connection.execute('DROP TABLE IF EXISTS "extension_tool_invocations"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v12-to-v13'")


def remove_v12(connection):
    remove_v13(connection)
    for table in ("conversation_tool_calls", "conversation_tool_sources", "model_rounds"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    has_model_calls = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'model_calls'"
    ).fetchone() is not None
    has_model_accounts = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'model_call_accounts'"
    ).fetchone() is not None
    if not has_model_calls and not has_model_accounts:
        connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v11-to-v12'")
        return
    if has_model_calls != has_model_accounts:
        raise RuntimeError("historical fixture has only one model call table")
    connection.execute("CREATE TEMP TABLE fixture_calls AS SELECT * FROM model_calls")
    connection.execute("CREATE TEMP TABLE fixture_accounts AS SELECT * FROM model_call_accounts")
    connection.execute("DROP TABLE model_call_accounts")
    connection.execute("DROP TABLE model_calls")
    for statement in V10_MIGRATION_STATEMENTS[2:]:
        connection.execute(statement)
    connection.execute("INSERT INTO model_calls SELECT * FROM fixture_calls")
    connection.execute("INSERT INTO model_call_accounts SELECT * FROM fixture_accounts")
    connection.execute("DROP TABLE fixture_accounts")
    connection.execute("DROP TABLE fixture_calls")
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v11-to-v12'")


def remove_v11(connection):
    remove_v12(connection)
    for table in ("conversation_sent_history", "conversation_delivery_receipts", "conversation_parts",
                  "conversation_inputs", "conversation_batches"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v10-to-v11'")


def remove_v10(connection):
    remove_v11(connection)
    for table in ("model_call_accounts", "model_calls", "model_requests", "model_budget_accounts"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v9-to-v10'")


def remove_v9(connection):
    remove_v10(connection)
    for table in ("execution_events", "execution_attempts", "execution_tasks", "task_supervisor"):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v8-to-v9'")
