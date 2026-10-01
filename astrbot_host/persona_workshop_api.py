"""Dashboard routes for persona drafts and the role-profile source preview.

这个模块是「人格工坊」唯一面向 AstrBot 的部分，负责：

1. 用宿主当前解析到的人格**读**出原文和显示名（``NativePrivateBridge.persona_snapshot``），
   逐字透传给页面。**不返回 instruction_hash**——那是安全相关值，不进任何页面。
2. 把人格稿版本的追加/撤回交给 ``companion_v2.persona_craft``。
3. 按操作者点击，为角色档案生成一次可审阅草稿；草稿本身不写入配置。

**没有写人格的路径，这是设计而不是遗漏。** V2 把 AstrBot 人格当作宿主所有、只读：
写回人格会改变 ``instruction_hash``，但同一 Bot/人格/角色仍是原身份，
已固定的运行档继续沿用当前选中的人格提示词。V1 的问卷
曾经让用户填完之后难以再改，用户的原话是「填完问卷之后再想改就不好改了」。本页因此只到「给出
一份可编辑的草稿」为止：最后一步由操作者自己复制回 AstrBot。
"""

from __future__ import annotations

import asyncio
import json

from astrbot.api.web import request
from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.knowledge.catalog import KnowledgeCatalog
from companion_v2.knowledge.retrieval import KnowledgeCandidate, KnowledgeRetriever, query_for_context
from companion_v2.persona_craft import PersonaSnapshot, PersonaWorkshop
from companion_v2.role_profile.configuration import (FIELD_LIMITS as ROLE_PROFILE_FIELD_LIMITS,
    GROUP as ROLE_PROFILE_GROUP, RoleProfileConfigurationOwner,
    configuration_fields as role_profile_configuration_fields,
    target_for as role_profile_target_for)
from companion_v2.role_profile.drafts import (MAX_KNOWLEDGE_CHARS, MAX_KNOWLEDGE_ITEMS,
    MAX_SOURCE_CHARS, MAX_SUPPLEMENT_CHARS, build_role_profile_prompt,
    normalize_knowledge_references, parse_role_profile_draft)
from companion_v2.relationships.profile import (FIELD_LIMITS as RELATIONSHIP_PROFILE_FIELD_LIMITS,
    GROUP as RELATIONSHIP_PROFILE_GROUP, TOTAL_CHAR_LIMIT as RELATIONSHIP_PROFILE_TOTAL_CHAR_LIMIT,
    RelationshipProfileConfigurationOwner,
    configuration_fields as relationship_profile_configuration_fields,
    target_for as relationship_profile_target_for)
from companion_v2.relationships.profile_drafts import (build_relationship_profile_prompt,
    parse_relationship_profile_draft)

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion_v2/persona"

# 与页面目录同一道门：能管理本安装的账号。人格原文属于安装级配置视图，
# 不该因为某个会话窗口被分享给普通对象。
MANAGEMENT_ACTION = "memory.manage"


def management_scope(installation_id):
    return ScopeRef(installation_id, "companion", ScopeKind.SYSTEM, "page.management")


def current_role_profile(runtime, session):
    target = role_profile_target_for(session.profile.target)
    snapshot = RoleProfileConfigurationOwner(runtime).read(target, role_profile_configuration_fields())
    return {name: snapshot.fields[f"{ROLE_PROFILE_GROUP}.{name}"].value
            for name in ROLE_PROFILE_FIELD_LIMITS}


def current_relationship_profile(runtime, session):
    target = relationship_profile_target_for(session.profile.target)
    snapshot = RelationshipProfileConfigurationOwner(runtime).read(
        target, relationship_profile_configuration_fields())
    return {
        "revision": snapshot.revision,
        "fields": {name: snapshot.fields[f"{RELATIONSHIP_PROFILE_GROUP}.{name}"].value
                   for name in RELATIONSHIP_PROFILE_FIELD_LIMITS},
    }


