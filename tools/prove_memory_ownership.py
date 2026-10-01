"""非空性证明：逐个改坏实现，确认对应断言真的会红，再按 SHA-256 还原。

每个变异体只改一处、只针对一条行为。跑完打印「变异 → 失败的测试 → 是否已还原为
字节相同」。这不是测试套件的一部分，是一次性验收脚本。"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_ASTRBOT_ROOT = ROOT.parents[2]
PYTHON = _ASTRBOT_ROOT / "backend" / "python" / "python.exe"

CONTEXT = ROOT / "companion_v2" / "memory" / "context.py"
SERVICE = ROOT / "companion_v2" / "memory" / "service.py"
TOOL_LOOP = ROOT / "companion_v2" / "conversation" / "tool_loop.py"
PAGE = ROOT / "pages" / "陪伴小屋" / "memory-page.js"

MUTATIONS = (
    ("M1 关掉注入侧的让位判定", CONTEXT, "if self.delegated():", "if False and self.delegated():"),
    ("M2 关掉工具侧的让位判定", TOOL_LOOP,
     "        return self.memory is not None and memory_context is not None and memory_context.delegated()",
     "        return False"),
    # 探测现在一次交回「判定 + 活句柄」（推送复用同一条发现路径），所以变异体也
    # 跟着走 MemoryOwnerHandle：让「声明在但句柄空」被当成让位（静默降级）。
    ("M3 让「声明在但句柄空」被当成让位（静默降级）", ROOT / "companion_v2" / "adapters" / "astrbot" / "memory_owner.py",
     "    if owner is None:\n        return MemoryOwnerHandle(MemoryOwnership(owner=RENDER_SELF, reason=reason_if_none,",
     "    if owner is None:\n        return MemoryOwnerHandle(MemoryOwnership(owner=RENDER_EXTERNAL, reason=REASON_EXTERNAL_ACTIVE,"),
    ("M4 页面徽标改回「V2 独占记忆」的说法", PAGE,
     '"<span></span>V2 记忆库读取正常 <b>V2</b>"',
     '"<span></span>记忆读取正常 <b>V2</b>"'),
    ("M5 让 V2 自己的默认结论变成「让位」", ROOT / "companion_v2" / "capabilities" / "ownership.py",
     "        return MemoryOwnership(owner=RENDER_SELF, reason=self.reason)",
     "        return MemoryOwnership(owner=RENDER_EXTERNAL, reason=REASON_EXTERNAL_ACTIVE)"),
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tests():
    import os

    environment = dict(os.environ)
    parts = [str(_ASTRBOT_ROOT / "backend" / "app"), str(ROOT), str(ROOT.parent)]
    environment["PYTHONPATH"] = ";".join(parts)
    completed = subprocess.run(
        [PYTHON, "-X", "utf8", "-m", "unittest", "tests.test_memory_ownership"],
        cwd=ROOT, capture_output=True, text=True, env=environment,
    )
    output = completed.stdout + completed.stderr
    failed = set()
    for line in output.splitlines():
        for prefix in ("FAIL: ", "ERROR: "):
            if line.startswith(prefix):
                failed.add(line[len(prefix):].split(" ")[0].strip())
    ok = "\nOK" in output or output.rstrip().endswith("OK")
    if not ok and not failed:
        return ["<unparsed>:" + output.strip().splitlines()[-1][:80] if output.strip() else "<no output>"]
    return sorted(failed)


def main():
    baseline = run_tests()
    print(f"baseline failures: {baseline}")
    if baseline:
        print("baseline is not green; aborting")
        return 1
    results = []
    for label, path, old, new in MUTATIONS:
        original = path.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        assert text.count(old) == 1, (label, text.count(old))
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        try:
            failed = run_tests()
        finally:
            path.write_bytes(original)
        restored = hashlib.sha256(path.read_bytes()).hexdigest() == before
        results.append((label, failed, restored))
        print(f"{label}: {len(failed)} failing -> {failed} | restored byte-identical: {restored}")
    print("all restored:", all(item[2] for item in results))
    print("every mutation broke something:", all(item[1] for item in results))
    return 0 if all(item[1] and item[2] for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
