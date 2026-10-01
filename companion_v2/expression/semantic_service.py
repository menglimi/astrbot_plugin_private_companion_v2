"""Composition of shared semantic ports with memory, vocabulary and reactions."""

import asyncio
from dataclasses import replace
import json
import logging
import time

from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import ScopeKind
from companion_v2.model_gateway.embedding import EmbeddingGateway
from companion_v2.model_gateway.semantic_search import CatalogSearch
from companion_v2.model_gateway.models import ToolSpec
from companion_v2.storage.semantic import SemanticStore
from companion_v2.memory.semantic import MemorySemanticRecall
from companion_v2.memory.group.slang import GroupSlang, INSTRUCTION as SLANG_INSTRUCTION
from .reaction_configuration import read_settings as read_reaction_settings
from .reaction_configuration import read_snapshot as read_reaction_configuration
from .reactions import ReactionLibrary, INSTRUCTION
from .reaction_preferences import ReactionPreferences
logger = logging.getLogger(__name__)


FIELDS = {"reaction.search": (("intent",), ()), "slang.search": (("query",), ()),
          "slang.learn": (("term", "meaning", "input_handle"), ("usage", "correction"))}
# Reaction vector backfill shares the one background registry with memory, under
# a namespaced key so ``prepare_memory`` still finds the memory job by owner.
REACTION_BACKFILL_KEY = "reaction-backfill:"


