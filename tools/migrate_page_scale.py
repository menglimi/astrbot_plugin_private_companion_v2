"""把一页的写死尺度换成共享令牌。

写这个通用版的原因：剩下还有七八个页面要做同样的事，逐页手抄一份脚本
既慢又会让每页的映射口径慢慢分叉。差异只有三处，都做成参数：
字号的数值→档位映射、间距容差、以及需要豁免的左侧缩进值。

用法：
    python3 tools/migrate_page_scale.py setup-guide.css              # 预演
    python3 tools/migrate_page_scale.py setup-guide.css --write      # 写入

默认只预演。**先预演看一眼差异再写**——写死值里混着"节奏"与"实测值"，
后者吸附到令牌就会错位（列表项目符号离文字多远、卡片离轨道线多远）。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages" / "陪伴小屋"

# 尺度令牌的档位值。与 tokens.css 保持一致；改这里就是改吸附目标。
SPACE = {"--sp-1": 4, "--sp-2": 8, "--sp-3": 12, "--sp-4": 16,
         "--sp-5": 22, "--sp-6": 30, "--sp-7": 40, "--sp-8": 54}
RADIUS = {"--r-2xs": 3, "--r-xs": 6, "--r-sm": 9, "--r-md": 12, "--r-lg": 16, "--r-xl": 22}

# 字号档位。数值→档位按**角色**而不是就近：
# 12 与 13 挤在一起时都算正文，14 起升一档，否则页面会同时出现
# "12 是标签、12 是正文"这种自相矛盾的层级。
#
# 2026-10-01 补齐两端的空档。之前这张表只覆盖 9–36，于是表外的值在预演里
# 落进「未处理」，看起来像"该手工判断的实测值"，实际是**机械缺口**：
#   · 下界：维护页有 59 处 7px/8px（最该升上去的那一批），原样留着就等于
#     迁移完仍写着全站最小的字号。它们按角色并入 micro——micro 已是唯一的
#     "最小档"，再单独留一档比它更小的字号，与"八档"的说法直接冲突。
#   · 上界：状态页 23px、语义页 34/38/42/46px。这些是数字展示与时钟，
#     角色上是 display（23）与 hero（34–46）；档位本身是上限，36 以上不再
#     细分，否则同一屏会出现 42 与 46 两个只差 4px 的"不同档"。
# 两端都只是把表外值收进已有八档，没有新增档位、也没有放宽容差。
FONT = {
    7: "micro", 8: "micro",
    9: "micro", 9.5: "micro", 10: "micro", 10.5: "micro",
    11: "tiny", 11.5: "tiny",
    12: "body", 12.5: "body", 13: "body", 13.5: "body",
    14: "lead", 14.5: "lead", 15: "lead", 15.5: "lead",
    16: "title", 17: "title",
    18: "head", 19: "head", 20: "head", 21: "head",
    22: "display", 23: "display", 24: "display", 25: "display", 26: "display", 27: "display", 28: "display",
    29: "hero", 30: "hero", 31: "hero", 32: "hero", 34: "hero", 36: "hero",
    38: "hero", 42: "hero", 46: "hero",
}

# ≤3px 是描边、微调与 1px 分隔线，不构成版式节奏。
FLOOR = 3
TOLERANCE = 2

# 属性名必须从声明处开始，不能匹配别的属性的尾巴。
# 反例：`scroll-margin-top:16px` —— 没有这个断言时，正则会在 `margin-top:`
# 那里接上去，把审计的 SPACING 集合**管不到**的属性也一起改掉。
# 改一个审计看不见的值，等于让"迁移完了"这句话失去依据。
# 加了断言之后，命中的属性与 audit_page_scale.py 的 SPACING 一一对应。
SPACING_PROP = re.compile(
    r"(?<![-\w])(padding(?:-(?:top|right|bottom|left))?|margin(?:-(?:top|right|bottom|left))?|gap)\s*:\s*([^;{}]+)")

# clamp(下界, 流体值, 上界)。三个参数要分开看，不能整体当成一个数值去吸附。
CLAMP = re.compile(r"clamp\(([^()]*)\)")


def token_sum(target):
    """把 target 精确写成若干 --sp-* 之和；凑不出就返回 None。

    给 clamp() 的边界用。边界是**边界**不是节奏档位：上界差 4px，在大屏上
    就是整块留白少一截，肉眼直接看得出来。所以超出容差时不吸附，
    而是用令牌相加把原值精确表达出来——几何不变，又不留游离的写死值。
    """
    items = list(SPACE.items())
    for key, value in items:
        if value == target:
            return "var(%s)" % key
    for key_a, value_a in items:
        for key_b, value_b in items:
            if value_a + value_b == target:
                return "calc(var(%s) + var(%s))" % (key_a, key_b)
    return None


def nearest(table, value):
    key = min(table, key=lambda k: (abs(table[k] - value), table[k]))
    return key, table[key]


def migrate(text, *, measured=()):
    """返回 (新文本, 改动计数, 未处理的残留清单)。"""
    counts = {"font": 0, "space": 0, "radius": 0}
    left = {"font": [], "space": [], "radius": []}

    def font(match):
        value = float(match.group(1))
        tier = FONT.get(value)
        if tier is None:
            left["font"].append(match.group(0))
            return match.group(0)
        counts["font"] += 1
        return "font-size:var(--fs-%s)" % tier

    text = re.sub(r"font-size:\s*([\d.]+)px", font, text)

    def radius(match):
        value = float(match.group(1))
        # "整条边都圆掉"不是档位，是一个语义：--r-pill（tokens.css 里 999px）。
        # 原来是 >=50 就原样留着，于是 99px 这种近似值落在两不管的地带：
        # 它既没进档位，也不在审计的 999px 豁免里，只能一直挂在告警上。
        # 这几页本来就有 var(--r-pill) 在用（models 5 处、semantic 2 处、
        # action 1 处），所以换过去是同一种说法，不是新增词汇。
        if value >= 50:
            counts["radius"] += 1
            return "border-radius:var(--r-pill)"
        key, snapped = nearest(RADIUS, value)
        if abs(snapped - value) > TOLERANCE:
            left["radius"].append(match.group(0))
            return match.group(0)
        counts["radius"] += 1
        return "border-radius:var(%s)" % key

    text = re.sub(r"border-radius:\s*([\d.]+)px", radius, text)

    def clamp_bounds(inner):
        """clamp(下界, 流体值, 上界)：两个边界走令牌，中间的流体值原样保留。

        不做这一步时，`clamp(20px,3vw,34px)` 的下界会被通用规则改成
        var(--sp-5)，上界 34px 因为超出容差留在原地——半迁移的形态最坏：
        值改了一半，审计照样红，而人看着"已经用了令牌"以为迁完了。
        """
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) != 3:
            left["space"].append("clamp(%s)" % inner)
            return "clamp(%s)" % inner
        for index in (0, 2):
            m = re.fullmatch(r"(\d+(?:\.\d+)?)px", parts[index])
            if not m:
                continue
            v = float(m.group(1))
            if v <= FLOOR:
                continue
            key, snapped = nearest(SPACE, v)
            if abs(snapped - v) <= TOLERANCE:
                parts[index] = "var(%s)" % key
                counts["space"] += 1
                continue
            exact = token_sum(v)
            if exact:
                parts[index] = exact
                counts["space"] += 1
                continue
            left["space"].append(parts[index])
        return "clamp(%s)" % ", ".join(parts)

    def spacing(match):
        prop, value = match.group(1), match.group(2)
        # 左侧缩进是实测值（项目符号离文字、卡片离轨道线），吸附会错位。
        if prop in ("padding-left", "margin-left") or prop in ("padding", "margin"):
            values = value.split()
            side = values[-1] if len(values) == 4 else (values[0] if prop.startswith("padding") and len(values) == 2 else None)
            if side and side.rstrip() in {("%gpx" % m) for m in measured}:
                left["space"].append("%s:%s" % (prop, value))
                return match.group(0)

        def one(vm):
            v = float(vm.group(1))
            if v <= FLOOR:
                return vm.group(0)
            key, snapped = nearest(SPACE, v)
            if abs(snapped - v) > TOLERANCE:
                left["space"].append(vm.group(0))
                return vm.group(0)
            counts["space"] += 1
            return "var(%s)" % key

        # clamp() 整段先摘出来单独处理，否则通用规则会把它的上界也一起吸附。
        slots = []

        def stash(cm):
            slots.append(clamp_bounds(cm.group(1)))
            return "\x00%d\x00" % (len(slots) - 1)

        masked = CLAMP.sub(stash, value)
        masked = re.sub(r"(\d+(?:\.\d+)?)px", one, masked)
        for index, tokenized in enumerate(slots):
            masked = masked.replace("\x00%d\x00" % index, tokenized)
        return prop + ":" + masked

    text = re.sub(SPACING_PROP, spacing, text)
    return text, counts, left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", help="文件名，如 setup-guide.css")
    ap.add_argument("--write", action="store_true", help="真的写入（默认只预演）")
    ap.add_argument("--measured", default="", help="逗号分隔的左侧缩进实测值，如 19,44,48")
    args = ap.parse_args()

    path = PAGES / args.page
    if not path.exists():
        print("找不到 %s" % path)
        return 1
    measured = tuple(float(v) for v in args.measured.split(",") if v.strip())
    text = path.read_text(encoding="utf-8")
    lines_before = len(text.splitlines())
    new, counts, left = migrate(text, measured=measured)

    print("预演 %s" % args.page)
    print("  字号 → 令牌 %d 处" % counts["font"])
    print("  间距 → 令牌 %d 处" % counts["space"])
    print("  圆角 → 令牌 %d 处" % counts["radius"])
    for kind in ("font", "space", "radius"):
        if left[kind]:
            uniq = sorted(set(left[kind]))
            print("  未处理（%s）%d 处：" % (kind, len(left[kind])) + "、".join(uniq[:8])
                  + ("…" if len(uniq) > 8 else ""))
    print("  行数 %d → %d" % (lines_before, len(new.splitlines())))

    if not args.write:
        print("\n（未写入。确认上面的「未处理」都是该保留的实测值后加 --write）")
        return 0
    # 写文件必须显式给 newline="\n"。Windows 上 path.write_text 默认
    # newline=None，会把每个 \n 翻成 os.linesep 也就是 \r\n——
    # 一次迁移就把整份文件的行尾换掉，与工程约定的 LF 冲突，
    # 而且 diff 会变成"全文件都改了"，真正的改动反而看不出来。
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    print("\n已写入 %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
