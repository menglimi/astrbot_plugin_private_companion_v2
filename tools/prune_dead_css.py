# -*- coding: utf-8 -*-
"""摘掉样式表里已经没有任何渲染处引用的死规则。

为什么需要它：页面改版（首页从卡片网格改成清单、管理页从卡片墙改成
分隔线清单）之后，渲染代码不再产出某些 class，但样式表里的规则会留着。
它们不会报错，也不会有人发现——直到某天有人搜到一个类名，误以为
「这里在用」，照着旧规则写新代码。

判据必须来自**渲染代码**（.js / .html 的 class="…"），不是 grep 整个仓库：
- 注释里提到某个类名不算「在用」——本次就吃过这个亏，home.css 的说明里
  写了 .home-jumpbar，检测器把它当成了引用；
- 其他 css 文件里定义过也不算「在用」——那是另一条死规则。

用法：
    python3 tools/prune_dead_css.py --check          # 只报告
    python3 tools/prune_dead_css.py --write          # 就地改写
    python3 tools/prune_dead_css.py --check --css pages/陪伴小屋/styles.css
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "陪伴小屋"

# 这些不是「页面渲染出来的 class」，而是运行期由 JS 写到 root 上的状态名，
# 或由 CSS 自己组合使用的形状 token。误删会让主题/密度/动效开关失效。
KEEP = {
    "active", "large-text", "compact", "standard", "roomy", "sharp", "round",
    "full", "low", "off", "small", "light", "dark",
}
# 元素/伪类选择器里出现这些前缀就不当类是「死」的判据。
BUILTIN = re.compile(r"^(html|body|button|input|textarea|select|svg|img|h[1-6]|p|a|ul|ol|li|dl|dt|dd|table|thead|tbody|tr|td|th|form|label|nav|aside|header|footer|main|section|article|div|span|strong|small|em|b|i|code|pre|meter|progress|dialog|canvas|video|audio|figure|blockquote|hr|br)$")


def strip_comments(source: str) -> str:
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def page_sources():
    """页面自有的脚本与静态 HTML，**含 workspaces/ 子目录**，排除构建产物。

    子目录不能漏：四个宿主工作区（host / identity / life / relationships）
    各有自己的 app.js，它们的 class 也是真实渲染。漏掉会让工具把在用的规则
    报成死的。
    """
    for path in PAGE.rglob("*.js"):
        if "assets" in path.parts or "preview" in path.name or "node_modules" in path.parts:
            continue
        yield path
    for path in PAGE.rglob("*.html"):
        if "assets" in path.parts or path.name in {
            "shell-preview.html", "theme-preview.html", "v2-surface-preview.html"}:
            continue
        yield path


def rendered_classes() -> set[str]:
    """所有页面脚本与静态 HTML 里**真的写进 class=** 的类名。"""
    used: set[str] = set()
    for path in page_sources():
        source = strip_comments(path.read_text(encoding="utf-8"))
        # 静态与模板里的 class="…"；模板里可能有 ${...}，按 token 切。
        for m in re.finditer(r'class="([^"]*)"', source):
            for token in re.split(r"[\s${}'\"]+", m.group(1)):
                if re.fullmatch(r"[a-z][a-z0-9-]*", token or ""):
                    used.add(token)
            # 模板表达式里的字符串字面量同样会变成类名：
            #   `class="home-item ${unavailable?'unavailable':''}"` 产出
            #   「unavailable」。光按 token 切会把它漏掉，于是
            #   .home-item.unavailable 被误判成死规则。
            for expr in re.findall(r"\$\{([^}]*)\}", m.group(1)):
                for lit in re.findall(r"['\"]([a-z][a-z0-9-]*)['\"]", expr):
                    used.add(lit)
                for lit in re.findall(r"\b([a-z][a-z0-9-]*)\s*\+", expr):
                    used.add(lit)
        # classList.add/remove/toggle("x") 也是真实使用
        for m in re.finditer(r"classList\.\w+\(\s*['\"]([a-z][a-z0-9-]*)['\"]", source):
            used.add(m.group(1))
        # setAttribute('class', '…')
        for m in re.finditer(r"setAttribute\(\s*['\"]class['\"]\s*,\s*['\"]([^'\"]*)['\"]", source):
            for token in m.group(1).split():
                if re.fullmatch(r"[a-z][a-z0-9-]*", token):
                    used.add(token)
        # 自建 DOM 辅助：`node("button", undefined, "person-card")`。
        # 各工作区用这种写法，类名是第三个参数——不认它会把整族规则误删。
        for m in re.finditer(
                r"\b(?:node|el|elem|element|make|create\w*)\(\s*(['\"][^'\"]*['\"]|[^,()]*)"
                r"(?:,\s*(['\"][^'\"]*['\"]|undefined|null|[^,()]*))?"
                r",\s*['\"]([^'\"]+)['\"]", source):
            for token in m.group(3).split():
                if re.fullmatch(r"[a-z][a-z0-9-]*", token):
                    used.add(token)
        # 安全网：任何形如 classList 语义的裸短字符串都留着。
        # 宁可漏报死规则，也不要删掉在用的——漏报只是文件大一点，
        # 误删会让界面上某一块忽然没有样式，而且不报错。
        for m in re.finditer(r"['\"]([a-z][a-z0-9]*(-[a-z0-9]+)+)['\"]", source):
            used.add(m.group(1))
        # dataset 驱动的状态：data-* 名不等于 class 名，跳过。
    return used


def selector_classes(selector: str) -> set[str]:
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", selector))


def is_dead(selector: str, alive: set[str]) -> bool:
    """一条选择器是否已经没有任何渲染处。"""
    parts = [p for p in re.split(r"\s*[>+~]\s*|\s+", selector.strip()) if p]
    if not parts:
        return False
    found = False
    for part in parts:
        if part.startswith("@"):
            return False
        if ":" in part and not part.startswith("."):
            return False                      # 伪类/伪元素单独成段，不判
        cls = selector_classes(part)
        if not cls:
            name = re.sub(r"^[.#]", "", part).split(":")[0]
            if BUILTIN.match(name) or part.startswith(("::", ":")):
                continue
            return False                      # 认不出的形状，保守留着
        found = True
        relevant = cls - KEEP
        if relevant and (relevant & alive):
            return False
    return found


def parse_blocks(source: str):
    """产出 (选择器起点, 选择器终点, 块起点, 块终点, 深度)。"""
    out = []
    i = 0
    n = len(source)
    while i < n:
        j = source.find("{", i)
        if j < 0:
            break
        sel = source[i:j]
        # 找配对右括号
        depth = 1
        k = j + 1
        while k < n and depth:
            if source[k] == "{":
                depth += 1
            elif source[k] == "}":
                depth -= 1
            k += 1
        out.append((i, j, j, k, sel))
        i = k
    return out


def prune(source: str, alive: set[str]):
    kept, dropped = [], []
    out = source
    # 自内向外改写会把偏移打乱；改成自后向前应用。
    edits = []
    for start, selend, bodystart, bodyend, rawsel in reversed(parse_blocks(source)):
        sel = rawsel.strip()
        if not sel or sel.startswith("@"):
            continue
        if not re.match(r"^[.#:\[]", sel):
            continue
        parts = [p.strip() for p in sel.split(",") if p.strip()]
        if not parts:
            continue
        live = [p for p in parts if not is_dead(p, alive)]
        if len(live) == len(parts):
            kept.append(sel)
            continue
        if live:
            # 部分保留：只替换选择器文本，块体不动。
            new = ",\n".join(live)
            new = re.sub(r"[ \t]+", " ", new)
            lead = rawsel[:len(rawsel) - len(rawsel.lstrip())]
            edits.append((start + len(lead), selend, new))
            kept.append(new)
        else:
            # 整条删除：连同块体一起，并把前面的空白收掉。
            cut_from = start
            while cut_from > 0 and source[cut_from - 1] in " \t":
                cut_from -= 1
            edits.append((cut_from, bodyend, ""))
            dropped.append(sel[:100])
    for a, b, rep in edits:
        out = out[:a] + rep + out[b:]
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    return out, dropped, kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--css", action="append", default=[])
    args = ap.parse_args()
    if not (args.check or args.write):
        ap.error("需要 --check 或 --write")

    targets = [pathlib.Path(p) for p in args.css] or [PAGE / "styles.css", PAGE / "shell.css"]
    alive = rendered_classes()
    print("渲染代码里在用的 class：%d 个" % len(alive))

    total = 0
    for path in targets:
        source = path.read_text(encoding="utf-8")
        pruned, dropped, kept = prune(source, alive)
        total += len(dropped)
        print("\n%s" % path.name)
        print("  规则：保留 %d 条，删除 %d 条" % (len(kept), len(dropped)))
        print("  体积：%d → %d 字节" % (len(source), len(pruned)))
        if dropped and args.check:
            for sel in dropped[:15]:
                print("    - %s" % sel)
            if len(dropped) > 15:
                print("    … 另有 %d 条" % (len(dropped) - 15))
        if args.write and pruned != source:
            path.write_text(pruned, encoding="utf-8", newline="\n")
    if args.check and total:
        print("\n共 %d 条死规则。用 --write 改写。" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
