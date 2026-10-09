"use strict";

(async () => {
  const output = document.getElementById("result");
  const prefix = "/api/plug/astrbot_plugin_private_companion_v2/";
  const allowed = new Set([
    "backup",
    "backup/create",
    "backup/inspect",
    "dashboard/plugin/reload",
    "host/status",
    "host/probe",
    "host/initialize",
    "host/start",
    "host-options",
    "host-options/weather",
    "accounts/read",
    "accounts/reapply",
    "migration/targets-read",
    "migration/role-plan",
    "legacy",
    "legacy/plan",
    "legacy/apply",
    "legacy/data-plan",
    "legacy/data-apply",
  ]);
  const safeValue = value => {
    if (Array.isArray(value)) return value.map(safeValue);
    if (!value || typeof value !== "object") return value;
    const result = {};
    for (const [key, item] of Object.entries(value)) {
      if (/token|prompt|credential|secret|api_host|content|text|body|before|after|sha256|fingerprint|actor_id|session_id|path|filename/i.test(key)) continue;
      result[key] = safeValue(item);
    }
    return result;
  };

  try {
    const spec = JSON.parse(decodeURIComponent(location.hash.slice(1)));
    const route = String(spec.route || "").replace(/^\/+/, "");
    if (route === "dashboard/plugin/reload") {
      const response = await fetch("/api/plugin/reload", {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name: "astrbot_plugin_private_companion_v2"}),
      });
      const payload = await response.json();
      output.textContent = JSON.stringify({
        http_status: response.status,
        status: payload?.status || "unknown",
        message: payload?.message || "",
      }, null, 2);
      return;
    }
    const routedMigration = /^host\/targets\/[A-Za-z0-9_-]+\/roles\/[0-9a-f]{64}\/legacy(?:\/(?:plan|apply|data-plan|data-apply))?$/.test(route)
      || /^host\/targets\/[A-Za-z0-9_-]+\/roles\/[0-9a-f]{64}\/legacy-group-data\/(?:plan|apply)$/.test(route);
    if (!allowed.has(route) && !routedMigration) throw new Error("route_not_allowed");
    let method = route === "accounts/reapply" ? "POST"
      : route === "accounts/read" ? "GET"
      : spec.method === "POST" ? "POST" : "GET";
    let query = typeof spec.query === "string" && spec.query ? `?${spec.query}` : "";
    let body = spec.body && typeof spec.body === "object" ? {...spec.body} : undefined;
    if (body?.plan_token === "@last") {
      body.plan_token = sessionStorage.getItem("legacy-migration-plan-token") || "";
      if (!body.plan_token) throw new Error("plan_token_not_found");
    }
    let apiRoute = route;
    if (route === "migration/targets-read") {
      apiRoute = "page/targets";
      method = "GET";
      query = "";
      body = undefined;
    } else if (route === "migration/role-plan") {
      const request = spec.body && typeof spec.body === "object" ? spec.body : {};
      const scope = request.scope === "group" ? "group" : "private";
      const targetIndex = request.target_index;
      const roleIndex = request.role_index;
      if (!Number.isInteger(targetIndex) || targetIndex < 0
          || !Number.isInteger(roleIndex) || roleIndex < 0) throw new Error("migration_target_index_invalid");
      let targets;
      try { targets = JSON.parse(sessionStorage.getItem("migration-target-inventory") || "null"); }
      catch { targets = null; }
      if (!Array.isArray(targets)) throw new Error("migration_inventory_not_read");
      const target = targets.filter(item => item.scope_kind === scope)[targetIndex];
      const role = target?.roles?.[roleIndex];
      const base = scope === "group" ? role?.legacy_group_data_api : role?.legacy_api;
      if (typeof base !== "string" || !base.startsWith("/astrbot_plugin_private_companion_v2/")) {
        throw new Error("migration_role_route_unavailable");
      }
      apiRoute = base.replace(/^\/astrbot_plugin_private_companion_v2\//, "")
        + (scope === "group" ? "/plan" : "/data-plan");
      method = "GET";
      body = undefined;
      const sourcePersonaId = typeof request.source_persona_id === "string" ? request.source_persona_id : "";
      query = sourcePersonaId ? `?source_persona_id=${encodeURIComponent(sourcePersonaId)}` : "";
    } else if (route === "accounts/read" || route === "accounts/reapply") {
      apiRoute = "accounts";
      if (route === "accounts/read") {
        body = undefined;
      } else {
        try {
          body = JSON.parse(sessionStorage.getItem("legacy-migration-account-bindings") || "null");
        } catch {
          body = null;
        }
        if (!body || typeof body !== "object") throw new Error("account_bindings_not_read");
      }
    }
    const response = await fetch(prefix + apiRoute + query, {
      method,
      credentials: "same-origin",
      headers: body ? {"Content-Type": "application/json"} : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const payload = await response.json();
    const data = payload?.data && typeof payload.data === "object" ? payload.data : {};
    if (typeof data.plan_token === "string") {
      sessionStorage.setItem("legacy-migration-plan-token", data.plan_token);
    }
    const visibleData = safeValue(data);
    let presentedData = visibleData;
    if (route === "migration/targets-read") {
      const targets = Array.isArray(data.targets) ? data.targets : [];
      sessionStorage.setItem("migration-target-inventory", JSON.stringify(targets));
      const privateTargets = targets.filter(item => item.scope_kind === "private");
      const groupTargets = targets.filter(item => item.scope_kind === "group");
      presentedData = {
        private_target_count: privateTargets.length,
        private_role_count: privateTargets.reduce((count, item) => count + (item.roles?.length || 0), 0),
        group_target_count: groupTargets.length,
        group_role_count: groupTargets.reduce((count, item) => count + (item.roles?.length || 0), 0),
        private_route_count: privateTargets.filter(item => item.roles?.some(role => role.legacy_api)).length,
        group_route_count: groupTargets.filter(item => item.roles?.some(role => role.legacy_group_data_api)).length,
      };
    } else if (route === "migration/role-plan") {
      const request = spec.body && typeof spec.body === "object" ? spec.body : {};
      const scope = request.scope === "group" ? "group" : "private";
      const targetIndex = request.target_index;
      const roleIndex = request.role_index;
      sessionStorage.setItem(`migration-role-plan-${scope}-${targetIndex}-${roleIndex}`, JSON.stringify(data));
      const memory = data.memory_database || {};
      const projection = memory.projection || {};
      const owners = memory.identity_inventory || {};
      const sourceGroups = new Set([
        ...(data.group_networks || []).map(item => item.source_group_id),
        ...(data.worldbook?.groups || []).map(item => item.source_group_id),
        ...(data.worldbook?.member_profile_groups || []).map(item => item.source_group_id),
      ].filter(Boolean));
      presentedData = {
        scope,
        reaction_assets: {total: data.reaction_assets?.total ?? 0,
          ready: data.reaction_assets?.ready ?? 0, already_present: data.reaction_assets?.already_present ?? 0},
        journals: {total: data.journals?.total ?? 0, ready: data.journals?.ready ?? 0,
          already_present: data.journals?.already_present ?? 0,
          derivative_retry_count: data.journals?.derivative_retry_count ?? 0},
        worldbook: {general_count: data.worldbook?.general_count ?? 0,
          group_count: data.worldbook?.group_count ?? 0,
          selected_group_count: sourceGroups.size},
        source_persona_count: (data.persona_sources || []).length,
        ready_persona_count: (data.persona_sources || []).filter(item => item.state === "ready").length,
        archive: {state: data.archive?.state, file_count: data.archive?.file_count,
          total_bytes: data.archive?.total_bytes},
        memory_database: {
          state: memory.state,
          record_count: memory.record_count,
          identity_owner_count: owners.owner_count ?? owners.owners?.length ?? 0,
          projection_state: projection.state,
          selected_owner_count: memory.selected_owner_ids?.length ?? 0,
          imported_count: projection.imported,
          excluded_count: projection.excluded_count,
          source_archive_retained: projection.source_archive_retained,
        },
        finding_count: (data.findings || []).length,
      };
    } else if (route === "accounts/read") {
      const bindings = {
        enabled: data.enabled === true,
        accounts: Array.isArray(data.accounts) ? data.accounts : [],
        sessions: Array.isArray(data.sessions) ? data.sessions : [],
        personas: Array.isArray(data.personas) ? data.personas : [],
        groups: Array.isArray(data.groups) ? data.groups : [],
      };
      sessionStorage.setItem("legacy-migration-account-bindings", JSON.stringify(bindings));
      presentedData = {
        enabled: bindings.enabled,
        account_count: bindings.accounts.length,
        session_count: bindings.sessions.length,
        persona_mapping_count: bindings.personas.length,
        group_target_count: bindings.groups.length,
        discovery_account_count: data.discovered?.accounts?.length ?? 0,
        discovery_persona_count: data.discovered?.personas?.length ?? 0,
        discovery_group_count: (data.discovered?.targets || []).filter(item => item.scope_kind === "group").length,
      };
    } else if (route === "accounts/reapply") {
      presentedData = {
        saved: data.saved,
        enabled: data.configuration?.enabled,
        account_count: data.configuration?.accounts?.length ?? 0,
        session_count: data.configuration?.sessions?.length ?? 0,
        persona_mapping_count: data.configuration?.personas?.length ?? 0,
        group_target_count: data.configuration?.groups?.length ?? 0,
        started: data.started,
        requires_reload: data.requires_reload,
        requires_initialize: data.requires_initialize,
        startup_error: data.startup_error,
        directory_refresh_pending: data.directory_refresh_pending,
      };
    } else if (route.endsWith("legacy/data-plan")) {
      const memory = data.memory_database || {};
      const projection = memory.projection || {};
      const inventory = memory.identity_inventory || {};
      presentedData = {
        reaction_assets: Object.fromEntries(["total", "ready", "already_present", "batch_count", "batch_bytes"]
          .filter(key => data.reaction_assets?.[key] !== undefined)
          .map(key => [key, data.reaction_assets[key]])),
        journals: Object.fromEntries(["total", "ready", "already_present", "batch_count"]
          .filter(key => data.journals?.[key] !== undefined)
          .map(key => [key, data.journals[key]])),
        worldbook: Object.fromEntries(["total", "general_count", "member_count", "member_profile_count", "group_count", "base_state", "group_state"]
          .filter(key => data.worldbook?.[key] !== undefined)
          .map(key => [key, data.worldbook[key]])),
        archive: Object.fromEntries(["state", "file_count", "total_bytes", "excluded_count"]
          .filter(key => data.archive?.[key] !== undefined)
          .map(key => [key, data.archive[key]])),
        memory_database: {
          state: memory.state,
          total_bytes: memory.total_bytes,
          table_count: memory.table_count,
          record_count: memory.record_count,
          identity_owner_count: inventory.owner_count ?? inventory.owners?.length ?? 0,
          selected_owner_count: memory.selected_owner_ids?.length ?? 0,
          selected_group_mapping_count: memory.selected_group_mappings?.length ?? 0,
          projection: {
            state: projection.state,
            scanned: projection.scanned,
            imported: projection.imported,
            excluded: projection.excluded,
            excluded_count: projection.excluded_count,
            read_model: projection.read_model,
            source_archive_retained: projection.source_archive_retained,
          },
        },
        findings: (data.findings || []).map(item => ({
          source_id: item.source_id, action: item.action, state: item.state,
        })),
      };
    } else if (route.endsWith("legacy/data-apply")) {
      const memory = data.memory_materials || {};
      presentedData = {
        reaction_created: data.reaction_created,
        reaction_duplicates: data.reaction_duplicates,
        reaction_remaining: data.reaction_remaining,
        reaction_error_count: data.reaction_errors?.length ?? 0,
        journal_created: data.journal_created,
        journal_remaining: data.journal_remaining,
        journal_derivatives_created: data.journal_derivatives_created,
        journal_derivatives_remaining: data.journal_derivatives_remaining,
        journal_error_count: data.journal_errors?.length ?? 0,
        worldbook: data.worldbook,
        archive: data.archive ? { state: data.archive.state, file_count: data.archive.file_count, total_bytes: data.archive.total_bytes } : null,
        memory_archive: data.memory_archive ? { state: data.memory_archive.state, asset_count: data.memory_archive.asset_count, total_bytes: data.memory_archive.total_bytes } : null,
        memory_materials: {
          state: memory.state,
          selected_owner_count: memory.selected_owner_count,
          imported: memory.imported,
          excluded: memory.excluded,
          reason: memory.reason,
          source_archive_retained: memory.source_archive_retained,
        },
        errors: data.errors,
        idempotent: data.idempotent,
      };
    } else if (route === "legacy/plan" || route.endsWith("/legacy/plan")) {
      const intents = data.intents || [];
      presentedData = {
        configuration_scope: data.configuration_scope,
        source_change_count: data.source_change_count,
        change_count: data.change_count,
        preserved_count: data.preserved_count,
        intent_count: intents.length,
        intents: intents.map(item => ({
          scope: item.scope,
          target_kind: item.target_kind,
          group_id: item.group_id,
          fields: Array.isArray(item.fields) ? item.fields : Object.keys(item.changes || {}),
        })),
        weather_validation: (data.differences || []).filter(item =>
          String(item.field || item.field_id || "").includes("weather.provider")
        ).map(item => ({field: item.field || item.field_id, kind: item.kind, explain: item.explain})),
        difference_count: data.differences?.length ?? 0,
        difference_kinds: (data.differences || []).reduce((counts, item) => {
          const kind = String(item.kind || "unknown");
          counts[kind] = (counts[kind] || 0) + 1;
          return counts;
        }, {}),
        review_fields: (data.differences || [])
          .filter(item => ["invalid_value", "partial_mapping", "conflict", "manual_mapping",
            "manual_required", "strategy_not_representable", "invalid_combination", "review_required"]
            .includes(item.kind))
          .map(item => ({field: String(item.field || item.field_id || ""), kind: item.kind}))
          .filter(item => /^[A-Za-z0-9_.:-]+$/.test(item.field))
          .slice(0, 120),
        scope_status: data.scope_status,
      };
    } else if (route === "legacy/apply") {
      presentedData = {
        configuration_scope: data.configuration_scope,
        written_count: data.written_count,
        written: data.written,
        restart_required: data.restart_required,
        errors: data.errors,
        skipped: data.skipped,
      };
    } else if (route === "host/status") {
      const targets = data.targets || [];
      presentedData = {
        mode: data.mode,
        enabled: data.enabled,
        group_delivery_mode: data.group_delivery_mode,
        state: data.state,
        accepting: data.accepting,
        failure_code: data.failure_code,
        settings_error: data.settings_error,
        target_count: targets.length,
        private_target_count: targets.filter(item => item.scope_kind === "private").length,
        group_target_count: targets.filter(item => item.scope_kind === "group").length,
        role_count: targets.reduce((count, item) => count + (item.roles?.length || 0), 0),
      };
    } else if (route === "host/probe") {
      presentedData = {
        targets: data.targets,
        group_targets: data.group_targets,
        personas: data.personas,
        model_request_sent: data.model_request_sent,
        platform_message_sent: data.platform_message_sent,
      };
    } else if (route === "host/initialize") {
      presentedData = {initialized: data.initialized, replayed: data.replayed};
    }
    output.textContent = JSON.stringify({
      http_status: response.status,
      status: payload?.status || "unknown",
      code: data.code || "",
      message: safeValue(payload?.message || ""),
      reason: safeValue(payload?.reason || ""),
      data: presentedData,
    }, null, 2);
  } catch (error) {
    output.textContent = JSON.stringify({status: "error", message: String(error)}, null, 2);
  }
})();
