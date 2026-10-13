"""V2 reality speech services."""
from __future__ import annotations
from .common import *

class RealitySpeechMethods:

    async def _synthesize_realtime_voice(self, text: str, **kwargs: Any) -> dict[str, Any]:
        api = self.v2_host_api()
        synthesizer = getattr(api, 'synthesize_realtime_voice', None) if api is not None else None
        if not callable(synthesizer):
            return {'success': False, 'error': 'V2 当前语音服务不可用'}
        kwargs['play_local'] = False
        return await synthesizer(text, **kwargs)
