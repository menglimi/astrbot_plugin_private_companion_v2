#!/usr/bin/env python3
"""存储基线审计：把 V2 自有 SQLite 的大小与增长量出来，越线才动 schema。

为什么值得一个脚本
------------------
「存储现在还行」这种判断不落成数字，下次改动时就会无声退回：WAL 会一直长，
`*_history` 会一直堆，`memory_views.document_json` 会越来越肥。使用者当前明确
**暂不**加 WAL 自动维护／截断，也**暂不**加新索引与历史保留策略——这是有意的
取舍，不是遗漏。代价是这几个量从此没有守卫。本脚本把取舍落成**带触发条件的
观察项**：平时只报数，越线才要求动 schema，避免"哪天想起来了才去看一眼"。

阈值只写在下面的具名常量里
--------------------------
不在函数里写魔法数字，也不因为某次实测难看就放宽阈值：阈值一旦成为"照着现状
调"的东西，它就只是把现状复述一遍，不再是守卫。要改就改常量，并在这里写清
新依据。

六项检查，各自在防什么
----------------------
1. **主库大小**（`companion-v2.sqlite3`）。只报数，不判定。单看绝对值说明不了
   问题——2 MB 的库配上 700 KB 的 WAL 才是问题——所以它同时是第 2 项的分母。
   这里刻意**不**发明一条"主库不得超过 N MB"的上限：没有依据的上限只会让人
   以为已经有守卫了。

2. **WAL 常驻大小（硬线）与 WAL／主库比值（提示项）**。WAL 是 WAL 模式的正常
   组成，但常驻不回收的 WAL 会：把"备份/拷贝一个文件"变成"三个文件必须一起拿"
   （少拿 `-wal` 就静默丢掉最近写入）、让只读分析工具读到旧快照、并让磁盘占用
   接近翻倍。
   · **硬线只有绝对值：`-wal` > 32 MB。** 32 MB 是"单个 `-wal` 已经大到不该再
     靠下次启动 checkpoint 兜底"的量级。
   · **比值（> 25%）是提示项，不参与退出码。** 起因是实测：主库 2.23 MiB 时
     `-wal` 只要 712 KiB，比值就是 31.2%——它越了线，可这么小的 WAL 对磁盘和
     备份几乎没有影响。比值是一条**常驻**阈值，而小库的比值天然偏高（一次批量
     写入就能让它过半）；同一组数字放到大库上，同一条线又永远不会触发。拿它判红
     等于"库小的时候必然误报、库大了永远不会报"，真正的越线反而没人看。所以比值
     照常打印并标注"小库比值天然偏高，仅作观察"，越线只以提示形式出现。

3. **`*_history` 行数（合计与单域最大值）**。历史表是回滚与审计的凭据，删了就
   没有第二次机会，所以现状是只增不减。触发线：合计 > 5000 行，或单域 > 1000 行。
   依据是"这张表还有没有人会去读"——几百行的时候翻起来是查证，几万行的时候
   就只是一份没人读的日志，那时要么加保留窗口，要么承认它已经变成冷数据。
   单域线比合计线更早生效（1000 × 5 个域才到合计线），因为涨的通常只有一个域。

4. **`memory_views.document_json` 的长度分布（平均／最大）**。它是"为读优化的
   物化视图"，本该是短文档；一旦有人把整份会话或整篇材料塞进来，读放大、写放大
   与 WAL 增长会一起变坏，而且看不出来。触发线：最大 > 64 KB，或平均 > 4 KB。
   64 KB 是"这条记录已经不适合逐行读"的量级；4 KB 是"平均一条就等于一整页
   SQLite page"的量级——超过它，视图表就不再是索引而是正文。

5. **表与索引数量及比值**。只报数，不判定。索引数量本身不是缺陷，但它和
   "上次加索引是什么时候、加的算不算数"直接相关，所以记下来供对照。

6. **各表行数 Top N**。只报数，用于观察增长：哪个域在长、长得比上次快多少，
   都要先有个可比的数字。

只读保证
--------
本脚本**只读**：连接一律走 `file:<路径>?mode=ro`（URI 打开阶段就拒绝写事务）
并立刻 `PRAGMA query_only=ON`（第二道闸，防止以后加进来的语句变成写）。它
**不写库、不 checkpoint、不 VACUUM、不改 journal_mode**——审计有副作用就不再
是审计。这两个保证由 tests/test_storage_audit.py 用"跑完前后文件哈希与 mtime
不变、目录文件集合不变"守住。

只读的边界（实测，不是推测）
----------------------------
主库与 `-wal` 在审计前后字节与 mtime 都不变——不 checkpoint、不截断、不写入。
唯一会变的是 `-shm`：它是 SQLite 的 wal-index 共享内存，**任何**一次只读打开
（哪怕只跑一句 `SELECT COUNT(*)`）都会更新里面的读标记，字节会变、大小不变。
这是 SQLite 的行为，不是本工具多做的事；测试里有一条对照用例把这条边界钉住，
而不是把断言放宽了事。

库不存在或为空时按「未初始化」处理，**不算失败**：刚装好的实例本来就什么都没有。

不依赖 AstrBot 运行实例
-----------------------
只用标准库（`sqlite3` / `pathlib`），不导入 `companion_v2` 或 `astrbot_host`，
所以 AstrBot 没在跑、甚至没装，也能对着一份数据目录跑。数据根来源有两种：
`--data-root` 显式指定，或按 AstrBot 的目录约定自动发现（见 default_data_root）。

与 tools/audit_storage.py 的分工
--------------------------------
同目录下的 `tools/audit_storage.py` 是**另一个既有工具**（显式传 `--database` /
`--profiles-root`，在临时目录里对快照做 `StorageRuntime.open()`、量启动耗时与
锁形态），不属于本次交付。本文件是只读的基线审计，两者并存、互不依赖，也不要
互相改名。

用法：python tools/audit_storage_baseline.py [--data-root <插件数据目录或 runtime 目录>] [--json]
退出码 0 = 硬线没有越线（含"库还没初始化"）；非 0 = 至少一项硬线越线。提示项不影响退出码。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
import unicodedata

# 本插件目录：…/data/plugins/astrbot_plugin_private_companion
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]

MAIN_DATABASE = "companion-v2.sqlite3"
# 旁库：memory-search 整库可重建；semantic-catalog **含目录原始数据**，不能当
# 可丢弃派生物，只有它的向量部分可以再生成。这里只报大小，不判定，也不清理。
SEARCH_DATABASE = "memory-search.sqlite3"
CATALOG_DATABASE = "semantic-catalog.sqlite3"
WAL_SUFFIX = "-wal"

# AstrBot 的数据根是平铺的：<astrbot>/data/plugin_data/<插件目录名>/。
# 每个 profile 各自持有一个 runtime 目录，三库都在 runtime 里。
RUNTIME_GLOBS = ("profiles/*/runtime", "installations/*/runtime")

# ---------------------------------------------------------------------------
# 触发线。改动前先读模块 docstring 里对应的依据；阈值的注释写在常量上。
# ---------------------------------------------------------------------------

# WAL 常驻与主库的比值：**提示线，不是硬线**（不参与退出码）。
# 25% 是"WAL 已经开始和主库同量级"的位置，但比值对库的大小极敏感：主库 2.23 MiB
# 时 -wal 只要 712 KiB 就到 31.2%，而这么大的 WAL 对磁盘与备份几乎没有影响；
# 反过来说，库长大后同一条线又永远不会触发。一条"小库必然误报、大库永不触发"的
# 常驻阈值不能用来判红，只适合当观察项：照常打印，越线出提示，退出码不变。
WAL_RATIO_NOTICE_LIMIT = 0.25

# WAL 绝对体积上限。32 MiB 是"单个 -wal 已经大到不该靠下次启动兜底"的量级，
# 与比值线互补：库很大时比值会被稀释，靠这条兜住。
WAL_ABSOLUTE_LIMIT_BYTES = 32 * 1024 * 1024

# `*_history` 合计行数上限。超过它，历史表更像一份没人读的日志而不是回滚凭据。
HISTORY_TOTAL_LIMIT = 5000

# 单个域（单张 `*_history`）的行数上限。比合计线更早生效：涨的通常只有一个域，
# 等合计越线时，那个域已经堆积了很久。
HISTORY_DOMAIN_LIMIT = 1000

# `memory_views.document_json` 单条最大长度。64 KiB 是"这条记录已经不适合逐行读"
# 的量级；到这一步读放大与写放大都会一起变坏。
DOCUMENT_MAX_LIMIT_BYTES = 64 * 1024

# `memory_views.document_json` 平均长度。4 KiB = 一整页 SQLite page：平均值到
# 这里，视图表就不再是索引，而是把正文抄了一份。
DOCUMENT_AVERAGE_LIMIT_BYTES = 4 * 1024

# 第 6 项报多少张表。只影响可读性，不影响判定。
TOP_TABLE_COUNT = 10

# 越线项的处置建议。建议只指向"先查清再决定"，不指向本工具不具备的动作：
# 工具不 checkpoint、不建索引、不清理历史，这些都必须由使用者显式决定。
SUGGESTED_ACTIONS = {
    "wal_ratio": "先确认是不是活锁期的暂时膨胀；若确认常驻，只在停机窗口由维护流程显式 "
                 "wal_checkpoint(TRUNCATE)，不启用自动维护（使用者已决定暂不加）。",
    "wal_bytes": "先定位是哪次批量写入喂肥了 WAL，再决定是否需要一次显式 checkpoint。",
    "history_total": "先按域看是哪张表在涨；确认它的用途（审计还是回滚）之后再谈保留窗口。",
    "history_domain": "先看该域的增长速率，再决定是否给这一个域加保留策略。",
    "document_max": "定位最大那条记录属于哪个域，确认是否把本不该入库的内容写进了视图。",
    "document_average": "document_json 变大通常是往视图里放了整份文档；先查写入侧。",
}


def human_bytes(size: int) -> str:
    """把字节数写成人类可读形式（1024 进制，标注 KiB/MiB 以免与 MB 混淆）。"""
    if size < 1024:
        return "%d B" % size
    if size < 1024 * 1024:
        return "%.1f KiB" % (size / 1024)
    return "%.2f MiB" % (size / (1024 * 1024))


def sized(size: int) -> str:
    """精确值 + 可读值：基线记录要能原样对上，不能只有四舍五入过的数。

    小于 1 KiB 时可读值与精确值同一形态，只输出一次，避免"554 B（554 B）"。
    """
    raw = "%d B" % size
    human = human_bytes(size)
    return raw if human == raw else "%s（%s）" % (raw, human)


def _display_width(text: str) -> int:
    """终端显示宽度：CJK 全宽字符占两列，否则中文表头会把表格挤歪。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _quote(name: str) -> str:
    """标识符加引号：表名来自 sqlite_master，仍然按约定转义双引号。"""
    return '"' + name.replace('"', '""') + '"'


