"""Capture one exact loaded Star, API, port and immutable native declaration."""

from collections import Counter
from dataclasses import dataclass
import inspect

from companion_v2.adapters.astrbot.tools import AstrBotToolDeclaration
from companion_v2.capabilities.native import NativeManifest, parse_manifest
from companion_v2.conversation.external_tools import ExtensionToolDescriptor
from companion_v2.execution.models import ProviderBinding, SideEffect, encode
from companion_v2.model_gateway.models import ToolSpec


def synchronous(method):
    if not callable(method) or inspect.iscoroutinefunction(method):
        raise ValueError("native discovery requires a synchronous method")
    result = method()
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise ValueError("native discovery cannot await provider code")
    return result


def stars_by_id(context):
    items = {}
    try:
        for star in context.get_all_stars():
            identifier = getattr(star, "root_dir_name", None)
            if type(identifier) is str and identifier:
                items.setdefault(identifier, []).append(star)
    except Exception:
        return {}
    return items


@dataclass(frozen=True)
class NativeLease:
    star: object
    instance: object
    api: object
    port: object
    manifest: NativeManifest

    @classmethod
    def capture(cls, identifier, star):
        if getattr(star, "activated", False) is not True:
            raise ValueError("native provider is not active")
        instance = getattr(star, "star_cls", None)
        api = getattr(instance, "extension_api", None)
        port = synchronous(getattr(api, "companion_v2_native", None))
        if port is None:
            return None
        if not inspect.iscoroutinefunction(getattr(port, "execute", None)):
            raise ValueError("native execution must be cooperative asynchronous I/O")
        manifest = parse_manifest(synchronous(getattr(port, "manifest", None)),
                                  plugin_id=identifier, version=str(getattr(star, "version", "")))
        return cls(star, instance, api, port, manifest)

    def current(self, context):
        matches = stars_by_id(context).get(self.manifest.plugin_id, ())
        if len(matches) != 1 or matches[0] is not self.star:
            return False
        try:
            current = self.capture(self.manifest.plugin_id, matches[0])
            return (current is not None and current.instance is self.instance and current.api is self.api
                    and current.port is self.port and current.manifest == self.manifest)
        except Exception:
            return False

    def declarations(self):
        result = []
        for tool in self.manifest.tools:
            descriptor = ExtensionToolDescriptor(
                ToolSpec(tool["action"], tool["description"], encode(tool["parameters"])),
                self.manifest.package,
                ProviderBinding(tool["capability"], self.manifest.provider_id,
                                self.manifest.package.package_version, self.manifest.generation),
                tool["source_owner"], SideEffect(tool["side_effect"]), tool["timeout_seconds"],
            )
            result.append(AstrBotToolDeclaration(
                f"native:{self.manifest.plugin_id}:{tool['action']}", descriptor))
        return tuple(result)


def discover(context, *, excluded_extensions=()):
    candidates, issues = [], []
    excluded_extensions = frozenset(excluded_extensions)
    for identifier, matches in sorted(stars_by_id(context).items()):
        # These are V2 modules now. Never acquire execution from their legacy
        # companion Stars, even when the user keeps a V1 installation enabled.
        if identifier in {"astrbot_plugin_" + name + "_companion" for name in
                          ("content", "image", "screen", "reality", "together", "game", "live_stream")}:
            continue
        if len(matches) != 1:
            issues.append((identifier, "native_instance_conflict"))
            continue
        star = matches[0]
        if getattr(star, "activated", False) is not True:
            continue
        api = getattr(getattr(star, "star_cls", None), "extension_api", None)
        if not callable(getattr(api, "companion_v2_native", None)):
            continue
        try:
            lease = NativeLease.capture(identifier, star)
            if lease is None:
                continue
            if lease.manifest.package.extension_id in excluded_extensions:
                continue
            candidates.append((lease, lease.declarations()))
        except Exception:
            issues.append((identifier, "native_declaration_invalid"))
    actions = Counter(d.descriptor.tool.action for _, declarations in candidates for d in declarations)
    extensions = Counter(lease.manifest.package.extension_id for lease, _ in candidates)
    entries = {}
    for lease, declarations in candidates:
        if extensions[lease.manifest.package.extension_id] > 1 or any(actions[d.descriptor.tool.action] > 1 for d in declarations):
            issues.append((lease.manifest.plugin_id, "native_action_conflict"))
            continue
        entries.update({declaration.host_tool_id: (declaration, lease) for declaration in declarations})
    # Keep all attested owners. Per-request availability and model budgets are
    # decided after assembly, rather than disabling the installed directory.
    return entries, tuple(issues)


def declarations_for_manifest(manifest):
    result = []
    for tool in manifest.tools:
        descriptor = ExtensionToolDescriptor(
            ToolSpec(tool["action"], tool["description"], encode(tool["parameters"])),
            manifest.package,
            ProviderBinding(tool["capability"], manifest.provider_id,
                            manifest.package.package_version, manifest.generation),
            tool["source_owner"], SideEffect(tool["side_effect"]), tool["timeout_seconds"],
        )
        result.append(AstrBotToolDeclaration(
            f"native:{manifest.plugin_id}:{tool['action']}", descriptor))
    return tuple(result)
