"""Native session metadata and reviewed topology, without copying chat history."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging

from companion_v2.adapters.astrbot.group import group_event_route
from companion_v2.adapters.astrbot.native import (
    account_number,
    bounded_native_lookup,
    configured_default_persona_id,
)
from companion_v2.execution.models import TaskError, digest
from .identity_derivation import derive_bot_id, derive_role_id, role_display_name
from .native import SESSION_SETTINGS_LOOKUP_BUDGET_SECONDS, load_session_settings


logger = logging.getLogger(__name__)


def session_route(umo):
    if not isinstance(umo, str):
        return None
    parts = umo.split(":")
    if len(parts) != 3 or not parts[0]:
        return None
    platform, kind, session = parts
    try:
        ids = session.split("_")
        if kind == "FriendMessage" and len(ids) == 1:
            return platform, "private", account_number(session)
        if kind == "GroupMessage" and len(ids) in (1, 2):
            for value in ids:
                account_number(value)
            return platform, "group", ids[-1]
    except ValueError:
        pass
    return None


class SessionTopology:
    def __init__(self, controller):
        self.controller = controller
        self.path = controller.data_root / "setup" / "session_directory.json"
        self._pending = set()
        self._closed = False
        self._write_lock = asyncio.Lock()
        self._persona_role_snapshot = {}

    def schedule_observe(self, event):
        """Keep optional directory IO outside native reply hooks."""
        if self._closed or self.controller._terminated:
            return None

        async def record():
            try:
                await self.observe(event)
            except Exception as error:
                logger.warning("[CompanionV2] 会话目录后台更新失败 error_type=%s", type(error).__name__)

        task = asyncio.create_task(record(), name="companion-v2-session-observation")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def close(self):
        """Drain started writes; a cancelled to_thread call could outlive shutdown."""
        self._closed = True
        if self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)

    def configured(self, settings=None):
        controller = self.controller
        if settings is not None:
            return [{**vars(target), "scope_kind": kind}
                    for targets, kind in ((settings.targets, "private"), (settings.group_targets, "group"))
                    for target in targets]
        if controller._multi_host:
            section = controller.config.get("multi_host", {})
            return [{**item, "scope_kind": kind}
                    for field, kind in (("targets", "private"), ("group_targets", "group"))
                    for item in section.get(field, []) if isinstance(item, dict)]
        return controller.status().get("targets", [])

    def accounts(self, settings=None):
        context = self.controller.context
        enumerator = getattr(getattr(context, "platform_manager", None), "get_insts", None)
        platforms = list(enumerator() or []) if callable(enumerator) else []
        if not platforms:
            fallback = getattr(context, "platform", None)
            platforms = list(getattr(context, "platforms", {}).values()) or ([fallback] if fallback else [])
        aliases = {(row["platform_id"], row["account_id"]): row["bot_id"] for row in self.configured(settings)}
        if settings is not None:
            registered = [{"platform_id": account.platform_id, "account_id": account.self_id,
                           "bot_id": account.bot_id} for account in settings.accounts]
        else:
            shared = self.controller.config.get("multi_host", {})
            registered = shared.get("accounts", []) if isinstance(shared, dict) else []
        for row in registered if isinstance(registered, list) else ():
            if (isinstance(row, dict) and all(isinstance(row.get(field), str) and row[field].strip()
                    for field in ("platform_id", "account_id", "bot_id"))):
                aliases[(row["platform_id"], row["account_id"])] = row["bot_id"]
        result = {}
        for platform in platforms:
            try:
                meta = platform.meta()
                if meta.name != "aiocqhttp":
                    continue
                clients = platform.get_client()._wsr_api_clients
                for raw_id in clients:
                    account = account_number(raw_id)
                    result[(meta.id, account)] = {"platform_id": meta.id, "account_id": account,
                        "bot_id": aliases.get((meta.id, account), derive_bot_id(account))}
            except (AttributeError, ValueError, TypeError):
                continue
        return sorted(result.values(), key=lambda row: (row["platform_id"], int(row["account_id"])))

    def _observed(self):
        if not self.path.is_file():
            return {}
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(rows, dict):
            raise TaskError("session_directory_invalid", "the native session directory is unreadable")
        return rows

    async def services(self, umo):
        return await load_session_settings(umo)

    def persona_selection_snapshot(self, umo, account_id):
        """Return the last installed window-to-persona/role mapping."""
        snapshot = self._persona_role_snapshot.get((umo, account_id))
        if snapshot is not None:
            return snapshot
        route = session_route(umo)
        if route is None:
            return None
        platform, kind, _peer = route
        native_kind = "FriendMessage" if kind == "private" else "GroupMessage"
        return self._persona_role_snapshot.get((f"{platform}:{native_kind}:*", account_id))

    def update_persona_selection_snapshot(self, umo, account_id, bot_id, persona_id, role_id, conversation_id):
        """Refresh one verified live window after a native lookup or conversation reset."""
        controller = self.controller
        settings = controller.settings if controller._multi_host else None
        route = session_route(umo)
        if settings is None or route is None:
            return
        platform, kind, peer = route
        target = (settings.private_target(platform, account_id, peer) if kind == "private"
                  else settings.group_target(platform, account_id, peer))
        mapping = next((item for item in settings.personas
                        if item.bot_id == bot_id and item.persona_id == persona_id and item.role_id == role_id), None)
        if (target is None or target.bot_id != bot_id or mapping is None
                or not any(item.self_id == account_id and item.bot_id == bot_id for item in settings.accounts)):
            return
        self._persona_role_snapshot[(umo, account_id)] = {
            "bot_id": bot_id, "persona_id": persona_id, "role_id": role_id,
            "conversation_id": conversation_id, "selection_source": "verified",
        }

    def persona_mapping_snapshot(self, umo, account_id, bot_id):
        snapshot = self.persona_selection_snapshot(umo, account_id)
        settings = self.controller.settings
        if snapshot is None or settings is None or snapshot["bot_id"] != bot_id:
            return None
        return next((item for item in settings.personas
                     if item.bot_id == bot_id and item.persona_id == snapshot["persona_id"]
                     and item.role_id == snapshot["role_id"]), None)

    def _publish_persona_role_snapshot(self, targets, *, complete, scope_kind=None):
        discovered = {}
        for row in targets:
            if (row.get("native") is not True or row.get("details_available") is not True
                    or not row.get("unified_msg_origin") or not row.get("account_id")
                    or not row.get("bot_id") or not row.get("persona_id")):
                continue
            role = next((item for item in row.get("roles", ())
                         if row["persona_id"] in item.get("persona_ids", ())), None)
            if not role or not role.get("role_id"):
                continue
            discovered[(row["unified_msg_origin"], row["account_id"])] = {
                "bot_id": row["bot_id"], "persona_id": row["persona_id"],
                "role_id": role["role_id"], "conversation_id": row.get("conversation_id"),
                "selection_source": "conversation",
            }

        if complete:
            retained = {key: value for key, value in self._persona_role_snapshot.items()
                        if scope_kind is not None and (session_route(key[0]) is None
                                                       or session_route(key[0])[1] != scope_kind)}
            retained.update(discovered)
            self._persona_role_snapshot = retained
        else:
            self._persona_role_snapshot.update(discovered)

    async def _seed_configured_persona_snapshot(self, settings, *, scope_kind=None):
        if settings is None:
            return
        mappings = tuple(settings.personas)
        windows = []
        windows.extend((target, f"{target.platform_id}:FriendMessage:{target.participant_id}", "private")
                       for target in settings.targets if target.participant_id != "*")
        windows.extend((target, f"{target.platform_id}:GroupMessage:{target.group_id}", "group")
                       for target in settings.group_targets if target.group_id != "*")
        windows.extend((target, f"{target.platform_id}:FriendMessage:*", "private")
                       for target in settings.targets if target.participant_id == "*")
        windows.extend((target, f"{target.platform_id}:GroupMessage:*", "group")
                       for target in settings.group_targets if target.group_id == "*")
        for target, umo, kind in windows:
            if scope_kind is not None and kind != scope_kind:
                continue
            key = (umo, target.account_id)
            if key in self._persona_role_snapshot:
                continue
            candidates = [item for item in mappings if item.bot_id == target.bot_id]
            override_lookup = getattr(self.controller.native_types, "session_persona_override_lookup", None)
            try:
                selected = (await bounded_native_lookup(override_lookup(umo), operation="session_settings")
                            if callable(override_lookup) and not umo.endswith(":*") else None)
                if selected == "":
                    selected = None
                if selected is None:
                    # A single registered mapping is not a native persona choice.
                    selected = await self._selected_native_persona(umo, None)
            except TaskError:
                continue
            mapping = next((item for item in candidates if item.persona_id == selected), None)
            if mapping is None:
                continue
            self._persona_role_snapshot[key] = {
                "bot_id": target.bot_id, "persona_id": mapping.persona_id,
                "role_id": mapping.role_id, "conversation_id": None,
                "selection_source": "configured",
            }

    async def _selected_native_persona(self, umo, conversation_persona_id):
        # AstrBot routes a group's persona through the per-UMO agent config. The
        # conversation row still carries the private/default persona, and passing
        # it here would make every group window look like the private persona.
        if type(umo) is str and ":GroupMessage:" in umo:
            configured = configured_default_persona_id(self.controller.context, umo)
            if (configured not in (None, "", "default", "[%None]")
                    and conversation_persona_id not in ("default", "[%None]")):
                conversation_persona_id = None
        lookup = getattr(self.controller.native_types, "persona_selection_lookup", None)
        if callable(lookup):
            resolved = lookup(self.controller.context, umo, conversation_persona_id)
            return (await bounded_native_lookup(resolved, operation="persona", report_slow=False)
                    if inspect.isawaitable(resolved) else resolved)
        return conversation_persona_id or configured_default_persona_id(self.controller.context, umo)

    async def reply_enabled(self, event):
        try:
            services = await asyncio.wait_for(
                self.services(event.unified_msg_origin), timeout=SESSION_SETTINGS_LOOKUP_BUDGET_SECONDS)
        except TimeoutError:
            logger.warning("[CompanionV2] 会话回复开关读取超时，继续 AstrBot 核心回复")
            return True
        return services.get("session_enabled", True)

    async def observe(self, event):
        controller = self.controller
        if controller._terminated or type(event) is not controller.native_types.event:
            return
        route = session_route(event.unified_msg_origin)
        if route is None:
            return
        platform_id, kind, peer = route
        platform = controller.context.get_platform_inst(platform_id)
        message, session, meta = event.message_obj, event.session, event.platform_meta
        login = account_number(message.self_id)
        if (platform is None or meta.name != "aiocqhttp" or platform.get_client() is not event.bot
                or not event.bot._wsr_api_clients.get(login)):
            return
        if kind == "group":
            native = group_event_route(event)
            if (native.platform_id, native.account_id, native.group_id) != (platform_id, login, peer):
                return
        elif (message.group_id or account_number(message.sender.user_id) != peer
              or getattr(message.type, "value", None) != "FriendMessage"
              or getattr(session.message_type, "value", None) != "FriendMessage"
              or session.session_id != peer or session.platform_id != platform_id
              or session.platform_name != platform_id or meta.id != platform_id):
            return
        manager = controller.context.conversation_manager
        cid = await bounded_native_lookup(manager.get_curr_conversation_id(event.unified_msg_origin),
                                          operation="conversation_id")
        if controller._terminated:
            return
        key = digest([platform_id, login, event.unified_msg_origin])
        row = {"unified_msg_origin": event.unified_msg_origin, "account_id": login,
               "conversation_id": cid, "last_seen_at": controller.now().isoformat()}
        if kind == "group":
            group = getattr(message, "group", None)
            group_name = getattr(group, "group_name", None)
            if isinstance(group_name, str) and group_name.strip():
                row["group_name"] = group_name.strip()[:128]
        async with self._write_lock:
            await asyncio.to_thread(self._store_observation, key, row)

    def _store_observation(self, key, row):
        rows = self._observed()
        rows[key] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(rows, ensure_ascii=False, sort_keys=True) + "\n",
                             encoding="utf-8", newline="\n")
        temporary.replace(self.path)

    async def _native_sessions(self, platforms, *, scope_kind=None):
        manager = getattr(self.controller.context, "conversation_manager", None)
        reader = getattr(getattr(manager, "db", None), "get_session_conversations", None)
        rows = {}
        issues = []
        if callable(reader):
            for platform in sorted(platforms):
                page = 1
                while True:
                    filters = ({"search_query": ":FriendMessage:" if scope_kind == "private" else ":GroupMessage:"}
                               if scope_kind else {})
                    try:
                        batch, total = await bounded_native_lookup(
                            reader(page=page, page_size=100, platform=platform, **filters),
                            operation="session_directory")
                    except TaskError as error:
                        issues.append(self._directory_issue(error, platform_id=platform))
                        break
                    except Exception as error:
                        issues.append(self._directory_issue(error, platform_id=platform,
                                                            default_stage="session_directory"))
                        break
                    for item in batch:
                        umo = item.get("session_id")
                        route = session_route(umo)
                        if route and (scope_kind is None or route[1] == scope_kind):
                            rows[umo] = {**item, "unified_msg_origin": umo}
                    if not batch or page * 100 >= total:
                        break
                    page += 1
        else:
            for umo, cid in getattr(manager, "session_conversations", {}).items():
                route = session_route(umo)
                if route and route[0] in platforms and (scope_kind is None or route[1] == scope_kind):
                    rows[umo] = {"unified_msg_origin": umo, "conversation_id": cid}
        return rows, issues

    async def inventory(self, *, settings=None, scope_kind=None):
        return (await self.inventory_report(settings=settings, scope_kind=scope_kind))["targets"]

    async def inventory_report(self, *, settings=None, scope_kind=None):
        accounts, configured = self.accounts(settings), self.configured(settings)
        if scope_kind is not None:
            configured = [row for row in configured if row["scope_kind"] == scope_kind]
        if settings is not None:
            routes = {(row["platform_id"], row["account_id"]) for row in configured}
            accounts = [row for row in accounts if (row["platform_id"], row["account_id"]) in routes]
        platforms = {row["platform_id"] for row in accounts}
        native, issues = await self._native_sessions(platforms, scope_kind=scope_kind)
        observed = {}
        for row in self._observed().values():
            umo = row.get("unified_msg_origin")
            route = session_route(umo)
            if route and route[0] in platforms and (scope_kind is None or route[1] == scope_kind):
                observed.setdefault(umo, []).append(row)
                native_row = native.setdefault(umo, {"unified_msg_origin": umo,
                                       "conversation_id": row.get("conversation_id")})
                if row.get("group_name") and not native_row.get("group_name"):
                    native_row["group_name"] = row["group_name"]
        mappings = ([vars(row) for row in settings.personas] if settings is not None else
                    self.controller.config.get("multi_host", {}).get("personas", []) if self.controller._multi_host else [])
        slots = asyncio.Semaphore(4)

        async def read(umo, item):
            async with slots:
                try:
                    rows = await self._session_windows(umo, item, accounts, configured, mappings, observed,
                                                       managed_only=settings is not None)
                    return rows, None
                except TaskError as error:
                    return self._partial_windows(umo, accounts, configured, observed), error

        # One stale or slow conversation must not erase the rest of the directory.
        native_items = list(native.items())
        tasks = [asyncio.create_task(read(umo, item)) for umo, item in native_items]
        batches = await asyncio.gather(*tasks, return_exceptions=True)
        result = []
        for (umo, _), value in zip(native_items, batches):
            if isinstance(value, BaseException):
                if isinstance(value, asyncio.CancelledError):
                    raise value
                issues.append(self._directory_issue(value))
                result.extend(self._partial_windows(umo, accounts, configured, observed))
                continue
            rows, error = value
            result.extend(rows)
            if error is not None:
                issues.append(self._directory_issue(error))
        represented = {row["target_id"] for row in result}
        for binding in configured:
            if binding["target_id"] not in represented:
                result.append({**binding, "session_key": "configured-" + binding["target_id"],
                               "managed": True, "native": False,
                                "roles": binding.get("roles") or [{"role_id": row["role_id"],
                                    "role_name": role_display_name(row["role_id"], [row["persona_id"]]),
                                    "persona_ids": [row["persona_id"]]}
                                   for row in mappings if row.get("bot_id") == binding["bot_id"]]})
        targets = sorted(result, key=lambda row: (not row["managed"], row["platform_id"], row["account_id"], row["session_key"]))
        complete = not issues
        self._publish_persona_role_snapshot(targets, complete=complete, scope_kind=scope_kind)
        snapshot_settings = settings if settings is not None else (
            self.controller.settings if self.controller._multi_host else None)
        await self._seed_configured_persona_snapshot(snapshot_settings, scope_kind=scope_kind)
        return {"targets": targets, "complete": complete, "issues": self._unique_issues(issues)}

    @staticmethod
    def _directory_issue(error, *, platform_id="", default_stage="details"):
        code = getattr(error, "code", "session_details_unavailable")
        reason = str(error) if isinstance(error, TaskError) else "AstrBot 会话详情未能读取。"
        stage = code.rsplit("__", 1)[-1] if code.startswith("host_native_lookup_timeout__") else default_stage
        return {"code": code, "stage": stage, "platform_id": platform_id, "reason": reason}

    @staticmethod
    def _unique_issues(issues):
        counts = {}
        for issue in issues:
            key = (issue["code"], issue["stage"], issue["platform_id"], issue["reason"])
            counts[key] = counts.get(key, 0) + 1
        return [{"code": code, "stage": stage, "platform_id": platform, "reason": reason, "count": count}
                for (code, stage, platform, reason), count in sorted(counts.items())]

    @staticmethod
    def _partial_windows(umo, accounts, configured, observed):
        route = session_route(umo)
        if route is None:
            return []
        platform, kind, peer = route
        peer_field = "group_id" if kind == "group" else "participant_id"
        explicit = {row.get("account_id") for row in observed.get(umo, []) if row.get("account_id")}
        bindings = [row for row in configured if row.get("platform_id") == platform
                    and row.get("scope_kind") == kind and row.get(peer_field) == peer]
        if bindings:
            return []
        if explicit:
            selected = [row for row in accounts if row["platform_id"] == platform
                        and row["account_id"] in explicit]
        elif bindings:
            selected = [{"platform_id": row["platform_id"], "account_id": row["account_id"],
                         "bot_id": row["bot_id"]} for row in bindings]
        else:
            selected = [{"platform_id": platform, "account_id": "", "bot_id": ""}]

        result = []
        observed_name = next((row.get("group_name") or row.get("display_name")
                              for row in observed.get(umo, [])
                              if isinstance(row.get("group_name") or row.get("display_name"), str)
                              and (row.get("group_name") or row.get("display_name")).strip()), "")
        for account in selected:
            account_id = account.get("account_id", "")
            binding = next((row for row in bindings if row.get("account_id") == account_id), None)
            session_key = "session-" + digest([platform, account_id, umo])[:24]
            result.append({**account, "session_key": session_key,
                "target_id": binding["target_id"] if binding else session_key,
                "scope_kind": kind, peer_field: peer, "unified_msg_origin": umo,
                **({"display_name": observed_name, "group_name": observed_name} if kind == "group" and observed_name else {}),
                "conversation_id": "", "managed": False, "native": True,
                "details_available": False, "persona_id": "", "persona_override": "",
                "persona_source": "unresolved",
                "llm_enabled": True, "session_enabled": True, "persona_pinned": False, "roles": []})
        return result

    async def _session_windows(self, umo, item, accounts, configured, mappings, observed, *, managed_only):
        manager = getattr(self.controller.context, "conversation_manager", None)
        result = []
        platform, kind, peer = session_route(umo)
        candidates = [row for row in accounts if row["platform_id"] == platform]
        if not candidates:
            return result
        peer_field = "group_id" if kind == "group" else "participant_id"
        account_matches = [row for row in configured if row["platform_id"] == platform
                           and row["scope_kind"] == kind and row.get(peer_field) in (peer, "*")]
        exact = {row["account_id"] for row in observed.get(umo, [])}
        if exact:
            candidates = [row for row in candidates if row["account_id"] in exact]
        elif len(candidates) > 1:
            ids = {row["account_id"] for row in account_matches}
            candidates = [row for row in candidates if row["account_id"] in ids] if len(ids) == 1 else []
        if managed_only:
            candidates = [row for row in candidates if any(
                binding["account_id"] == row["account_id"] for binding in account_matches)]
            if not candidates:
                return result
        if not candidates:
            candidates = [{"platform_id": platform, "account_id": "", "bot_id": ""}]
        observed_name = next((row.get("group_name") or row.get("display_name")
                              for row in observed.get(umo, [])
                              if isinstance(row.get("group_name") or row.get("display_name"), str)
                              and (row.get("group_name") or row.get("display_name")).strip()), "")
        native_name = item.get("group_name") or item.get("display_name") or observed_name
        cid = await bounded_native_lookup(manager.get_curr_conversation_id(umo), operation="conversation_id")
        if cid != item.get("conversation_id") or cid is None and umo not in observed:
            return result
        services = await bounded_native_lookup(self.services(umo), operation="session_settings")
        override = services.get("persona_id")
        if override == "":
            override = None
        if override is not None:
            if (type(override) is not str or not override.strip() or len(override) > 120
                    or any(ord(char) < 32 for char in override)):
                raise TaskError("host_persona_invalid", "the V2 window persona override is invalid")
        for account in candidates:
            matches = [row for row in account_matches if row["account_id"] == account["account_id"]]
            binding = next((row for row in matches if row.get(peer_field) == peer), None)
            binding = binding or next((row for row in matches if row.get(peer_field) == "*"), None)
            if override is not None:
                selected = override
                persona_source = "v2_window_override"
            else:
                if self.controller._multi_host:
                    native_persona = await self._selected_native_persona(umo, item.get("persona_id"))
                    selected = native_persona if type(native_persona) is str else ""
                    persona_source = "astrbot_selection" if selected else "unresolved"
                elif not self.controller._multi_host:
                    configured_ids = {persona_id for row in matches for role_row in row.get("roles", [])
                                      for persona_id in role_row.get("persona_ids", []) if persona_id}
                    selected = next(iter(configured_ids)) if len(configured_ids) == 1 else ""
                    persona_source = "role_mapping" if selected and binding else "unresolved"
            role = next((row["role_id"] for row in mappings if row.get("bot_id") == account["bot_id"]
                         and row.get("persona_id") == selected), None)
            if binding and not self.controller._multi_host:
                role = binding["roles"][0]["role_id"]
            key = "session-" + digest([platform, account["account_id"], umo])[:24]
            roles = ([{"role_id": role, "role_name": role_display_name(role, [selected]),
                       "persona_ids": [selected]}] if role else [])
            result.append({**account, "session_key": key, "target_id": binding["target_id"] if binding else key,
                "scope_kind": kind, "group_id" if kind == "group" else "participant_id": peer,
                **({"display_name": native_name, "group_name": native_name} if kind == "group" and native_name else {}),
                "unified_msg_origin": umo, "conversation_id": cid,
                "managed": binding is not None and (not self.controller._multi_host or role is not None),
                "native": True, "details_available": True,
                "persona_id": selected, "persona_override": services.get("persona_id") or "",
                "persona_source": persona_source,
                "llm_enabled": services.get("llm_enabled", True),
                "session_enabled": services.get("session_enabled", True),
                "persona_pinned": bool(binding and not self.controller._multi_host),
                "roles": roles})
        return result

    async def select(self, session_key):
        return next((row for row in await self.inventory() if row["session_key"] == session_key), None)
