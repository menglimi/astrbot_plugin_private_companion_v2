"""Confirmed group replies and bounded iterative checks of their original evidence."""

from datetime import datetime
from contextlib import contextmanager
from contextvars import ContextVar
import json

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.configuration.models import ConfigurationError
from companion_v2.delivery.media import payload_hash
from companion_v2.sources.dependencies import key as source_key
from .foreground import ContributionState
from .reply_settings import validate as validate_reply_settings
from .style_context import ConversationExpressionStyleContext


MAX_ANCESTORS = 128
_READ_STEPS = ContextVar("group_history_read_steps", default=None)
_READ_CACHE = ContextVar("group_history_read_cache", default=None)


class GroupReplyHistory:
    def __init__(self, groups):
        self.groups, self.runtime = groups, groups.runtime

    def depends_on_memory(self, reference, identifiers):
        """Trace stored IDs only, to retire a turn's own superseded history.

        This grants no read access to bodies. Normal reads validate the entire
        original graph before a model may request a mutation.
        """
        pending, seen = [reference], set()
        while pending:
            ref = pending.pop()
            key = self.groups.reference_key(ref)
            if key in seen or ref["kind"] == "input":
                continue
            if len(seen) >= MAX_ANCESTORS:
                raise TaskError("group_history_budget", "group reply ancestry exceeds the bounded read budget")
            seen.add(key)
            part = self.runtime.read_one("SELECT batch_id FROM conversation_parts WHERE part_id = ?", (ref["part_id"],))
            if part is None:
                raise TaskError("group_reply_unavailable", "original history part is unavailable")
            saved = json.loads(self.groups.messages.batch(part["batch_id"])["contributions_json"])
            if any(item["memory_id"] in identifiers for item in saved.get("group_memory", {}).get("references", [])):
                return True
            for row in self.runtime.read_all("SELECT action, result_json FROM conversation_tool_calls WHERE batch_id = ? AND state = 'succeeded'", (part["batch_id"],)):
                if row["action"] in ("group.memory.query", "group.memory.remember"):
                    value = json.loads(row["result_json"])["payload"]
                    ids = [item["memory_id"] for item in value["items"]] if row["action"] == "group.memory.query" else [value["memory_id"]]
                    if identifiers.intersection(ids):
                        return True
            pending.extend(saved.get("group_context", {}).get("references", []))
        return False

    @contextmanager
    def _reading(self):
        """Share one bounded snapshot across nested history, quotes and images."""
        token = _READ_STEPS.set([0]) if _READ_STEPS.get() is None else None
        cache_token = _READ_CACHE.set({}) if _READ_CACHE.get() is None else None
        try:
            with self.runtime.read_snapshot():
                yield
        finally:
            if cache_token is not None:
                _READ_CACHE.reset(cache_token)
            if token is not None:
                _READ_STEPS.reset(token)

    def source_evidence(self, snapshot, context, batch_id, at):
        """Return hashes only after every source was read through its owner."""
        with self._reading():
            self.groups.read(snapshot, context, batch_id, at)
            batch = self.groups.messages.batch(batch_id)
            before, evidence = self.groups.cutoff(batch_id), []
            for reference in snapshot["references"]:
                self.read(reference, context, batch["role_instruction"], at, before, evidence=evidence)
            result = []
            # These originals were already authorized under their own members;
            # the consuming member never receives a raw source read privilege.
            for reference in sorted(set(evidence), key=source_key):
                require(self.groups.messages.sources.validate_reference(reference, observed_at=at))
                row = self.runtime.read_one("""SELECT content_hash, payload_json FROM sources
                    WHERE source_id = ? AND lineage_id = ? AND source_revision = ?""", source_key(reference))
                result.append({"source": reference, "content_hash": row["content_hash"],
                               "payload_hash": digest(json.loads(row["payload_json"]))})
            return tuple(result)

    def read(self, reference, context, role_instruction, at, before, *, evidence=None, images=None):
        with self._reading():
            self.groups.authorize(context, at)
            return self._read(reference, context, role_instruction, at, before,
                              evidence if evidence is not None else [], images)

    def _read(self, reference, context, role_instruction, at, before, evidence, images):
        groups = self.groups
        pending, seen, root = [(reference, before)], {}, None
        root_images, evidence_start, latest = (), len(evidence), 0
        cache, namespace = _READ_CACHE.get(), (self, context.role_binding, role_instruction, at)
        while pending:
            ref, cutoff = pending.pop()
            key = groups.reference_key(ref)
            # Every edge must point to an earlier batch/input, including cached nodes.
            if key in seen:
                prior, position = seen[key]
                if prior != ref or position >= cutoff:
                    raise TaskError("group_history_changed", "group history cannot change identity or include a future input")
                continue
            if len(seen) >= MAX_ANCESTORS:
                raise TaskError("group_history_budget", "group reply ancestry exceeds the bounded read budget")
            cached = cache.get((namespace, key))
            if cached is not None:
                prior, position, last_input, (item, source), sources, originals = cached
                if prior != ref or last_input >= cutoff:
                    raise TaskError("group_history_changed", "cached history must retain its identity and precede the consuming input")
                evidence.extend(sources)
                latest = max(latest, last_input)
            else:
                _READ_STEPS.get()[0] += 1
                if _READ_STEPS.get()[0] > MAX_ANCESTORS:
                    raise TaskError("group_history_budget", "group history and quote ancestry exceed the shared read budget")
                if ref["kind"] == "input":
                    start = len(evidence)
                    item, source = groups.read_input(ref, context, role_instruction, at, cutoff, evidence=evidence)
                    evidence.append(source)
                    position = self.runtime.read_one("SELECT rowid FROM conversation_inputs WHERE event_key = ?", (ref["event_key"],))[0]
                    originals = ()
                    cache[namespace, key] = dict(ref), position, position, (item, source), tuple(evidence[start:]), originals
                else:
                    item, position, dependencies, originals = self._reply(ref, context, role_instruction, at, cutoff, evidence)
                    source = None  # Prior Bot wording is history, not independent factual evidence.
                    pending.extend(dependencies)
            seen[key] = ref, position
            latest = max(latest, position)
            if root is None:
                root = item, source
                root_images = originals
        # A reply becomes reusable only once its complete ancestry succeeded.
        root_key = groups.reference_key(reference)
        cache[namespace, root_key] = (dict(reference), seen[root_key][1], latest, root,
                                      tuple(dict.fromkeys(evidence[evidence_start:])), root_images)
        if images is not None:
            images.extend(root_images)
        return root

    def _reply(self, reference, context, role_instruction, at, before, evidence):
        groups = self.groups
        row = self.runtime.read_one("""SELECT p.*, h.origin_key AS history_origin, h.receipt_ref AS history_receipt,
            h.delivered_at AS history_time, h.batch_id AS history_batch, r.receipt_json
            FROM conversation_parts p JOIN conversation_sent_history h ON h.part_id = p.part_id
            JOIN conversation_delivery_receipts r ON r.part_id = p.part_id AND r.receipt_ref = h.receipt_ref
            WHERE p.part_id = ?""", (reference["part_id"],))
        if (row is None or row["state"] != "delivered" or groups.reply_ref(row) != reference
                or row["history_time"] != row["delivered_at"] or row["history_receipt"] != row["receipt_ref"]
                or row["history_batch"] != row["batch_id"] or datetime.fromisoformat(row["delivered_at"]) > at):
            raise TaskError("group_reply_unproven", "group history requires the original confirmed reply")
        batch, original = groups.original(row["batch_id"], context, role_instruction, at)
        groups.messages.recalls.check_reply(original.scope, row["platform_ref"])
        first_input = groups.cutoff(row["batch_id"])
        if first_input >= before or row["history_origin"] != original.key or batch["state"] != "ready":
            raise TaskError("group_reply_unavailable", "reply must precede this batch and retain its original context")
        proof = json.loads(row["receipt_json"])
        expected = {"part_id": row["part_id"], "operation_id": row["operation_id"], "origin_key": original.key,
            "payload_hash": row["payload_hash"], "sender": json.loads(row["sender_json"]), "status": "delivered",
            "receipt_ref": row["receipt_ref"], "platform_ref": row["platform_ref"], "delivered_at": row["delivered_at"]}
        if any(proof.get(k) != v for k, v in expected.items()) or not row["platform_ref"]:
            raise TaskError("group_reply_unproven", "the original group delivery receipt changed")
        saved = json.loads(batch["contributions_json"])
        if (type(saved) is not dict
                or set(saved) - {"inputs", "materials", "group_context", "group_memory", "reply_settings",
                                 "expression_style", "person_card", "group_network"}
                or type(saved.get("inputs")) is not list or not 1 <= len(saved["inputs"]) <= 32
                or type(saved.get("materials")) is not list or len(saved["materials"]) > 32):
            raise TaskError("group_reply_profile", "group history has no reader for another profile's material")
        try:
            if "person_card" in saved:
                groups.messages.acquaintance.validate_snapshot(saved["person_card"], original)
            if "group_network" in saved:
                groups.messages.group_network.validate_snapshot(saved["group_network"], original)
        except TaskError as error:
            raise TaskError("group_reply_profile", "group reply metadata belongs to another conversation") from error
        if "expression_style" in saved:
            # Adopted expression rules change a reply's wording, not its facts,
            # so the snapshot only has to be well formed here. Re-resolving its
            # samples would let a retired rule delete an already delivered reply
            # from the group history.
            try:
                ConversationExpressionStyleContext.validate_snapshot(saved["expression_style"], original)
            except TaskError as error:
                raise TaskError("group_reply_profile", "group reply style profile is invalid") from error
        settings = saved.get("reply_settings")
        if settings is not None:
            if (type(settings) is not dict or set(settings) not in (
                    {"settings", "configuration_token"}, {"settings", "configuration_token", "streaming_explicit"})
                    or type(settings["configuration_token"]) is not str
                    or "streaming_explicit" in settings and type(settings["streaming_explicit"]) is not bool):
                raise TaskError("group_reply_profile", "group reply settings are unavailable")
            try:
                validate_reply_settings(settings["settings"])
            except ConfigurationError as exc:
                raise TaskError("group_reply_profile", "group reply settings are invalid") from exc
        if "group_memory" in saved:
            evidence.extend(m.source for m in groups.messages.group_memory.context.contributions(
                saved["group_memory"], original, row["batch_id"]) if m.source is not None)
        tools = groups.messages.tools
        for call in self.runtime.read_all("SELECT * FROM conversation_tool_calls WHERE batch_id = ? ORDER BY sequence", (row["batch_id"],)):
            if tools is None:
                raise TaskError("group_reply_profile", "group history has no reader for another profile's tool")
            # Re-read each original through its owner. Group image operations
            # keep the external child receipt, provider and source authority.
            _, materials = tools._validate_result(call, None, original, at)
            if materials is not None:
                materials = materials if isinstance(materials, tuple) else (materials,)
                evidence.extend(m.source for m in materials if m.source is not None)
        # Generated visuals also informed text-only replies. Their original
        # bytes and manifests remain dependencies even when no image was sent.
        groups.messages.generated_images.read_batch(batch, original, at, evidence=evidence)
        inputs = self.runtime.read_all("SELECT * FROM conversation_inputs WHERE batch_id = ? ORDER BY position", (row["batch_id"],))
        selected = [item for item in inputs if item["event_key"] in saved["inputs"]]
        if [item["event_key"] for item in selected] != saved["inputs"]:
            raise TaskError("group_input_unavailable", "original reply inputs were changed")
        from .messages import event_from_document
        events = tuple(event_from_document(json.loads(item["event_json"]), original) for item in selected)
        images, manifest = groups.messages.reply_images.for_part(row, batch, original, at, input_events=events)
        if payload_hash(row["text"], images) != row["payload_hash"]:
            raise TaskError("group_reply_unproven", "group reply text and ordered images differ from their receipt")
        if manifest is not None:
            evidence.append(manifest)
            evidence.extend(view.source for image in images for view in image.evidence_images)
        dependencies = [(groups.input_ref(item), before) for item in selected]
        # Non-history contributions, if explicitly supplied by a trusted producer,
        # must still be governed sources in this exact group audience.
        from .messages import source_from_document
        for material in saved["materials"]:
            if material["state"] == ContributionState.READY.value:
                record = groups.messages._read_source(source_from_document(material["source"]), original, "text", at)
                if record.audience != original.audience:
                    raise TaskError("group_input_audience", "reply material is outside its original group audience")
                evidence.append(record.reference)
        if "group_context" in saved:
            snapshot = saved["group_context"]
            groups.validate_snapshot(snapshot, original, row["batch_id"])
            dependencies.extend((ref, first_input) for ref in snapshot["references"])
        return {"type": "confirmed_group_reply", "part_id": row["part_id"], "role_id": original.role_binding.role.subject_id,
                "bot_id": original.scope.bot_id, "account_id": original.scope.account_id,
                "in_reply_to_speaker_id": original.actor.principal.native_account_id,
                "delivered_at": row["delivered_at"], "platform_ref": row["platform_ref"],
                "recipient_read": "unknown", "text": row["text"],
                **({"images": [{**item, "view": "historical_metadata_only"}
                               for item in groups.messages.reply_images.describe(images)]} if images else {})}, first_input, dependencies, images