def role_profile_world_knowledge(runtime, session, *, persona_id, persona_text, supplement):
    """Select bounded, imported, role-wide lore without user or window material."""
    target = session.profile.target
    role_id = target.role_binding.role.subject_id
    accepted_roles = {role_id, persona_id} - {None, ""}
    candidates = []
    labels = {}
    source_chars = 0
    catalog = KnowledgeCatalog(runtime)
    for version in catalog.active(runtime.installation_id, limit=16):
        binding = version.binding
        if binding.native_scope_ids or binding.scope_kind is not None:
            continue
        source_roles = {binding.role_id, binding.persona_id} - {None, ""}
        if source_roles and not source_roles.intersection(accepted_roles):
            continue
        for entry in version.entries:
            if not entry.enabled or entry.native_scope_ids or not entry.content.strip():
                continue
            if source_chars + len(entry.content) > 60000:
                break
            identifier = f"role-profile-{len(candidates)}:{entry.entry_id}"[:256]
            candidate = KnowledgeCandidate(
                identifier, entry.content, role_id=binding.role_id, persona_id=binding.persona_id,
                priority=entry.priority, name=entry.name, keywords=entry.keywords,
                aliases=entry.aliases, knowledge_base_id=entry.knowledge_base_id,
                document_id=entry.document_id, document_name=entry.document_name,
                chunk_index=entry.chunk_index,
            )
            candidates.append(candidate)
            labels[identifier] = {
                "title": entry.document_name or entry.name or entry.entry_id,
                "source": "AstrBot 知识库" if entry.knowledge_base_id else "AstrBot 世界书",
                "text": entry.content,
            }
            source_chars += len(entry.content)

    if not candidates:
        return []
    query = query_for_context(
        "角色身份 外貌 性格 口吻 习惯 价值观 目标 世界观 时代 法则 能力 地点 组织 "
        + str(persona_text or "")[:9000] + "\n" + str(supplement or "")[:MAX_SUPPLEMENT_CHARS],
        scope=target.scope, role_id=role_id, persona_id=persona_id,
        max_hits=MAX_KNOWLEDGE_ITEMS, max_chars=MAX_KNOWLEDGE_CHARS, max_per_document=3,
    )
    selected = KnowledgeRetriever(candidates).select(query)
    return normalize_knowledge_references([labels[hit.candidate.candidate_id] for hit in selected.hits])

# 一条命令只带这几项，多一项都判无效——版本记录是不可变的，字段错了不能"部分保存"。
COMMANDS = {"save": {"text", "note", "expected_current"},
            "restore": {"version_id", "note", "expected_current"}}


