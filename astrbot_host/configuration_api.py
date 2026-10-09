"""Dashboard-only editors for the configuration groups the cottage edits itself.

Groups that already had owners and consumers but no read-write route get one
here. Each section keeps its own edit token because the scopes differ: the daily
allowance is an installation/role ceiling while review, reaction retrieval,
retracted-text reading, screen material, acquaintance cards and role growth are
per-conversation window settings, and the shelf, wardrobe and reference material
are role settings a single window must not narrow. Contact preferences are the
first group with a relationship layer in the middle of the chain, so it publishes
four layers; its two relationship-wide allowances stay unwritable at window layer
and say so through the field contract.
"""

import json

from astrbot.api.web import request
from companion_v2.configuration.management import (AcquaintanceManagement, BusyGateManagement,
                                                   ContentAuthoringManagement,
                                                   DiaryAndRestManagement, GroupParticipationManagement,
                                                   ImageQuotaManagement,
                                                   ImageOutputManagement,
                                                   ImageReviewManagement, KnowledgeManagement,
                                                   LibraryManagement,
                                                   ModelBudgetManagement, ProactiveContactManagement,
                                                   PrivateAccessManagement,
                                                   ReactionRetrievalManagement,
                                                   RecallManagement, ReferenceManagement,
                                                   RoleGrowthManagement, RoleGrowthSkillsManagement,
                                                   RoleProfileManagement,
                                                   RelationshipProfileManagement,
                                                   QzoneManagement,
                                                   ScreenManagement, WardrobeManagement)
from companion_v2.configuration.models import ConfigurationError
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.knowledge.configuration import KnowledgeSettings

from .knowledge_sources import AstrBotKnowledgeSources

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion_v2/config"
SECTIONS = {"quota": ImageQuotaManagement, "image_review": ImageReviewManagement,
            "image.output": ImageOutputManagement,
            "busy_gate": BusyGateManagement,
            "content.authoring": ContentAuthoringManagement,
            "reaction": ReactionRetrievalManagement, "budget": ModelBudgetManagement,
            "recall": RecallManagement, "screen": ScreenManagement,
            # QQ 空间拓展的角色级开关与节流；安装与逐会话同意不在这里，归能力安装路由。
            "qzone": QzoneManagement,
            "person": AcquaintanceManagement, "role_growth": RoleGrowthManagement,
            # 私聊用户权限的默认值与拒绝文案（层只有安装与角色：默认值不跟窗口走）。
            "private_access": PrivateAccessManagement,
            "role.growth.skills": RoleGrowthSkillsManagement,
            "knowledge": KnowledgeManagement, "life": DiaryAndRestManagement,
            "role_profile": RoleProfileManagement,
            "relationship_profile": RelationshipProfileManagement,
            "library": LibraryManagement,
            "wardrobe": WardrobeManagement, "photo.reference": ReferenceManagement,
            "group_participation": GroupParticipationManagement,
            # 主动联系偏好是唯一一个四层组（安装/角色/关系/窗口），也是此前 158 项里
            # 92 项在任何页面上都点不到的那一组。它的两个关系级额度按窗口写入会被拒
            # （contact_relationship_budget_scope），编辑器会在字段契约里去掉窗口层。
            "proactive.contact": ProactiveContactManagement}


def _document(raw, *, expected):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite value")))
    if type(data) is not dict or set(data) != expected:
        raise ValueError("unexpected or missing configuration fields")
    return data


class ConfigurationWebAPI:
    """One route family for the groups the cottage edits outside their own page."""

    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.status, ["GET"], "Read image, reaction and budget settings"),
                (PREFIX + "/configure", self.configure, ["POST"],
                 "Save one of those groups with its own edit token")]

    async def _run(self, action):
        from .web_api import outcome_response
        try:
            username = request.username
            if type(username) is not str or not username.strip() or username.startswith("api_key:"):
                raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
            query = request.query
            if set(query.keys()) - {"sections"} or any(len(query.getlist(key)) != 1 for key in query.keys()):
                raise TaskError("configuration_request_invalid", "unexpected configuration query")
            data = None
            if action == "configure":
                raw = await request.body()
                if len(raw) > 32768:
                    raise ValueError("configuration request is too large")
                data = _document(raw, expected={"section", "operation_key", "edit_token", "changes"})
                if data["section"] not in SECTIONS:
                    raise TaskError("configuration_request_invalid", "unknown configuration section")
                if (type(data["operation_key"]) is not str or not data["operation_key"].strip()
                        or len(data["operation_key"]) > 128 or type(data["edit_token"]) is not str
                        or len(data["edit_token"]) != 64 or type(data["changes"]) is not dict or not data["changes"]):
                    raise ValueError("provide a stable operation key, edit token and explicit changes")
            async with self.controller._control_lock:
                controller = self.controller
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "plugin is stopped")
                session = controller.session or controller.last_session
                if session is None or controller.runtime is None:
                    raise TaskError("staging_not_initialized", "load the V2 profile first")
                operator = dashboard_operator(controller.runtime, username, at=controller.now())
                context = session.profile.target
                if action == "status":
                    result = Outcome.success(await self._status(session.application, context, operator, query,
                                                                 host_context=controller.context))
                else:
                    editor = SECTIONS[data["section"]](session.application, context)
                    result = editor.configure(operator, {key: data[key]
                                                         for key in ("operation_key", "edit_token", "changes")})
                    if result.is_success:
                        # The operation receipt confirms the write. Pages refresh status
                        # separately so a slow projection cannot turn a committed write
                        # into an unconfirmed POST.
                        result = Outcome.success({"result": result.unwrap()})
                return outcome_response(result)
        except (TaskError, ConfigurationError) as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return outcome_response(Outcome.failed("configuration_request_invalid",
                                                   "invalid UTF-8 configuration request"))

    @staticmethod
    def _requested(query):
        raw = query.get("sections", "") or ""
        wanted = tuple(SECTIONS) if not raw else tuple(part.strip() for part in raw.split(",") if part.strip())
        if not wanted or set(wanted) - set(SECTIONS) or len(set(wanted)) != len(wanted):
            raise TaskError("configuration_request_invalid", "unknown configuration section")
        return wanted

    async def _status(self, app, context, operator, query, *, host_context=None, section_names=None):
        sections = {}
        for name in section_names if section_names is not None else self._requested(query):
            sections[name] = {**SECTIONS[name](app, context).status(operator).unwrap(), "section": name}
            if name == "knowledge":
                section = sections[name]
                try:
                    selected = KnowledgeSettings.from_values(section["settings"]).knowledge_source_ids()
                except Exception:
                    selected = ()
                try:
                    sources = await AstrBotKnowledgeSources(host_context).list_sources()
                    sources_available = bool(getattr(host_context, "kb_manager", None))
                except Exception:
                    sources = []
                    sources_available = False
                available = {item["id"] for item in sources}
                available.update(doc["id"] for item in sources for doc in item.get("documents", ()))
                for identifier in selected:
                    if identifier not in available:
                        sources.append({"id": identifier, "type": "missing", "kb_id": "",
                                        "name": "不可用来源 · " + identifier,
                                        "documents": []})
                section["knowledge_sources"] = sources
                section["knowledge_sources_available"] = sources_available
        return {"sections": sections}

    async def status(self):
        return await self._run("status")

    async def configure(self):
        return await self._run("configure")
