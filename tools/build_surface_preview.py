"""Render the review preview from the extracted CSVs.

The preview is a *view* of the data, so it is generated, never hand-edited. The
previous hand-written version still said 320 fields after the extractor was fixed,
which is exactly the drift this script exists to prevent.

Run from the repository root, after ``build_v2_inventory.py`` and
``resolve_ledger_landings.py``::

    python3 tools/build_surface_preview.py

Writes ``docs/V2_SURFACE_PREVIEW_20260928.html``.
"""

from __future__ import annotations

import collections
import csv
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "docs" / "V2_CONFIG_SURFACE_20260928.csv"
PLUGINS = ROOT / "docs" / "V2_PLUGIN_CONFIG_20260928.csv"
RESOLVED = ROOT / "docs" / "V1_V2_CONFIG_RESOLVED_20260928.csv"
OUT = ROOT / "docs" / "V2_SURFACE_PREVIEW_20260928.html"

# Which registry groups each navigation page is responsible for. This mapping is a
# design decision, not a fact derivable from the code, so it is stated once here
# rather than inferred from names.
PAGE_GROUPS = {
    "感知": ("knowledge", "screen", "conversation.perception", "conversation.recall",
             "photo.reference", "conversation.image_review",
             "conversation.media_quota", "content.authoring"),
    "决策": ("person", "role.state", "role.growth", "conversation.busy_gate"),
    "行动": ("role.life", "library", "wardrobe"),
    "表达": ("conversation.presentation", "expression.learning", "expression.reaction"),
    "自我": ("knowledge",),
    "主动与联系": ("proactive.contact",),
    "事实与经历": ("memory",),
    "学习与反思": ("expression.learning", "role.growth"),
    "模型与连接": tuple(),  # model.* is matched by prefix, not by exact group name
}

# Plugin config groups shown on each page. These are a different mechanism, so they
# are listed separately and never added into a registry ratio.
PAGE_PLUGIN_GROUPS = {
    "模型与连接": ("model",),
    "账号与会话": ("runtime", "multi_host", "target", "staging", "poke"),
    "外观与设置": ("voice_reply", "segmentation"),
}

PAGE_NOTES = {
    "小屋": "生活总览与观察；由独立拓展页承载",
    "感知": "角色能看到、听到、读到的信息",
    "决策": "角色怎么做判断，以及它现在的状态",
    "行动": "除回复以外的行为",
    "产出": "角色产出的内容；由独立拓展页承载",
    "表达": "角色怎么说话",
    "自我": "角色自己的设定与世界知识",
    "关系与权限": "角色、人物、群与授权；由独立拓展页承载",
    "主动与联系": "候选、联系节奏与编排",
    "事实与经历": "事实、原话与群词义",
    "学习与反思": "从经历里学到什么",
    "模型与连接": "公共模型与任务路由",
    "治理与维护": "运行状态、预算、迁移与资料",
    "开始使用": "首次连接引导",
    "外观与设置": "主题与显示维度",
    "账号与会话": "Bot、人格、会话窗口的运行接线与生命周期",
    "资料与维护": "备份、导入导出与预览数据",
}

STATE_LABEL = {"covered": "已接", "missing": "待接", "intended": "有意不接"}
STATE_CLASS = {"covered": "ok", "missing": "todo", "intended": "ghost"}


