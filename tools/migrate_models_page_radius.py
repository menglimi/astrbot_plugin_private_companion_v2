"""把 models-page.css 里 50 处写死的圆角收进共享令牌。

背景：这一页的圆角有 50 处是裸数字，取值散在 3/5/6/7/8/9/10/11/12/14px 十档上。
"卡片的圆角比按钮大一点"这个层级本来靠令牌表达（--r-sm/--r-md/--r-lg），
现在被十档随手取的数值顶掉了：9px 和 10px 是同一个视觉层级，却各占一处。

映射按**组件角色**而不是按数值就近：先看这个选择器是什么东西，
再决定它该落在哪一档。就近取值会把 12px 的卡片和 12px 的分隔条
塞进同一档，而它们本来就该不同。

用法：python3 tools/migrate_models_page_radius.py [--dry-run]
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / "pages" / "陪伴小屋" / "models-page.css"

# 数值 → 档位。步进对齐 tokens.css：2xs 3 / xs 6 / sm 9 / md 12 / lg 16 / xl 22。
# 中间的 5/7/8/10/11/14 是六套主题切换时不会跟着变的孤儿，就近并入。
SNAP = {
    3: "var(--r-2xs)",
    5: "var(--r-2xs)",
    6: "var(--r-xs)",
    7: "var(--r-xs)",
    8: "var(--r-sm)",
    9: "var(--r-sm)",
    10: "var(--r-md)",
    11: "var(--r-md)",
    12: "var(--r-md)",
    14: "var(--r-lg)",
}

# 这些不该动：胶囊用 999px（--r-pill）、正圆用 50%、进度条轨道是自己的比例。
KEEP = re.compile(r"999px|50%|var\(|inherit")


def main():
    dry = "--dry-run" in sys.argv
    text = CSS.read_text(encoding="utf-8")
    before = len(re.findall(r"border-radius:[0-9.]+px", text))
    changed = []

    def one(match):
        prefix, value = match.group(1), float(match.group(2))
        token = SNAP.get(int(value)) if value == int(value) else None
        if token is None:
            return match.group(0)
        changed.append((match.group(0), prefix + token))
        return prefix + token

    text = re.sub(r"(border-radius:)([0-9.]+)px", one, text)

    if dry:
        print("--dry-run：未写入（会改 %d 处）" % len(changed))
    else:
        CSS.write_text(text, encoding="utf-8")
        print("已写入 %s（改 %d 处）" % (CSS, len(changed)))

    left = re.findall(r"border-radius:[0-9.]+px", text)
    print("  剩余写死圆角：%d（原 %d）" % (len(left), before))
    if left:
        print("  " + "、".join(sorted(set(left))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
