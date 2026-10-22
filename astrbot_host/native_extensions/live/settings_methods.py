"""V2 live settings services."""
from __future__ import annotations
from .common import *

class LiveSettingsMethods:

    def _register_page_api_if_available(self) -> None:
        pass

    async def _persist_config_compatibility_migrations(self) -> None:
        changed = int(getattr(self, '_config_compatibility_migrations', 0) or 0)
        native_changed = int(getattr(self, '_live_config_migrations', 0) or 0)
        changed += native_changed
        if not changed:
            return
        save = getattr(self.config, 'save_config', None)
        try:
            if callable(save):
                result = save()
                if inspect.isawaitable(result):
                    await result
            if native_changed:
                logger.info('[配置] 已迁移 %s 个 Live 旧配置到 V2 原生设置', native_changed)
            if getattr(self, '_config_compatibility_migrations', 0):
                logger.info('[配置] 已为 %s 个 Live2D 条目补齐 AstrBot template_list 模板标识', self._config_compatibility_migrations)
        except Exception as exc:
            logger.warning(f'[配置] Live2D 条目兼容迁移写入失败，当前运行仍已修复: {exc}')
        finally:
            self._config_compatibility_migrations = 0
            self._live_config_migrations = 0

    def _get_config_room_id(self) -> int:
        return self._safe_parse_int(self.config.get('bilibili_room_id') or self.config.get('bili_live_room_id'), 0)

    def _get_bili_open_live_config(self) -> dict[str, Any]:
        return {'access_key_id': str(self.config.get('bilibili_ACCESS_KEY_ID') or '').strip(), 'access_key_secret': str(self.config.get('bilibili_ACCESS_KEY_SECRET') or '').strip(), 'app_id': self._safe_parse_int(self.config.get('bilibili_APP_ID'), 0), 'room_owner_auth_code': str(self.config.get('bilibili_ROOM_OWNER_AUTH_CODE') or '').strip()}

    def _get_laplace_config(self) -> dict[str, Any]:
        bridge_url = str(self.config.get('laplace_event_bridge_url') or self.config.get('bili_live_laplace_url') or '').strip()
        if not bridge_url:
            host = str(self.config.get('laplace_event_bridge_host') or 'localhost').strip()
            port = self._safe_parse_int(self.config.get('laplace_event_bridge_port'), 9696)
            bridge_url = f'ws://{host}:{port}'
        return {'bridge_url': bridge_url, 'token': str(self.config.get('laplace_event_bridge_token') or self.config.get('bili_live_laplace_token') or '').strip()}

    async def _persist_plugin_config_updates(self, updates: dict[str, Any]) -> bool:
        if not updates:
            return True
        manager = getattr(getattr(self, 'page_api', None), 'config_manager', None)
        if manager is None:
            try:
                from .page_config import PageConfigManager
                manager = PageConfigManager(self, 'astrbot_plugin_private_companion.live', logger)
            except Exception:
                manager = None
        if manager is not None and callable(getattr(manager, 'apply_updates', None)):
            return bool(await manager.apply_updates(updates))
        for key, value in updates.items():
            self.config[key] = value
        return False

    def _page_api_helper(self) -> Any | None:
        if self.page_api is not None:
            return self.page_api
        try:
            from .page_api import LiveStreamCompanionPageApi
            self.page_api = LiveStreamCompanionPageApi(self)
            return self.page_api
        except Exception as e:
            logger.debug(f'[B站直播] 创建拓展页控制 helper 失败: {e}')
            return None

    def _config_bool(self, value: Any, default: bool=False) -> bool:
        if value is None:
            return default
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {'1', 'true', 'yes', 'on', '开启'}:
                return True
            if text in {'0', 'false', 'no', 'off', '关闭'}:
                return False
        return bool(value)

    def _configured_bot_self_id(self) -> str:
        settings = getattr(self.controller, 'settings', None)
        return str(getattr(settings, 'account_id', '') or '')

    def _bili_live_reply_identity_mode(self) -> str:
        raw = str(self.config.get('bili_live_reply_identity_mode') or 'host').strip().lower()
        aliases = {'anchor': 'host', 'streamer': 'host', '主播模式': 'host', '主播': 'host', 'assistant': 'assistant', 'helper': 'assistant', 'moderator': 'assistant', '主播助理模式': 'assistant', '主播助理': 'assistant', '助理': 'assistant'}
        mode = aliases.get(raw, raw)
        return mode if mode in {'host', 'assistant'} else 'host'

    def _bili_live_reply_identity_label(self) -> str:
        return '主播助理模式' if self._bili_live_reply_identity_mode() == 'assistant' else '主播模式'

    def _bili_live_streamer_identity_from_companion_enabled(self) -> bool:
        return bool(self.config.get('bili_live_streamer_identity_from_v2_enabled', self.config.get('bili_live_streamer_identity_from_companion_enabled', True)))

    def _private_companion_primary_user_live_identity(self) -> dict[str, Any]:
        if not self._bili_live_streamer_identity_from_companion_enabled():
            return {}
        plugin = self._get_v2_live_state_owner()
        if plugin is None:
            return {}
        data = getattr(plugin, 'data', None)
        if not isinstance(data, dict):
            return {}
        users = data.get('users') if isinstance(data.get('users'), dict) else {}
        profiles = data.get('profiles') if isinstance(data.get('profiles'), dict) else {}
        if not profiles:
            profiles = data.get('worldbook_member_profiles') if isinstance(data.get('worldbook_member_profiles'), dict) else {}
        target_ids = self._private_companion_target_ids(plugin)
        for user_id in target_ids:
            user = users.get(str(user_id)) if isinstance(users, dict) else None
            profile = profiles.get(str(user_id)) if isinstance(profiles, dict) else None
            identity = self._build_private_companion_live_identity_item(str(user_id), user if isinstance(user, dict) else {}, profile if isinstance(profile, dict) else {}, plugin)
            if identity.get('name') or identity.get('identity_note'):
                return identity
        return {}

    def _build_private_companion_live_identity_item(self, user_id: str, user: dict[str, Any], profile: dict[str, Any], plugin: Any) -> dict[str, Any]:
        name_candidates = [user.get('live_display_name'), user.get('live_name'), profile.get('live_display_name'), profile.get('live_name'), profile.get('streamer_name'), profile.get('name'), user.get('nickname'), user.get('display_name'), user.get('name'), getattr(plugin, 'default_nickname', '')]
        name = ''
        for item in name_candidates:
            name = self._clean_bili_live_streamer_name(item)
            if name:
                break
        aliases: list[str] = []
        for raw in (profile.get('aliases'), profile.get('observed_names'), user.get('alias_user_ids')):
            if isinstance(raw, list):
                for item in raw:
                    alias = self._clean_bili_live_streamer_name(item)
                    if alias and alias != name and (alias not in aliases):
                        aliases.append(alias)
        note_candidates = [user.get('live_identity'), user.get('live_identity_note'), profile.get('live_identity'), profile.get('live_identity_note'), profile.get('identity_note'), profile.get('note'), profile.get('content')]
        note = ''
        for item in note_candidates:
            note = self._single_line_text(item, 180)
            if note:
                break
        return {'user_id': user_id, 'name': name, 'aliases': aliases[:6], 'identity_note': note, 'source': 'v2_live_state'}

    def _bili_live_streamer_identity(self) -> dict[str, Any]:
        manual_name = self._bili_live_streamer_manual_display_name()
        companion_identity = self._private_companion_primary_user_live_identity()
        identity = dict(companion_identity)
        if manual_name:
            identity['name'] = manual_name
            identity['source'] = 'config'
        if identity.get('name') or identity.get('identity_note'):
            return identity
        return {'name': '主播', 'aliases': [], 'identity_note': '', 'source': 'fallback'}

    def _build_bili_live_identity_instruction(self) -> str:
        if self._bili_live_reply_identity_mode() == 'assistant':
            streamer = self._bili_live_streamer_reference()
            identity = self._bili_live_streamer_identity()
            aliases = identity.get('aliases') if isinstance(identity.get('aliases'), list) else []
            alias_text = '；可用称呼：' + '、'.join(aliases[:4]) if aliases else ''
            note = self._single_line_text(identity.get('identity_note'), 160)
            note_text = f'；身份线索：{note}' if note else ''
            return f'## 直播身份模式\n当前为主播助理模式：你是辅助 {streamer} 直播的聊天助手/场控助理，不是主播本人。当前主播称呼：{streamer}{alias_text}{note_text}。请用主播助理的身份承接弹幕，可以说“{streamer}这边”“我帮{streamer}看着弹幕”“我帮你记下”，但不要假装自己正在直播、不要把观众对主播说的话全部揽到自己身上，也不要替主播做私人承诺。如果弹幕是在问直播声音、画面、流程或观众互动，请以助理口吻简短确认和协助。'
        return '## 直播身份模式\n当前为主播模式：你就是直播间正在出声回应弹幕的主播/Bot 本人。请用第一人称自然回应观众，像主播现场接话；不要说自己只是助理、场控或转述者。'

    def _bili_live_reply_identity_prompt_line(self) -> str:
        if self._bili_live_reply_identity_mode() == 'assistant':
            streamer = self._bili_live_streamer_reference()
            return f'身份：你是辅助 {streamer} 直播的主播助理/聊天助手，不是主播本人；用助理口吻回应观众，必要时说“{streamer}这边/我帮{streamer}”。'
        return '身份：你就是直播间主播/Bot 本人，用第一人称像主播现场接话。'
