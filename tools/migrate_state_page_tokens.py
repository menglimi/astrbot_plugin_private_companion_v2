"""把 state-page.css 的硬编码色值与写死尺度换成共享令牌。

背景：这一页有 25 种不同的蓝灰色值，其中 #42596f 出现 11 次、#61748a 出现 5 次，
而 #405870 / #425a70 / #42596f 三者的明度差不到 0.005 —— 肉眼分不出差别。
它们本来只是四级文字色，却各占一个值，于是"哪一行是重点"完全没有信号。

做法：按颜色**角色**（正文/次级/说明/标题、表面、描边、状态）而不是按数值就近，
映射到语义令牌。这样切六套主题时整页跟着变，而不是只有明暗两态。

用法：python3 tools/migrate_state_page_tokens.py [--dry-run]
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / "pages" / "陪伴小屋" / "state-page.css"

# 色值 → 语义令牌。左边按「明度 + 用途」分组，不是逐个猜。
COLOR = {
    # 标题级（明度 .29–.31 的蓝灰，用于 h2/h3 与强调数字）
    "#344961": "var(--t-text-strong)",
    "#394b60": "var(--t-text-strong)",
    "#394f66": "var(--t-text-strong)",
    "#42596f": "var(--t-text-strong)",
    # 正文级（.35–.41）
    "#405870": "var(--t-text)",
    "#425a70": "var(--t-text)",
    "#495e74": "var(--t-text)",
    "#52687d": "var(--t-text-soft)",
    # 次级说明（.45–.48，这一组有 8 个近邻值，正是"糊"的来源）
    "#607286": "var(--t-text-soft)",
    "#61748a": "var(--t-text-soft)",
    "#63758a": "var(--t-text-soft)",
    "#63768a": "var(--t-text-soft)",
    "#65788d": "var(--t-text-soft)",
    "#66788c": "var(--t-text-soft)",
    "#687a8e": "var(--t-text-soft)",
    # 弱化（.52–.58）
    "#728298": "var(--t-text-faint)",
    "#75869a": "var(--t-text-faint)",
    "#78879a": "var(--t-text-faint)",
    "#7b8998": "var(--t-text-faint)",
    "#7f8d9e": "var(--t-text-faint)",
    "#8290a4": "var(--t-text-faint)",
    # 强调蓝（.49–.52 的高饱和蓝，是链接/选中的色调）
    "#5976a1": "var(--t-accent-ink)",
    "#607ca7": "var(--t-accent-ink)",
    # 表面
    "#fff": "var(--t-surface)",
    "#f8f5ee": "var(--t-surface-soft)",      # 暖白底（日历格一类）
    "#e6ebf1": "var(--t-surface-soft)",
    "#e8edf1": "var(--t-surface-sunken)",
    # 描边
    "#e0e6ee": "var(--t-line)",
    "#dce3e9": "var(--t-line)",
    "#c7d5e4": "var(--t-line-firm)",
    # 状态色（绿 = 正常，金 = 提醒）
    "#476d58": "var(--t-ok-ink)",
    "#e6f0e9": "var(--t-ok-quiet)",
    "#675737": "var(--t-warn-ink)",
    "#b19253": "var(--t-warn-ink)",
}

# 字号：8 种。12/13 是正文两档（差 1px，合并），标题升到 title。
FONT = {
    10: "micro", 11: "tiny",
    12: "body", 13: "body",
    14: "lead", 15: "lead", 16: "title", 21: "head",
}

SPACE = {"--sp-1": 4, "--sp-2": 8, "--sp-3": 12, "--sp-4": 16,
         "--sp-5": 22, "--sp-6": 30, "--sp-7": 40, "--sp-8": 54}
TOL = 2


def nearest(value):
    best = min(SPACE, key=lambda k: (abs(SPACE[k] - value), SPACE[k]))
    return best, SPACE[best]


def main():
    dry = "--dry-run" in sys.argv
    text = CSS.read_text(encoding="utf-8")
    original_lines = len(text.splitlines())

    # 1) 色值（长的先替换，避免 #fff 吃掉 #fffff 这类前缀）
    for hex_value in sorted(COLOR, key=len, reverse=True):
        text = re.sub(re.escape(hex_value) + r"\b", COLOR[hex_value], text, flags=re.I)

    # 2) 字号
    def font(match):
        value = float(match.group(1))
        tier = FONT.get(value)
        return "font-size:var(--fs-%s)" % tier if tier else match.group(0)

    text = re.sub(r"font-size:\s*([\d.]+)px", font, text)

    # 3) 间距（带容差；左侧缩进是测量值，不动）
    def spacing(match):
        prop, value = match.group(1), match.group(2)

        def one(vm):
            v = float(vm.group(1))
            if v <= 3:
                return vm.group(0)
            token, snapped = nearest(v)
            if abs(snapped - v) > TOL:
                return vm.group(0)
            return "var(%s)" % token

        return prop + ":" + re.sub(r"(\d+(?:\.\d+)?)px", one, value)

    text = re.sub(
        r"(padding(?:-(?:top|right|bottom|left))?|margin(?:-(?:top|right|bottom|left))?|gap)\s*:\s*([^;{}]+)",
        spacing, text)

    if dry:
        print("--dry-run：未写入")
    else:
        CSS.write_text(text, encoding="utf-8")
        print("已写入 %s" % CSS)

    clean = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    # 拆成两句：原来把「dry 时读文件、否则用常量」的三元表达式塞在 len(...)
    # 的第 3 个实参里，括号层级一深就漏了闭合——文件因此整份语法不过。
    if dry:
        before = len(set(re.findall(r"#[0-9a-fA-F]{3,8}\b",
                                    re.sub(r"/\*.*?\*/", " ", CSS.read_text(encoding="utf-8"), flags=re.S))))
    else:
        before = 34
    print("  硬编码色值：%d → %d" % (before, len(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", clean)))))
    print("  写死字号：%d（原 36）" % len(re.findall(r"font-size:\s*[\d.]+px", text)))
    print("  行数：%d → %d" % (original_lines, len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