def default_data_root() -> pathlib.Path | None:
    """按 AstrBot 的目录约定自动发现本插件的数据目录。

    约定来自仓库里既有的读取器（tools/inspect_profile_depth.py 等）：
    插件目录是 `<astrbot>/data/plugins/<插件目录名>`，它的数据目录是
    `<astrbot>/data/plugin_data/<插件目录名>`（即插件目录的父目录的父目录下的
    plugin_data）。仓库不在 AstrBot 数据目录里时，退回 `~/.astrbot` 下的同一条
    约定。两条都不存在就返回 None——调用方负责打印一句明确说明并以 0 退出，
    不把它当错误刷栈。
    """
    candidates = (
        PLUGIN_ROOT.parents[1] / "plugin_data" / PLUGIN_ROOT.name,
        pathlib.Path.home() / ".astrbot" / "data" / "plugin_data" / PLUGIN_ROOT.name,
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def resolve_runtime_root(root: pathlib.Path) -> tuple[pathlib.Path | None, tuple[pathlib.Path, ...]]:
    """把数据目录解析成真正放着三库的 runtime 目录。

    两种输入都接受：
      · 直接就是 runtime 目录（自己含 companion-v2.sqlite3）；
      · 插件数据目录（其下是 profiles/<名>/runtime 或 installations/<名>/runtime）。
    多个 profile 时选**主库最近被写过**的那个——它是当前在用的实例；其余一并
    返回，由调用方打印出来，避免"悄悄只审计了一个"。
    """
    if (root / MAIN_DATABASE).is_file():
        return root, ()
    found: list[pathlib.Path] = []
    for pattern in RUNTIME_GLOBS:
        found.extend(path for path in root.glob(pattern) if (path / MAIN_DATABASE).is_file())
    if not found:
        return None, ()
    found.sort(key=lambda path: (path / MAIN_DATABASE).stat().st_mtime, reverse=True)
    return found[0], tuple(found[1:])


def read_only_connection(database: pathlib.Path) -> sqlite3.Connection:
    """打开一个只读连接：URI 的 mode=ro 加 PRAGMA query_only=ON，两道闸。

    mode=ro 在打开阶段就拒绝写事务；query_only 保证之后任何语句都不会变成写。
    两者都只是"保证不写"：这里不做 checkpoint、不做 VACUUM、不改 journal_mode。
    """
    uri = "file:%s?mode=ro" % pathlib.Path(database).as_posix()
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _measure(database: pathlib.Path) -> dict:
    """连一次库，把所有要量的东西读出来。返回的字典只含事实，不含判定。"""
    facts: dict = {
        "schema_version": None,
        "journal_mode": None,
        "page_size": None,
        "page_count": None,
        "tables": [],
        "index_count": 0,
        "row_counts": {},
        "history_rows": {},
        "memory_views": None,
    }
    connection = read_only_connection(database)
    try:
        facts["journal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
        facts["page_size"] = connection.execute("PRAGMA page_size").fetchone()[0]
        facts["page_count"] = connection.execute("PRAGMA page_count").fetchone()[0]
        facts["tables"] = [
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        ]
        facts["index_count"] = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
            "AND name NOT LIKE 'sqlite_%'").fetchone()[0]
        try:
            row = connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()
            facts["schema_version"] = row[0] if row else None
        except sqlite3.Error:
            # 最小库（例如定向测试里手搓的那个）没有 runtime_metadata：不是缺陷。
            facts["schema_version"] = None
        for table in facts["tables"]:
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM %s" % _quote(table)).fetchone()[0]
            except sqlite3.Error:
                # 虚表等取不到行数的表：跳过，不因此判红。
                continue
            facts["row_counts"][table] = count
            if table.endswith("_history"):
                facts["history_rows"][table] = count
        if "memory_views" in facts["tables"]:
            row = connection.execute(
                "SELECT COUNT(*), COALESCE(AVG(length(CAST(document_json AS BLOB))), 0), "
                "COALESCE(MAX(length(CAST(document_json AS BLOB))), 0) "
                "FROM memory_views").fetchone()
            facts["memory_views"] = {
                "rows": row[0],
                "average_bytes": round(float(row[1]), 2),
                "maximum_bytes": int(row[2]),
            }
    finally:
        connection.close()
    return facts


def _check(key: str, item: str, measured: str, threshold: str | None, basis: str,
           *, over_line: bool = False, mode: str = "info") -> dict:
    """一条检查的实测行。

    mode 只有三种，判定强度从这里出：
      · "hard"     —— 硬线，越线进 violations 并决定退出码；
      · "advisory" —— 提示线，越线只进 notices，**不参与退出码**；
      · "info"     —— 只报数，没有线。
    `violated` 由 mode 与 over_line 推出来（而不是在调用处各自写一遍），
    这样"只有硬线能判红"是这条函数里唯一一处事实。
    """
    return {
        "key": key,
        "item": item,
        "measured": measured,
        "threshold": threshold,
        "mode": mode,
        "over_line": over_line,
        "violated": over_line and mode == "hard",
        "basis": basis,
    }


def _build_checks(facts: dict, main_bytes: int, wal_bytes: int) -> list[dict]:
    """按实测事实装配各项检查。事实与判定分开，判定规则只在这一处。"""
    ratio = (wal_bytes / main_bytes) if main_bytes else 0.0
    checks = [
        _check(
            "main_bytes", "主库大小", sized(main_bytes), None,
            "只报数：绝对体积本身说明不了问题，它是 WAL／主库比值的分母。"),
        _check(
            "wal_bytes", "WAL 常驻大小", sized(wal_bytes),
            "> %s" % sized(WAL_ABSOLUTE_LIMIT_BYTES),
            "WAL 常驻不回收会让备份从「一个文件」变成「三个文件必须一起拿」。",
            over_line=wal_bytes > WAL_ABSOLUTE_LIMIT_BYTES, mode="hard",
        ),
        _check(
            "wal_ratio", "WAL／主库比值", "%.1f %%" % (ratio * 100),
            "> %.0f %%" % (WAL_RATIO_NOTICE_LIMIT * 100),
            "小库的 WAL 比值天然偏高（主库才几 MiB 时，一次批量写入就能过半），"
            "同一条线在库长大后永远不会触发，所以只作观察、不判红。",
            over_line=bool(main_bytes) and ratio > WAL_RATIO_NOTICE_LIMIT, mode="advisory",
        ),
    ]

    history = facts["history_rows"]
    total = sum(history.values())
    domain, domain_rows = (max(history.items(), key=lambda item: item[1]) if history else ("—", 0))
    checks.extend([
        _check(
            "history_total", "历史表合计行数", "%d 行（%d 张 *_history 表）" % (total, len(history)),
            "> %d 行" % HISTORY_TOTAL_LIMIT,
            "历史只增不减；超过这个量级它更像没人读的日志，而不是回滚凭据。",
            over_line=total > HISTORY_TOTAL_LIMIT, mode="hard",
        ),
        _check(
            "history_domain", "单域历史最大行数",
            "%d 行（%s）" % (domain_rows, domain),
            "> %d 行" % HISTORY_DOMAIN_LIMIT,
            "单域线比合计线更早生效：涨的通常只有一个域。",
            over_line=domain_rows > HISTORY_DOMAIN_LIMIT, mode="hard",
        ),
    ])

    views = facts["memory_views"]
    if views is None:
        checks.extend([
            _check("document_max", "document_json 最大长度", "无 memory_views 表", None,
                   "表不存在时不判定，也不当作失败。"),
            _check("document_average", "document_json 平均长度", "无 memory_views 表", None,
                   "表不存在时不判定，也不当作失败。"),
        ])
    else:
        checks.extend([
            _check(
                "document_max", "document_json 最大长度",
                "%s，%d 行" % (sized(views["maximum_bytes"]), views["rows"]),
                "> %s" % sized(DOCUMENT_MAX_LIMIT_BYTES),
                "视图本该是短文档；到这个量级已经不适合逐行读。",
                over_line=views["maximum_bytes"] > DOCUMENT_MAX_LIMIT_BYTES, mode="hard",
            ),
            _check(
                "document_average", "document_json 平均长度",
                "%.1f B（%d 行）" % (views["average_bytes"], views["rows"]),
                "> %s" % sized(DOCUMENT_AVERAGE_LIMIT_BYTES),
                "平均一条到一整页 page 时，物化视图就不再是索引，而是把正文抄了一份。",
                over_line=views["average_bytes"] > DOCUMENT_AVERAGE_LIMIT_BYTES, mode="hard",
            ),
        ])

    table_count = len(facts["tables"])
    checks.extend([
        _check("table_count", "表数量", "%d 张" % table_count, None,
               "只报数：表数量本身不是缺陷，记下来供与上次对照。"),
        _check("index_count", "索引数量", "%d 个" % facts["index_count"], None,
               "只报数：索引不是缺陷，但它决定写入放大，需要与增长一起看。"),
        _check(
            "index_table_ratio", "索引／表 比值",
            "%.2f" % (facts["index_count"] / table_count) if table_count else "—", None,
            "只报数：用来判断「再加索引」这件事还值不值得。"),
    ])
    return checks


def build_report(root: pathlib.Path) -> dict:
    """审计一个数据根，返回可打印、可 JSON 化的报告（判定与事实都在里面）。"""
    report: dict = {
        "tool": "tools/audit_storage_baseline.py",
        "data_root": str(root),
        "data_root_exists": root.is_dir(),
        "runtime_root": None,
        "profile": None,
        "unused_runtime_roots": [],
        "status": "UNINITIALIZED",
        "schema_version": None,
        "journal_mode": None,
        "database_bytes": 0,
        "wal_bytes": 0,
        "sidecars": {},
        "checks": [],
        "top_tables": [],
        "violations": [],
        "notices": [],
        "notes": [],
    }
    if not root.is_dir():
        report["notes"].append("数据目录不存在：%s" % root)
        return report

    runtime, others = resolve_runtime_root(root)
    report["unused_runtime_roots"] = [str(path) for path in others]
    if runtime is None:
        report["notes"].append(
            "在 %s 下没有找到 %s，按「未初始化」处理（不算失败）。" % (root, MAIN_DATABASE))
        return report

    report["runtime_root"] = str(runtime)
    # profile 名只在标准布局（…/profiles/<名>/runtime）里存在。直接传一个 runtime
    # 目录时，它的父目录名（可能是 Temp 之类）不代表 profile，宁可不报。
    report["profile"] = runtime.parent.name if runtime.name == "runtime" else None
    report["sidecars"] = {
        name: (runtime / name).stat().st_size
        for name in (SEARCH_DATABASE, CATALOG_DATABASE) if (runtime / name).is_file()
    }

    database = runtime / MAIN_DATABASE
    report["database_bytes"] = database.stat().st_size
    wal_path = pathlib.Path(str(database) + WAL_SUFFIX)
    report["wal_bytes"] = wal_path.stat().st_size if wal_path.exists() else 0

    if report["database_bytes"] == 0:
        report["notes"].append("主库存在但为 0 字节，按「未初始化」处理。")
        return report

    try:
        facts = _measure(database)
    except sqlite3.Error as error:
        # 打不开／读不到不等于"越线"：这里不判红，但也不冒充通过。
        report["status"] = "UNREADABLE"
        report["notes"].append(
            "主库读不出来：%s: %s。本次没有任何测量值，不能当作通过。"
            % (type(error).__name__, error))
        return report

    report["schema_version"] = facts["schema_version"]
    report["journal_mode"] = facts["journal_mode"]
    report["checks"] = _build_checks(facts, report["database_bytes"], report["wal_bytes"])
    report["violations"] = [check for check in report["checks"] if check["violated"]]
    # 提示项与越线项分开：提示只出现在报告里，永远不进 violations，也就不影响退出码。
    report["notices"] = [check for check in report["checks"]
                         if check["mode"] == "advisory" and check["over_line"]]
    report["top_tables"] = sorted(
        facts["row_counts"].items(), key=lambda item: (-item[1], item[0]))[:TOP_TABLE_COUNT]
    report["top_tables"] = [{"table": name, "rows": count} for name, count in report["top_tables"]]
    report["status"] = "RED" if report["violations"] else "OK"
    return report


def render(report: dict) -> None:
    """人类可读输出：一张"实测 vs 阈值"表，加提示项、越线项与建议动作。"""
    print("=" * 78)
    print("V2 存储基线审计（只读：不写库、不 checkpoint、不 VACUUM）")
    print("=" * 78)
    print("  数据目录：%s" % report["data_root"])
    if report["runtime_root"]:
        print("  审计数据根：%s" % report["runtime_root"])
        if report["profile"]:
            print("  profile：%s" % report["profile"])
        for path in report["unused_runtime_roots"]:
            print("  未审计：%s（本次只审计主库最近被写的那个 profile）" % path)
    print()

    if report["status"] == "UNINITIALIZED":
        print("未初始化：")
        for note in report["notes"]:
            print("  · %s" % note)
        print()
        print("结论：没有可审计的库，按「未初始化」处理，不算失败。")
        return
    if report["status"] == "UNREADABLE":
        print("无法读取：")
        for note in report["notes"]:
            print("  · %s" % note)
        return

    print("  库：%s（journal_mode=%s，schema=%s）"
          % (MAIN_DATABASE, report["journal_mode"], report["schema_version"]))
    for name, size in sorted(report["sidecars"].items()):
        extra = ""
        if name == CATALOG_DATABASE:
            extra = "  ← 含目录原始数据，不是可丢弃派生物（只有向量部分可再生成）"
        elif name == SEARCH_DATABASE:
            extra = "  ← 整库可重建"
        print("  旁库：%s %s%s" % (name, sized(size), extra))
    print()

    print("【实测 vs 阈值】")
    print("  " + _pad("检查项", 24) + _pad("实测", 34) + _pad("阈值", 26) + "判定")
    print("  " + "-" * 92)
    for check in report["checks"]:
        if check["mode"] == "advisory":
            verdict = "! 提示" if check["over_line"] else "✓"
        elif check["mode"] == "hard":
            verdict = "✗ 越线" if check["over_line"] else "✓"
        else:
            verdict = "·只报数"
        print("  " + _pad(check["item"], 24) + _pad(check["measured"], 34)
              + _pad(check["threshold"] or "—", 26) + verdict)
    print()

    print("【各表行数 Top %d】" % TOP_TABLE_COUNT)
    if not report["top_tables"]:
        print("  （没有可统计的表）")
    for index, row in enumerate(report["top_tables"], start=1):
        print("  %2d. %-42s %d" % (index, row["table"], row["rows"]))
    print()

    if report["notices"]:
        print("【提示 %d 项（不参与退出码）】" % len(report["notices"]))
        for check in report["notices"]:
            print("  ! %s：%s，提示线 %s" % (check["item"], check["measured"], check["threshold"]))
            print("      说明：%s" % check["basis"])
            action = SUGGESTED_ACTIONS.get(check["key"])
            if action:
                print("      若确实要处理：%s" % action)
        print()

    if report["violations"]:
        print("越线 %d 项（硬线写在 tools/audit_storage_baseline.py 的具名常量里）："
              % len(report["violations"]))
        for check in report["violations"]:
            print("  ✗ %s：%s，触发线 %s" % (check["item"], check["measured"], check["threshold"]))
            print("      依据：%s" % check["basis"])
            action = SUGGESTED_ACTIONS.get(check["key"])
            if action:
                print("      建议动作：%s" % action)
    else:
        print("结论：全部在观察线以内，本次没有需要动 schema 的越线项。")
        if report["notices"]:
            print("      另有 %d 项提示（不参与退出码）：%s"
                  % (len(report["notices"]),
                     "、".join(check["item"] for check in report["notices"])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="V2 存储基线审计（只读；越线返回非 0）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-root", type=pathlib.Path, default=None,
        help="插件数据目录（含 profiles/）或直接含三库的 runtime 目录；"
             "缺省按 AstrBot 目录约定自动发现")
    parser.add_argument(
        "--json", action="store_true", help="输出机器可读的 JSON 报告（不打印表格）")
    args = parser.parse_args(argv)

    if args.data_root is not None:
        root = args.data_root
    else:
        root = default_data_root()
        if root is None:
            # 发现不到不是错误：明确说一句然后用 0 退出，不刷栈。
            print("自动发现失败：按 AstrBot 的目录约定找不到本插件的数据目录；"
                  "请用 --data-root 指定插件数据目录或 runtime 目录。本次没有审计任何库。")
            return 0

    report = build_report(pathlib.Path(root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        render(report)
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
