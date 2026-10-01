"""Audited Python dependency boundary for disposable native acceptance workers.

This detects legacy dependencies in trusted test processes; it is not an OS
sandbox for arbitrary native code. Never run untrusted downloaded providers here.
"""

from __future__ import annotations

import ast
import builtins
from contextlib import contextmanager
import importlib
import importlib.abc
import os
from pathlib import Path
import socket
import sys
import threading
from urllib.parse import unquote, urlsplit
from unittest.mock import patch

LEGACY_IDS = frozenset({"astrbot_plugin_private_companion", "astrbot_plugin_remember_you"})
LEGACY_ALIASES = LEGACY_IDS | {"privatecompanion", "privatecompanionplugin"}
LEGACY_FILES = frozenset({"companions.json", "memory_companion.db", "creative_state.json"})


class NativeAcceptanceViolation(RuntimeError):
    pass


def legacy_name(value):
    return isinstance(value, str) and any(part.casefold() in LEGACY_ALIASES for part in value.split("."))


def path_value(value):
    if isinstance(value, int) or value is None:
        return None
    text = os.fsdecode(value)
    if text == ":memory:":
        return None
    if text.startswith("file:"):
        parsed = urlsplit(text)
        if parsed.path == ":memory:":
            return None
        text = unquote(("//" + parsed.netloc if parsed.netloc else "") + parsed.path)
        if os.name == "nt" and len(text) > 3 and text[0] == "/" and text[2] == ":":
            text = text[1:]
    return Path(text).absolute().resolve()


def legacy_path(path):
    return any(part.casefold() in LEGACY_IDS | LEGACY_FILES for part in path.parts)


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left), _literal(node.right)
        return left + right if left is not None and right is not None else None
    return None


def scan_dependencies(source, filename="source.py"):
    """Check executable references, allowing inert compatibility metadata."""
    findings = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        code = None
        if isinstance(node, ast.Import) and any(legacy_name(a.name) for a in node.names):
            code = "legacy_import"
        elif isinstance(node, ast.ImportFrom):
            if legacy_name(node.module) or any(legacy_name(a.name) for a in node.names):
                code = "legacy_import"
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            values = [_literal(arg) for arg in node.args]
            if name in {"__import__", "import_module", "find_spec"} and any(legacy_name(v) for v in values):
                code = "legacy_import"
            elif name in {"get_registered_star", "get_star", "get_plugin"} and any(legacy_name(v) for v in values):
                code = "legacy_discovery"
            elif name in {"open", "connect", "read_text", "read_bytes", "iterdir", "scandir", "listdir"}:
                if any(v and any(part.casefold() in LEGACY_IDS | LEGACY_FILES
                                 for part in v.replace("\\", "/").split("/")) for v in values):
                    code = "legacy_data"
        if code:
            findings.append({"file": filename, "line": node.lineno, "code": code})
    return findings


