"""V2 live rooms services."""
from __future__ import annotations
from .common import *

class LiveRoomsMethods:

    def _get_current_bili_room_text(self) -> str:
        if not self._bili_live_client:
            return str(self._get_config_room_id() or '未知')
        room_id = getattr(self._bili_live_client, 'real_room_id', None)
        if room_id:
            return str(room_id)
        return str(self._get_config_room_id() or '未知')

    def _match_private_companion_member(self, plugin: Any, live_username: str, event: LiveDanmakuEvent | None=None) -> dict[str, Any] | None:
        external_ids = self._private_companion_live_external_ids(live_username, event)
        if not external_ids:
            return None
        data = getattr(plugin, 'data', None)
        profiles = data.get('worldbook_member_profiles') if isinstance(data, dict) else None
        if isinstance(profiles, dict):
            for user_id, profile in profiles.items():
                if not isinstance(profile, dict) or not profile.get('enabled', True):
                    continue
                profile_ids = {str(user_id)}
                raw_external = profile.get('external_ids')
                if isinstance(raw_external, list):
                    profile_ids.update((str(item).strip() for item in raw_external if str(item).strip()))
                for key in ('linked_bili_profile_id', 'live_profile_id'):
                    value = str(profile.get(key) or '').strip()
                    if value:
                        profile_ids.add(value)
                if external_ids & profile_ids:
                    match = self._private_companion_linked_match(plugin, str(user_id), profile)
                    match['identity_verified'] = True
                    return match
        return None
