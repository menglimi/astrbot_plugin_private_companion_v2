"""Validate one explicit UTF-8 staging document, without loading AstrBot or storage."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from companion_v2.adapters.astrbot.staging_config import MAX_CONFIG_BYTES, StagingConfiguration, StagingConfigurationError


def main():
    parser = argparse.ArgumentParser(description="仅校验试运行配置的格式与边界，不初始化数据库或连接宿主。")
    parser.add_argument("configuration", type=Path, help="明确指定的 UTF-8 JSON 文件")
    args = parser.parse_args()
    try:
        with args.configuration.open("rb") as stream:
            payload = stream.read(MAX_CONFIG_BYTES + 1)
        if len(payload) > MAX_CONFIG_BYTES:
            raise StagingConfigurationError("configuration exceeds the UTF-8 document limit")
        configuration = StagingConfiguration.parse(payload.decode("utf-8"))
    except StagingConfigurationError as error:
        print(json.dumps({"valid": False, "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print(json.dumps({"valid": False, "reason": "cannot read a bounded UTF-8 configuration file"}), file=sys.stderr)
        return 2
    print(json.dumps({"valid": True, "fingerprint": configuration.fingerprint,
        "delivery_mode": configuration.delivery_mode, "capability_count": len(configuration.capabilities),
        "native_host_verified": False, "initialized": False, "started": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
