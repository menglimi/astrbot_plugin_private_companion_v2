"""V2 live media services."""
from __future__ import annotations
from .common import *

class LiveMediaMethods:

    def _get_bilibili_ai_bot_api(self):
        return None

    def _bilibili_ai_live_session_id(self) -> str:
        room_id = self._get_current_bili_room_text()
        started_at = int(self._bili_session_started_at or time.time())
        return f'bili_live:{room_id}:{started_at}'

    async def _record_bilibili_ai_live_event(self, event: LiveDanmakuEvent) -> None:
        if not event.user_id or event.username == '系统':
            return
        allowed_types = self.config.get('bilibili_ai_memory_event_types', ['danmaku', 'gift', 'super_chat', 'buy_guard', 'follow'])
        if not isinstance(allowed_types, list) or event.event_type not in {str(item).strip() for item in allowed_types}:
            return
        if event.event_id and event.event_id in self._bilibili_ai_written_event_ids:
            return
        if event.event_id:
            self._bilibili_ai_written_event_ids.add(event.event_id)
        api = self._get_bilibili_ai_bot_api()
        if api is None:
            self._bilibili_ai_written_event_ids.discard(event.event_id)
            return
        try:
            await api.record_live_event(user_id=event.user_id, username=event.username, event_type=event.event_type, content=event.content, session_id=self._bilibili_ai_live_session_id(), event_id=event.event_id, room_id=self._get_current_bili_room_text(), amount=event.amount, extra={'backend_cmd': str((event.raw or {}).get('cmd', ''))})
        except Exception as e:
            self._bilibili_ai_written_event_ids.discard(event.event_id)
            logger.warning('[B站直播] 写入 BiliBot 直播记忆失败: %s', e)

    async def _build_bilibili_ai_memory_context(self, events: list[LiveDanmakuEvent]) -> str:
        api = self._get_bilibili_ai_bot_api()
        if api is None:
            return ''
        by_user: dict[str, list[LiveDanmakuEvent]] = {}
        for event in events:
            if event.user_id and event.username != '系统':
                by_user.setdefault(event.user_id, []).append(event)
        if not by_user:
            return ''
        lines: list[str] = []
        for user_id, user_events in list(by_user.items())[-3:]:
            query = ' '.join((item.content for item in user_events[-3:] if item.content)).strip()
            if not query:
                continue
            try:
                recalled = await api.recall_user(user_id, query, memory_limit=3, video_limit=1, exclude_event_ids={item.event_id for item in user_events if item.event_id})
            except Exception as e:
                logger.debug('[B站直播] 读取 BiliBot 用户记忆失败 uid=%s: %s', user_id, e)
                continue
            profile = recalled.get('profile') if isinstance(recalled, dict) else {}
            memories = recalled.get('memories') if isinstance(recalled, dict) else []
            videos = recalled.get('video_memories') if isinstance(recalled, dict) else []
            logger.debug('[B站直播] 已读取 BiliBot 用户画像与记忆 uid=%s profile=%s memories=%s videos=%s', user_id, bool(profile), len(memories) if isinstance(memories, list) else 0, len(videos) if isinstance(videos, list) else 0)
            detail: list[str] = []
            if isinstance(profile, dict):
                if profile.get('impression'):
                    detail.append('印象：' + self._single_line_text(profile['impression'], 100))
                facts = profile.get('facts') if isinstance(profile.get('facts'), list) else []
                tags = profile.get('tags') if isinstance(profile.get('tags'), list) else []
                if facts:
                    detail.append('事实：' + '；'.join((self._single_line_text(item, 60) for item in facts[-4:])))
                if tags:
                    detail.append('标签：' + '、'.join((self._single_line_text(item, 30) for item in tags[-6:])))
                refs = profile.get('video_refs') if isinstance(profile.get('video_refs'), list) else []
                if refs:
                    titles = [self._single_line_text(item.get('title') or item.get('bvid'), 45) for item in refs[-4:] if isinstance(item, dict)]
                    if titles:
                        detail.append('视频关系：' + '、'.join(titles))
            if memories:
                detail.append('相关记忆：' + '；'.join((self._single_line_text(item.get('text', ''), 110) for item in memories[:3] if isinstance(item, dict))))
            if videos:
                detail.append('相关视频记忆：' + '；'.join((self._single_line_text(item.get('text', ''), 130) for item in videos[:1] if isinstance(item, dict))))
            detail = [item for item in detail if item and (not item.endswith('：'))]
            if detail:
                username = self._single_line_text(user_events[-1].username, 40)
                lines.append(f'- {username}（B站 UID {user_id}）：' + '；'.join(detail))
        if not lines:
            return ''
        return '## BiliBot 用户画像与记忆\n以下内容通过当前事件携带的 B站 UID 精确关联，不是按昵称猜测。只在与当前弹幕直接相关时自然承接；不要提 UID、画像、记忆系统或内部检索，也不要把轻量视频关系直接解释成喜欢。\n' + '\n'.join(lines)

    def _build_bilibili_ai_self_activity_context(self, events: list[LiveDanmakuEvent]) -> str:
        query = ' '.join((str(event.content or '') for event in events[-5:]))
        if not re.search('(今天|今日|最近|刚才).{0,12}(看|做|视频|番|动态|评论)|(看了什么|做了什么|最近干嘛|今天干嘛)', query):
            return ''
        api = self._get_bilibili_ai_bot_api()
        if api is None or not callable(getattr(api, 'activity_overview', None)):
            return ''
        recent_requested = '最近' in query
        try:
            if recent_requested:
                today = datetime.date.today()
                overviews = [str(api.activity_overview((today - datetime.timedelta(days=days_ago)).isoformat()) or '').strip() for days_ago in range(3)]
                overview = '\n\n'.join((item for item in overviews if item))
                activity_scope = '最近三天'
            else:
                overview = str(api.activity_overview() or '').strip()
                activity_scope = '今天'
        except Exception as e:
            logger.debug('[B站直播] 直接读取 BiliBot 活动失败: %s', e)
            return ''
        if not overview:
            return ''
        return f'## BiliBot 活动（已直接读取）\n活动范围：{activity_scope}。\n下面是 BiliBot API 已经返回的真实活动记录。请依据它直接回答当前直播问题，不要再次调用 recall_today、recall_video 或其他用于查询今日活动的工具，也不要只说‘让我查一下/让我想想’。用当前人设自然概括即可。\n' + overview[:3200]
