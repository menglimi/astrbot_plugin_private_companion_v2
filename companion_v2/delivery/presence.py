"""Optional platform presentation follows the original host and conversation lifecycle."""

import asyncio
from datetime import timedelta
import json

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, stamp


class PresenceCoordinator:
    def __init__(self, app, port):
        self.app, self.runtime, self.port = app, app.runtime, port
        self.typing, self.suppressed, self.contexts, self.results = {}, {}, {}, {}
        self._result_contexts = {}
        self.status_worker = None
        self.closed = False

    @staticmethod
    def account(context):
        s = context.scope
        return digest([s.installation_id, s.platform, s.bot_id, s.account_id])

    @classmethod
    def route(cls, context):
        return digest([cls.account(context), context.scope.native_scope_id])

    def bind(self, context):
        self.contexts[context.key] = context

    def _record_result(self, key, result, *context_keys):
        self.results[key] = {"recorded_at": stamp(self.app.now()), **result}
        self._result_contexts[key] = frozenset(context_keys)

    def results_for(self, context):
        """An account or native route alone does not identify the original persona."""
        results = {key: dict(result) for key, result in self.results.items()
                   if context.key in self._result_contexts.get(key, ())}
        account = self.account(context)
        if account not in results:
            latest = self.latest_status(context)
            if latest and latest["context_key"] == context.key:
                results[account] = self.stored_result(latest)
        return results

    def latest_status(self, context):
        return self.runtime.read_one("SELECT * FROM platform_presence_operations WHERE account_key = ? ORDER BY rowid DESC LIMIT 1",
                                     (self.account(context),))

    @staticmethod
    def stored_result(row):
        return {**json.loads(row["result_json"]), "recorded_at": row["updated_at"],
                "operation_id": row["operation_id"], "operation_state": row["state"],
                "desired": json.loads(row["request_json"])}

    def active_turn(self, context):
        """Presentation follows this recipient's turn, not the role's shared body."""
        return self.runtime.read_one("""SELECT f.batch_id, f.state FROM conversation_flows f
            JOIN conversation_batches b USING(batch_id)
            WHERE b.origin_key = ? AND f.state IN ('collecting','generating','delivering')
            ORDER BY f.sequence LIMIT 1""", (context.key,))

    def _allowed(self, context, option, action):
        self.app.require_running()
        self.app.role_state.access.check(context, action)
        values, _ = self.app.role_state.settings(context)
        if not values[option]:
            raise TaskError("presentation_disabled", "optional presentation is disabled")
        return values

    async def _pulse(self, context):
        # One continuous lease covers the whole turn, including tools and part gaps.
        # Stop refreshing when the lease ends; don't issue an unverified protocol toggle.
        while not self.closed:
            values = self._allowed(context, "typing_enabled", "platform.typing")
            turn = self.active_turn(context)
            def current():
                nonlocal turn
                self._allowed(context, "typing_enabled", "platform.typing")
                turn = self.active_turn(context)
                if turn is None:
                    raise TaskError("typing_turn_closed", "the original reply has ended")
            result = await asyncio.wait_for(self.port.typing(context, before_dispatch=current), timeout=3)
            self._record_result("typing:" + self.route(context),
                                {**result, "batch_id": turn["batch_id"] if turn else None}, context.key)
            if result.get("state") != "accepted":
                return
            await asyncio.sleep(values["typing_refresh_seconds"])

    def advance(self):
        if self.closed:
            return
        rows = self.runtime.read_all("""SELECT b.context_json, f.batch_id, f.sequence FROM conversation_flows f
            JOIN conversation_batches b USING(batch_id)
            WHERE f.state IN ('collecting','generating','delivering') ORDER BY f.sequence LIMIT 64""", ())
        active = {}
        for row in rows:
            context = TaskContext.restore(json.loads(row["context_json"]))
            self.bind(context)
            try:
                self._allowed(context, "typing_enabled", "platform.typing")
            except TaskError:
                continue
            route = self.route(context)
            if route not in active:
                active[route] = (context, row["batch_id"])
        for key, (context, batch, worker) in tuple(self.typing.items()):
            current = active.get(key)
            if not current or current[0].key != context.key:
                worker.cancel()
                # Retain the handle until cancellation is acknowledged; never overlap a replacement.
                if worker.done():
                    if not worker.cancelled():
                        worker.exception()
                    del self.typing[key]
                continue
            if worker.done():
                if not worker.cancelled():
                    error = worker.exception()
                    if error:
                        self._record_result("typing:" + key,
                            {"state": "unknown", "code": getattr(error, "code", "typing_failed"),
                             "batch_id": batch}, context.key)
                    self.suppressed[key] = current[1]
                del self.typing[key]
        for key, (context, batch) in active.items():
            if key not in self.typing and self.suppressed.get(key) != batch:
                worker = asyncio.create_task(self._pulse(context), name="companion:typing:" + key)
                self.typing[key] = (context, batch, worker)
                worker.add_done_callback(lambda done: self.app.notify())
        self.suppressed = {k: v for k, v in self.suppressed.items() if k in active}
        if self.status_worker and self.status_worker.done():
            if not self.status_worker.cancelled():
                error = self.status_worker.exception()
                if error:
                    self.results["presence"] = {"state": "unknown", "code": getattr(error, "code", "presence_failed")}
            self.status_worker = None
        if self.status_worker is None and self._candidates():
            self.status_worker = asyncio.create_task(self._sync_status(), name="companion:presence")

    def desired(self, context):
        return self.desired_status(context)["desired"]

    @staticmethod
    def intent_hash(desired):
        return digest(desired["wording"]) if "wording" in desired else digest(["online", desired["mode"]])

    def desired_status(self, context):
        """The same public intent and reasons serve dispatch and read-only diagnostics."""
        available = set()
        for option in ("presence_enabled", "online_status_enabled"):
            try:
                values = self._allowed(context, option, "platform.presence")
                available.add(option)
            except TaskError:
                continue
        if not available:
            raise TaskError("presentation_disabled", "optional account status is unavailable")
        now = self.app.now()
        if "presence_enabled" in available:
            try:
                window = self.app.calendar.occurrences(context, start=now, end=now + timedelta(seconds=1))
                current = [row for row in window["items"] if row["kind"] == "role_plan" and row["state"] == "accepted" and row["presence"]]
                if window["partial"] or len(current) > 1:
                    return {"desired": None, "reason": "presence_calendar_partial" if window["partial"] else "presence_plan_conflict"}
                if current:
                    row = current[0]
                    return {"desired": {"wording": row["presence"], "basis": "calendar_plan",
                            "reference": [row["id"], row["revision"], row["sequence"]]}, "reason": None}
            except TaskError:
                pass
        if values["enabled"]:
            state = self.app.role_state.read(context)
            public = state.get("values", {})
            mode = public.get("online_mode")
            if "online_status_enabled" in available and mode:
                return {"desired": {"mode": mode, "basis": "role_simulation",
                        "reference": [state["revision"]]}, "reason": None}
            wording = public.get("presence")
            if "presence_enabled" in available and wording:
                return {"desired": {"wording": wording, "basis": "role_simulation", "reference": [state["revision"]]}, "reason": None}
        return {"desired": None, "reason": "presence_no_public_wording"}

    def _candidates(self):
        candidates = {}
        for context in tuple(self.contexts.values()):
            if self._status_available(context):
                candidates.setdefault(self.account(context), []).append(context)
        return candidates

    def _status_available(self, context):
        for option in ("presence_enabled", "online_status_enabled"):
            try:
                self._allowed(context, option, "platform.presence")
                return True
            except TaskError:
                continue
        return False

    async def _sync_status(self):
        candidates = self._candidates()
        for account, contexts in candidates.items():
            if len(contexts) != 1:
                self._record_result(account, {"state": "blocked", "code": "multiple_presence_owners"},
                                    *(context.key for context in contexts))
                continue
            context = contexts[0]
            desired = self.desired(context)
            if desired is None:
                continue
            desired_hash = self.intent_hash(desired)
            latest = self.latest_status(context)
            if latest and latest["desired_hash"] == desired_hash:
                # A previous account result still belongs to its original persona.
                self._record_result(account, self.stored_result(latest), latest["context_key"])
                continue  # ACK, failure and unknown are all persisted; never pulse the same account status.
            operation = "presence-" + digest([account, context.key, desired, latest["operation_id"] if latest else None])
            if self.desired(context) != desired:
                continue
            with self.runtime.transaction() as connection:
                connection.execute("INSERT INTO platform_presence_operations VALUES (?, ?, ?, ?, 'started', ?, ?, ?)",
                    (operation, account, context.key, desired_hash, encode(desired), stamp(self.app.now()), encode({"state": "unknown"})))
            try:
                # The port rechecks native account, persona and grants immediately before the action.
                def current():
                    if self.desired(context) != desired:
                        raise TaskError("presence_changed", "original public status changed")
                    for other in self.contexts.values():
                        if other.key != context.key and self.account(other) == account and self._status_available(other):
                            raise TaskError("multiple_presence_owners", "account has competing status owners")
                action = (self.port.custom_status(context, desired["wording"], before_dispatch=current)
                          if "wording" in desired else
                          self.port.online_status(context, desired["mode"], before_dispatch=current))
                result = await asyncio.wait_for(action, timeout=3)
            except BaseException as error:
                result = {"state": "unknown", "code": "presence_interrupted"}
                self._record_result(account, self._receipt(operation, result), context.key)
                if isinstance(error, asyncio.CancelledError):
                    raise
            else:
                self._record_result(account, self._receipt(operation, result), context.key)

    def _receipt(self, operation, result):
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE platform_presence_operations SET state = ?, result_json = ?, updated_at = ? WHERE operation_id = ?",
                (result["state"], encode(result), stamp(self.app.now()), operation))
            row = connection.execute("SELECT * FROM platform_presence_operations WHERE operation_id = ?", (operation,)).fetchone()
            return self.stored_result(row)

    def cancel_running(self):
        for _, _, worker in self.typing.values():
            worker.cancel()
        if self.status_worker:
            self.status_worker.cancel()

    @property
    def active_handles(self):
        return tuple("typing:" + key for key, (_, _, worker) in self.typing.items() if not worker.done()) + (
            ("presence",) if self.status_worker is not None and not self.status_worker.done() else ())

    async def close(self):
        self.closed = True
        self.cancel_running()
        workers = [w for _, _, w in self.typing.values()] + ([self.status_worker] if self.status_worker else [])
        if workers:
            await asyncio.wait(workers, timeout=0.25)
            for worker in workers:
                if worker.done() and not worker.cancelled():
                    worker.exception()
