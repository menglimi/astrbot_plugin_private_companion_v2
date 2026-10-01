"""Static mapping ledger for V1 user-visible and integration surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SurfaceClassification(str, Enum):
    CORE = "core"
    CAPABILITY = "capability"
    PROVIDER = "provider"
    MIGRATION_ONLY = "migration-only"
    RETIRED = "retired"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class LegacySurfaceEntry:
    """One V1 surface and the route by which V2 must account for it."""

    surface_id: str
    v1_surface: str
    classification: SurfaceClassification
    v2_route: str
    reason: str
    acceptance_scope: tuple[str, ...]


@dataclass(frozen=True)
class LegacySurfaceLedger:
    schema_version: str
    entries: tuple[LegacySurfaceEntry, ...]

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.schema_version:
            errors.append("schema_version_missing")
        seen_surface_ids: set[str] = set()
        for item in self.entries:
            if not item.surface_id or item.surface_id in seen_surface_ids:
                errors.append(f"surface_id_invalid:{item.surface_id}")
            seen_surface_ids.add(item.surface_id)
            if not item.v1_surface:
                errors.append(f"v1_surface_missing:{item.surface_id}")
            if not isinstance(item.classification, SurfaceClassification):
                errors.append(f"classification_invalid:{item.surface_id}")
            if not item.v2_route:
                errors.append(f"v2_route_missing:{item.surface_id}")
            if not item.reason:
                errors.append(f"reason_missing:{item.surface_id}")
            if not item.acceptance_scope:
                errors.append(f"acceptance_scope_missing:{item.surface_id}")
        return tuple(errors)


LEGACY_SURFACE_LEDGER = LegacySurfaceLedger(
    schema_version="companion-v2.legacy-surface-ledger.v0",
    entries=(
        LegacySurfaceEntry(
            surface_id="private.passive_message_hook",
            v1_surface="private message event hook",
            classification=SurfaceClassification.CORE,
            v2_route="conversation.foreground_reply",
            reason="The primary private conversation must retain a V2-owned route.",
            acceptance_scope=("RG-01", "RG-08", "S5-FRP"),
        ),
        LegacySurfaceEntry(
            surface_id="group.passive_message_hook",
            v1_surface="group message event hook",
            classification=SurfaceClassification.CORE,
            v2_route="conversation.group_participation",
            reason="Group participation remains a core route with its own governance.",
            acceptance_scope=("RG-01", "RG-06", "RG-08"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.status",
            v1_surface="陪伴 状态",
            classification=SurfaceClassification.CORE,
            v2_route="companion.status",
            reason="Current role state is a direct user-facing core behavior.",
            acceptance_scope=("RG-01", "RG-04", "RG-09"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.calendar",
            v1_surface="陪伴 查看今日日程 / 日期列表 / 日期添加 / 日期删除",
            classification=SurfaceClassification.CORE,
            v2_route="life.calendar",
            reason="Schedules and explicit dates are V2 domain records, not generated prose.",
            acceptance_scope=("RG-01", "RG-05", "RG-09"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.active_diagnostics",
            v1_surface="陪伴 查看主动判定",
            classification=SurfaceClassification.CORE,
            v2_route="diagnostics.active_decision",
            reason="Users need evidence for proactive behavior and repair decisions.",
            acceptance_scope=("RG-01", "RG-05", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.manual_diagnosis",
            v1_surface="陪伴 答疑 / 排障 / 诊断 / 说明",
            classification=SurfaceClassification.CORE,
            v2_route="diagnostics.explain_self_check_incident_repair_proposal",
            reason="General diagnosis uses current scoped evidence; proactive inspection is only one check.",
            acceptance_scope=("RG-01", "RG-06", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.diagnosis_confirm",
            v1_surface="陪伴 答疑确认 / 应用答疑建议",
            classification=SurfaceClassification.CORE,
            v2_route="management.repair_proposal.confirm",
            reason="Confirmation rechecks the original proposal, actor, scope, permissions, and configuration revision.",
            acceptance_scope=("RG-01", "RG-06", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.diagnosis_cancel",
            v1_surface="陪伴 答疑取消 / 取消答疑建议",
            classification=SurfaceClassification.CORE,
            v2_route="management.repair_proposal.cancel",
            reason="Cancellation closes the original pending proposal without applying its changes.",
            acceptance_scope=("RG-01", "RG-06", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.diagnosis_setting",
            v1_surface="陪伴 答疑设置 / 答疑修改",
            classification=SurfaceClassification.CORE,
            v2_route="configuration.authorized_command_patch",
            reason="Explicit settings use the same authorized, versioned configuration service as the management page.",
            acceptance_scope=("RG-01", "RG-06", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.recall",
            v1_surface="陪伴 撤回消息 / 自然询问刚才撤回了什么",
            classification=SurfaceClassification.CORE,
            v2_route="conversation.recall_and_tombstone",
            reason="Recall must preserve source, tombstone, and current visibility semantics.",
            acceptance_scope=("RG-01", "RG-05", "RG-06"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.role_profile",
            v1_surface="陪伴 昵称 / 语气 / 画像 / 日记",
            classification=SurfaceClassification.CORE,
            v2_route="role.profile_and_journal",
            reason="Role expression and owned journal material belong to the core role domain.",
            acceptance_scope=("RG-01", "RG-05", "RG-09"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.capability_list",
            v1_surface="陪伴 能力列表",
            classification=SurfaceClassification.CORE,
            v2_route="capability.inventory",
            reason="Installed and disabled capabilities need one visible V2 inventory.",
            acceptance_scope=("RG-01", "RG-04", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.tts",
            v1_surface="陪伴 TTS语种",
            classification=SurfaceClassification.CAPABILITY,
            v2_route="capability.voice.preferences",
            reason="Voice is optional and carries its own provider and consent boundary.",
            acceptance_scope=("RG-01", "RG-04", "RG-06"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.city",
            v1_surface="陪伴 绑定城市 / 查看城市 / 解绑城市",
            classification=SurfaceClassification.CAPABILITY,
            v2_route="capability.location.explicit_city",
            reason="An explicit city choice remains separate from live location access.",
            acceptance_scope=("RG-01", "RG-04", "RG-06"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.reference_images",
            v1_surface="陪伴 参考图 / 参考图库",
            classification=SurfaceClassification.CAPABILITY,
            v2_route="capability.image_reference_library",
            reason="Reference media needs asset ownership and visibility checks.",
            acceptance_scope=("RG-01", "RG-05", "RG-08"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.wardrobe",
            v1_surface="陪伴 衣柜",
            classification=SurfaceClassification.CAPABILITY,
            v2_route="capability.wardrobe",
            reason="Wardrobe data is a role-adjacent optional capability with assets.",
            acceptance_scope=("RG-01", "RG-05", "RG-08"),
        ),
        LegacySurfaceEntry(
            surface_id="extension.memory",
            v1_surface="Memory Companion integration and long-term memory command",
            classification=SurfaceClassification.PROVIDER,
            v2_route="provider.memory",
            reason="Memory remains an independently owned provider with a versioned adapter.",
            acceptance_scope=("RG-01", "RG-03", "RG-05", "RG-06"),
        ),
        LegacySurfaceEntry(
            surface_id="extension.content",
            v1_surface="Content Companion creative commands",
            classification=SurfaceClassification.PROVIDER,
            v2_route="provider.content",
            reason="Creative projects stay with their declared owner until a handoff is verified.",
            acceptance_scope=("RG-01", "RG-03", "RG-05"),
        ),
        LegacySurfaceEntry(
            surface_id="extension.image",
            v1_surface="Image and ComfyUI generation integration",
            classification=SurfaceClassification.PROVIDER,
            v2_route="provider.image",
            reason="Image generation and originals need a provider receipt and asset adapter.",
            acceptance_scope=("RG-01", "RG-03", "RG-07", "RG-08"),
        ),
        LegacySurfaceEntry(
            surface_id="extension.reality",
            v1_surface="Reality, Screen, and mobile companion integration",
            classification=SurfaceClassification.PROVIDER,
            v2_route="provider.reality",
            reason="Reality capability ownership includes current consent and device binding.",
            acceptance_scope=("RG-01", "RG-03", "RG-06", "RG-07"),
        ),
        LegacySurfaceEntry(
            surface_id="page.dashboard",
            v1_surface="dashboard pages and page API routes",
            classification=SurfaceClassification.CORE,
            v2_route="management.dashboard",
            reason="Management remains reachable even when optional providers are unavailable.",
            acceptance_scope=("RG-01", "RG-04", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="migration.req041_dual_write",
            v1_surface="REQ041 migration coordinator, dual write, and replay",
            classification=SurfaceClassification.MIGRATION_ONLY,
            v2_route="migration.checkpoint_and_reconciliation",
            reason="V2 replaces internal migration machinery with its own checkpointed handoff.",
            acceptance_scope=("RG-03", "RG-05", "RG-09", "RG-10"),
        ),
        LegacySurfaceEntry(
            surface_id="private.command.force_layer_password",
            v1_surface="陪伴 输出夹层密码 / 强制输出夹层密码",
            classification=SurfaceClassification.RETIRED,
            v2_route="diagnostics.recoverable_configuration",
            reason="V2 does not expose or manufacture secrets as a compatibility behavior.",
            acceptance_scope=("RG-01", "RG-04", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="extension.live_session",
            v1_surface="Live streaming integration",
            classification=SurfaceClassification.DEFERRED,
            v2_route="capability.live_session",
            reason="The capability remains ledgered until its scene, role, and receipt contract passes its domain gate.",
            acceptance_scope=("RG-01", "RG-07", "RG-12"),
        ),
        LegacySurfaceEntry(
            surface_id="extension.together_and_game",
            v1_surface="Together and game extension sessions",
            classification=SurfaceClassification.DEFERRED,
            v2_route="capability.shared_session",
            reason="Shared sessions require their own interaction and animation contract before activation.",
            acceptance_scope=("RG-01", "RG-05", "RG-07", "RG-12"),
        ),
    ),
)