def load_nav() -> list[tuple[str, list[tuple[str, str]]]]:
    """Parse ``navGroups`` out of app.js so the preview cannot disagree with the app."""
    source = (ROOT / "pages" / "陪伴小屋" / "app.js").read_text(encoding="utf-8")
    match = re.search(r"navGroups\s*=\s*(\[[\s\S]*?\n\];)", source)
    if not match:
        raise SystemExit("navGroups not found in app.js")
    literal = match.group(1).rstrip(";")
    # The declaration is a JS literal with comments; strip those, then read the labels.
    literal = re.sub(r"/\*[\s\S]*?\*/", "", literal)
    literal = re.sub(r"//[^\n]*", "", literal)
    groups = []
    for group_match in re.finditer(r"\[\s*'([^']+)'\s*,\s*(\[[\s\S]*?\])\s*\]", literal):
        label = group_match.group(1)
        pages = re.findall(r"\[\s*'[^']*'\s*,\s*'[^']*'\s*,\s*'[^']*'\s*,\s*'([^']+)'\s*\]",
                           group_match.group(2))
        if pages:
            groups.append((label, [(page, "") for page in pages]))
    return groups


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def bar(covered: int, total: int) -> str:
    if not total:
        return ('<p class="ratio muted">本页无注册配置项<br><small>或由独立拓展页承载</small></p>'
                '<ul class="tags"><li class="ghost">仅页面入口</li></ul>')
    percent = round(covered * 100 / total)
    cls = "bar" if covered else "bar none"
    return (f'<div class="{cls}"><i style="width:{percent}%"></i></div>'
            f'<p class="ratio"><b>{covered}</b> / {total} 已接</p>'
            f'<ul class="tags">{"".join(f"<li>{html.escape(g)}</li>" for g in GROUPS_BY_PAGE.get(PAGE_OF_CARD, ()))}</ul>')


def main() -> int:
    surface = read_csv(SURFACE)
    plugins = read_csv(PLUGINS)
    resolved = read_csv(RESOLVED)
    nav = load_nav()

    tally = collections.Counter(row["state"] for row in surface)
    per_group: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in surface:
        per_group[row["group"]][row["state"]] += 1

    total_registry = len(surface)
    total_plugin = len(plugins)
    verdicts = collections.Counter(row["verified_verdict"] for row in resolved)
    kinds = collections.Counter(row["resolved_kind"] for row in resolved)
    owed = [row for row in resolved if row["disposition"] == "owed"]

    # ---- chapter 1: navigation cards -------------------------------------------
    global GROUPS_BY_PAGE, PAGE_OF_CARD
    GROUPS_BY_PAGE, PAGE_OF_CARD = {}, ""
    for _label, pages in nav:
        for page, _ in pages:
            GROUPS_BY_PAGE[page] = PAGE_GROUPS.get(page, ())

    cards_html = []
    for label, pages in nav:
        cards = []
        for page, _ in pages:
            PAGE_OF_CARD = page
            groups = PAGE_GROUPS.get(page, ())
            if page == "模型与连接":
                own = [row for row in surface if row["group"].startswith("model.")]
                covered = sum(1 for row in own if row["state"] == "covered")
                inner = bar(covered, len(own))
            else:
                selected = [row for row in surface if row["group"] in groups]
                covered = sum(1 for row in selected if row["state"] == "covered")
                inner = bar(covered, len(selected))
            plugin_groups = PAGE_PLUGIN_GROUPS.get(page, ())
            plugin_count = sum(1 for row in plugins
                               if row["path"].split(".")[0] in plugin_groups)
            extra = (f'<ul class="tags"><li>插件配置 {plugin_count}</li></ul>'
                     if plugin_count else "")
            cards.append(
                f'<article class="card">\n<h4>{html.escape(page)}</h4>'
                f'<p>{html.escape(PAGE_NOTES.get(page, ""))}</p>{inner}{extra}\n</article>')
        cards_html.append(
            f'<div class="navgroup"><h3>{html.escape(label)}</h3><div class="cards">'
            + "".join(cards) + "</div></div>")

    # ---- chapter 2: gaps --------------------------------------------------------
    gap_rows = []
    for group, counter in sorted(per_group.items(), key=lambda kv: -kv[1]["missing"]):
        if not counter["missing"]:
            continue
        gap_rows.append(f"<tr><td><code>{html.escape(group)}</code></td>"
                        f'<td class="num">{counter["missing"]}</td>'
                        f'<td class="num">{counter["covered"]}</td>'
                        f'<td class="num">{counter["intended"]}</td>'
                        f'<td class="num">{sum(counter.values())}</td></tr>')

    intended = [row for row in surface if row["state"] == "intended"]
    intended_rows = "".join(
        f'<tr><td><code>{html.escape(row["field_id"])}</code></td></tr>' for row in intended)

    # ---- chapter 3: ledger ------------------------------------------------------
    verdict_html = "".join(
        f'<div class="verdict"><span class="vl">{html.escape(name)}</span>'
        f'<span class="vn">{count}</span>'
        f'<span class="vp">{count / len(resolved):.1%}</span></div>'
        for name, count in verdicts.most_common())

    kind_html = "".join(
        f'<div class="verdict"><span class="vl">{html.escape(name)}</span>'
        f'<span class="vn">{count}</span>'
        f'<span class="vp">{count / len(resolved):.1%}</span></div>'
        for name, count in kinds.most_common())

    owed_html = "".join(
        f'<li><b>{html.escape(row["v1_key"].split(".")[0])}</b>'
        f'<span>{html.escape(row["disposition"])}</span></li>' for row in owed[:20])

    unresolved = [row for row in resolved if row["resolved_kind"] == "unresolved"]

    # ---- chapter 4: field table -------------------------------------------------
    filter_chips = "".join(
        f'<button class="chip" data-filter="{"all" if index == 0 else state}">'
        f'{label} {total_registry if index == 0 else tally[state]}</button>'
        for index, (state, label) in enumerate([("", "全部"), ("covered", "已接"),
                                                ("missing", "待接"), ("intended", "有意不接")]))
    field_rows = "".join(
        f'<tr data-state="{row["state"]}"><td><code>{html.escape(row["field_id"])}</code></td>'
        f'<td class="dim">{html.escape(row["kind"])}</td>'
        f'<td class="dim">{html.escape(row["default"])[:24]}</td>'
        f'<td class="dim">{html.escape(row["layers"])}</td>'
        f'<td class="dim">{html.escape(row["apply"])}</td>'
        f'<td><span class="st {STATE_CLASS[row["state"]]}">{STATE_LABEL[row["state"]]}</span></td>'
        f'<td class="dim">{html.escape(row["where"][:70])}</td></tr>'
        for row in surface)

    plugin_rows = "".join(
        f'<tr><td><code>{html.escape(row["path"])}</code></td>'
        f'<td class="dim">{html.escape(row["kind"])}</td>'
        f'<td class="dim">{html.escape(str(row["default"]))[:20]}</td>'
        f'<td class="dim">{html.escape(row["description"])}</td></tr>'
        for row in plugins)

    css = (ROOT / "docs" / "preview.css").read_text(encoding="utf-8") \
        if (ROOT / "docs" / "preview.css").exists() else DEFAULT_CSS

    document = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>V2 功能与配置盘点 · 预览稿</title><style>{css}</style></head><body>
