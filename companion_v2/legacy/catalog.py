"""Static V1 source inventory for the direct-replacement release gate.

The catalog describes supported sources. It intentionally does not locate, open, or
transform any source: locating a V1 installation is a separate concern, and the actual
transformations live beside the domain they convert.

**Handler status (2026-10-01).** ``private.host_configuration`` has the only automatic
converter: :mod:`companion_v2.legacy.weather_migration` converts the V1 weather group.
It is a converter for one group, not the whole host configuration, and it takes an
already-read mapping rather than opening anything itself. The core profile, work/delivery,
and world/assets sources are catalogued explicitly as ``NO_HANDLER`` until their
converters exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


V1_PLUGIN_ID = "astrbot_plugin_private_companion"
V1_SUPPORTED_VERSION = "6.6.2"


class CatalogAction(str, Enum):
    """The allowed post-migration disposition for one declared legacy source."""

    CONVERTED = "converted"
    NO_HANDLER = "no_handler"
    COMPAT_READABLE = "compat_readable"
    RETAINED_EXTERNAL = "retained_external"
    HELD = "held"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class LegacyCatalogEntry:
    """One versioned legacy source and its required V2 handling contract."""

    source_id: str
    source_plugin_id: str
    source_version: str
    owner: str
    source_paths: tuple[str, ...]
    format_signature: str
    action: CatalogAction
    handler_id: str
    acceptance_scope: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityDispositionEntry:
    """一条能力级处置：**不是**数据归属，而是「这项能力谁对外表达」。

    为什么必须有它：记忆伴侣的 ``memory_companion.db`` 是 ``COMPAT_READABLE``
    （保持原位可读、V2 不复制），但**能力**上 V2 已经让位——注入与工具都归它。
    两件事的结论相反，用同一条记录表达就一定会写错其中一个：把数据改成
    ``RETAINED_EXTERNAL`` 等于说「V2 不读这个库了」，而 V2 其实照旧读；把能力
    留在 ``COMPAT_READABLE`` 等于说「两边都可以对外表达」，那正是要消掉的重复。

    所以数据级事实留在 :data:`LEGACY_COMPATIBILITY_CATALOG`（并留在迁移发现里，
    用户可以逐条看见），能力级事实放在 :data:`CAPABILITY_DISPOSITIONS`。迁移的
    发现/试算只读前者，不会因为这条记录多出一份「数据在哪」的报告。
    """

    capability_id: str
    provider_plugin_id: str
    provider_display_name: str
    owner: str
    disposition: CatalogAction
    declaration: str
    reason: str


# 能力级处置表。目前只有记忆一条：本插件认「我会牢牢记住你」为记忆能力的提供方，
# 表达式（注入与工具）都让它，V2 自己退回去继续记录事实。声明路径写明它公开的
# 取句柄函数——V2 读的就是这个声明，不是文件是否存在。
CAPABILITY_DISPOSITIONS = (
    CapabilityDispositionEntry(
        capability_id="memory",
        provider_plugin_id="astrbot_plugin_memory_companion",
        provider_display_name="我会牢牢记住你",
        owner="memory_companion.conversation_and_governance",
        disposition=CatalogAction.RETAINED_EXTERNAL,
        declaration="main.py:get_active_bridge / main.py:get_memory_companion_bridge",
        reason=(
            "记忆的对外表达（每轮注入与模型可用的记忆工具）归它，V2 让位以免出现两套记忆叙事，"
            "也避免模型把新记忆分别写进两个库；句柄消失、声明停用或读不到时 V2 立刻恢复自己的"
            "注入与工具，所以这是可逆的让位，不是把能力让出去。"
        ),
    ),
)


@dataclass(frozen=True)
class LegacyCompatibilityCatalog:
    """Immutable, reviewable inventory used to scope future automatic migration."""

    schema_version: str
    target_plugin_id: str
    supported_v1_versions: tuple[str, ...]
    entries: tuple[LegacyCatalogEntry, ...]

    def entry(self, source_id: str) -> LegacyCatalogEntry:
        for candidate in self.entries:
            if candidate.source_id == source_id:
                return candidate
        raise KeyError(source_id)

    def entries_for_plugin(self, plugin_id: str) -> tuple[LegacyCatalogEntry, ...]:
        return tuple(item for item in self.entries if item.source_plugin_id == plugin_id)

    def validate(self) -> tuple[str, ...]:
        """Return structural defects without opening any legacy source."""

        errors: list[str] = []
        if not self.schema_version:
            errors.append("schema_version_missing")
        if self.target_plugin_id != V1_PLUGIN_ID:
            errors.append("target_plugin_identity_mismatch")
        if not self.supported_v1_versions:
            errors.append("supported_v1_versions_missing")

        seen_source_ids: set[str] = set()
        for item in self.entries:
            if not item.source_id or item.source_id in seen_source_ids:
                errors.append(f"source_id_invalid:{item.source_id}")
            seen_source_ids.add(item.source_id)
            if not item.source_plugin_id:
                errors.append(f"source_plugin_missing:{item.source_id}")
            if not item.source_version:
                errors.append(f"source_version_missing:{item.source_id}")
            if not item.owner:
                errors.append(f"owner_missing:{item.source_id}")
            if not item.source_paths:
                errors.append(f"source_paths_missing:{item.source_id}")
            if not item.format_signature:
                errors.append(f"format_signature_missing:{item.source_id}")
            if not isinstance(item.action, CatalogAction):
                errors.append(f"action_invalid:{item.source_id}")
            if not item.handler_id:
                errors.append(f"handler_missing:{item.source_id}")
            if not item.acceptance_scope:
                errors.append(f"acceptance_scope_missing:{item.source_id}")
        return tuple(errors)


LEGACY_COMPATIBILITY_CATALOG = LegacyCompatibilityCatalog(
    schema_version="companion-v2.legacy-compatibility-catalog.v0",
    target_plugin_id=V1_PLUGIN_ID,
    supported_v1_versions=(V1_SUPPORTED_VERSION,),
    entries=(
        LegacyCatalogEntry(
            source_id="private.host_configuration",
            source_plugin_id=V1_PLUGIN_ID,
            source_version=V1_SUPPORTED_VERSION,
            owner="private_companion.configuration",
            source_paths=("host-config:astrbot_plugin_private_companion",),
            format_signature="astrbot-plugin-config.v1",
            action=CatalogAction.CONVERTED,
            handler_id="v2.private-config-converter",
            acceptance_scope=("RG-03", "RG-04", "RG-05"),
        ),
        LegacyCatalogEntry(
            source_id="private.core_profiles",
            source_plugin_id=V1_PLUGIN_ID,
            source_version=V1_SUPPORTED_VERSION,
            owner="private_companion.role_and_relationship",
            source_paths=("companions.json", "persona_profiles"),
            format_signature="private-core.json-or-configured-sqlite.v1",
            action=CatalogAction.NO_HANDLER,
            handler_id="v2.private-core-converter",
            acceptance_scope=("RG-03", "RG-05", "RG-06", "RG-09"),
        ),
        LegacyCatalogEntry(
            source_id="memory.timeline_and_governance",
            source_plugin_id="astrbot_plugin_memory_companion",
            source_version=V1_SUPPORTED_VERSION,
            owner="memory_companion.conversation_and_governance",
            source_paths=("memory_companion.db",),
            format_signature="memory-companion.sqlite.v1",
            action=CatalogAction.COMPAT_READABLE,
            handler_id="v2.memory-snapshot-adapter",
            acceptance_scope=("RG-03", "RG-05", "RG-06", "RG-09"),
        ),
        # 注意：这一条**保持** COMPAT_READABLE，一个字都不改。它说的是数据事实
        # （库留在原处、V2 只读不复制），而记忆能力现在由 CAPABILITY_DISPOSITIONS
        # 里的那条记录声明为 RETAINED_EXTERNAL。两件事结论相反但都对，混在一条
        # 记录里必然写错其中一个。
        LegacyCatalogEntry(
            source_id="private.work_and_delivery",
            source_plugin_id=V1_PLUGIN_ID,
            source_version=V1_SUPPORTED_VERSION,
            owner="private_companion.work_and_delivery",
            source_paths=("framework_work/work.db", "framework_work/delivery.db"),
            format_signature="private-work-delivery.sqlite.v1",
            action=CatalogAction.NO_HANDLER,
            handler_id="v2.work-delivery-converter",
            acceptance_scope=("RG-05", "RG-07", "RG-08", "RG-09"),
        ),
        LegacyCatalogEntry(
            source_id="private.world_assets",
            source_plugin_id=V1_PLUGIN_ID,
            source_version=V1_SUPPORTED_VERSION,
            owner="private_companion.world_and_assets",
            source_paths=("framework_world/album.db", "framework_world/resources"),
            format_signature="private-world-album-and-files.v1",
            action=CatalogAction.NO_HANDLER,
            handler_id="v2.world-asset-converter",
            acceptance_scope=("RG-04", "RG-05", "RG-08"),
        ),
        LegacyCatalogEntry(
            source_id="content.creative_projects",
            source_plugin_id="astrbot_plugin_content_companion",
            source_version=V1_SUPPORTED_VERSION,
            owner="content_companion.creative_projects",
            source_paths=("creative_state.json",),
            format_signature="content-creative-state.json.v1",
            action=CatalogAction.RETAINED_EXTERNAL,
            handler_id="v2.content-owner-adapter",
            acceptance_scope=("RG-03", "RG-05", "RG-12"),
        ),
        LegacyCatalogEntry(
            source_id="image.generation_state",
            source_plugin_id="astrbot_plugin_image_companion",
            source_version=V1_SUPPORTED_VERSION,
            owner="image_companion.generation_and_assets",
            source_paths=("image_generation_state.json",),
            format_signature="image-generation-state.json.v1",
            action=CatalogAction.RETAINED_EXTERNAL,
            handler_id="v2.image-owner-adapter",
            acceptance_scope=("RG-03", "RG-05", "RG-08", "RG-12"),
        ),
        LegacyCatalogEntry(
            source_id="reality.device_and_observations",
            source_plugin_id="astrbot_plugin_reality_companion",
            source_version=V1_SUPPORTED_VERSION,
            owner="reality_companion.device_and_observation",
            source_paths=("reality_companion.json", "device-side-material"),
            format_signature="reality-state-and-device-contract.v1",
            action=CatalogAction.RETAINED_EXTERNAL,
            handler_id="v2.reality-owner-adapter",
            acceptance_scope=("RG-03", "RG-05", "RG-06", "RG-07", "RG-12"),
        ),
        LegacyCatalogEntry(
            source_id="extensions.session_and_media",
            source_plugin_id=V1_PLUGIN_ID,
            source_version=V1_SUPPORTED_VERSION,
            owner="extension_session_and_media",
            source_paths=("together", "live", "game", "extension-owned-media"),
            format_signature="extension-specific-state.v1",
            action=CatalogAction.HELD,
            handler_id="v2.extension-owner-inventory",
            acceptance_scope=("RG-03", "RG-05", "RG-07", "RG-12"),
        ),
    ),
)


def validate_capability_dispositions(entries=CAPABILITY_DISPOSITIONS) -> tuple[str, ...]:
    """Return structural defects in the capability-level dispositions.

    和 :meth:`LegacyCompatibilityCatalog.validate` 一样：只查结构，不打开任何来源。
    两条纪律各查一次——能力 id 不能重复（一项能力只能有一个对外表达者），让位
    必须真的是 ``RETAINED_EXTERNAL``（写成 ``COMPAT_READABLE`` 就等于说两边都
    可以对外表达，那正是这次要消掉的重复）。
    """

    errors: list[str] = []
    seen: set[str] = set()
    for item in entries:
        if not item.capability_id or item.capability_id in seen:
            errors.append(f"capability_id_invalid:{item.capability_id}")
        seen.add(item.capability_id)
        if not item.provider_plugin_id:
            errors.append(f"provider_plugin_missing:{item.capability_id}")
        if not item.provider_display_name:
            errors.append(f"provider_display_name_missing:{item.capability_id}")
        if not item.owner:
            errors.append(f"owner_missing:{item.capability_id}")
        if not item.declaration:
            errors.append(f"declaration_missing:{item.capability_id}")
        if not item.reason:
            errors.append(f"reason_missing:{item.capability_id}")
        if not isinstance(item.disposition, CatalogAction):
            errors.append(f"disposition_invalid:{item.capability_id}")
        elif item.disposition is not CatalogAction.RETAINED_EXTERNAL:
            errors.append(f"delegated_capability_must_be_retained_external:{item.capability_id}")
    return tuple(errors)
