"""V1 数据迁移：发现 → 计划 → 交给宿主执行。

这是「装完 V2 之后，原来 V1 的数据怎么办」的实现。目录
(:mod:`companion_v2.legacy.catalog`) 早先只**声明**了要支持哪些来源、每条该怎么
处置、哪几条还没写转换器——它不定位、不打开、不转换任何东西。本模块补上定位与
转换，并严格按目录里的 ``action`` 走。

## 为什么是三步

因为「哪条能迁、哪条只能读、哪条迁不动」必须先给用户看，而不是迁到一半报错。
V1 的数据分三类，处置完全不同：

* ``CONVERTED`` —— 能变成 V2 的记录。只有本插件自己的数据在这一类。
* ``COMPAT_READABLE`` —— 保持原位可读，V2 不复制它。记忆伴侣的时间线属于这里：
  V2 自己会从对话里长出新的事实，把旧库整份复制过来只会产生两份互相矛盾的真相。
* ``RETAINED_EXTERNAL`` / ``HELD`` —— 归别的插件或别的子系统所有。本插件既不该
  搬也不该改，只能报告「它在哪、归谁管」。

## 为什么本模块不写库

配置写入在 V2 里要经过 ``ConfigurationService.patch``，而那需要**操作者身份**、
一次已登记的 operation、以及当前 edit token——三样都属于宿主层，域核心拿不到也不
该伪造。所以这里只产出 ``ConfigIntent``（作用域 + 分组 + 字段改动），由
``astrbot_host`` 侧带着真实 actor 提交。这样切有额外好处：发现与试算变成纯读、
可重复、可测，而真正写库的那一步在宿主里只有几行。

## 三条纪律

1. **只读探测**。发现阶段不写任何东西，连 V1 的库都以 ``mode=ro`` 打开。
2. **不改 V1**。单向读取 + 写入 V2；V1 数据根全程不动，迁移失败也不损坏原安装。
3. **不做无根据的转换**。V1 有而 V2 结构上放不下的值（超上限的刷新间隔、数字型
   LocationID…）由对应域的转换器产出 ``Difference``，页面据此告诉用户哪一项被改
   了、为什么——而不是悄悄改小。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from companion_v2.foundation.outcome import Outcome
from companion_v2.legacy.catalog import (
    LEGACY_COMPATIBILITY_CATALOG,
    CatalogAction,
    LegacyCatalogEntry,
)
from companion_v2.legacy.weather_migration import convert_weather_config


# 目录里 ``source_paths`` 有的写成 ``host-config:<plugin_id>``：那不是文件，
# 而是「宿主配置里的一个插件配置段」，单独处理。
_CONFIG_PREFIX = "host-config:"


class MigrationState(str, Enum):
    """一个来源在发现阶段的判定结果。"""

    READY = "ready"            # 存在，转换器已就绪，可以迁
    ABSENT = "absent"          # 这台机器上没有这份 V1 数据
    NO_HANDLER = "no_handler"  # 存在，但转换器还没写
    READ_ONLY = "read_only"    # 存在，按目录只做兼容读取，不复制
    EXTERNAL = "external"      # 存在，归别的插件所有，这里只报告
    HELD = "held"              # 存在，归属未定，暂不动
    UNREADABLE = "unreadable"  # 存在但打不开或结构不符


@dataclass(frozen=True)
class SourceFinding:
    """一个 V1 来源的探测结果。**不含数据内容**，只有结论与理由。"""

    source_id: str
    owner: str
    action: str
    state: str
    paths: tuple[str, ...]
    detail: str = ""
    byte_size: int = 0

    def document(self) -> dict:
        return {
            "source_id": self.source_id,
            "owner": self.owner,
            "action": self.action,
            "state": self.state,
            "paths": list(self.paths),
            "detail": self.detail,
            "byte_size": self.byte_size,
        }


@dataclass(frozen=True)
class ConfigIntent:
    """一条「把某作用域的某几个字段写成这些值」的意图。

    ``group_id`` 是 V2 配置分组名（如 ``state``、``contact``），``changes`` 是
    ``field_id → 值``。``scope`` 用 V2 的配置作用域名（如 ``role.state``），
    由宿主侧解析成真正的 ``ConfigTarget``——作用域到目标的推导依赖运行期身份，
    不属于本模块。
    """

    scope: str
    group_id: str
    changes: dict
    source_id: str


@dataclass
class MigrationPlan:
    """发现结果 + 试算结果。"""

    v1_root: str
    findings: tuple[SourceFinding, ...] = ()
    warnings: tuple[str, ...] = ()
    intents: tuple[ConfigIntent, ...] = ()
    differences: tuple[dict, ...] = ()

    def counts(self) -> dict:
        result: dict[str, int] = {}
        for finding in self.findings:
            result[finding.state] = result.get(finding.state, 0) + 1
        return result

    @property
    def migratable(self) -> tuple[SourceFinding, ...]:
        return tuple(item for item in self.findings if item.state == MigrationState.READY.value)

    @property
    def change_count(self) -> int:
        return sum(len(intent.changes) for intent in self.intents)

    def document(self) -> dict:
        return {
            "v1_root": self.v1_root,
            "findings": [item.document() for item in self.findings],
            "counts": self.counts(),
            "warnings": list(self.warnings),
            "change_count": self.change_count,
            "intents": [
                {"scope": item.scope, "group_id": item.group_id,
                 "fields": sorted(item.changes), "source_id": item.source_id}
                for item in self.intents
            ],
            "differences": list(self.differences),
            "supported_v1_versions": list(LEGACY_COMPATIBILITY_CATALOG.supported_v1_versions),
            "migratable": [item.source_id for item in self.migratable],
        }


def read_json(path: Path):
    """读一个 JSON 文件；坏文件返回 None 而不是抛错。

    迁移不该因为一份可选文件损坏就整体失败——那样用户连「还有什么能迁」都看不到。
    损坏会作为 finding 的 detail 报出去。
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _size_of(paths: tuple[Path, ...]) -> int:
    total = 0
    for path in paths:
        try:
            if path.is_file():
                total += path.stat().st_size
            elif path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        total += child.stat().st_size
        except OSError:
            continue
    return total


