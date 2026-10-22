"""Small relevant recall snapshots; every later use rechecks original versions."""

import json

from companion_v2.capabilities.ownership import delegated_memory, failure_reason
from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.execution.models import TaskError, encode, require
from companion_v2.foundation.refs import ScopeKind

from .habits import habit_capture, habit_contribution
from .models import AtomRef, owner_key
from .pinned import select_pinned, visible_fact


DELEGATED_STATE = "delegated"
"""快照状态：这一轮的记忆表达归别家插件，V2 不注入任何记忆材料。"""


def visible_experience(value):
    return {**{key: value[key] for key in ("view_id", "revision", "title", "entities", "links", "occurred_at", "perspective")},
            "statements": [{"text": statement["text"]} for statement in value["statements"]],
            "meaning": "derived_summary_not_independent_evidence"}


class MemoryContext:
    def __init__(self, memory):
        self.memory = memory

    def delegated(self) -> bool:
        """这段时期记忆表达是否已经让给别家插件。

        每次询问都重新判定、不缓存：别家的句柄消失后的**下一个请求**就该回到
        V2 自己的记忆，不能靠一个持久标志记住让位状态。
        """

        return bool(self.memory.delegated())

    def ownership(self) -> dict:
        """给页面/日志用的判定原文（含让位原因），判定不可用时给出兜底原因码。"""

        owner = getattr(self.memory, "owner", None)
        state = None
        if owner is not None:
            try:
                state = owner.state()
            except Exception:
                state = None
        if state is None or not hasattr(state, "document"):
            return {"owner": "self", "reason": failure_reason(owner),
                    "module": "", "provider": "", "display_name": ""}
        return state.document()

    def capture(self, context, batch_id, sources, deadline_at, *, session_id=None):
        """Capture one read-only snapshot under one explicit query session.

        The session id doubles as the authorization key: ``query.begin`` checks
        the current identity, role and private audience again and refuses a
        session owned by another original context, so two captures of the same
        owner never share recalled handles. A caller without a conversation batch
        supplies its own bounded session id instead of inventing a batch.
        """
        query, policy = self.memory.query, self.memory.writer.access.policy_for(context)
        snapshot = {"version": 1, "context_key": context.key,
                    "session_id": "memory:" + batch_id if session_id is None else session_id,
                    "state": "ready", "references": [], "handles": [], "mutations": [],
                    "core_ids": [], "core_omitted": False, "experience_references": []}
        if self.delegated():
            return self._delegated_snapshot(snapshot)
        try:
            query.begin(context, snapshot["session_id"], expires_at=deadline_at)
            current_text = []
            for reference in sources:
                evidence = self.memory.writer.access.capture(context, reference)
                snapshot["handles"].append(query.offer(context, snapshot["session_id"], evidence))
                current_text.append(self.memory.writer.access.evidence(context, evidence))
            core, omitted = select_pinned(self.memory.writer, context, policy)
            snapshot["references"].extend(core)
            snapshot["core_ids"] = [item["atom_id"] for item in core]
            snapshot["core_omitted"] = omitted
            # The habit profile is read again when the prompt is built; only this
            # turn's availability is sealed here. Read-only, so it
            # stays valid inside the sealing transaction.
            snapshot["habits"] = habit_capture(self.memory, context, "\n".join(current_text))
        except TaskError as error:
            return {**snapshot, "state": "unavailable", "reason": error.code, "references": [], "handles": []}
        try:
            if policy.automatic_context and policy.context_items:
                intent = "\n".join(current_text)[-240:]
                used, remaining = 0, policy.context_items
                # One relevant experience shares the existing topical budget.
                # Core facts retain their separate allocation and original order.
                if self.memory.runtime.read_one("""SELECT 1 FROM memory_views
                        WHERE owner_key = ? AND kind = 'experience' AND state = 'active' LIMIT 1""", (owner_key(context),)):
                    try:
                        experiences = require(query.query(context, snapshot["session_id"], query_intent=intent,
                            kind="experiences", limit=1))
                        snapshot["recall_pending"] = experiences.get("index_state") == "catching_up" or experiences.get("scan_limited", False)
                        for item in experiences["items"]:
                            value = require(self.memory.experiences.read(context, item["view_id"], expected_revision=item["revision"]))
                            size = len(encode(visible_experience(value)))
                            if size <= policy.context_chars:
                                snapshot["experience_references"].append({"view_id": item["view_id"], "revision": item["revision"]})
                                used, remaining = size, remaining - 1
                    except TaskError as error:
                        snapshot["recall_unavailable"] = error.code
                if not remaining:
                    return snapshot
                result = require(query.query(context, snapshot["session_id"], query_intent=intent, limit=remaining))
                snapshot["recall_pending"] = snapshot.get("recall_pending", False) or result.get("index_state") == "catching_up" or result.get("scan_limited", False)
                for item in result["items"]:
                    if item["atom_id"] in snapshot["core_ids"]:
                        continue
                    size = len(encode(visible_fact(item)))
                    if used + size <= policy.context_chars:
                        snapshot["references"].append({"atom_id": item["atom_id"], "revision": item["revision"]})
                        used += size
        except TaskError as error:
            # A derived search failure must not erase authorized core context.
            snapshot["recall_unavailable"] = error.code
        return snapshot

    def _delegated_snapshot(self, snapshot):
        """让位期的空快照：没有句柄、没有引用，只有一条「谁在提供记忆」。

        仍然是一条可读的快照（带 ``version`` 与 ``context_key``），所以
        ``contributions``、主动消息路径和 ``enrich_semantic`` 的既有形状检查都照旧
        通过——让位期不需要在别处再插一次「如果是让位就跳过」的分支。

        注意这里**只**关掉表达：事实、经历、整理批次照旧写入 V2 自己的库，所以
        牢插件消失时不是从零开始，而是接着已有的记录继续长。这是有意的：让位是
        表达层的切换，不是存储的切换。
        """

        return {**snapshot, "state": DELEGATED_STATE, "reason": failure_reason(self.memory.owner),
                "delegated_to": self.ownership().get("display_name", ""),
                "references": [], "handles": [], "core_ids": [], "experience_references": []}

    def contact_capture(self, context, session_key, sources, deadline_at):
        """A batch-free recall snapshot for one proactive contact opportunity.

        A proactive message has no conversation batch, so it must not pretend to
        have one: a fabricated ``conversation_batches`` row would let a later
        ``enrich_semantic`` or owner refresh address a batch that never carried
        the user's input. The snapshot therefore only borrows the batch path's
        session-identity rule, over a key from the contact itself, and reuses
        ``capture`` unchanged. Everything the snapshot authorizes is still
        revalidated when the prompt is built: ``policy_for``, ``check`` and every
        per-reference owner read run again, so a disabled memory, a moved role
        binding or a forgotten source denies a proactive message exactly as it
        denies a reply. Callers keep the key unique per opportunity so two
        opportunities never share recalled handles.
        """
        if type(session_key) is not str or not session_key.startswith("memory-") or len(session_key) > 512:
            raise ValueError("contact memory session key must be bounded text under its own namespace")
        return self.capture(context, session_key, sources, deadline_at, session_id=session_key)

    def contact_contributions(self, snapshot, context):
        """The snapshot's materials for a proactive prompt, minus input handles.

        ``capture`` also seals source handles so a reply turn can offer the
        original spans it was shown. A proactive generation is not a turn and has
        no memory tools, so those handles are unreachable there; publishing them
        would only suggest a lookup that cannot exist. The stored material itself
        is unchanged and still built under the same budgets.
        """
        return tuple(item for item in self.contributions(snapshot, context)
                     if item.purpose != "current_input_handles")

    def enrich_semantic(self, context, batch_id, query_intent, vector, model):
        """Merge one current-turn embedding recall into the sealed snapshot.

        The query result is disposable; only exact object revisions are saved in
        the batch.  The original context and batch revision are checked again
        before the compare-and-swap update so a late index cannot replace a
        newer owner mutation.
        """
        if context.scope.kind is not ScopeKind.PRIVATE:
            raise TaskError("memory_context_scope", "semantic private memory requires a private context")
        if type(batch_id) is not str or not batch_id or len(batch_id) > 512:
            raise ValueError("batch_id must be bounded text")
        if type(query_intent) is not str or not query_intent.strip() or len(query_intent) > 2000:
            raise ValueError("query_intent must be bounded text")
        if not isinstance(vector, tuple) or type(model) is not str or not model:
            return False

        self.memory.writer.access.check(context)
        query = self.memory.query
        session_id = "memory:" + batch_id
        query._session(context, session_id)
        row = self.memory.runtime.read_one(
            "SELECT origin_key, state, revision, contributions_json FROM conversation_batches WHERE batch_id = ?",
            (batch_id,),
        )
        if row is None or row["origin_key"] != context.key:
            raise TaskError("memory_batch_unavailable", "memory batch belongs to another original context")
        if row["state"] != "sealed":
            return False
        saved = json.loads(row["contributions_json"])
        snapshot = saved.get("memory_context") if isinstance(saved, dict) else None
        if not isinstance(snapshot, dict) or snapshot.get("state") != "ready":
            return False
        if snapshot.get("context_key") != context.key or snapshot.get("session_id") != session_id:
            raise TaskError("memory_snapshot_invalid", "semantic recall must retain the original memory session")

        policy = self.memory.writer.access.policy_for(context)
        # 让位期连嵌入召回都不做：那会为一份不会注入的材料付一次模型调用，
        # 而且它的结果也不会有人用。
        if not policy.automatic_context or not policy.context_items or self.delegated():
            return False

        unavailable = []
        pending = bool(snapshot.get("recall_pending"))
        semantic_experiences, semantic_facts = [], []

        try:
            result = require(query.query(context, session_id, query_intent=query_intent,
                kind="experiences", limit=1, vector=vector, model=model))
            semantic_experiences = result.get("items", [])
            pending = pending or result.get("index_state") != "ready" or result.get("scan_limited", False)
            coverage = result.get("vector_coverage") or {}
            pending = pending or coverage.get("complete") is False
        except TaskError as error:
            unavailable.append(error.code)

        try:
            result = require(query.query(context, session_id, query_intent=query_intent,
                kind="facts", limit=policy.context_items, vector=vector, model=model))
            semantic_facts = result.get("items", [])
            pending = pending or result.get("index_state") != "ready" or result.get("scan_limited", False)
            coverage = result.get("vector_coverage") or {}
            pending = pending or coverage.get("complete") is False
        except TaskError as error:
            unavailable.append(error.code)

        references = snapshot.get("references", [])
        if not isinstance(references, list) or len(references) > 64:
            raise TaskError("memory_snapshot_invalid", "invalid memory references")
        core_ids = set(snapshot.get("core_ids", []))
        core_refs = [reference for reference in references
                     if isinstance(reference, dict) and reference.get("atom_id") in core_ids]
        lexical_facts = [reference for reference in references
                         if isinstance(reference, dict) and reference.get("atom_id") not in core_ids]
        lexical_experiences = snapshot.get("experience_references", [])
        if not isinstance(lexical_experiences, list) or len(lexical_experiences) > 16:
            raise TaskError("memory_snapshot_invalid", "invalid experience references")

        selected_facts, selected_experiences = [], []
        seen_facts, seen_experiences = set(), set()
        used, count = 0, 0

        def add_experience(reference):
            nonlocal used, count
            if (type(reference) is not dict or set(reference) != {"view_id", "revision"}
                    or type(reference["view_id"]) is not str or type(reference["revision"]) is not int):
                return
            identity = (reference["view_id"], reference["revision"])
            if identity in seen_experiences or count >= policy.context_items:
                return
            try:
                value = require(self.memory.experiences.read(context, reference["view_id"],
                                                              expected_revision=reference["revision"]))
                size = len(encode(visible_experience(value)))
            except TaskError:
                unavailable.append("memory_experience_changed")
                return
            if size > policy.context_chars or used + size > policy.context_chars:
                return
            seen_experiences.add(identity)
            selected_experiences.append({"view_id": reference["view_id"], "revision": reference["revision"]})
            used, count = used + size, count + 1

        def add_fact(reference):
            nonlocal used, count
            if (type(reference) is not dict or set(reference) != {"atom_id", "revision"}
                    or type(reference["atom_id"]) is not str or type(reference["revision"]) is not int):
                return
            identity = (reference["atom_id"], reference["revision"])
            if identity in seen_facts or reference["atom_id"] in core_ids or count >= policy.context_items:
                return
            try:
                value = require(self.memory.writer.read(context, AtomRef(**reference)))
                size = len(encode(visible_fact(value)))
            except TaskError:
                unavailable.append("memory_fact_changed")
                return
            if used + size > policy.context_chars:
                return
            seen_facts.add(identity)
            selected_facts.append({"atom_id": reference["atom_id"], "revision": reference["revision"]})
            used, count = used + size, count + 1

        # Embedding results lead the shared topical budget. Lexical results fill
        # any remaining room when the index is still catching up.
        for item in semantic_experiences:
            add_experience({"view_id": item.get("view_id"), "revision": item.get("revision")})
        for item in semantic_facts:
            add_fact({"atom_id": item.get("atom_id"), "revision": item.get("revision")})
        for reference in lexical_experiences:
            add_experience(reference)
        for reference in lexical_facts:
            add_fact(reference)

        snapshot["references"] = core_refs + selected_facts
        snapshot["experience_references"] = selected_experiences
        snapshot["recall_pending"] = pending
        if unavailable:
            snapshot["recall_unavailable"] = unavailable[-1]
        changed = {**saved, "memory_context": snapshot}
        payload = encode(changed)
        with self.memory.runtime.transaction() as connection:
            updated = connection.execute(
                """UPDATE conversation_batches
                   SET contributions_json = ?, revision = revision + 1
                   WHERE batch_id = ? AND origin_key = ? AND state = 'sealed' AND revision = ?""",
                (payload, batch_id, context.key, row["revision"]),
            ).rowcount
            if not updated:
                raise TaskError("memory_context_changed", "memory context changed while semantic recall was prepared")
        return True

    def contributions(self, snapshot, context):
        if not isinstance(snapshot, dict) or snapshot.get("version") != 1 or snapshot.get("context_key") != context.key:
            raise TaskError("memory_snapshot_invalid", "memory context must retain its original identity")
        if snapshot.get("state") == "unavailable":
            return ()
        if snapshot.get("state") == DELEGATED_STATE:
            # 快照是让位期封的、但提问时判定已经反过来（或反过来）：以**提问时**的
            # 判定为准。让位就让位，不再注入；回到自己就按自己来——两边都以这里的
            # 一次判定为唯一口径，不留「半注入」的中间态。
            return () if self.delegated() else self._self_contributions(snapshot, context)
        return self._self_contributions(snapshot, context)

    def _self_contributions(self, snapshot, context):
        self.memory.writer.access.check(context)
        if not isinstance(snapshot.get("references"), list) or len(snapshot["references"]) > 64:
            raise TaskError("memory_snapshot_invalid", "invalid memory references")
        materials, seen = [], set()
        core_used = total_used = core_count = recall_used = recall_count = 0
        core_omitted, recall_truncated = snapshot.get("core_omitted", False), False
        core_ids = set(snapshot.get("core_ids", []))
        policy = self.memory.writer.access.policy_for(context)
        # Reserve room for core facts first, including ones written this turn.
        references = sorted(snapshot["references"], key=lambda ref: ref["atom_id"] not in core_ids)
        for reference in (ref for ref in references if ref["atom_id"] in core_ids):
            ref = AtomRef(**reference)
            if ref in seen:
                continue
            seen.add(ref)
            record = require(self.memory.writer.read(context, ref))
            payload = encode(visible_fact(record))
            size = len(payload)
            if record["atom_id"] in core_ids:
                if (core_count >= policy.core_items or core_used + size > policy.core_chars
                        or total_used + size > policy.inclusion_chars):
                    core_omitted = True
                    continue
                core_used += size
                core_count += 1
            else:
                continue
            total_used += size
            materials.append(ContextContribution("memory:" + record["atom_id"], "memory", "pinned_memory",
                ContributionState.READY, payload))
        experience_refs = snapshot.get("experience_references", [])
        if not isinstance(experience_refs, list) or len(experience_refs) > 16:
            raise TaskError("memory_snapshot_invalid", "invalid experience references")
        seen_experiences = set()
        for reference in experience_refs:
            if (type(reference) is not dict or set(reference) != {"view_id", "revision"}
                    or type(reference["view_id"]) is not str or type(reference["revision"]) is not int):
                raise TaskError("memory_snapshot_invalid", "experience requires an exact original revision")
            identity = (reference["view_id"], reference["revision"])
            if identity in seen_experiences:
                continue
            seen_experiences.add(identity)
            value = require(self.memory.experiences.read(context, reference["view_id"], expected_revision=reference["revision"]))
            payload = encode(visible_experience(value))
            size = len(payload)
            if (total_used + size > policy.inclusion_chars or recall_used + size > policy.context_chars
                    or recall_count >= policy.context_items):
                recall_truncated = True
                continue
            total_used += size
            recall_used += size
            recall_count += 1
            materials.append(ContextContribution("memory:experience:" + reference["view_id"], "memory", "current_experience",
                ContributionState.READY, payload))
        for reference in (ref for ref in references if ref["atom_id"] not in core_ids):
            ref = AtomRef(**reference)
            if ref in seen:
                continue
            seen.add(ref)
            record = require(self.memory.writer.read(context, ref))
            payload = encode(visible_fact(record))
            size = len(payload)
            if (total_used + size > policy.inclusion_chars or recall_used + size > policy.context_chars
                    or recall_count >= policy.context_items):
                recall_truncated = True
                continue
            total_used += size
            recall_used += size
            recall_count += 1
            materials.append(ContextContribution("memory:" + record["atom_id"], "memory", "current_memory",
                ContributionState.READY, payload))
        # One more bounded private material on the existing contribution channel:
        # repeated original utterances; the reply model interprets their meaning
        # against the current input rather than a keyword-derived question flag.
        habit = habit_contribution(self.memory, context)
        if habit is not None:
            materials.append(habit)
        if core_omitted:
            materials.append(ContextContribution("memory:core-budget", "memory", "memory_coverage",
                ContributionState.READY, "部分置顶记忆因上下文预算未注入；需要时查询，不把未展示当作没有。"))
        if recall_truncated:
            materials.append(ContextContribution("memory:recall-budget", "memory", "memory_coverage",
                ContributionState.READY, "话题记忆存在预算截断；需要时进一步查询，不把未展示当作没有。"))
        if snapshot.get("recall_pending"):
            materials.append(ContextContribution("memory:recall-pending", "memory", "memory_coverage",
                ContributionState.READY, "本次记忆召回尚未完成；需要具体往事时继续查询，不把暂未查到当作没有。"))
        if snapshot.get("recall_unavailable"):
            materials.append(ContextContribution("memory:recall-unavailable", "memory", "memory_coverage",
                ContributionState.READY, "本次记忆检索暂不可用，未完成往事查找；只依据当前可见材料回答，不把未返回当作没有或已经忘记。"))
        if snapshot["handles"]:
            materials.append(ContextContribution("memory:input-sources", "memory", "current_input_handles",
                ContributionState.READY, encode(snapshot["handles"])))
        return tuple(materials)

    def after_write(self, batch_id, context, receipt):
        """An acknowledged change in this turn replaces only its own dependency.

        Unrelated/external changes still fail the original snapshot. We never
        refresh a stale whole prompt and silently accept everything now in storage.
        """
        if not receipt.get("atom_id") or receipt["state"] != "persisted":
            return
        runtime = self.memory.runtime
        with runtime.transaction() as connection:
            row = connection.execute("SELECT contributions_json FROM conversation_batches WHERE batch_id = ?", (batch_id,)).fetchone()
            if row is None:
                return
            saved = json.loads(row["contributions_json"])
            snapshot = saved.get("memory_context")
            if not snapshot or snapshot["context_key"] != context.key or snapshot["state"] != "ready":
                return
            snapshot["references"] = [r for r in snapshot["references"] if r["atom_id"] != receipt["atom_id"]]
            snapshot["core_ids"] = [i for i in snapshot.get("core_ids", []) if i != receipt["atom_id"]]
            reference = AtomRef(receipt["atom_id"], receipt["revision"])
            current = self.memory.writer.read(context, reference)
            if current.is_success:
                snapshot["references"].append({"atom_id": reference.atom_id, "revision": reference.revision})
                if current.unwrap()["context_mode"] == "pinned":
                    snapshot["core_ids"].append(reference.atom_id)
            snapshot["mutations"].append({"atom_id": reference.atom_id, "operation_id": receipt["operation_id"]})
            connection.execute("UPDATE conversation_batches SET contributions_json = ? WHERE batch_id = ?", (encode(saved), batch_id))
