"""把插件身份从 `..._v2` 收编成 V1 的 `astrbot_plugin_private_companion`（7.0.0）。

默认只演练（dry-run），加 `--apply` 才写文件。设计原则：

* **一次改完**：页面里调用宿主的地址必须和宿主注册的 PREFIX 同时改，
  否则两边都对不上。所以这个脚本只在该改的范围内全量替换。
* **保护 V1 相关常量**：迁移要读 V1 的目录名、数据根兼容层要认旧 V2 目录名，
  这两个字符串必须保留，否则改名后读不到 V1/V2 的老数据。
* **测试跟着改**：测试里硬编码了大量旧名字，改名后必须一起改，否则一片红。

用法：
    python tools/rename_plugin_identity_700.py            # 演练
    python tools/rename_plugin_identity_700.py --apply    # 写入

改完后的验收顺序见 docs/PLUGIN_RENAME_700_20261018.md。
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD = "astrbot_plugin_private_companion"
NEW = "astrbot_plugin_private_companion"

SKIP_DIRS = {".git", "build", "node_modules", "__pycache__", ".verify-shards", "fixtures", "docs"}
SKIP_FILES = {
    "shell-preview.html",
    "shell-preview-mock.html",
    "tools/rename_plugin_identity_700.py",
    # 保护：这两个文件里的旧名字是「V1 数据目录」和「旧 V2 数据根」，不是插件身份。
    "astrbot_host/legacy_config.py",
    "astrbot_host/storage_location.py",
    "tests/test_data_root_compat.py",
}
SUFFIXES = {".py", ".js", ".cjs", ".json", ".yaml", ".yml", ".toml", ".html", ".css", ".md"}


def wanted(path: Path) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    if relative in SKIP_FILES:
        return False
    if set(path.relative_to(ROOT).parts) & SKIP_DIRS:
        return False
    return path.suffix in SUFFIXES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写入改动；默认只演练")
    arguments = parser.parse_args()

    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or not wanted(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        count = text.count(OLD)
        if not count:
            continue
        rows.append((path, count, text))

    total = sum(count for _, count, _ in rows)
    for path, count, _ in rows:
        print(f"{count:4d}  {path.relative_to(ROOT).as_posix()}")
    print(f"\n共 {len(rows)} 个文件 / {total} 处")
    if not arguments.apply:
        print("演练模式：加 --apply 才会写入。")
        return 0

    for path, _, text in rows:
        path.write_text(text.replace(OLD, NEW), encoding="utf-8", newline="\n")
    print(f"已写入 {len(rows)} 个文件。")
    print("别忘了手工步骤：AGENTS.md 的注册名约定、metadata.yaml 的 name、能力安装 id 的旧前缀兼容读取。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
