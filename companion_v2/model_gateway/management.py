"""Dashboard model task settings for one authorized private role context."""

from dataclasses import asdict
from datetime import date, timedelta
import json

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.execution.models import TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.role_work.life.management import RoleLifeManagement
from .budget import effective_soft
from .replacement_rules import checked_rules, validate_targets


FIELDS = ("provider", "fallback", "prompt", "max_output_tokens", "replacement_rules", "fallback_on_refusal",
          "timeout_seconds", "replacement_scope")
OWNER = "configuration"


def _target(context, layer):
    scope = context.scope
    return ConfigTarget(scope.installation_id, layer, context.role_binding.role,
                        scope if layer is ConfigLayer.WINDOW else None, bot_id=scope.bot_id)


def _field(value, inherited):
    return {"value": value.value, "inherited_value": inherited.value,
            "source": value.source.layer.value if value.source else "default",
            "inherited_source": inherited.source.layer.value if inherited.source else "default",
            "explicit": value.explicit}


class ModelManagement:
    def __init__(self, app, context):
        self.app, self.context = app, context
        self.access = RoleLifeManagement(app, context)

    def _profile(self, kind):
        if type(kind) is not str or kind not in self.app.router.profiles:
            raise TaskError("model_task_unavailable", "select a registered model task")
        return self.app.router.profiles[kind]

    def _snapshots(self, operator, profile):
        now = self.app.now()
        current = require(self.app.configuration.read(operator, target=_target(self.context, ConfigLayer.WINDOW),
                                                      group_id=profile.group, observed_at=now))
        inherited = require(self.app.configuration.read(operator, target=_target(self.context, ConfigLayer.ROLE),
                                                        group_id=profile.group, observed_at=now))
        return current, inherited

    def _project(self, operator, profile):
        current, inherited = self._snapshots(operator, profile)
        fields = {name: _field(current.fields[profile.group + "." + name],
                               inherited.fields[profile.group + "." + name]) for name in FIELDS}
        application = require(self.app.configuration.application_status(operator,
            target=_target(self.context, ConfigLayer.WINDOW), group_id=profile.group, observed_at=self.app.now()))
        return {"kind": profile.kind, "lane": profile.lane.value, "capabilities": list(profile.capabilities),
                "default_prompt": profile.default_prompt, "prompt_version": profile.version,
                "fields": fields, "edit_token": current.edit_token, "application_state": application.state,
                "apply_mode": current.apply_mode.value, "revision": current.revision}

    def _runtime_diagnostics(self):
        runtime = self.app.runtime
        context_key = self.context.key
        identity_scope = {
            "dashboard_operator": "verified",
            "role_access": "verified",
            "token_ledger": "current_role",
        }
        pragma = lambda name: runtime.read_one("PRAGMA " + name, ())[0]
        storage = {
            "journal_mode": str(pragma("journal_mode")).lower(),
            "synchronous": int(pragma("synchronous")),
            "busy_timeout_ms": int(pragma("busy_timeout")),
            "foreign_keys": bool(pragma("foreign_keys")),
            "page_count": int(pragma("page_count")),
            "freelist_count": int(pragma("freelist_count")),
            "schema_version": int(pragma("user_version")),
        }
        batches = runtime.read_all("""SELECT b.batch_id, b.created_at, b.state AS batch_state,
                b.part_count, f.state AS flow_state, f.reason,
                COUNT(DISTINCT i.event_key) AS input_count,
                COUNT(DISTINCT CASE WHEN p.state = 'delivered' THEN p.part_id END) AS delivered_parts,
                COUNT(DISTINCT CASE WHEN p.state = 'failed' THEN p.part_id END) AS failed_parts,
                COUNT(DISTINCT CASE WHEN p.state = 'unknown' THEN p.part_id END) AS unknown_parts,
                COUNT(DISTINCT CASE WHEN p.state IN ('pending', 'dispatched') THEN p.part_id END) AS pending_parts
            FROM conversation_batches b
            LEFT JOIN conversation_flows f ON f.batch_id = b.batch_id
            LEFT JOIN conversation_inputs i ON i.batch_id = b.batch_id
            LEFT JOIN conversation_parts p ON p.batch_id = b.batch_id
            WHERE b.origin_key = ?
            GROUP BY b.batch_id
            ORDER BY b.created_at DESC LIMIT 12""", (context_key,))
        conversation = [{
            "created_at": row["created_at"], "batch_state": row["batch_state"],
            "flow_state": row["flow_state"] or "not_started", "flow_reason": row["reason"] or "",
            "input_count": row["input_count"] or 0, "part_count": row["part_count"] or 0,
            "delivered_parts": row["delivered_parts"] or 0, "failed_parts": row["failed_parts"] or 0,
            "unknown_parts": row["unknown_parts"] or 0, "pending_parts": row["pending_parts"] or 0,
        } for row in batches]
        flow_rows = runtime.read_all("""SELECT b.created_at, b.state AS batch_state, b.part_count,
                f.state AS flow_state, f.due_at, f.merge_until, f.deadline_at, f.policy_json, f.reason,
                COUNT(DISTINCT i.event_key) AS input_count
            FROM conversation_batches b
            JOIN conversation_flows f ON f.batch_id = b.batch_id
            LEFT JOIN conversation_inputs i ON i.batch_id = b.batch_id
            WHERE b.origin_key = ?
            GROUP BY b.batch_id
            ORDER BY b.created_at DESC LIMIT 8""", (context_key,))
        debounce_trace = []
        for row in flow_rows:
            try:
                policy = json.loads(row["policy_json"])
            except (TypeError, ValueError):
                policy = {}
            if not isinstance(policy, dict):
                policy = {}

            def milliseconds(name):
                value = policy.get(name)
                if type(value) not in (int, float) or not 0 <= value <= 3600:
                    return None
                return round(value * 1000)

            debounce_trace.append({
                "at": row["created_at"], "batch_state": row["batch_state"],
                "flow_state": row["flow_state"], "reason": row["reason"],
                "input_count": row["input_count"] or 0, "part_count": row["part_count"] or 0,
                "due_at": row["due_at"], "merge_until": row["merge_until"],
                "deadline_at": row["deadline_at"],
                "quiet_window_ms": milliseconds("quiet_seconds"),
                "merge_window_ms": milliseconds("maximum_wait_seconds"),
                "turn_timeout_ms": milliseconds("turn_timeout_seconds"),
            })
        material_rows = runtime.read_all("""SELECT
                COALESCE(json_extract(m.value, '$.owner'), 'unknown') AS owner,
                COALESCE(json_extract(m.value, '$.purpose'), 'unknown') AS purpose,
                COALESCE(json_extract(m.value, '$.state'), 'unknown') AS state,
                COUNT(*) AS uses
            FROM (SELECT contributions_json FROM conversation_batches
                  WHERE origin_key = ? ORDER BY created_at DESC LIMIT 20) AS recent
            JOIN json_each(recent.contributions_json, '$.materials') AS m
            GROUP BY owner, purpose, state ORDER BY uses DESC, owner, purpose LIMIT 24""", (context_key,))
        materials = [{"owner": row["owner"], "purpose": row["purpose"],
                      "state": row["state"], "uses": row["uses"]} for row in material_rows]
        proactive = runtime.read_one("""SELECT COUNT(*) AS calls, MAX(created_at) AS latest_at
            FROM proactive_contacts WHERE origin_key = ?""", (context_key,))
        return {"storage": storage, "conversation": conversation, "prompt_materials": materials,
                "identity_scope": identity_scope, "debounce_trace": debounce_trace,
                "proactive": {"calls": proactive["calls"] if proactive else 0,
                              "latest_at": proactive["latest_at"] if proactive else None}}

    @outcome
    def status(self, operator):
        with self.app.runtime.read_snapshot():
            self.access.authorize(operator)
            return {"tasks": [self._project(operator, profile) for profile in self.app.router.profiles.values()],
                    "providers": [{"id": provider.binding.provider, "capabilities": list(provider.capabilities),
                                   "max_output_tokens": provider.maximum_output_tokens,
                                   "supports_model_override": provider.supports_model_override,
                                   "model": provider.model}
                                   for provider in self.app.router.providers.values()],
                    "host_state": self.app.state}

    @outcome
    def maintenance(self, operator):
        """Read role-scoped model usage and diagnostics without exposing prompt material."""
        with self.app.runtime.read_snapshot():
            self.access.authorize(operator)
            now = self.app.now()
            runtime_diagnostics = self._runtime_diagnostics()
            scope = self.context.scope
            role_address = [scope.installation_id, scope.bot_id, asdict(self.context.role_binding.role)]
            today = now.date().isoformat()
            periods = [(now.date() - timedelta(days=offset)).isoformat() for offset in range(29, -1, -1)]
            candidate_days = self.app.runtime.read_all("""SELECT DISTINCT
                    substr(COALESCE(c.finished_at, c.started_at, r.created_at), 1, 10) AS day
                FROM model_calls c JOIN model_requests r ON r.task_id = c.task_id
                ORDER BY day""", ())
            all_days = {today}
            for item in candidate_days:
                value = item["day"]
                try:
                    parsed = date.fromisoformat(value)
                except (TypeError, ValueError):
                    continue
                if parsed.isoformat() == value:
                    all_days.add(value)
            role_accounts = {period: digest(["role", role_address, period]) for period in all_days}
            usage_fields = (
                "calls", "tokens", "cost_microusd", "unconfirmed_calls", "failures", "unknown_calls",
                "active_calls", "cache_reported_calls", "cache_telemetry_calls", "cache_input_tokens",
                "cached_input_tokens", "cache_creation_tokens", "cache_other_input_tokens", "input_tokens",
                "output_tokens", "latency_total_ms", "latency_samples",
            )

            def empty_usage():
                return dict.fromkeys(usage_fields, 0)

            def add_usage(target, row):
                for name in usage_fields:
                    target[name] += row.get(name, 0) or 0

            by_day, by_provider, by_task = {}, {}, {}
            day_provider, day_task, hourly = {}, {}, {}
            recent_rows = []
            ordered_days = sorted(all_days)
            batch_size = 300
            for offset in range(0, len(ordered_days), batch_size):
                batch_days = ordered_days[offset:offset + batch_size]
                account_keys = tuple(role_accounts[period] for period in batch_days)
                placeholders = ",".join("?" for _ in account_keys)
                grouped_rows = self.app.runtime.read_all(f"""SELECT
                        substr(COALESCE(c.finished_at, c.started_at, r.created_at), 1, 10) AS day,
                        CASE WHEN json_valid(c.provider_json)
                            THEN COALESCE(json_extract(c.provider_json, '$.provider'), '') ELSE '' END AS provider,
                        t.kind AS kind,
                        COUNT(*) AS calls,
                        SUM(COALESCE(c.actual_tokens, 0)) AS tokens,
                        SUM(COALESCE(c.actual_cost, 0)) AS cost_microusd,
                        SUM(CASE WHEN c.actual_tokens IS NULL THEN 1 ELSE 0 END) AS unconfirmed_calls,
                        SUM(CASE WHEN f.call_id IS NULL THEN 0 ELSE 1 END) AS failures,
                        SUM(CASE WHEN c.state = 'unknown' THEN 1 ELSE 0 END) AS unknown_calls,
                        SUM(CASE WHEN c.state IN ('reserved', 'dispatched') THEN 1 ELSE 0 END) AS active_calls,
                        SUM(CASE WHEN c.input_tokens IS NOT NULL AND c.cached_input_tokens IS NOT NULL THEN 1 ELSE 0 END)
                            AS cache_reported_calls,
                        SUM(CASE WHEN c.input_tokens IS NOT NULL AND c.cached_input_tokens IS NOT NULL THEN c.input_tokens ELSE 0 END)
                            AS cache_input_tokens,
                        SUM(CASE WHEN c.input_tokens IS NOT NULL AND c.cached_input_tokens IS NOT NULL THEN c.cached_input_tokens ELSE 0 END)
                            AS cached_input_tokens,
                        SUM(COALESCE(c.cache_creation_tokens, 0)) AS cache_creation_tokens,
                        SUM(CASE WHEN c.input_tokens IS NOT NULL AND c.cached_input_tokens IS NOT NULL THEN
                            MAX(0, c.input_tokens - c.cached_input_tokens - COALESCE(c.cache_creation_tokens, 0))
                            ELSE 0 END) AS cache_other_input_tokens,
                        SUM(CASE WHEN c.cached_input_tokens IS NOT NULL OR c.cache_creation_tokens IS NOT NULL THEN 1 ELSE 0 END)
                            AS cache_telemetry_calls,
                        SUM(COALESCE(c.input_tokens, 0)) AS input_tokens,
                        SUM(COALESCE(c.output_tokens, 0)) AS output_tokens,
                        SUM(COALESCE(c.latency_ms, 0)) AS latency_total_ms,
                        SUM(CASE WHEN c.latency_ms IS NULL THEN 0 ELSE 1 END) AS latency_samples
                    FROM model_calls c
                    JOIN model_call_accounts ca ON ca.call_id = c.call_id
                    JOIN model_requests r ON r.task_id = c.task_id
                    JOIN execution_tasks t ON t.task_id = c.task_id
                    LEFT JOIN model_call_failures f ON f.call_id = c.call_id
                    WHERE ca.account_key IN ({placeholders})
                    GROUP BY day, provider, kind""", account_keys)
                for row in grouped_rows:
                    day = row["day"]
                    provider = row["provider"] if type(row["provider"]) is str and row["provider"] else "未知 Provider"
                    kind = row["kind"] if type(row["kind"]) is str and row["kind"] else "unknown"
                    values = {name: row[name] or 0 for name in usage_fields}
                    add_usage(by_day.setdefault(day, empty_usage()), values)
                    add_usage(by_provider.setdefault(provider, empty_usage()), values)
                    add_usage(by_task.setdefault(kind, empty_usage()), values)
                    add_usage(day_provider.setdefault((day, provider), empty_usage()), values)
                    add_usage(day_task.setdefault((day, kind), empty_usage()), values)
                hour_rows = self.app.runtime.read_all(f"""SELECT
                        substr(COALESCE(c.finished_at, c.started_at, r.created_at), 1, 10) AS day,
                        substr(COALESCE(c.finished_at, c.started_at, r.created_at), 12, 2) AS hour,
                        COUNT(*) AS calls, SUM(COALESCE(c.actual_tokens, 0)) AS tokens,
                        SUM(COALESCE(c.actual_cost, 0)) AS cost_microusd
                    FROM model_calls c
                    JOIN model_call_accounts ca ON ca.call_id = c.call_id
                    JOIN model_requests r ON r.task_id = c.task_id
                    WHERE ca.account_key IN ({placeholders})
                    GROUP BY day, hour ORDER BY day, hour""", account_keys)
                for row in hour_rows:
                    hourly[(row["day"], row["hour"])] = {name: row[name] or 0
                        for name in ("calls", "tokens", "cost_microusd")}
                recent_rows.extend(self.app.runtime.read_all(f"""SELECT c.state, c.position, c.actual_tokens,
                        c.actual_cost, c.input_tokens, c.cached_input_tokens, c.cache_creation_tokens, c.output_tokens,
                        c.latency_ms, c.finished_at, c.started_at, r.created_at, t.kind, c.provider_json,
                        f.code AS failure_code
                    FROM model_calls c
                    JOIN model_call_accounts ca ON ca.call_id = c.call_id
                    JOIN model_requests r ON r.task_id = c.task_id
                    JOIN execution_tasks t ON t.task_id = c.task_id
                    LEFT JOIN model_call_failures f ON f.call_id = c.call_id
                    WHERE ca.account_key IN ({placeholders})
                    ORDER BY COALESCE(c.finished_at, c.started_at, r.created_at) DESC, c.position DESC LIMIT 80""",
                    account_keys))

            def project_usage(row, key=None):
                projected = {name: int(row.get(name) or 0) for name in usage_fields
                             if name not in ("latency_total_ms", "latency_samples")}
                latency_count = int(row.get("latency_samples") or 0)
                projected["avg_latency_ms"] = (round(row["latency_total_ms"] / latency_count)
                                                if latency_count else None)
                if key is not None:
                    projected["key"] = key
                return projected

            def ranked(rows):
                return sorted(rows, key=lambda item: (-item["tokens"], item["key"]))

            def dimension_rows(source, *, day=None, limit=8):
                entries = []
                for key, values in source.items():
                    if day is not None and key[0] != day:
                        continue
                    name = key[1] if day is not None else key
                    entries.append(project_usage(values, name))
                return ranked(entries)[:limit]

            windows = {}
            for label, length in (("7d", 7), ("30d", 30)):
                start = (now.date() - timedelta(days=length - 1)).isoformat()
                totals = empty_usage()
                providers_in_window, tasks_in_window = {}, {}
                for period, values in by_day.items():
                    if start <= period <= today:
                        add_usage(totals, values)
                for (period, provider), values in day_provider.items():
                    if start <= period <= today:
                        add_usage(providers_in_window.setdefault(provider, empty_usage()), values)
                for (period, kind), values in day_task.items():
                    if start <= period <= today:
                        add_usage(tasks_in_window.setdefault(kind, empty_usage()), values)
                windows[label] = {"start_day": start, "end_day": today,
                    "totals": project_usage(totals),
                    "providers": dimension_rows(providers_in_window, limit=100),
                    "tasks": dimension_rows(tasks_in_window, limit=100)}

            history = []
            for period in sorted(by_day):
                entry = project_usage(by_day[period], period)
                entry["providers"] = dimension_rows(day_provider, day=period)
                entry["tasks"] = dimension_rows(day_task, day=period)
                history.append(entry)
            history_by_day = {row["key"]: row for row in history}
            daily = []
            for period in periods:
                entry = history_by_day.get(period, project_usage(empty_usage(), period))
                daily.append(entry)
            all_time = project_usage({name: sum(row[name] for row in by_day.values()) for name in usage_fields})
            all_time["providers"] = dimension_rows(by_provider, limit=12)
            all_time["tasks"] = dimension_rows(by_task, limit=16)
            all_time["days"] = len(history)
            hourly_rows = [{"day": day, "hour": hour, **values}
                           for (day, hour), values in sorted(hourly.items())]
            provider_rows = dimension_rows(by_provider, limit=100)
            task_rows = dimension_rows(by_task, limit=100)

            # Keep the latest samples bounded while merging results from account-key batches.
            recent_rows.sort(key=lambda row: (row["finished_at"] or row["started_at"] or row["created_at"] or "",
                                              row["position"] or 0), reverse=True)
            recent_rows = recent_rows[:80]
            recent = []
            for row in recent_rows:
                try:
                    provider_record = json.loads(row["provider_json"])
                except (TypeError, ValueError):
                    provider_record = None
                provider_id = provider_record.get("provider", "") if isinstance(provider_record, dict) else ""
                if type(provider_id) is not str:
                    provider_id = ""
                input_tokens = row["input_tokens"]
                cached_tokens = row["cached_input_tokens"]
                cache_rate = (round(cached_tokens * 100 / input_tokens, 1)
                              if cached_tokens is not None and input_tokens is not None and input_tokens > 0 else None)
                recent.append({"kind": row["kind"], "provider": provider_id, "state": row["state"],
                    "tokens": row["actual_tokens"], "cost_microusd": row["actual_cost"],
                    "input_tokens": input_tokens, "cached_input_tokens": cached_tokens,
                    "cache_creation_tokens": row["cache_creation_tokens"], "output_tokens": row["output_tokens"],
                    "cache_hit_rate": cache_rate, "latency_ms": row["latency_ms"],
                    "failure": row["failure_code"],
                    "at": row["finished_at"] or row["started_at"] or row["created_at"]})
            today_account = role_accounts[now.date().isoformat()]
            budget_row = self.app.runtime.read_one(
                "SELECT token_limit, held_tokens, spent_tokens FROM model_budget_accounts WHERE account_key = ?",
                (today_account,))
            policy = self.app.gateway.ledger.policy
            budget = {"limit_tokens": budget_row["token_limit"] if budget_row else policy.role.tokens,
                      "spent_tokens": budget_row["spent_tokens"] if budget_row else 0,
                      "held_tokens": budget_row["held_tokens"] if budget_row else 0}
            soft = effective_soft(self.app.runtime, self.context, self.app.gateway.ledger.soft)
            summary = project_usage({name: sum(by_day.get(period, empty_usage())[name] for period in periods)
                                     for name in usage_fields})
            known_calls = summary["calls"] - summary["unconfirmed_calls"]
            cache_reported = summary["cache_reported_calls"]
            cache_telemetry = summary["cache_telemetry_calls"]
            cached = summary["cached_input_tokens"]
            cache_input = summary["cache_input_tokens"]
            cache_creation = summary["cache_creation_tokens"]
            cache_other = summary["cache_other_input_tokens"]
            cache_denominator = cache_input
            summary.update({"cache_reported_calls": cache_reported, "cache_telemetry_calls": cache_telemetry,
                "known_calls": known_calls,
                "cache_coverage_pct": round(cache_reported * 100 / known_calls, 1) if known_calls else None,
                "cache_input_tokens": cache_input, "cached_input_tokens": cached,
                "cache_creation_tokens": cache_creation, "cache_other_input_tokens": cache_other,
                "cache_hit_rate": round(cached * 100 / cache_denominator, 1) if cache_denominator else None})
            budget.update({"soft_limit_enabled": bool(soft and soft.enabled),
                           "soft_limit_tokens": soft.tokens if soft else 0})
            providers = [{"id": item.binding.provider, "model": item.model}
                         for item in self.app.router.providers.values()]
            return {"generated_at": now.isoformat(), "summary": summary, "daily": daily,
                    "history": history, "totals": all_time, "windows": windows, "by_provider": provider_rows,
                    "by_task": task_rows, "hourly": hourly_rows, "recent": recent,
                    "budget": budget, "providers": providers, "window_days": 30,
                    "ledger_scope": "current_role", "runtime": runtime_diagnostics}

    @outcome
    def check_storage(self, operator):
        """Run explicit read-only SQLite integrity and foreign-key checks."""
        with self.app.runtime.read_only_snapshot() as connection:
            self.access.authorize(operator)
            integrity = [row[0] for row in connection.execute("PRAGMA quick_check")]
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchmany(20)
            return {"status": "ok" if integrity == ["ok"] and not foreign_keys else "failed",
                    "integrity": integrity[:8], "foreign_key_issues": len(foreign_keys),
                    "foreign_key_sample": [list(row) for row in foreign_keys[:5]]}

    def _changes(self, profile, data, current, inherited):
        changes, reset = data["changes"], data["reset"]
        if (type(changes) is not dict or type(reset) is not list or not changes and not reset
                or any(type(name) is not str or name not in FIELDS for name in changes)
                or any(type(name) is not str or name not in FIELDS for name in reset)
                or len(reset) != len(set(reset)) or set(changes).intersection(reset)):
            raise TaskError("model_configuration_invalid", "select distinct task fields to save or inherit")
        values = {name: current.fields[profile.group + "." + name].value for name in FIELDS}
        for name in reset:
            values[name] = inherited.fields[profile.group + "." + name].value
        values.update(changes)
        if (type(values["provider"]) is not str or type(values["fallback"]) is not str
                or type(values["prompt"]) is not str
                or len(values["prompt"]) > 8000 or type(values["max_output_tokens"]) is not int
                or type(values["fallback_on_refusal"]) is not bool
                or not 1 <= values["max_output_tokens"] <= 32768
                or type(values["timeout_seconds"]) is not int or not 1 <= values["timeout_seconds"] <= 600
                or values["replacement_scope"] not in ("all", "plugin", "conversation")):
            raise TaskError("model_configuration_invalid", "check task prompt and output token limit")
        selected = [values["provider"]] + ([values["fallback"]] if values["fallback"] else [])
        if len(set(selected)) != len(selected):
            raise TaskError("model_fallback_duplicate", "fallback must differ from the primary provider")
        for provider_id in selected:
            provider = self.app.router.providers.get(provider_id)
            if provider is None:
                raise TaskError("model_provider_unavailable", "the provider has no registered V2 adapter")
            if not set(profile.capabilities).issubset(provider.capabilities):
                raise TaskError("model_capability_mismatch", "the provider lacks task capabilities")
            if values["max_output_tokens"] > provider.maximum_output_tokens:
                raise TaskError("model_output_limit", "output limit exceeds the selected provider")
        try:
            validate_targets(checked_rules(values["replacement_rules"]), self.app.router.providers,
                             capabilities=profile.capabilities, max_output_tokens=values["max_output_tokens"])
        except ValueError as error:
            raise TaskError("model_route_invalid", str(error)) from error
        return {profile.group + "." + name: value for name, value in changes.items()}, tuple(
            profile.group + "." + name for name in reset)

    @outcome
    def configure(self, operator, data):
        if type(data) is not dict or set(data) != {"kind", "operation_key", "edit_token", "changes", "reset"}:
            raise TaskError("model_configuration_invalid", "provide one complete model task patch")
        kind, key, token = data["kind"], data["operation_key"], data["edit_token"]
        if (type(key) is not str or not key.strip() or len(key) > 128
                or type(token) is not str or len(token) != 64):
            raise TaskError("model_configuration_invalid", "provide a stable operation key and edit token")
        with self.app.runtime.transaction():
            self.access.authorize(operator)
            profile = self._profile(kind)
            current, inherited = self._snapshots(operator, profile)
            changes, reset = self._changes(profile, data, current, inherited)
            op_id = "model-settings:" + digest([operator.subject, self.context.key, kind, key])
            receipt = require(self.app.configuration.patch(operator,
                target=_target(self.context, ConfigLayer.WINDOW), group_id=profile.group,
                operation=OperationRef(op_id, OWNER, self.context.scope, VersionRef(op_id, 1), op_id),
                expected_edit_token=token, changes=changes, reset_to_inherit=reset,
                observed_at=self.app.now()))
            return {"replayed": receipt.replayed, "operation_id": op_id, "task": self._project(operator, profile)}