<header class="masthead"><div class="wrap">
<p class="kicker">审核稿 · 2026-09-28 · 由脚本生成</p>
<h1>陪伴 V2.0 功能与配置盘点</h1>
<p class="standfirst">功能与配置项的现状清单，按当前导航顺序排列。所有数字由脚本从代码库
直接抽取，可重新生成；<strong>这不是设计提案，是给人核对的地基</strong>。</p>
<dl class="tally">
<div><dt>注册表字段</dt><dd>{total_registry}<small>25 个 provider</small></dd></div>
<div><dt>插件配置</dt><dd>{total_plugin}<small>AstrBot 安装级</small></dd></div>
<div><dt>已接控件</dt><dd>{tally["covered"]}<small>{tally["covered"] * 100 // total_registry}%</small></dd></div>
<div><dt>待接</dt><dd>{tally["missing"]}<small>净缺口</small></dd></div>
<div><dt>有意不接</dt><dd>{tally["intended"]}<small>非未做</small></dd></div>
<div><dt>V1 判定</dt><dd>{len(resolved)}<small>权威账本行</small></dd></div>
<div><dt>已定位落点</dt><dd>{len(resolved) - len(unresolved)}<small>{(len(resolved) - len(unresolved)) * 100 // len(resolved)}%</small></dd></div>
<div><dt>待人工</dt><dd>{len(unresolved)}<small>无法定位</small></dd></div>
</dl></div></header>
<main class="wrap">

<section class="chapter"><h2><span>一</span>按导航归类</h2>
<p class="lede">{sum(len(p) for _, p in nav)} 个入口，{len(nav)} 组。卡片标明这一页挂了多少
注册表字段、进度如何，以及有多少项属于「插件配置」这套独立机制。</p>
{"".join(cards_html)}
</section>

<section class="chapter"><h2><span>二</span>缺口分布</h2>
<p class="lede">净缺口 {tally["missing"]} 项，集中在两处；其余分组为零。这不是按页面平摊的
数字，是从注册表逐个字段数出来的。</p>
<table><thead><tr><th>分组</th><th class="num">待接</th><th class="num">已接</th>
<th class="num">不接</th><th class="num">合计</th></tr></thead><tbody>
{"".join(gap_rows)}
</tbody></table>
<h3>有意不接的 {len(intended)} 项</h3>
<p class="note">不是未做。这 {len(intended)} 项都是明确决定不设控件的，理由见清单文档。</p>
<table><tbody>{intended_rows}</tbody></table>
</section>

<section class="chapter"><h2><span>三</span>V1 迁移现状</h2>
<p class="lede">账本给每个 V1 键一个判定，但只有 100 行填了具体字段名，其余是散文。
下面把散文也降成了落点，好判断哪些判定真的拦得住迁移。</p>
<div class="split">
<div><h3>判定分布</h3><div class="verdicts">{verdict_html}</div></div>
<div><h3>落点回查</h3><div class="verdicts">{kind_html}</div>
<div class="asidebox"><h4>怎么读这两列</h4>
<p>判定说的是「要不要迁」，落点说的是「迁到哪」。<strong>{len(unresolved)} 行两者都对不上</strong>，
其中 {sum(1 for row in unresolved if row["verified_verdict"] == "not-migrated-by-design")} 行
本来就不打算迁、{sum(1 for row in unresolved if row["verified_verdict"] == "implemented-elsewhere")} 行
在别处已实现——对迁移不构成阻塞。</p></div></div>
</div>
<h3>欠账 {len(owed)} 行</h3>
<p class="note">这 {len(owed)} 行要人手过一遍，其中
{sum(1 for row in owed if row["resolved_kind"] == "unresolved")} 行落点未定。</p>
<ul class="owed">{owed_html}</ul>
</section>

<section class="chapter"><h2><span>四</span>逐字段明细</h2>
<p class="lede">注册表 {total_registry} 个字段逐项列出。<code>where</code> 列是页面源码里
检出该字段名的位置——空着就是没有控件。</p>
<div class="filters">{filter_chips}</div>
<table class="fields"><thead><tr><th>字段</th><th>种类</th><th>默认</th><th>层</th>
<th>生效</th><th>状态</th><th>控件位置</th></tr></thead><tbody>{field_rows}</tbody></table>
<h3>插件配置 {total_plugin} 项</h3>
<p class="note">这套由 AstrBot 自己读取，与上面的注册表是两套机制，不并入同一个比例。</p>
<table class="fields"><thead><tr><th>路径</th><th>类型</th><th>默认</th><th>说明</th></tr></thead>
<tbody>{plugin_rows}</tbody></table>
</section>
</main>
<footer><div class="wrap">
<p>重新生成：<code>python3 tools/build_v2_inventory.py &amp;&amp; python3 tools/resolve_ledger_landings.py &amp;&amp; python3 tools/build_surface_preview.py</code></p>
<p>数据来源：25 个 <code>configuration_fields()</code>、<code>_conf_schema.json</code>、
<code>docs/V1_V2_CONFIG_VERIFIED_20260927.csv</code>、<code>pages/陪伴小屋/app.js</code>。</p>
</div></footer>
<script>
document.querySelectorAll('.chip').forEach(function(chip){{
  chip.addEventListener('click', function(){{
    document.querySelectorAll('.chip').forEach(function(other){{ other.classList.remove('active'); }});
    chip.classList.add('active');
    var want = chip.dataset.filter;
    document.querySelectorAll('.fields tr[data-state]').forEach(function(row){{
      row.hidden = want !== 'all' && row.dataset.state !== want;
    }});
  }});
}});
</script>
</body></html>"""

    OUT.write_text(document, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  registry {total_registry}  plugin {total_plugin}  "
          f"covered {tally['covered']}  missing {tally['missing']}  intended {tally['intended']}")
    print(f"  ledger {len(resolved)}  resolved {len(resolved) - len(unresolved)}  "
          f"unresolved {len(unresolved)}")
    return 0


DEFAULT_CSS = """
:root{color-scheme:light;--ink:#1c1f26;--ink-soft:#4d5566;--ink-faint:#838b9c;
--paper:#fbfaf7;--rule:#e2ded4;--rule-firm:#cfc9bb;--accent:#4a5b8c;--accent-quiet:#eceef5;
--ok:#3f6b56;--ok-q:#e6eee9;--warn:#8a6a2a;--warn-q:#f6eeda;--stop:#8d5560}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:15px/1.65 "Iowan Old Style",Palatino,Georgia,"Songti SC",serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 32px}
code{font-family:"SFMono-Regular",Menlo,Consolas,monospace;font-size:.85em;background:#eeece6;
border-radius:3px;padding:1px 5px;color:var(--ink-soft)}
.masthead{border-bottom:2px solid var(--ink);padding:56px 0 26px}
.kicker{margin:0;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-faint);
font-family:"SFMono-Regular",Menlo,monospace}
.masthead h1{margin:14px 0 0;font-size:42px;line-height:1.05;letter-spacing:-.02em;font-weight:600}
.standfirst{margin:18px 0 0;max-width:62ch;font-size:16px;line-height:1.75;color:var(--ink-soft)}
.standfirst strong{color:var(--ink);font-weight:600}
.tally{display:flex;flex-wrap:wrap;margin:34px 0 0;border-top:1px solid var(--rule)}
.tally>div{flex:1 1 120px;padding:16px 18px 14px 0;border-right:1px solid var(--rule)}
.tally>div:last-child{border-right:0}
.tally dt{margin:0;font-size:11px;color:var(--ink-faint);letter-spacing:.05em}
.tally dd{margin:6px 0 0;font-size:27px;line-height:1;font-variant-numeric:tabular-nums;font-weight:600}
.tally dd small{display:block;margin-top:5px;font-size:11px;font-weight:400;color:var(--ink-faint)}
main{padding-bottom:80px}
.chapter{margin-top:64px}
.chapter>h2{display:flex;align-items:baseline;gap:14px;margin:0 0 12px;font-size:23px;font-weight:600;
border-bottom:1px solid var(--ink);padding-bottom:11px}
.chapter>h2 span{font-family:"SFMono-Regular",Menlo,monospace;font-size:12px;color:var(--ink-faint);
letter-spacing:.1em}
.chapter>h3{margin:32px 0 8px;font-size:16px;font-weight:600}
.lede{margin:0 0 30px;max-width:70ch;color:var(--ink-soft);font-size:15px;line-height:1.8}
.navgroup{display:grid;grid-template-columns:132px minmax(0,1fr);gap:28px;padding:26px 0;
border-top:1px solid var(--rule)}
.navgroup:first-of-type{border-top:0}
.navgroup>h3{margin:0;font-size:13px;font-weight:600;line-height:1.4}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:1px;
background:var(--rule);border:1px solid var(--rule)}
.card{background:var(--paper);padding:17px 18px 15px}
.card h4{margin:0;font-size:14.5px;font-weight:600}
.card p{margin:6px 0 0;font-size:12.5px;line-height:1.6;color:var(--ink-faint)}
.bar{height:3px;background:var(--accent-quiet);margin:13px 0 7px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent)}
.bar.none{background:transparent;border-bottom:1px dashed var(--rule-firm)}
.ratio{margin:0!important;font-size:12px!important;color:var(--ink-soft)!important;
font-variant-numeric:tabular-nums}
.ratio b{font-size:14px;color:var(--ink)}
.ratio.muted{color:var(--ink-faint)!important}
.tags{display:flex;flex-wrap:wrap;gap:5px;list-style:none;margin:11px 0 0;padding:0}
.tags li{font-family:"SFMono-Regular",Menlo,monospace;font-size:10.5px;border:1px solid var(--rule-firm);
border-radius:2px;padding:1px 6px;color:var(--ink-faint)}
.tags li.ghost{border-style:dashed}
.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:44px;align-items:start}
.split h3{margin:0 0 10px;font-size:16px;font-weight:600}
.note{margin:0 0 14px;font-size:13px;color:var(--ink-faint);line-height:1.7;max-width:66ch}
table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:22px}
thead th{text-align:left;font-size:11px;font-weight:600;color:var(--ink-faint);letter-spacing:.05em;
border-bottom:1px solid var(--ink);padding:0 10px 7px 0}
tbody td{padding:8px 10px 8px 0;border-bottom:1px solid var(--rule);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;width:56px}
.dim{color:var(--ink-faint);font-size:12px}
.asidebox{border:1px solid var(--rule-firm);border-left:3px solid var(--accent);background:#fff;
padding:18px 19px;margin-bottom:18px}
.asidebox h4{margin:0 0 9px;font-size:13px;font-weight:600}
.asidebox p{margin:0;font-size:12.5px;line-height:1.72;color:var(--ink-soft)}
.asidebox strong{color:var(--ink)}
.verdicts{display:flex;flex-direction:column;border-top:1px solid var(--ink);margin-bottom:26px}
.verdict{display:grid;grid-template-columns:minmax(0,1fr) 64px 56px;gap:12px;align-items:baseline;
padding:9px 0;border-bottom:1px solid var(--rule)}
.vl{font-size:13.5px}
.vn,.vp{text-align:right;font-variant-numeric:tabular-nums;font-size:13.5px}
.vp{color:var(--ink-faint);font-size:12px}
.owed{display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:0 0 20px;padding:0}
.owed li{display:flex;align-items:baseline;gap:7px;border:1px solid var(--rule);background:#fff;
padding:5px 10px;font-size:11.5px}
.owed li b{font-variant-numeric:tabular-nums;color:var(--accent);font-size:12.5px}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 20px}
.chip{border:1px solid var(--rule-firm);background:transparent;border-radius:2px;padding:5px 11px;
color:var(--ink-soft);cursor:pointer;font-family:"SFMono-Regular",Menlo,monospace;font-size:11px}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip.active{background:var(--ink);border-color:var(--ink);color:var(--paper)}
.fields{font-size:12.5px}
.fields thead th{position:sticky;top:0;background:var(--paper);z-index:1}
.fields td:first-child{white-space:nowrap}
.fields tr[data-state="missing"]{background:#fffdf6}
.fields tr[data-state="missing"] td:first-child code{background:var(--warn-q);color:var(--warn)}
.fields tr[data-state="intended"]{opacity:.55}
.st{font-size:11px;border-radius:2px;padding:2px 7px;white-space:nowrap}
.st.ok{background:var(--ok-q);color:var(--ok)}
.st.todo{background:var(--warn-q);color:var(--warn)}
.st.ghost{background:#eeece6;color:var(--ink-faint)}
.fields tr[hidden]{display:none}
footer{border-top:1px solid var(--rule);padding:22px 0 40px;color:var(--ink-faint);font-size:12px;
line-height:1.8}
footer p{margin:0 0 6px}
@media(max-width:900px){.split{grid-template-columns:1fr;gap:26px}
.navgroup{grid-template-columns:1fr;gap:12px}.masthead h1{font-size:31px}.wrap{padding:0 20px}
.fields{font-size:11.5px}}
@media print{body{background:#fff}.chip{display:none}.chapter{page-break-inside:avoid}
.card{border:1px solid var(--rule)}.cards{background:transparent}}
"""


if __name__ == "__main__":
    raise SystemExit(main())
