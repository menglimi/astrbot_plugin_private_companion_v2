"""把 models-page.css 的自造色板与写死尺度换成共享令牌。

背景：这一页曾经自带一整套色板（--m-card/--m-ink/--m-accent…一共 21 个变量，
每个都写死十六进制），外加一份手写的 html[data-theme="night"] 暗色副本。
后果有两个：
  1. 六套主题切换时这一页只有明暗两态，其余四套（暮色/深林/高对比）不生效；
  2. 它逃过了 audit_theme_tokens.py 的检查——那个脚本只看 var(--t-*) 的引用，
     不检查有没有人绕开令牌自己造色。

做法：把 --m-* 的定义改成指向语义令牌的别名，再顺手把写死的字号与间距
换成 --fs-* / --sp-*。保留 --m-* 这些名字本身，因为 CSS 里有 300 多处引用它们，
改名要动的地方远多于改值——而"改值不改名"已经足以让主题生效。

用法：python3 tools/migrate_models_page_tokens.py [--dry-run]
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / "pages" / "陪伴小屋" / "models-page.css"

# --m-* → 语义令牌。左边是语义角色，不是颜色外观：
# 卡片底 / 次级底 / 正文三级 / 两种描边 / 选中态 / 强调色 / 三档状态色。
ALIAS = {
    "m-card":      "var(--t-surface)",
    "m-card2":     "var(--t-surface-soft)",
    "m-ink":       "var(--t-text)",
    "m-ink2":      "var(--t-text-soft)",
    "m-ink3":      "var(--t-text-faint)",
    "m-line":      "var(--t-line)",
    "m-line2":     "var(--t-line-firm)",
    "m-sel":       "var(--t-accent-quiet)",
    "m-sel2":      "var(--t-surface-sunken)",
    "m-accent":    "var(--t-accent-ink)",
    "m-accent2":   "var(--t-accent-solid)",
    "m-accent3":   "var(--t-accent)",
    "m-green":     "var(--t-ok-ink)",
    "m-green-bg":  "var(--t-ok-quiet)",
    "m-amber":     "var(--t-warn-ink)",
    "m-amber-bg":  "var(--t-warn-quiet)",
    "m-red":       "var(--t-risk-ink)",
    "m-red-bg":    "var(--t-risk-quiet)",
    "m-shadow":    "var(--t-shadow)",
    # 圆角与间距也一并接上。
    "m-r":         "var(--r-md)",
    "m-rs":        "var(--r-sm)",
}

# 字号角色映射。这一页有 15 种字号，收成共享档位。
FONT = {
    9: "micro", 9.5: "micro", 10: "micro", 10.5: "micro",
    11: "tiny", 11.5: "tiny",
    12: "body", 12.5: "body",
    13: "body", 13.5: "lead", 14: "lead",
    15: "title", 18: "head", 19: "head", 20: "head",
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
    original = text

    # 1) 把 --m-* 的定义（值那一侧）换成语义令牌。
    #    只改写「定义处」，引用处 var(--m-card) 原样保留。
    #
    #    两个坑都在同一个正则里：
    #      · 定义常常一行写好几个（`--m-card:#fff; --m-card2:#fafaff;`），
    #        所以值要匹配到分号为止，不能用「后面紧跟 ; 或 }」当条件——那样第一个之后全漏；
    #      · 变量名有前缀重名（--m-green 与 --m-green-bg），
    #        一次 re.sub 里替换掉 --m-green 会吃掉 --m-green-bg 的匹配位置。
    #        改成按变量逐个替换，互不干扰。
    for name, token in ALIAS.items():
        text = re.sub(
            r"--%s\s*:\s*(?:#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))\s*;" % re.escape(name),
            "--%s:%s;" % (name, token),
            text,
        )

    # 1b) 非色值的 --m-* 也要接上：圆角与阴影。
    #     上一步的正则只吃色值，圆角/阴影这两类名字会漏在网络里当写死值。
    for name, pattern, token in (
        ("m-r", r"14px", "var(--r-md)"),
        ("m-rs", r"10px", "var(--r-sm)"),
        ("m-shadow", r"[^;]*?(?=;)", "var(--t-shadow)"),
    ):
        text = re.sub(
            r"--%s\s*:\s*%s\s*;" % (re.escape(name), pattern),
            "--%s:%s;" % (name, token),
            text,
        )

    # 2) 删掉整块手写的暗色副本 —— 语义令牌自己会随主题变，副本不再需要。
    text = re.sub(
        r'\nhtml\[data-theme="(?:night|dark)"\][^{]*\{[^}]*\}',
        "", text)

    # 3) 写死的白色：实心底上的前景用 --t-on-solid，浮层用 --t-surface-raised。
    #    这两处漏掉的话，暗色主题下会变成白底白字或白点。
    text = text.replace("background:#fff;", "background:var(--t-surface-raised);")
    text = text.replace("color:#fff;", "color:var(--t-on-solid);")
    text = text.replace("background:#fff}", "background:var(--t-surface-raised)}")
    text = text.replace("color:#fff}", "color:var(--t-on-solid)}")

    # 3b) 阴影与遮罩。写死的 rgba 阴影在暗色主题下会发灰，
    #     遮罩更明显——深灰遮罩铺在更深的背景上，模态一开反而像被"点亮"了一块。
    for old, new in (
        ("box-shadow:0 1px 3px rgba(59,62,82,.08)", "box-shadow:var(--t-shadow)"),
        ("box-shadow:0 8px 28px rgba(59,62,82,.16)", "box-shadow:var(--t-shadow-lift)"),
        ("box-shadow:-14px 0 44px rgba(30,32,48,.16)", "box-shadow:var(--t-shadow-lift)"),
        ("background:rgba(30,32,48,.3)", "background:var(--scrim)"),
    ):
        text = text.replace(old, new)

    # 4) 字号收进共享档位。
    def font(match):
        value = float(match.group(1))
        tier = FONT.get(value)
        return "font-size:var(--fs-%s)" % tier if tier else match.group(0)

    text = re.sub(r"font-size:\s*([\d.]+)px", font, text)

    # 5) 间距收进共享档位，带容差保护。
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

    # 报告
    left_hex = len(re.findall(r"#[0-9a-fA-F]{3,8}\b", re.sub(r"/\*.*?\*/", " ", text, flags=re.S)))
    left_font = len(re.findall(r"font-size:\s*[\d.]+px", text))
    palettes = len(re.findall(r"--m-[a-z0-9]+\s*:\s*(?:#|rgba?\()", text))
    print("  剩余硬编码色值：%d（原 35 十六进制 + 14 rgb）" % left_hex)
    print("  剩余写死字号：%d（原 101）" % left_font)
    print("  仍是真实色值的 --m-* 定义：%d（原 21）" % palettes)
    print("  手写暗色副本：%d 块（原 2）"
          % len(re.findall(r'html\[data-theme="(?:night|dark)"\]', text)))
    print("  文件行数：%d → %d" % (len(original.splitlines()), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
