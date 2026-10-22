"""Optional platform presentation follows the original host and conversation lifecycle."""

import asyncio
from datetime import timedelta
import json
import logging

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, stamp
from companion_v2.foundation.refs import ScopeKind


logger = logging.getLogger(__name__)


class PresenceCoordinator:
    def __init__(self, app, port):
        self.app, self.runtime, self.port = app, app.runtime, port
        self.typing, self.suppressed, self.contexts, self.results = {}, {}, {}, {}
        self.native_replies, self._typing_wakes = {}, {}
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

    def begin_native_reply(self, context, turn_id):
        """Hold typing from authenticated intake through the final native send.

        Generation observations can complete before AstrBot starts delivery.
        This live lease therefore belongs to the entire reply, not that row.
        A route keeps its empty lease after completion so delayed observation
        writes cannot restart typing. Concurrent turns share one refresh worker.
        """
        if self.closed or context.scope.kind is not ScopeKind.PRIVATE:
            return
        from companion_v2.conversation.reset import boundary
        route, reset = self.route(context), boundary(self.runtime, context.scope)
        lease = self.native_replies.get(route)
        if lease is None or lease["context"] != context or lease["reset"] != reset:
            lease = {"context": context, "reset": reset, "turns": {}}
            self.native_replies[route] = lease
        lease["turns"].setdefault(turn_id, {"batch_id": turn_id, "state": "prepared",
                                          "execution_path": "astrbot_core"})
        self.bind(context)
        self._advance_typing()
        self.app.notify()

    def finish_native_reply(self, context, turn_id):
        lease = self.native_replies.get(self.route(context))
        if lease is not None and lease["context"] == context:
            lease["turns"].pop(turn_id, None)
            self._advance_typing()
            self.app.notify()

    def native_reply_stage(self, context, turn_id, stage):
        lease = self.native_replies.get(self.route(context))
        turn = (lease["turns"].get(turn_id)
                if lease is not None and lease["context"] == context else None)
        if turn is None:
            return
        turn["state"] = stage
        if stage == "delivering":
            # QQ can clear the indicator when a bubble arrives. Wake the same
            # worker immediately instead of leaving the next part gap unmarked.
            wake = self._typing_wakes.get(self.route(context))
            if wake is not None:
                wake.set()

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
        lease = self.native_replies.get(self.route(context))
        if lease is not None:
            if lease["context"] != context:
                return None
            from companion_v2.conversation.reset import boundary
            if boundary(self.runtime, context.scope) != lease["reset"]:
                lease["turns"].clear()
            return next(reversed(lease["turns"].values()), None)
        from companion_v2.conversation.native_turns import latest_scope
        native = latest_scope(self.runtime, context.scope)
        if native is not None:
            if native["context_key"] == context.key and native["generation_state"] in ("prepared", "running"):
                return {"batch_id": native["turn_id"], "state": native["generation_state"],
                        "execution_path": "astrbot_core"}
            return None
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
        wake = self._typing_wakes.setdefault(self.route(context), asyncio.Event())
        reported_batch = None
        while not self.closed:
            wake.clear()
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
            batch = turn["batch_id"] if turn else None
            if batch != reported_batch or result.get("state") != "accepted":
                logger.info("[CompanionV2] QQ 输入提示 recipient=%s turn_id=%s state=%s code=%s",
                            context.scope.native_scope_id, batch, result.get("state"), result.get("code", ""))
                reported_batch = batch
            if result.get("state") != "accepted":
                return
            try:
                await asyncio.wait_for(wake.wait(), timeout=values["typing_refresh_seconds"])
            except asyncio.TimeoutError:
                pass

    def advance(self):
        if self.closed:
            return
        self._advance_typing()
        if self.status_worker and self.status_worker.done():
            if not self.status_worker.cancelled():
                error = self.status_worker.exception()
                if error:
                    self.results["presence"] = {"state": "unknown", "code": getattr(error, "code", "presence_failed")}
            self.status_worker = None
        if self.status_worker is None and self._candidates():
            self.status_worker = asyncio.create_task(self._sync_status(), name="companion:presence")

    def _advance_typing(self):
        if self.closed:
            return
        rows = self.runtime.read_all("""SELECT b.context_json, f.batch_id, f.sequence FROM conversation_flows f
            JOIN conversation_batches b USING(batch_id)
            WHERE f.state IN ('collecting','generating','delivering') ORDER BY f.sequence LIMIT 64""", ())
        from companion_v2.conversation.native_turns import context_rows
        native = context_rows(self.runtime, kind="private")
        rows = (*rows, *({"context_json": row["context_json"], "batch_id": row["turn_id"]}
                        for row in native if row["generation_state"] in ("prepared", "running")),
                *({"context_json": encode(lease["context"]), "batch_id": turn["batch_id"]}
                  for lease in self.native_replies.values() for turn in lease["turns"].values()))
        active = {}
        for row in rows:
            context = TaskContext.restore(json.loads(row["context_json"]))
            self.bind(context)
            try:
                self._allowed(context, "typing_enabled", "platform.typing")
                turn = self.active_turn(context)
                if turn is None:
                    continue
            except TaskError:
                continue
            route = self.route(context)
            if route not in active:
                active[route] = (context, turn["batch_id"])
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
        self.native_replies.clear()
        self.cancel_running()
        workers = [w for _, _, w in self.typing.values()] + ([self.status_worker] if self.status_worker else [])
        if workers:
            await asyncio.wait(workers, timeout=0.25)
            for worker in workers:
                if worker.done() and not worker.cancelled():
                    worker.exception()
