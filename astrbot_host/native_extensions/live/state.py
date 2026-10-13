"""V2-owned live state and the small host-facing profile adapter.

Live platform events are public observations and do not belong in a private
conversation memory view.  This store therefore keeps a bounded, explicitly
live-scoped JSON document under the V2 native data root.  It is deliberately
not a plugin discovery or compatibility bridge.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any


SCHEMA = "companion.live-state.v1"


def _empty_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "profiles": {},
        "users": {},
        "groups": {},
        "bot_diaries": [],
        "state_conditions": [],
        "daily_state": {},
        "live_stream_companion": {
            "viewer_observations": {},
            "viewer_activity": {},
            "summaries": [],
            "memory_items": [],
            "topic_memory": {},
            "highlight_events": [],
            "open_threads": [],
            "stream_profile": {},
        },
    }


class LiveStateStore:
    """Own the durable live-only state used by the Live native extension."""

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.controller = getattr(runtime, "controller", None)
        self.data_dir = Path(getattr(runtime, "data_dir", ".")) / "native_v2"
        self.path = self.data_dir / "live_state.json"
        self.data = self._load()
        self._profile_refresh_at = 0.0
        self._profile_route = None
        # Existing activity code uses the owner object as a narrow data service.
        # Keeping this facade local makes it impossible to accidentally discover
        # another AstrBot plugin at runtime.
        self.owner = SimpleNamespace(data=self.data, default_nickname=self._default_nickname())
        self.owner._save_data_sync = self.save
        self.owner._configured_target_ids = self.configured_target_ids
        self.owner._canonical_private_user_id = lambda value: str(value or "").strip()
        self.owner._private_user_role = self.private_user_role
        self.owner._resolve_worldbook_member_by_name = self.resolve_profile_by_name
        self.owner._make_condition = self.make_condition
        self.owner._compose_state_from_conditions = self.compose_state

    def _load(self) -> dict[str, Any]:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            loaded = None
        state = _empty_state()
        if isinstance(loaded, dict) and loaded.get("schema") in (None, SCHEMA):
            state.update({key: value for key, value in loaded.items() if key in state})
        if not isinstance(state.get("profiles"), dict):
            state["profiles"] = loaded.get("worldbook_member_profiles", {}) if isinstance(loaded, dict) and isinstance(loaded.get("worldbook_member_profiles"), dict) else {}
        # Older V2 development snapshots used the descriptive key below.  It is
        # a local state migration, never a read from another plugin's data root.
        if isinstance(loaded, dict) and isinstance(loaded.get("worldbook_member_profiles"), dict):
            state["profiles"].update(loaded["worldbook_member_profiles"])
        state["worldbook_member_profiles"] = state["profiles"]
        nested = state.get("live_stream_companion")
        if not isinstance(nested, dict):
            nested = {}
            state["live_stream_companion"] = nested
        for key, default in _empty_state()["live_stream_companion"].items():
            if not isinstance(nested.get(key), type(default)):
                nested[key] = default.copy() if isinstance(default, (dict, list)) else default
        state["schema"] = SCHEMA
        return state

    def save(self) -> None:
        self.data["worldbook_member_profiles"] = self.data.get("profiles", {})
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
        os.replace(temporary, self.path)

    def _default_nickname(self) -> str:
        settings = getattr(self.controller, "settings", None)
        return str(getattr(settings, "nickname", "") or getattr(settings, "bot_name", "") or "").strip()

    def configured_target_ids(self) -> list[str]:
        self.refresh_profiles()
        context = self._current_profile_context()
        subject = getattr(getattr(getattr(context, "actor", None), "subject", None), "subject_id", "")
        profile_id = "v2:" + str(subject) if subject else ""
        return [profile_id] if profile_id in self.data.get("profiles", {}) else []

    def private_user_role(self, user: dict[str, Any], user_id: str = "") -> str:
        role = str(user.get("role") or user.get("identity_type") or "").strip().lower()
        return "owner" if role in {"owner", "primary", "主播", "主用户"} else role

    def _current_profile_context(self):
        """Use the bound delivery window, or the single host's verified target."""
        registry = getattr(self.controller, "native_extensions", None)
        application = getattr(registry, "application", None)
        session = getattr(self.controller, "session", None)
        if (application is None or getattr(application, "state", None) != "running"
                or getattr(session, "application", None) is not application):
            return None
        config = getattr(self.runtime, "config", {})
        origin = str(config.get("bili_live_auto_reply_session_id") or "").strip()
        if not origin:
            origin = str(getattr(self.runtime, "_live_bound_reply_session", "") or "").strip()
        if not origin:
            event = getattr(self.runtime, "_bili_reply_event_template", None)
            origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if origin:
            try:
                from astrbot.core.platform.message_session import MessageSession
                from astrbot.core.platform.message_type import MessageType
                from astrbot_host.mobile_together import MobileTogetherBridge
                route = MessageSession.from_str(origin)
                if route.message_type is not MessageType.FRIEND_MESSAGE:
                    return None
                resolved = MobileTogetherBridge(self.controller)._target_context(route.session_id)
                if resolved is None or resolved[1] is not application:
                    return None
                context = resolved[2]
                if (context.scope.platform != route.platform_id
                        or context.scope.native_scope_id != route.session_id):
                    return None
                return context
            except Exception:
                return None
        # Multi-user installations have no implicit primary person. The selected
        # live delivery route must identify one before any name is projected.
        if getattr(self.controller, "_multi_host", False):
            return None
        context = getattr(getattr(session, "profile", None), "target", None)
        scope = getattr(context, "scope", None)
        return context if getattr(getattr(scope, "kind", None), "value", None) == "private" else None

    def refresh_profiles(self, *, force: bool = False) -> None:
        """Refresh names after runtime attachment, scoped to the current bot/role."""
        application = getattr(getattr(self.controller, "native_extensions", None), "application", None)
        store = self.data.setdefault("profiles", {})
        self.data["worldbook_member_profiles"] = store
        if not isinstance(store, dict) or application is None:
            return
        runtime = getattr(application, "runtime", None)
        if runtime is None or not callable(getattr(runtime, "read_all", None)):
            return
        context = self._current_profile_context()
        scope = getattr(context, "scope", None)
        role_id = getattr(getattr(getattr(context, "role_binding", None), "role", None), "subject_id", "")
        route = None if scope is None or not role_id else {
            "installation_id": scope.installation_id, "platform": scope.platform,
            "bot_id": scope.bot_id, "account_id": scope.account_id, "role_id": role_id,
        }
        if not force and route == self._profile_route and time.monotonic() - self._profile_refresh_at < 10:
            return
        self._profile_route = route
        self._profile_refresh_at = time.monotonic()
        for key, profile in list(store.items()):
            if isinstance(profile, dict) and (profile.get("source") == "v2_acquaintance_names"
                    or profile.get("identity_type") == "v2_acquaintance"):
                store.pop(key, None)
        self.owner.default_nickname = self._default_nickname()
        if route is None:
            return
        try:
            rows = runtime.read_all(
                "SELECT document_json FROM memory_views WHERE kind = 'person.acquaintance.v1' AND state = 'active' "
                "ORDER BY updated_at DESC LIMIT 512"
            )
        except Exception:
            return
        for row in rows:
            try:
                document = json.loads(row["document_json"])
            except (KeyError, TypeError, ValueError):
                continue
            if not isinstance(document, dict):
                continue
            document_route = document.get("route") if isinstance(document.get("route"), dict) else {}
            if any(document_route.get(key) != value for key, value in route.items()):
                continue
            subject_id = str(document_route.get("subject_id") or "").strip()
            account_id = str(document.get("native_account_id") or "").strip()
            if not subject_id:
                continue
            name = str(document.get("admin_nickname") or document.get("platform_nickname") or "").strip()
            if not name:
                groups = document.get("group_cards") if isinstance(document.get("group_cards"), dict) else {}
                first = next(iter(groups.values()), {}) if groups else {}
                name = str(first.get("card") or "").strip() if isinstance(first, dict) else ""
            profile_id = "v2:" + subject_id
            store[profile_id] = {"user_id": profile_id, "identity_type": "v2_acquaintance",
                "name": name[:64], "aliases": [], "native_account_id": account_id,
                "external_ids": [f"{scope.platform}:account:{account_id}"] if account_id else [],
                "route": document_route, "enabled": True, "source": "v2_acquaintance_names"}

    def resolve_profile_by_name(self, name: str) -> list[dict[str, Any]]:
        needle = " ".join(str(name or "").split()).strip().lower()
        if not needle:
            return []
        matches = []
        for user_id, profile in self.data.get("profiles", {}).items():
            if not isinstance(profile, dict) or not profile.get("enabled", True):
                continue
            values = [profile.get("name"), *(profile.get("aliases") or []), *(profile.get("observed_names") or [])]
            tokens = [str(value or "").strip().lower() for value in values if str(value or "").strip()]
            if needle in tokens or any(needle in token or token in needle for token in tokens):
                matches.append({"user_id": str(user_id), "name": str(profile.get("name") or user_id), "source": "v2_profile"})
        return matches[:8]

    @staticmethod
    def make_condition(**values: Any) -> dict[str, Any]:
        return {"source": "live.native", "created_at": time.time(), **values}

    def compose_state(self, weather: dict[str, Any] | None = None) -> dict[str, Any]:
        conditions = self.data.get("state_conditions") if isinstance(self.data.get("state_conditions"), list) else []
        state = dict(weather or {})
        current = [item for item in conditions[-16:] if isinstance(item, dict)]
        if current:
            state["live_afterglow"] = current[-1]
        return state
