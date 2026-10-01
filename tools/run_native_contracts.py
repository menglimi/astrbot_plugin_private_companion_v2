"""Opt-in installed-host contract tests. Never run from AstrBot's data root.

Usage: <AstrBot Python> -X utf8 tools/run_native_contracts.py --host-source <app>
All AstrBot import-time data is redirected before its first import. HTTP is
handled by httpx.MockTransport, WebSocket acknowledgements by an in-memory peer.
"""

import argparse
import os
from pathlib import Path
import socket
import sys
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-source", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    source = args.host_source.resolve()
    if not (source / "astrbot" / "__init__.py").is_file() or "astrbot" in sys.modules:
        raise SystemExit("provide an installed source tree before any AstrBot import")
    previous = Path.cwd()
    attempts = []
    state = threading.local()
    original_pair, original_connect = socket.socketpair, socket.socket.connect
    def internal_pair(*args, **kwargs):
        state.internal_pair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            state.internal_pair = False
    def guarded_connect(sock, address):
        # Windows implements asyncio's private socketpair using loopback TCP.
        # Allow only that call path, not arbitrary localhost/production services.
        if getattr(state, "internal_pair", False) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        return no_network(sock, address)
    def no_network(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("network access is disabled in native contract tests")
    with TemporaryDirectory(prefix="companion-v2-native-", ignore_cleanup_errors=True) as directory:
        try:
            os.chdir(directory)
            sys.path[:0] = [str(repo), str(source)]
            with patch.dict(os.environ, {"ASTRBOT_ROOT": directory}), \
                    patch.object(socket, "socketpair", internal_pair), \
                    patch.object(socket.socket, "connect", guarded_connect), \
                    patch.object(socket.socket, "connect_ex", no_network), \
                    patch.object(socket, "create_connection", no_network):
                import astrbot
                from astrbot.core.utils.astrbot_path import get_astrbot_data_path
                if Path(get_astrbot_data_path()).resolve() != Path(directory).resolve() / "data":
                    raise AssertionError("host data root was not isolated")
                from tools.native_contract_cases import NativeContractTests
                result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeContractTests))
                print(f"AstrBot {astrbot.__version__}; native contract network attempts: {len(attempts)}; temporary data root verified.")
                return 0 if result.wasSuccessful() and not attempts else 1
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    raise SystemExit(main())
