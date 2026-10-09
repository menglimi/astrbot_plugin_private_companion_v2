# -*- coding: utf-8 -*-
r"""把两张样式表按「上下文 + 选择器」逐条对齐比较，列出消失与被改的规则。

为什么不用正则 `([^{}]+)\{([^{}]*)\}`：媒体查询会嵌套，
`@media(...){ .a{...} }` 里外两层都会被这条正则各抓一半，于是
「整条消失的选择器」里混进大量其实没消失的规则，diff 结果不可信。
我第一版就是这么错的——报出 85 条「消失」，其中多数只是被媒体查询
的括号切碎后重新拼接的名字对不上。

正确做法：维护一个块栈，进入 `@media` 时把前缀压栈，产出规则时
拼成 `@media(...) | .selector` 这样的带上下文键。
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path


def scan(path: Path):
    """产出 {上下文|选择器: [声明块, ...]}。"""
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)

    rules: dict[str, list[str]] = {}
    stack: list[str] = []          # 当前所处的 at-rule 上下文
    i, n = 0, len(src)
    buf = ""

    while i < n:
        ch = src[i]
        if ch == "{":
            head = buf.strip()
            buf = ""
            # head 以 @ 开头（media/supports/keyframes）→ 压栈，不产出规则
            if head.startswith("@"):
                stack.append(re.sub(r"\s+", " ", head))
            else:
                # 取到匹配的右括号
                depth, k = 1, i + 1
                while k < n and depth:
                    if src[k] == "{":
                        depth += 1
                    elif src[k] == "}":
                        depth -= 1
                    k += 1
                body = src[i + 1:k - 1]
                sel = re.sub(r"\s+", " ", head)
                key = (" | ".join(stack) + " | " if stack else "") + sel
                rules.setdefault(key, []).append(body.strip())
                i = k
                continue
        elif ch == "}":
            if stack:
                stack.pop()
            buf = ""
            i += 1
            continue
        else:
            buf += ch
        i += 1
    return rules


def main() -> int:
    old = scan(Path(sys.argv[1]))
    new = scan(Path(sys.argv[2]))
    scope = sys.argv[3] if len(sys.argv) > 3 else r"shell|stage|rail|#main|room-|voxel|topbar|panel|#homeShell"

    pat = re.compile(scope)

    gone = [k for k in old if k not in new and pat.search(k)]
    changed = [k for k in old if k in new and old[k] != new[k] and pat.search(k)]

    print("旧表规则 %d 条，新表规则 %d 条" % (len(old), len(new)))
    print()
    print("=== 消失的规则（%d 条，含关键词的 %d 条）===" % (sum(1 for k in old if k not in new), len(gone)))
    for k in gone:
        print("  %-64s %s" % (k[:64], " ‖ ".join(old[k])[:100]))
    print()
    print("=== 定义体变了的规则（%d 条）===" % len(changed))
    for k in changed:
        print("  %s" % k[:70])
        print("     旧: %s" % " ‖ ".join(old[k])[:140])
        print("     新: %s" % " ‖ ".join(new[k])[:140])
    return 0


if __name__ == "__main__":
    sys.exit(main())