def sqlite_tables(path: Path) -> tuple[str, ...] | None:
    """以只读方式列出表名；打不开或不是 SQLite 返回 None。

    ``mode=ro`` 是刻意的：发现阶段连一次意外写入都不该发生，而 sqlite3 的默认
    模式会为不存在的库**创建**文件——那会让「探测」变成一次对 V1 的改动。
    """
    if not path.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return tuple(row[0] for row in rows)
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def _locate(root: Path, source_paths: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    """把目录声明的相对路径拆成「还在的路径」与它们的绝对位置。"""
    present: list[str] = []
    located: list[Path] = []
    for relative in source_paths:
        if relative.startswith(_CONFIG_PREFIX):
            continue
        path = root / relative
        if path.exists():
            present.append(relative)
            located.append(path)
    return tuple(present), tuple(located)


class LegacyMigration:
    """一次迁移的发现与试算。宿主侧用 ``plan.document()`` 呈现，用
    ``plan.intents`` 写库。"""

    def __init__(self, *, v1_root: str | Path, v1_configuration=None) -> None:
        self.v1_root = Path(v1_root)
        # 宿主侧的插件配置（若拿得到）。给了它，「宿主配置段」这一条来源的存在性
        # 就不必依赖数据根里有没有转储——配置本来就在宿主的配置里。
        self.v1_configuration = v1_configuration if isinstance(v1_configuration, dict) else None

    # ── 发现 ───────────────────────────────────────────────────────────
    def discover(self) -> Outcome[tuple[SourceFinding, ...]]:
        """只读探测每个目录条目，返回结论而不是数据。"""
        if not self.v1_root.exists():
            return Outcome.failed("legacy_root_missing", f"没有找到 V1 数据目录：{self.v1_root}")
        if not self.v1_root.is_dir():
            return Outcome.failed("legacy_root_invalid", f"V1 数据位置不是一个目录：{self.v1_root}")
        return Outcome.success(tuple(self._inspect(entry) for entry in LEGACY_COMPATIBILITY_CATALOG.entries))

    def _inspect(self, entry: LegacyCatalogEntry) -> SourceFinding:
        """看一个来源在不在，并按它的 action 给出状态。

        顺序要紧：先判在不在，再判能不能迁。「不在」比「没写转换器」更基础——
        把不存在的项报成 no_handler 会让人去找一份根本没有的数据。
        """
        present, located = _locate(self.v1_root, entry.source_paths)
        size = _size_of(located)
        configured = any(path.startswith(_CONFIG_PREFIX) for path in entry.source_paths)

        if not present:
            # 只在数据根里找文件是不够的：宿主配置段的 ``source_paths`` 写的是
            # ``host-config:<plugin_id>``，没有文件路径，而 V1 的配置转储可能就
            # 摆在数据根里。所以对这类来源要额外看一眼转储存不存在，否则会给
            # 用户报一句「这台机器上没有这份数据」——而它其实就在那儿。
            if configured and self._configuration() is not None:
                state = self._state_for(entry)
                return SourceFinding(
                    entry.source_id, entry.owner, entry.action.value, state.value,
                    entry.source_paths,
                    "V1 的插件配置以配置转储的形式保存在数据根里。",
                    byte_size=size,
                )
            return SourceFinding(
                entry.source_id, entry.owner, entry.action.value,
                MigrationState.ABSENT.value, entry.source_paths,
                "V1 数据根里没有这个路径。",
            )

        for path in located:
            if path.suffix == ".db" and sqlite_tables(path) is None:
                return SourceFinding(
                    entry.source_id, entry.owner, entry.action.value,
                    MigrationState.UNREADABLE.value, present,
                    f"{path.name} 不是可读的 SQLite 库。", byte_size=size,
                )
            if path.suffix == ".json" and read_json(path) is None:
                return SourceFinding(
                    entry.source_id, entry.owner, entry.action.value,
                    MigrationState.UNREADABLE.value, present,
                    f"{path.name} 不是合法的 JSON。", byte_size=size,
                )

        state = self._state_for(entry)
        return SourceFinding(
            entry.source_id, entry.owner, entry.action.value, state.value,
            present, self._detail_for(entry, state), byte_size=size,
        )

    @staticmethod
    def _state_for(entry: LegacyCatalogEntry) -> MigrationState:
        """目录声明的处置 → 本次迁移能不能自动做。"""
        if entry.action is CatalogAction.CONVERTED:
            return (
                MigrationState.READY
                if entry.handler_id in HANDLERS
                else MigrationState.NO_HANDLER
            )
        if entry.action is CatalogAction.NO_HANDLER:
            return MigrationState.NO_HANDLER
        if entry.action is CatalogAction.COMPAT_READABLE:
            return MigrationState.READ_ONLY
        if entry.action is CatalogAction.RETAINED_EXTERNAL:
            return MigrationState.EXTERNAL
        if entry.action is CatalogAction.HELD:
            return MigrationState.HELD
        return MigrationState.NO_HANDLER

    @staticmethod
    def _detail_for(entry: LegacyCatalogEntry, state: MigrationState) -> str:
        return {
            MigrationState.READY: "可以迁移到 V2。",
            MigrationState.NO_HANDLER: "这份数据的转换器还没有写，本次迁移会跳过它。",
            MigrationState.READ_ONLY: "保持原位可读，V2 不复制它。",
            MigrationState.EXTERNAL: f"数据归 {entry.owner} 所有，V2 只报告它在哪里。",
            MigrationState.HELD: "归属尚未确定，暂不迁移。",
            MigrationState.UNREADABLE: "数据存在但读不出来。",
            MigrationState.ABSENT: "这台机器上没有这份数据。",
        }[state]

    # ── 试算 ───────────────────────────────────────────────────────────
    def plan(self) -> Outcome[MigrationPlan]:
        """发现 + 试算。**不写任何东西**，可以反复调用。

        试算把「会改成什么」提前摊开：哪些项会建、哪些会被改小、哪些需要用户补输入。
        用户看到差异再决定，比迁完才发现少了东西好。

        构造时给的 ``v1_configuration`` 是 V1 的插件配置映射；没给就试着从数据根里的
        配置转储读。
        """
        discovered = self.discover()
        if not discovered.is_success:
            # Failure 是冻结 dataclass，不能解包成位置参数。
            return Outcome.failed(discovered.failure.code, discovered.failure.reason)
        findings = discovered.unwrap()

        intents: list[ConfigIntent] = []
        differences: list[dict] = []
        warnings: list[str] = []

        for finding in findings:
            if finding.state != MigrationState.READY.value:
                continue
            converted = self._convert(finding)
            intents.extend(converted[0])
            differences.extend(converted[1])
            warnings.extend(converted[2])

        return Outcome.success(MigrationPlan(
            v1_root=str(self.v1_root),
            findings=findings,
            warnings=tuple(warnings),
            intents=tuple(intents),
            differences=tuple(differences),
        ))

    def _convert(self, finding: SourceFinding) -> tuple[list[ConfigIntent], list[dict], list[str]]:
        """把一个来源转成若干 ``ConfigIntent``。

        目前只有宿主配置段的天气一组有转换器；其余 ``READY`` 来源的转换器待写，
        遇到就说清「这份的转换器还没写」，而不是给一个空结果让人以为它迁完了。
        """
        warnings: list[str] = []

        if finding.source_id != "private.host_configuration":
            warnings.append(f"{finding.source_id} 的转换器还没有写，本次不会迁移它。")
            return [], [], warnings

        config = self._configuration()
        if config is None:
            warnings.append("读不到 V1 的插件配置，天气设置未能试算。")
            return [], [], warnings

        outcome = convert_weather_config(config)
        if not outcome.is_success:
            warnings.append(f"天气设置未能转换：{outcome.failure.reason}")
            return [], [], warnings

        migration = outcome.unwrap()
        # 转换器产出的键是 ``role.state.planning_weather_enabled`` 这种形状，
        # 前段是作用域、后段是字段。按作用域拆开是因为一次写入针对一个作用域。
        grouped: dict[str, dict] = {}
        for key, value in migration.changes.items():
            scope, _, field_id = str(key).rpartition(".")
            if not scope or not field_id:
                continue
            grouped.setdefault(scope, {})[field_id] = value

        intents = [
            ConfigIntent(scope=scope, group_id=GROUP_OF_SCOPE.get(scope, scope), changes=changes,
                         source_id=finding.source_id)
            for scope, changes in sorted(grouped.items())
        ]
        differences = [
            {"field": item.field_id, "kind": item.kind, "explain": item.summary,
             "before": item.v1_value, "after": item.v2_value}
            for item in migration.differences
        ]
        return intents, differences, warnings

    def _configuration(self):
        """V1 的插件配置：优先用宿主传进来的，其次数据根里的配置转储。

        两条路都要，因为它们的可靠性不同：宿主侧的配置是权威的，但只有宿主能读到；
        数据根里的转储谁都能读，但要求用户先导出过。任一条通就够了。
        """
        if self.v1_configuration is not None:
            return self.v1_configuration
        for name in ("companion_config.json", "plugin_config.json", "config.json"):
            path = self.v1_root / name
            if not path.is_file():
                continue
            loaded = read_json(path)
            if isinstance(loaded, dict):
                # V1 的导出有时把配置包在 weather_config 之类的子对象里，
                # 也常是平铺的一层。两种都接。
                nested = loaded.get("weather_config")
                if isinstance(nested, dict):
                    merged = {key: value for key, value in loaded.items() if key != "weather_config"}
                    merged.update(nested)
                    return merged
                return loaded
        return None


# 已经写好的转换器。写在代码里而不是配置里：「哪个转换器实现了」是**代码事实**，
# 不是运行期状态；放进配置就会出现「配置说有、代码里没有」的假阳性。
HANDLERS = frozenset({"v2.private-config-converter"})

# 转换器产出的键前段（``role.state`` / ``proactive.contact``）**就是** V2 的配置
# 分组名——``role_work/state/configuration.py`` 的 ``GROUP`` 与
# ``proactive/configuration.py`` 的 ``GROUP`` 恰好取这两个值，而
# ``ConfigurationService.patch`` 用的键形状是 ``GROUP + "." + field_id``。
# 所以作用域与分组在这里是同一个字符串，不需要再维护一张映射表：
# 多一张表就多一处会与上游定义漂移的地方。
GROUP_OF_SCOPE = {
    "role.state": "role.state",
    "proactive.contact": "proactive.contact",
}
