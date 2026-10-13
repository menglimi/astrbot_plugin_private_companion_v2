"""Static dependency and side-effect firewall for the V2-G0 source tree."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "aiohttp",
        "astrbot",
        "astrbot_host",
        "ctypes",
        "discord",
        "ftplib",
        "httpx",
        "onebot",
        "paramiko",
        "playwright",
        "requests",
        "selenium",
        "smtplib",
        "socket",
        "subprocess",
        "urllib",
        "websockets",
        "winreg",
    }
)

FORBIDDEN_RUNTIME_IMPORT_PREFIXES = (
    "astrbot_plugin_private_companion",
    "astrbot_plugin_remember_you",
)

FORBIDDEN_CALL_ROOTS = frozenset(
    {
        "aiohttp",
        "ctypes",
        "httpx",
        "os",
        "paramiko",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "websockets",
        "winreg",
    }
)

DATA_ACCESS_TERMINALS = frozenset(
    {
        "connect",
        "glob",
        "iterdir",
        "mkdir",
        "open",
        "read_bytes",
        "read_text",
        "rglob",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
    }
)

LEGACY_DATA_MARKERS = (
    "companions.json",
    "memory_companion.db",
    "framework_work",
    "framework_world",
    "creative_state.json",
    "image_generation_state.json",
    "reality_companion.json",
)

# Data owners have explicit local I/O policies. Host SDK and network calls stay
# in adapters; legacy sources are read only and destinations belong to V2.
APPROVED_IO_BY_MODULE = {
    "companion_v2.foundation.isolation": frozenset({"read_text", "rglob"}),
    "companion_v2.foundation.sqlite": frozenset({"connect"}),
    # This module owns only the rebuildable memory-search projection; canonical
    # memory records remain behind their storage owner.
    "companion_v2.memory.search": frozenset({"connect"}),
    "companion_v2.storage.runtime": frozenset({"connect", "mkdir"}),
    # Content-addressed screen originals: one local, durable write per capture
    # under the runtime data root; the storage owner still holds the metadata.
    "companion_v2.screen.originals": frozenset({"mkdir", "open", "unlink"}),
    # In-memory pixel-size probe of an already governed original; no path access.
    "companion_v2.conversation.media.screen": frozenset({"open"}),
    # The same in-memory probe for the background interpretation request: the bytes
    # come from ScreenRepository, never from a caller-supplied path.
    "companion_v2.screen.interpretation": frozenset({"open"}),
    # The semantic learning store owns its separate rebuildable SQLite database.
    "companion_v2.storage.semantic": frozenset({"connect"}),
    # Backup/restore owns the data-root copy contract: local archive reads,
    # writes and staging files only; no network and no V1 data access.
    "companion_v2.storage.backup": frozenset(
        {"connect", "glob", "mkdir", "open", "read_text", "unlink", "write_text"}),
    # V2 storage inventory and manifest-paired backup retention/transfer only.
    # Other storage modules retain the default filesystem prohibition.
    "companion_v2.storage.management": frozenset(
        {"glob", "mkdir", "open", "read_text", "rglob", "unlink"}),
    # V1 reads are confined to the explicitly invoked, read-only migration planner.
    # Migration writes still pass through the authenticated V2 configuration API.
    "companion_v2.legacy.migration": frozenset({"connect", "read_text", "rglob"}),
    # Installation-wide Laya settings and read-only local model-cache inventory.
    "companion_v2.decision.store": frozenset(
        {"glob", "read_text", "iterdir", "mkdir", "open", "unlink"}),
    # Explicit migration copies originals into V2 archives, leaving V1 intact.
    "companion_v2.legacy.archive": frozenset(
        {"read_text", "read_bytes", "open", "mkdir", "rglob"}),
    "companion_v2.legacy.data_migration": frozenset({"read_bytes", "iterdir", "connect"}),
    "companion_v2.legacy.memory_archive": frozenset(
        {"connect", "open", "mkdir", "read_text", "read_bytes"}),
    "companion_v2.legacy.profile_source": frozenset({"read_bytes", "connect"}),
    # Read-only source SQLite plus the separate V2 imported-materials projection.
    "companion_v2.memory.legacy_materials": frozenset({"connect", "open"}),
}

# Reference uploads and stored generated images are decoded from bounded bytes,
# never from caller-provided filesystem paths. Keep this exception narrower than
# the general file-I/O allowlist so Image.open(path) remains a violation.
APPROVED_IN_MEMORY_DECODERS_BY_MODULE = {
    "companion_v2.references.management": frozenset({"Image.open"}),
}

# Fixed resources shipped with V2; arbitrary paths and writes remain forbidden.
APPROVED_PACKAGE_RESOURCES_BY_MODULE = {
    "companion_v2.legacy.configuration_migration": frozenset({
        ("companion_v2.legacy", "configuration_rules.json"),
    }),
}

# Named import policies: pure string/URL normalization with no network I/O.
APPROVED_IMPORTS_BY_MODULE = {
    "companion_v2.proactive.external_materials": frozenset({"urllib.parse"}),
    "companion_v2.proactive.news_sources": frozenset({"urllib.parse"}),
    "companion_v2.legacy.data_migration": frozenset({"urllib.parse"}),
    # Typed transport exceptions only; this adapter does not send HTTP requests.
    "companion_v2.adapters.astrbot.provider_transport": frozenset({"httpx"}),
}

# Named call policies for otherwise forbidden roots, limited to exact terminals.
APPROVED_CALLS_BY_MODULE = {
    # Local durability for the content-addressed screen original write above.
    "companion_v2.screen.originals": frozenset({"fsync", "link"}),
    "companion_v2.storage.management": frozenset({"replace"}),
    "companion_v2.decision.store": frozenset({"os.environ.get", "fsync", "replace"}),
    "companion_v2.legacy.archive": frozenset({"stat", "scandir", "fsync"}),
    "companion_v2.legacy.data_migration": frozenset({"scandir"}),
    "companion_v2.legacy.memory_archive": frozenset({"scandir", "fsync"}),
}


@dataclass(frozen=True, order=True)
class IsolationViolation:
    """One static isolation rule violation, without exposing source content."""

    code: str
    relative_path: str
    line: int
    detail: str


@dataclass(frozen=True)
class IsolationReport:
    """Result of scanning a source package before it can gain runtime privileges."""

    source_root: Path
    violations: tuple[IsolationViolation, ...]

    @property
    def is_clean(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.is_clean:
            return "isolation scan clean"
        return "\n".join(
            f"{item.relative_path}:{item.line} [{item.code}] {item.detail}"
            for item in self.violations
        )

    def assert_clean(self) -> None:
        if not self.is_clean:
            raise RuntimeError(f"V2 isolation scan failed:\n{self.render()}")


class _IsolationVisitor(ast.NodeVisitor):
    def __init__(self, *, module_name: str, relative_path: str) -> None:
        self._module_name = module_name
        self._relative_path = relative_path
        self.violations: list[IsolationViolation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(alias.name, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._check_import(node.module, node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted_name = _dotted_name(node.func)
        if dotted_name:
            root = dotted_name.split(".", 1)[0]
            terminal = dotted_name.rsplit(".", 1)[-1]
            if root in FORBIDDEN_CALL_ROOTS:
                approved = APPROVED_CALLS_BY_MODULE.get(self._module_name, frozenset())
                if terminal not in approved and dotted_name not in approved:
                    self._add("forbidden_platform_or_network_call", node, dotted_name)
            elif terminal in {"__import__", "import_module"}:
                self._add("forbidden_dynamic_import", node, dotted_name)
            elif (terminal in DATA_ACCESS_TERMINALS
                  and not self._is_approved_io(terminal)
                  and not self._is_approved_in_memory_decoder(dotted_name, node)
                  and not self._is_approved_package_resource_read(node)):
                code = (
                    "legacy_data_access"
                    if _contains_legacy_data_marker(node)
                    else "unapproved_data_access"
                )
                self._add(code, node, dotted_name)
            elif terminal == "Path" and _contains_legacy_data_marker(node):
                self._add("legacy_data_path_reference", node, dotted_name)
        self.generic_visit(node)

    def _check_import(self, imported_name: str, node: ast.AST) -> None:
        root = imported_name.split(".", 1)[0]
        if root in FORBIDDEN_IMPORT_ROOTS:
            if imported_name not in APPROVED_IMPORTS_BY_MODULE.get(self._module_name, frozenset()):
                self._add("forbidden_import", node, imported_name)
            return
        if any(
            imported_name == prefix or imported_name.startswith(f"{prefix}.")
            for prefix in FORBIDDEN_RUNTIME_IMPORT_PREFIXES
        ):
            self._add("forbidden_v1_runtime_import", node, imported_name)

    def _is_approved_io(self, terminal: str) -> bool:
        return terminal in APPROVED_IO_BY_MODULE.get(self._module_name, frozenset())

    def _is_approved_in_memory_decoder(self, dotted_name: str, node: ast.Call) -> bool:
        return (
            dotted_name in APPROVED_IN_MEMORY_DECODERS_BY_MODULE.get(self._module_name, frozenset())
            and bool(node.args)
            and isinstance(node.args[0], ast.Call)
            and _dotted_name(node.args[0].func) == "BytesIO"
        )

    def _is_approved_package_resource_read(self, node: ast.Call) -> bool:
        policy = APPROVED_PACKAGE_RESOURCES_BY_MODULE.get(self._module_name, frozenset())
        if not policy or not isinstance(node.func, ast.Attribute) or node.func.attr != "read_text":
            return False
        resource = node.func.value
        if (not isinstance(resource, ast.Call) or not isinstance(resource.func, ast.Attribute)
                or resource.func.attr != "joinpath" or len(resource.args) != 1 or resource.keywords):
            return False
        package = resource.func.value
        if (not isinstance(package, ast.Call) or _dotted_name(package.func) != "files"
                or len(package.args) != 1 or package.keywords):
            return False
        package_name, resource_name = package.args[0], resource.args[0]
        return (isinstance(package_name, ast.Constant) and isinstance(resource_name, ast.Constant)
                and (package_name.value, resource_name.value) in policy)

    def _add(self, code: str, node: ast.AST, detail: str) -> None:
        self.violations.append(
            IsolationViolation(
                code=code,
                relative_path=self._relative_path,
                line=getattr(node, "lineno", 0),
                detail=detail,
            )
        )


def scan_source_tree(source_root: str | Path, *, package_name: str) -> IsolationReport:
    """Scan Python files for dependencies and I/O that G0 must not contain.

    The scanner reads source text solely to inspect the supplied source tree. It does
    not import the scanned files, execute code, contact services, or inspect data roots.
    """

    root = Path(source_root)
    if not root.is_dir():
        raise ValueError(f"source root does not exist: {root}")

    violations: list[IsolationViolation] = []
    for path in sorted(root.rglob("*.py"), key=lambda item: item.as_posix()):
        relative_path = path.relative_to(root)
        relative_text = relative_path.as_posix()
        module_name = _module_name(package_name, relative_path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative_text)
        except SyntaxError as error:
            violations.append(
                IsolationViolation(
                    code="syntax_error",
                    relative_path=relative_text,
                    line=error.lineno or 0,
                    detail=error.msg,
                )
            )
            continue
        visitor = _IsolationVisitor(
            module_name=module_name,
            relative_path=relative_text,
        )
        visitor.visit(tree)
        violations.extend(visitor.violations)

    return IsolationReport(source_root=root, violations=tuple(sorted(violations)))


def _module_name(package_name: str, relative_path: Path) -> str:
    parts = list(relative_path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join([package_name, *parts]) if parts else package_name


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return None


def _contains_legacy_data_marker(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            value = child.value.lower()
            if any(marker in value for marker in LEGACY_DATA_MARKERS):
                return True
    return False
