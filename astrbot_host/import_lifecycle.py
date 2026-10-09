"""Keep the plugin entry, relative host modules and core aliases in one graph."""

from pathlib import Path
import sys

from astrbot.core.star.star_handler import star_handlers_registry

from .logging_bridge import install_logging_bridge, retire_logging_bridge


def _belongs_to_root(module: object, root: Path) -> bool:
    source = getattr(module, "__file__", None)
    paths = (source,) if isinstance(source, str) else getattr(module, "__path__", ())
    try:
        return any(Path(path).resolve().is_relative_to(root) for path in paths)
    except (OSError, TypeError, ValueError):
        return False


def activate_plugin_imports(plugin_root: str, entry_name: str) -> bool:
    root = Path(plugin_root).resolve()
    existing = sys.modules.get("companion_v2")
    if existing is not None and not _belongs_to_root(existing, root):
        raise RuntimeError("another companion_v2 package is already loaded from a different source root")
    inserted = plugin_root not in sys.path
    if inserted:
        sys.path.insert(0, plugin_root)
    # Disabling preserves AstrBot metadata and decorated handlers. A fresh
    # import must replace those handlers before the decorators register again.
    for handler in tuple(star_handlers_registry):
        if handler.handler_module_path == entry_name:
            star_handlers_registry.remove(handler)
    install_logging_bridge(entry_name)
    return inserted


def retire_plugin_imports(plugin_root: str, entry_name: str, *, path_inserted: bool,
                          entry_globals: dict, preserve_modules: bool = False) -> None:
    entry = sys.modules.get(entry_name)
    if entry is not None and vars(entry) is not entry_globals:
        return
    root = Path(plugin_root).resolve()
    namespace = entry_name.rsplit(".", 1)[0]
    prefixes = (namespace, "companion_v2", "astrbot_host")
    owned = []
    if not preserve_modules:
        retire_logging_bridge(entry_name)
        for name, module in tuple(sys.modules.items()):
            if (any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
                    and _belongs_to_root(module, root)):
                owned.append((name, module))
    # Removing parent attributes as well as sys.modules avoids returning a
    # stale child through a later ``from package import child``.
    for name, module in sorted(owned, key=lambda item: item[0].count("."), reverse=True):
        if sys.modules.get(name) is not module:
            continue
        sys.modules.pop(name, None)
        parent_name, _, child_name = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, child_name, None) is module:
            delattr(parent, child_name)
    if path_inserted:
        # A draining core can resolve lazy imports through its package __path__.
        # Release the global path now so a new entry can own its next insertion.
        try:
            sys.path.remove(plugin_root)
        except ValueError:
            pass