class PersonaWorkshopWebAPI:
    """One route family per role: read the host persona, append draft versions."""

    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.status, ["GET"], "Read the host persona and its draft history"),
                (PREFIX + "/command", self.command, ["POST"],
                 "Append a persona draft version, or restore an earlier one"),
                (PREFIX + "/profile-draft", self.profile_draft, ["POST"],
                 "Generate a reviewable role-profile draft from the current host persona")]

    @staticmethod
    def _document(raw):
        """Decode one command body without letting a duplicate or NaN field through."""
        def unique(pairs):
            values = {}
            for key, value in pairs:
                if key in values:
                    raise ValueError("duplicate field")
                values[key] = value
            return values

        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite value")))
        if type(data) is not dict:
            raise ValueError("provide one command object")
        return data

    def _authorized(self, controller):
        """Resolve the Dashboard operator and require installation management."""
        if controller._terminated:
            raise TaskError("staging_host_terminated", "the plugin has stopped")
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
        session = controller.session or controller.last_session
        if session is None or controller.runtime is None:
            raise TaskError("staging_not_initialized", "load an initialized V2 profile first")
        operator = dashboard_operator(controller.runtime, username, at=controller.now())
        require(ObjectAccessPolicy(controller.runtime).feature_access(
            operator, scope=management_scope(controller.runtime.installation_id),
            action=MANAGEMENT_ACTION, observed_at=controller.now()))
        return session, operator

    @staticmethod
    def _bridge(controller, session):
        """The native bridge that can resolve a persona for this session's target.

        Multi-target views project one role on a shared session, so the bridge sits
        on the controller's own session there; both cases are read-only.
"""
        bridge = getattr(session, "bridge", None)
        if bridge is None:
            owner = getattr(controller, "controller", controller)
            bridge = getattr(owner.session or owner.last_session, "bridge", None)
        if not callable(getattr(bridge, "persona_snapshot", None)):
            raise TaskError("host_persona_unavailable", "this host assembly cannot resolve a persona for the page")
        return bridge

    async def _read_persona(self, controller, session) -> PersonaSnapshot:
        context = session.profile.target
        if context.scope.kind is not ScopeKind.PRIVATE:
            raise TaskError("persona_workshop_scope_unsupported", "the workshop edits a private conversation's persona")
        projection = await self._bridge(controller, session).persona_snapshot(context.scope)
        return PersonaSnapshot(projection["persona_id"], projection["name"], projection["text"],
                               projection["resolved"])

    def _workshop(self, controller, session, snapshot) -> PersonaWorkshop:
        # ``controller.now`` is the clock itself, not a timestamp: the version time
        # must be read when the version is written, not when the request arrives.
        return PersonaWorkshop(controller.runtime, installation_id=controller.runtime.installation_id,
                               role_id=session.profile.target.role_binding.role.subject_id, now=controller.now)

    async def status(self):
        from .web_api import outcome_response
        try:
            query = request.query
            if set(query.keys()) - {"limit"} or any(len(query.getlist(key)) != 1 for key in query.keys()):
                raise ValueError("unexpected query fields")
            limit = int(query.get("limit", "30"))
            async with self.controller._control_lock:
                controller = self.controller
                session, _ = self._authorized(controller)
                snapshot = await self._read_persona(controller, session)
                state = self._workshop(controller, session, snapshot).state(snapshot, limit=limit)
                return outcome_response(Outcome.success(state))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, OverflowError):
            return outcome_response(Outcome.failed("persona_workshop_request_invalid",
                                                   "invalid persona workshop request"))

    async def command(self):
        from .web_api import outcome_response
        try:
            if request.query:
                raise ValueError("commands do not accept query fields")
            raw = await request.body()
            if len(raw) > 262144:
                raise ValueError("body too large")
            data = self._document(raw)
            action = data.get("action")
            if action not in COMMANDS or set(data) != {"action"} | COMMANDS[action]:
                raise ValueError("provide exactly the fields this command needs")
            async with self.controller._control_lock:
                controller = self.controller
                session, _ = self._authorized(controller)
                snapshot = await self._read_persona(controller, session)
                workshop = self._workshop(controller, session, snapshot)
                if action == "save":
                    result = workshop.save(snapshot, text=data["text"], note=data["note"],
                                           expected_current=data["expected_current"])
                else:
                    result = workshop.restore(snapshot, version_id=data["version_id"], note=data["note"],
                                              expected_current=data["expected_current"])
                return outcome_response(Outcome.success(result))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return outcome_response(Outcome.failed("persona_workshop_request_invalid",
                                                   "invalid UTF-8 persona workshop command"))

    async def profile_draft(self):
        """Generate a role-owned or current-relationship draft without saving it."""
        from .web_api import outcome_response
        try:
            if request.query:
                raise ValueError("draft generation does not accept query fields")
            raw = await request.body()
            if len(raw) > 16384:
                raise ValueError("supplement too large")
            data = self._document(raw)
            if (set(data) not in ({"supplement"}, {"target", "supplement"})
                    or type(data["supplement"]) is not str):
                raise ValueError("provide a supplement and an optional draft target")
            draft_target = data.get("target", "role_profile")
            if draft_target not in {"role_profile", "relationship_profile"}:
                raise ValueError("unknown draft target")
            supplement = data["supplement"]
            if len(supplement) > MAX_SUPPLEMENT_CHARS:
                raise ValueError("supplement too large")

            async with self.controller._control_lock:
                controller = self.controller
                session, _ = self._authorized(controller)
                snapshot = await self._read_persona(controller, session)
                if not snapshot.resolved or not snapshot.text.strip():
                    raise TaskError("role_profile_source_unavailable", "no current AstrBot persona text is available")
                if len(snapshot.text) > MAX_SOURCE_CHARS:
                    raise TaskError("role_profile_source_too_large", "the current persona text is too large to draft safely")
                role_id = session.profile.target.role_binding.role.subject_id
                context_key = session.profile.target.key
                application = session.application
                owner = getattr(controller, "controller", controller)
                model_session = owner.session or owner.last_session
                model = getattr(model_session, "model", None)
                provider = getattr(model, "native", None)
                provider_id = getattr(model, "provider_id", "")
                if (model is None or provider is None or provider_id != model_session.profile.provider_id
                        or not callable(getattr(provider, "text_chat", None))):
                    raise TaskError("role_profile_model_unavailable", "the selected model cannot create a profile draft")
                model._current()
                try:
                    if draft_target == "role_profile":
                        existing_profile = current_role_profile(controller.runtime, session)
                        knowledge = role_profile_world_knowledge(
                            controller.runtime, session, persona_id=snapshot.persona_id,
                            persona_text=snapshot.text, supplement=supplement)
                        prompt = build_role_profile_prompt(snapshot.text, supplement,
                                                          current_profile=existing_profile,
                                                          knowledge_references=knowledge)
                        limits = ROLE_PROFILE_FIELD_LIMITS
                        total_limit = 30000
                    else:
                        existing_profile = current_relationship_profile(controller.runtime, session)
                        knowledge = []
                        prompt = build_relationship_profile_prompt(
                            snapshot.text, supplement, current_profile=existing_profile["fields"])
                        limits = RELATIONSHIP_PROFILE_FIELD_LIMITS
                        total_limit = RELATIONSHIP_PROFILE_TOTAL_CHAR_LIMIT
                except Exception as error:
                    raise TaskError("role_profile_context_unavailable",
                                    "the current role or relationship profile sources could not be read") from error

            try:
                response = await asyncio.wait_for(provider.text_chat(prompt=prompt, max_tokens=6800), timeout=90)
            except asyncio.TimeoutError as error:
                raise TaskError("role_profile_draft_timeout", "the profile draft request timed out") from error
            raw_text = getattr(response, "completion_text", response)
            parsed = (parse_role_profile_draft(
                raw_text, world_adaptation_mode=existing_profile.get("world_adaptation_mode", "auto"))
                if draft_target == "role_profile" else parse_relationship_profile_draft(raw_text))

            async with self.controller._control_lock:
                controller = self.controller
                current, _ = self._authorized(controller)
                current_role = current.profile.target.role_binding.role.subject_id
                if current.profile.target.key != context_key:
                    raise TaskError("role_profile_source_changed",
                                    "the selected person, role or conversation changed while drafting")
                current_owner = getattr(controller, "controller", controller)
                current_session = current_owner.session or current_owner.last_session
                current_model = getattr(current_session, "model", None)
                if (current.application is not application or current_role != role_id
                        or current_model is None or current_model.native is not provider):
                    raise TaskError("role_profile_source_changed", "the current role or model changed while drafting")
                current_model._current()
                latest = await self._read_persona(controller, current)
                if latest != snapshot:
                    raise TaskError("role_profile_source_changed", "the source persona changed while drafting")
                try:
                    if draft_target == "role_profile":
                        latest_profile = current_role_profile(controller.runtime, current)
                        latest_knowledge = role_profile_world_knowledge(
                            controller.runtime, current, persona_id=snapshot.persona_id,
                            persona_text=snapshot.text, supplement=supplement)
                    else:
                        latest_profile = current_relationship_profile(controller.runtime, current)
                        latest_knowledge = []
                except Exception as error:
                    raise TaskError("role_profile_context_unavailable",
                                    "the current role or relationship profile sources could not be read") from error
                if latest_profile != existing_profile:
                    raise TaskError("role_profile_source_changed", "the current profile changed while drafting")
                if latest_knowledge != knowledge:
                    raise TaskError("role_profile_source_changed", "world knowledge changed while drafting")

            return outcome_response(Outcome.success({
                "draft": parsed,
                "source": {"persona_id": snapshot.persona_id, "name": snapshot.name,
                           "source_chars": len(snapshot.text),
                           "source_preview": " ".join(snapshot.text.split())[:240]},
                "knowledge": knowledge,
                "limits": limits,
                "target": draft_target,
                "total_limit": total_limit,
            }))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return outcome_response(Outcome.failed("role_profile_draft_invalid", "the profile draft response was invalid"))
        except Exception:
            return outcome_response(Outcome.failed("role_profile_draft_failed", "the profile could not be drafted; check the selected model and try again"))