class NativeAcceptanceGuard(importlib.abc.MetaPathFinder):
    def __init__(self, *, root, read_roots=(), forbidden_roots=()):
        self.root = Path(root).resolve()
        self.read_roots = (self.root, *(Path(p).resolve() for p in read_roots))
        self.forbidden_roots = tuple(Path(p).resolve() for p in forbidden_roots)
        self.violations = []
        self.trusted_native_loads = []
        self._bootstrap_libraries = frozenset()
        self.active = False
        self._network = threading.local()
        self._patches = []

    def deny(self, code):
        self.violations.append({"code": code})
        raise NativeAcceptanceViolation(code)

    @contextmanager
    def runtime_bootstrap(self, library_names):
        """Allow named runtime DLLs only while the worker preloads trusted code.

        The worker must leave this scope before importing any copied plugin.
        File, legacy dependency, process and network guards stay active.
        """
        if self._bootstrap_libraries:
            raise RuntimeError("nested native bootstrap is not supported")
        self._bootstrap_libraries = frozenset(library_names)
        try:
            yield
        finally:
            self._bootstrap_libraries = frozenset()

    def check_module(self, name):
        if legacy_name(name):
            self.deny("legacy_import")

    def check_path(self, value, *, write=False):
        path = path_value(value)
        if path is None:
            return
        if legacy_path(path):
            self.deny("legacy_data")
        if any(path.is_relative_to(p) for p in self.forbidden_roots):
            self.deny("installed_data_or_plugin_access")
        roots = (self.root,) if write else self.read_roots
        if not any(path.is_relative_to(p) for p in roots):
            self.deny("outside_write_root" if write else "outside_read_roots")

    def find_spec(self, fullname, path=None, target=None):
        if self.active:
            self.check_module(fullname)
        return None

    def audit(self, event, args):
        if not self.active:
            return
        if event == "import":
            self.check_module(args[0])
        elif event == "open":
            mode, flags = args[1], args[2]
            write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            self.check_path(args[0], write=write)
        elif event == "sqlite3.connect":
            self.check_path(args[0], write=True)
        elif event in {"os.listdir", "os.scandir", "os.chdir"}:
            self.check_path(args[0] if args else os.getcwd())
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"}:
            self.check_path(args[0], write=True)
        elif event in {"os.rename", "os.link", "os.symlink"}:
            self.check_path(args[0], write=True)
            self.check_path(args[1], write=True)
        elif event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "os.exec", "os.startfile", "os.startfile/2"}:
            self.deny("child_process")
        elif event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"}:
            if not getattr(self._network, "socketpair", False):
                self.deny("network")
        elif event == "ctypes.dlopen":
            if args[0] in self._bootstrap_libraries:
                self.trusted_native_loads.append(args[0])
            else:
                self.deny("native_loader")

    def discover(self, name, stars=()):
        if legacy_name(name):
            self.deny("legacy_discovery")
        return next((s for s in self.catalog(stars) if getattr(s, "name", None) == name), None)

    def catalog(self, stars):
        result = list(stars)
        if any(legacy_name(getattr(s, "root_dir_name", None)) or legacy_name(getattr(s, "name", None)) for s in result):
            self.deny("legacy_discovery")
        return result

    def assert_clean(self):
        if any(legacy_name(name) for name in sys.modules):
            self.deny("legacy_module_cached")
        for module in tuple(sys.modules.values()):
            source = getattr(module, "__dict__", {}).get("__file__")
            if isinstance(source, str):
                path = path_value(source)
                if legacy_path(path) or any(path.is_relative_to(root) for root in self.forbidden_roots):
                    self.deny("forbidden_module_origin")
        if self.violations:
            raise NativeAcceptanceViolation("blocked dependency attempts remain in the audit record")

    def __enter__(self):
        self.assert_clean()
        original_import = builtins.__import__
        original_dynamic = importlib.import_module
        original_find_spec = importlib.util.find_spec
        original_socketpair = socket.socketpair

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            self.check_module(name)
            for member in fromlist or ():
                self.check_module(member)
            return original_import(name, globals, locals, fromlist, level)

        def guarded_dynamic(name, package=None):
            self.check_module(name)
            self.check_module(package)
            return original_dynamic(name, package)

        def guarded_find_spec(name, package=None):
            self.check_module(name)
            self.check_module(package)
            return original_find_spec(name, package)

        def socketpair(*args, **kwargs):
            # Windows' asyncio wakeup pair uses one internal loopback connect.
            previous = getattr(self._network, "socketpair", False)
            self._network.socketpair = True
            try:
                return original_socketpair(*args, **kwargs)
            finally:
                self._network.socketpair = previous

        self._patches = [patch.object(builtins, "__import__", guarded_import),
                         patch.object(importlib, "import_module", guarded_dynamic),
                         patch.object(importlib.util, "find_spec", guarded_find_spec),
                         patch.object(socket, "socketpair", socketpair)]
        for item in self._patches:
            item.start()
        sys.meta_path.insert(0, self)
        sys.addaudithook(self.audit)
        self.active = True
        return self

    def __exit__(self, *args):
        self.active = False
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        for item in reversed(self._patches):
            item.stop()
