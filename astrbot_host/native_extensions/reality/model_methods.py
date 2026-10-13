"""V2 reality model services."""
from __future__ import annotations
from .common import *

class RealityModelMethods:

    def _provider_supports_image(self, provider: Any) -> bool:
        return provider is not None and callable(getattr(provider, 'text_chat', None))

    def _record_llm_usage(self, *, provider_id='', task='', prompt='', completion='', elapsed_ms=0,
                          success=False, error='', resp=None, response=None) -> None:
        tracker = getattr(self, 'token_usage', None)
        if tracker is None:
            return
        try:
            tracker.record(provider_id=provider_id, task=task, prompt=prompt, completion=completion,
                elapsed_ms=elapsed_ms, success=success, error=error,
                response=resp if resp is not None else response, persist=False)
            pending = getattr(self, '_token_usage_save_task', None)
            if pending is None or pending.done():
                self._token_usage_save_task = self._create_lifecycle_background_task(
                    asyncio.to_thread(tracker.save, force=True), label='token_usage')
        except Exception as exc:
            logger.warning('[RealityCompanion] 模型用量统计暂不可用 error_type=%s', type(exc).__name__)

    async def _llm_call(self, prompt: str, **kwargs: Any) -> str:
        api = self.v2_host_api()
        caller = getattr(api, 'generate_reality_touch_text', None) if api is not None else None
        if not callable(caller):
            return ''
        return str(await caller(prompt, **kwargs) or '')

    async def _resolve_proactive_persona_prompt(self, user: dict[str, Any], **kwargs: Any) -> str:
        api = self.v2_host_api()
        getter = getattr(api, 'get_realtime_context', None) if api is not None else None
        if not callable(getter):
            return ''
        result = await getter(_single_line(user.get('user_id'), 120), purpose='reality_touch',
                              umo=_single_line(kwargs.get('umo'), 240))
        return str(result.get('prompt') or '') if isinstance(result, dict) else ''

    def _task_provider(self, *provider_ids: Any) -> str:
        return next((_single_line(item, 160) for item in provider_ids if _single_line(item, 160)), '')

    def _llm_timer_timezone_name(self) -> str:
        return self.environment_perception_timezone

    def _llm_timer_run_at(self, scheduled_ts: float) -> datetime:
        return self._environment_fromtimestamp(scheduled_ts)

    async def _delete_official_llm_timer_job(self, job_id: str) -> tuple[bool, str]:
        api = self.v2_host_api()
        deleter = getattr(api, 'delete_reality_touch_cron_job', None) if api is not None else None
        if not callable(deleter):
            return (False, 'AstrBot 官方 Cron 不可用')
        result = await deleter(job_id)
        if isinstance(result, tuple):
            return (bool(result[0]), str(result[1] if len(result) > 1 else ''))
        return (bool(result), '')

    async def _reply(self, event: AstrMessageEvent, text: str) -> None:
        sender = getattr(event, 'send', None)
        if callable(sender):
            await sender(event.plain_result(str(text or '')))

    def _reality_touch_location_check_text(self, user_id: str) -> str:
        context = self.mobile_context(user_id)
        location = context.get('location') if isinstance(context.get('location'), dict) else {}
        if not context.get('available'):
            reason = _single_line(location.get('reason'), 80)
            if reason == 'mobile_gateway_disabled':
                return '位置检查：手机陪伴终端网关未启用或尚未运行。'
            ttl = _safe_int((context.get('privacy') or {}).get('expires_after_seconds') if isinstance(context.get('privacy'), dict) else 0, 900, 60)
            return f'位置检查：当前没有有效的手机前台位置；可能尚未上报、已撤销或已超过 {ttl} 秒有效期。'
        parts = ['位置检查：手机陪伴终端位置有效']
        place = location.get('place') if isinstance(location.get('place'), dict) else {}
        place_name = _single_line(place.get('name'), 40) if place.get('matched') else ''
        label = _single_line(location.get('label'), 40)
        if place_name:
            parts.append(f'标记地点：{place_name}')
        elif label:
            parts.append(f'设备标记：{label}')
        latitude = location.get('latitude')
        longitude = location.get('longitude')
        if latitude is not None and longitude is not None:
            parts.append(f'约略坐标：{latitude}, {longitude}')
        accuracy = _safe_float(location.get('accuracy_m'), 0.0, 0.0)
        if accuracy > 0:
            parts.append(f'精度约 {round(accuracy)} 米')
        captured_at = _safe_float(location.get('captured_at'), 0.0, 0.0)
        if captured_at > 0:
            try:
                timezone = zoneinfo.ZoneInfo(self.environment_perception_timezone or 'Asia/Shanghai')
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                timezone = zoneinfo.ZoneInfo('Asia/Shanghai')
            captured_text = datetime.fromtimestamp(captured_at, timezone).strftime('%Y-%m-%d %H:%M:%S')
            parts.append(f'采集时间：{captured_text}')
        age = _safe_int(location.get('age_seconds'), 0, 0)
        parts.append(f'距采集约 {age} 秒')
        return '；'.join(parts) + '。'