class SemanticService:
    actions = frozenset(FIELDS)

    def __init__(self, app, port):
        self.app = app
        self.store = SemanticStore(app.runtime.data_root)
        self.gateway = EmbeddingGateway(port, timeout=self.store.settings()["timeout_seconds"])
        self.memory = MemorySemanticRecall(app.memory, self.gateway, self.store.settings)
        self.slang = GroupSlang(self)
        self.reactions = ReactionLibrary(self)
        self.reaction_preferences = ReactionPreferences(self)
        self.search = CatalogSearch(self.store, self.gateway, self.validate_item)
        self.locks, self.background, self.errors = {}, {}, {}
        self.backfill_runs = {}
        self.prepared = set()
        self.closed = False
        descriptions = {"reaction.search": "按角色想怎样回应检索表情原图，可提供安慰、吐槽等用途及否定语境；找不到可不发。",
                        "slang.search": "按当前原句查询本群梗与词义，结果仅作有证据的语义参考。",
                        "slang.learn": "根据本轮原始群发言学习词义；明确纠正时设 correction=true。"}
        self.catalog = tuple(ToolSpec(action, descriptions[action], encode({"type": "object",
            "properties": {k: {"type": "boolean" if k == "correction" else "string"} for k in (*required, *optional)},
            "required": list(required), "additionalProperties": False})) for action,(required,optional) in FIELDS.items())

    @staticmethod
    def owner(context):
        s = context.scope
        return digest(["semantic-owner.v1", s.installation_id, s.platform, s.bot_id, s.account_id,
                       s.kind, s.native_scope_id, s.session_id if s.kind is ScopeKind.GROUP else "", context.role_binding.role])

    def check(self, context, *, action="conversation.reply"):
        if self.closed:
            raise TaskError("semantic_stopped", "semantic service is stopped")
        require(self.app.tasks.authorize_context(context, action=action, observed_at=self.app.now()))

    @staticmethod
    def reaction_enabled(context, cfg):
        scope_setting = "reactions_group_enabled" if context.scope.kind is ScopeKind.GROUP else "reactions_private_enabled"
        return cfg["reactions_enabled"] and cfg[scope_setting]

    def reaction_available(self, context, batch_id, cfg=None):
        cfg = cfg or self.store.settings()
        return (cfg["enabled"] and not self.closed and self.reaction_enabled(context, cfg)
                and self.app.messages.reply_images.enabled
                and self.reaction_preferences.available(context, batch_id, cfg))

    def proactive_reaction_available(self, context, contact_id):
        cfg = self.store.settings()
        if not cfg["reactions_proactive_enabled"] or not self.reaction_available(context, contact_id, cfg):
            return False
        self.check(context, action="proactive.contact")
        return True

    def validate_item(self, item, context, *, action="conversation.reply"):
        cfg = self.store.settings()
        if not cfg["enabled"] or not cfg["slang_enabled" if item["kind"] == "slang" else "reactions_enabled"]:
            return False
        if context is not None:
            self.check(context, action=action)
            if item["owner"] != self.owner(context):
                return False
            if item["kind"] == "reaction" and not self.reaction_enabled(context, cfg):
                return False
        current = self.store.get(item["owner"], item["kind"], item["id"])
        if not current["enabled"] or current["revision"] != item["revision"]:
            return False
        return self.slang.validate(item, context) if item["kind"] == "slang" else True

    def catalog_for(self, context, batch_id=None):
        cfg = self.store.settings()
        if not cfg["enabled"] or self.closed:
            return ()
        self.check(context)
        available = []
        for tool in self.catalog:
            if tool.action == "reaction.search":
                if self.reaction_available(context, batch_id, cfg):
                    available.append(tool)
            elif cfg["slang_enabled"] and context.scope.kind is ScopeKind.GROUP:
                try:
                    self.slang.memory.access.check(context, "group.memory.write" if tool.action == "slang.learn" else "group.memory.read")
                    available.append(tool)
                except TaskError:
                    pass
        return tuple(available)

    def validate_arguments(self, action, args):
        required, optional = FIELDS[action]
        if type(args) is not dict or set(required) - set(args) or set(args) - set(required) - set(optional):
            raise ValueError("invalid semantic tool arguments")
        if any(type(v) is not (bool if k == "correction" else str) or isinstance(v, str) and len(v) > 2000 for k,v in args.items()):
            raise ValueError("invalid semantic argument value")

    async def execute(self, run, call):
        context, batch_id = run.task.spec.context, run.task.spec.request_ref
        if call.action not in {t.action for t in self.catalog_for(context, batch_id)}:
            raise TaskError("semantic_action_unavailable", "semantic action is disabled or unauthorized")
        args = json.loads(call.arguments_json)
        self.validate_arguments(call.action, args)
        if call.action == "reaction.search":
            payload = await self.reactions.search(context, batch_id, call.call_id, args["intent"])
        elif call.action == "slang.search":
            payload = {"kind": "slang", **await self.search.search(self.owner(context), "slang", args["query"], context=context)}
            self.store.offer(batch_id, call.call_id, self.owner(context), payload)
        else:
            item = self.slang.learn(context, batch_id, **args)
            payload = {"kind": "slang", "items": [{k: item[k] for k in ("id", "revision", "payload")}]}
            self.store.offer(batch_id, call.call_id, self.owner(context), payload)
        run.validate()
        return {"state": "succeeded", "effect": "committed" if call.action == "slang.learn" else "none", "payload": payload}

    def validate(self, row, context, result):
        self.check(context)
        if row["state"] != "succeeded":
            return result, None
        saved = dict(self.store.offers(row["batch_id"], self.owner(context))).get(row["tool_call_id"])
        if saved != result.get("payload"):
            raise TaskError("semantic_result_changed", "original semantic result is unavailable")
        kind = saved["kind"]
        changed = self.changed_slang(row["batch_id"])
        for offered in saved.get("items", []):
            item = self.store.get(self.owner(context), kind, offered["id"])
            if kind == "slang" and item["revision"] != offered["revision"] and offered["id"] in changed:
                if not self.validate_item(item, context):
                    raise TaskError("semantic_result_changed", "updated vocabulary evidence is unavailable")
                return {"state": "superseded", "effect": result["effect"], "reason": "changed_by_this_turn"}, None
            if item["revision"] != offered["revision"] or not self.validate_item(item, context):
                raise TaskError("semantic_result_changed", "original semantic evidence changed")
        return result, None

    def changed_slang(self, batch_id):
        rows = self.app.runtime.read_all("SELECT result_json FROM conversation_tool_calls WHERE batch_id=? AND action='slang.learn' AND state='succeeded'", (batch_id,))
        return {item["id"] for row in rows for item in json.loads(row["result_json"])["payload"]["items"]}

    async def prepare_turn(self, run):
        cfg = self.store.settings()
        if not cfg["enabled"] or run.task.task_id in self.prepared:
            return
        self.prepared.add(run.task.task_id)
        context = run.task.spec.context
        self.check(context)
        self.gateway.timeout = cfg["timeout_seconds"]
        self.reaction_preferences.prepare(context, run.task.spec.request_ref)
        # Learning runs before opening the model session, so its material is stable.
        if context.scope.kind is ScopeKind.GROUP and cfg["slang_enabled"]:
            try:
                async with self.locks.setdefault(self.owner(context), asyncio.Lock()):
                    try:
                        await self.slang.observe(context, run.task.spec.request_ref)
                        self.errors.pop("slang_learning", None)
                    except Exception as exc:
                        self.errors["slang_learning"] = getattr(exc, "code", type(exc).__name__)
                    rows = self.app.runtime.read_all("SELECT event_json FROM conversation_inputs WHERE batch_id=? AND withdrawn=0 ORDER BY position",
                        (run.task.spec.request_ref,))
                    from companion_v2.conversation.messages import source_from_document
                    texts = [self.app.messages._read_source(source_from_document(json.loads(r["event_json"])["source"]),
                        context, "text", self.app.now()).payload for r in rows]
                    result = await self.search.search(self.owner(context), "slang", "\n".join(texts)[:2000], context=context, limit=2)
                    self.store.offer(run.task.spec.request_ref, "__slang_context", self.owner(context), {"kind": "slang", **result})
            except Exception as exc:
                self.errors["slang_recall"] = getattr(exc, "code", type(exc).__name__)
        else:
            # Private memory is sealed before generation starts.  Prepare the
            # current wording while the owner lock is held, then merge only
            # exact revisions into that sealed snapshot.  A model outage must
            # leave the lexical snapshot usable and must never block a reply.
            if cfg["memory_enabled"]:
                key = self.owner(context)
                try:
                    async with self.locks.setdefault(key, asyncio.Lock()):
                        rows = self.app.runtime.read_all(
                            "SELECT event_json FROM conversation_inputs "
                            "WHERE batch_id=? AND withdrawn=0 ORDER BY position",
                            (run.task.spec.request_ref,),
                        )
                        from companion_v2.conversation.messages import source_from_document
                        texts = []
                        for row in rows:
                            event = json.loads(row["event_json"])
                            source = source_from_document(event["source"])
                            try:
                                record = self.app.messages._read_source(
                                    source, context, "text", self.app.now()
                                )
                            except Exception as error:
                                logger.warning("V2 semantic batch source read failed: %s", type(error).__name__)
                                continue
                            if isinstance(record.payload, str) and record.payload.strip():
                                texts.append(record.payload)
                        intent = "\n".join(texts)[-2000:]
                        if intent:
                            prepared = []
                            for kind in ("experiences", "facts"):
                                try:
                                    result = await self.memory.prepare(
                                        context, {"query_intent": intent, "kind": kind}
                                    )
                                except Exception as exc:
                                    self.errors["memory_recall"] = getattr(exc, "code", type(exc).__name__)
                                    result = {}
                                if result.get("vector") and result.get("model"):
                                    prepared.append(result)
                            if prepared:
                                try:
                                    self.app.memory.context.enrich_semantic(
                                        context,
                                        run.task.spec.request_ref,
                                        intent,
                                        prepared[0]["vector"],
                                        prepared[0]["model"],
                                    )
                                    self.errors.pop("memory_recall", None)
                                except Exception as exc:
                                    self.errors["memory_recall"] = getattr(exc, "code", type(exc).__name__)
                except Exception as exc:
                    # Source expiry, indexing, and provider failures are
                    # optional enrichment; the sealed lexical context remains
                    # authoritative for this turn.
                    self.errors["memory_recall"] = getattr(exc, "code", type(exc).__name__)
            self.schedule_memory(context)
        if len(self.prepared) > 1024:
            self.prepared = {run.task.task_id}

    def schedule_memory(self, context):
        cfg = self.store.settings()
        if self.closed or not cfg["enabled"] or not cfg["memory_enabled"] or context.scope.kind is ScopeKind.GROUP:
            return
        key = self.owner(context)
        if key in self.background:
            return
        async def fill():
            try:
                async with self.locks.setdefault(key, asyncio.Lock()):
                    for kind in ("facts", "sources", "experiences", "all"):
                        await self.memory.backfill(context, kind)
            except Exception as exc:
                self.errors["memory_backfill"] = getattr(exc, "code", type(exc).__name__)
            finally:
                self.background.pop(key, None)
        self.background[key] = asyncio.create_task(fill(), name="v2-semantic-backfill")

    def reaction_settings(self, context):
        """Window-scoped reaction bounds and their revision; never blocks a turn."""
        return read_reaction_configuration(self.app.runtime, context)

    def schedule_reaction_backfill(self, context, settings=None):
        """Fill a bounded batch of reaction vectors for one owner, off the reply path.

        V1 did this from its lifecycle background tasks with an enable switch, a
        batch size, a per-provider minimum interval and an in-flight set
        (``llm_tool_actions.py:5789-5837``).  The same shape is reused here with
        the one background registry memory already uses: one task per owner, so two
        runs cannot write the same vectors at once, cancelled on reconfigure and
        on shutdown.  The retrieval path only pays a dictionary lookup when the
        interval has not elapsed.
        """
        cfg = self.store.settings()
        if settings is None:
            settings = read_reaction_settings(self.app.runtime, context)
        if self.closed or not cfg["enabled"] or not settings.embedding_backfill_enabled:
            return
        owner = self.owner(context)
        key = REACTION_BACKFILL_KEY + owner
        if key in self.background:
            return
        now = time.monotonic()
        interval = settings.embedding_backfill_interval_seconds
        if interval and now - self.backfill_runs.get(key, 0.0) < interval:
            return
        self.backfill_runs[key] = now
        limit = settings.embedding_backfill_batch_size

        async def fill():
            try:
                async with self.locks.setdefault(owner, asyncio.Lock()):
                    await self.search.backfill(owner, "reaction", limit=limit,
                                               validate=lambda item: self.validate_item(item, None))
                self.errors.pop("reaction_backfill", None)
            except Exception as exc:
                self.errors["reaction_backfill"] = getattr(exc, "code", type(exc).__name__)
            finally:
                self.background.pop(key, None)

        self.background[key] = asyncio.create_task(fill(), name="v2-reaction-backfill")

    async def prepare_memory(self, context, args):
        pending = self.background.get(self.owner(context))
        if pending:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        async with self.locks.setdefault(self.owner(context), asyncio.Lock()):
            return await self.memory.prepare(context, args)

    def augment(self, batch, context, request):
        request = self.reactions.augment(batch, context, request)
        if context.scope.kind is ScopeKind.GROUP:
            from companion_v2.conversation.foreground import PromptMaterial
            payload = dict(self.store.offers(batch["batch_id"], self.owner(context))).get("__slang_context")
            if payload and payload["items"]:
                changed = self.changed_slang(batch["batch_id"])
                current_items = []
                for item in payload["items"]:
                    if item["id"] in changed:
                        continue
                    current = self.store.get(self.owner(context), "slang", item["id"])
                    if current["revision"] != item["revision"] or not self.validate_item(current, context):
                        raise TaskError("slang_context_changed", "group vocabulary evidence changed during this reply")
                    current_items.append(item)
                if current_items:
                    request = replace(request, context=replace(request.context, materials=request.context.materials + (
                        PromptMaterial("group.slang", "contextual_word_meanings", encode({**payload, "items": current_items})),)))
            request = replace(request, instruction=request.instruction + "\n" + SLANG_INSTRUCTION)
        return request

    @property
    def active_handles(self):
        return tuple("semantic:" + k for k,t in self.background.items() if not t.done())

    async def close(self):
        self.closed = True
        tasks = tuple(self.background.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.reactions.clear_lookups()
        self.gateway.clear()

    async def configure(self, changes, revision):
        result = self.store.configure(changes, revision)
        tasks = tuple(self.background.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.gateway.clear()
        self.gateway.timeout = result["timeout_seconds"]
        self.memory.continuations.clear()
        # A settings change changes the lookup identity; drop both the cached
        # results and the backfill throttle so the new interval applies at once.
        self.reactions.clear_lookups()
        self.backfill_runs.clear()
        return result

    def status(self):
        cfg = self.store.settings()
        try:
            binding = self.gateway.port.binding(cfg["embedding_provider"], "embedding")
            state = "ready" if cfg["enabled"] else "disabled"
        except Exception:
            binding, state = None, "lexical_fallback" if cfg["enabled"] else "disabled"
        return {"state": state, "settings": cfg, "model_binding": binding,
                "metrics": dict(self.gateway.metrics), "errors": dict(self.errors),
                "background_jobs": len(self.active_handles), "providers": self.gateway.port.inventory()}
