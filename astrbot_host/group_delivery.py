"""Finite group-only delivery grants and immutable per-batch admission intent."""

from dataclasses import asdict
from datetime import datetime

from companion_v2.execution.models import TaskError, stamp
from .group_settings import GroupTarget
from .settings import DELIVERY_AUTHORIZATION_TTL


CAPABILITY = "message.group.delivery"
GRANT_PREFIX = "host.multi.group.delivery:"
INTENT_PREFIX = "host.multi.group.delivery.intent:"


class GroupDeliveryAuthority:
    def __init__(self, authority):
        self.authority = authority

    def target(self, target_id):
        target = self.authority.target(target_id)
        if not isinstance(target, GroupTarget):
            raise TaskError("host_group_target_required", "group authorization requires an explicit group target")
        return target

    def validate_target(self, target):
        known = self.authority.target(target.target_id)
        if known != target:
            template = self.authority.settings.template_for(target)
            if template is None:
                raise TaskError("host_group_target_required", "the group does not belong to a registered Bot account")
        return target

    def authorize(self, target_id, expires_at):
        """正式版：不再需要授权；保留这个方法只为"记一条意愿"，它不参与放行。"""
        target = self.target(target_id)
        authority = self.authority
        now = authority.now()
        with authority.runtime.transaction():
            previous = authority.read(GRANT_PREFIX + target_id)
            grant = {"capability": CAPABILITY, "target": asdict(target),
                "revision": previous["revision"] + 1 if previous else 1, "issued_at": stamp(now),
                "expires_at": stamp(expires_at), "revoked": False}
            authority.write(GRANT_PREFIX + target_id, grant)
        return {"target_id": target_id, "authorized": True, "capability": CAPABILITY,
                "revision": grant["revision"], "expires_at": grant["expires_at"]}

    def revoke(self, target_id):
        """同上：记一笔"曾经收回"，但它不影响群聊投递（正式版没有这道闸）。"""
        self.target(target_id)
        authority = self.authority
        with authority.runtime.transaction():
            previous = authority.read(GRANT_PREFIX + target_id)
            authority.write(GRANT_PREFIX + target_id, {**(previous or {}), "revoked": True,
                "revision": previous["revision"] + 1 if previous else 1, "expires_at": stamp(authority.now())})
        return {"target_id": target_id, "authorized": True, "capability": CAPABILITY, "required": False}

    def access(self, target):
        """正式版：群聊投递不再需要逐群授权；仍然要求这是一个配置里的群目标。"""
        self.validate_target(target)
        return {"capability": CAPABILITY, "target": asdict(target), "revision": 1,
                "issued_at": stamp(self.authority.now()), "expires_at": None, "revoked": False}

    def status(self, target):
        try:
            value = self.access(target)
            return {"authorized": True, "capability": CAPABILITY, "revision": value["revision"],
                    "expires_at": value["expires_at"]}
        except TaskError:
            return {"authorized": False, "capability": CAPABILITY}

    def admit(self, target, context, batch_id, sender, *, replayed):
        authority = self.authority
        key = INTENT_PREFIX + batch_id
        if authority.read(key) is not None:
            return
        grant = self.access(target)
        authority.write(key, {"target": asdict(target), "origin_key": context.key, "mode": "onebot_group",
            "sender": asdict(sender), "grant_revision": grant["revision"]})

    def mode(self, batch_id):
        value = self.authority.read(INTENT_PREFIX + batch_id)
        return value["mode"] if value else "onebot_group"

    def authorize_envelope(self, target, envelope):
        authority = self.authority
        part = authority.runtime.read_one("SELECT batch_id FROM conversation_parts WHERE part_id = ?", (envelope.part_id,))
        intent = authority.read(INTENT_PREFIX + part["batch_id"]) if part else None
        grant = self.access(target)
        if (not intent or intent["mode"] != "onebot_group" or intent["target"] != asdict(target)
                or intent["origin_key"] != envelope.context.key or intent["sender"] != asdict(envelope.sender)):
            raise TaskError("host_group_delivery_intent_changed", "group delivery must retain its original admission")
        return grant
