import pathlib, json, sys

page = pathlib.Path("pages/陪伴小屋")
tokens = (page / "tokens.css").read_text(encoding="utf-8")
css = (page / "contact-page.css").read_text(encoding="utf-8")
js = (page / "contact-page.js").read_text(encoding="utf-8")

# 预览壳自己的样式。曾经这里只内联 tokens.css 的两个主题色块
# （[data-theme=courtyard/night]），而 --sp-* / --fs-* / --r-* 都定义在
# :root 块里——预览页上全部缺失，var(--sp-2) 逐条失效归零：
# 内边距 0、间距 0、字号退化成继承值。真页面是好的，
# 预览却「整体挤成一团」，而且每一轮改动都白调。
# 现在整份 tokens.css 原样内联（六套主题都在，预览只用到两套，无害），
# 外壳样式由本脚本持有，不再从上一份生成页里考古。
SHELL_CSS = """*{box-sizing:border-box}
body{margin:0;background:var(--t-canvas);color:var(--t-text);
  font:14px/1.7 MiSans,"Microsoft YaHei","PingFang SC",system-ui,sans-serif;
  padding:20px;transition:background .3s,color .3s}
.wrap{max-width:1180px;margin:0 auto}
.bar{display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap}
.bar h1{font-size:14px;font-weight:600;margin:0 auto 0 0;color:var(--t-text-strong)}
.bar button{font:inherit;font-size:12px;padding:6px 11px;border-radius:6px;cursor:pointer;
  color:var(--t-text);background:var(--t-surface);border:1px solid var(--t-line-firm)}
.bar button:hover{background:var(--t-surface-soft)}
.bar .hint{font-size:11px;color:var(--t-text-faint);width:100%;margin:0}
/* 预览划一条边界：框内是页面本体。 */
#contactWorkspace{border:1px dashed var(--t-line-firm);border-radius:9px;padding:16px;
  background:var(--t-surface-soft)}"""

CURVE = ("0.22,0.16,0.12,0.10,0.10,0.14,0.28,0.50,0.66,0.72,0.78,0.92,1.0,0.94,"
         "0.82,0.74,0.78,0.92,1.0,0.98,0.88,0.70,0.48,0.32")
settings = {
    "enabled": True, "automatic_enabled": True,
    "quiet_enabled": True, "quiet_start": "23:00", "quiet_end": "07:00",
    "quiet_timezone": "Asia/Shanghai",
    "proactive_intensity_preset": "balanced",
    "proactive_hour_activity_enabled": True, "proactive_hour_activity_curve": CURVE,
    "interval_seconds": 3600, "idle_seconds": 900,
    "max_contacts_24h": 3,
    "enable_proactive_burst": True, "proactive_burst_max_messages": 2,
    "proactive_burst_gap_min_seconds": 45, "proactive_burst_gap_max_seconds": 180,
    "proactive_closing_grace_minutes": 45, "proactive_closing_contacts_threshold": 3,
    "proactive_share_probability": 70, "proactive_intensity_body_chars": 0,
    "pause_until": "", "note": "",
    "contact_followup_after_minutes": 45, "contact_followup_cooldown_minutes": 180,
    "dedup_enabled": True, "dedup_last_message_enabled": True,
    "dedup_sent_window_minutes": 240, "dedup_last_message_window_minutes": 240,
    "dedup_min_shared_tokens": 2, "dedup_min_overlap_ratio": 0.4,
    "event_max_age_seconds": 3600,
    "dedup_policies": "semantic,content_fingerprint,life_event,event_revision",
    "enable_daily_greetings": True,
    "greeting_morning_window": "07:45-10:20", "greeting_noon_window": "12:05-13:35",
    "greeting_evening_window": "20:10-21:20", "greeting_idle_minutes": 30,
    "allow_insomnia_night_message": True,
    "insomnia_night_start": "23:00", "insomnia_night_end": "06:00",
    "insomnia_night_daily_limit": 1, "insomnia_require_sleep_state": False,
    "weather_checkin_enabled": True, "weather_checkin_time": "08:30",
    "weather_sample_minutes": 60, "weather_change_enabled": True,
    "dedup_weather_window_minutes": 1080,
    "official_weather_alert_enabled": False, "official_alert_poll_minutes": 5,
    "official_alert_min_severity": "severe",
    "news_share_enabled": True, "news_check_interval_minutes": 180,
    "news_source_kind": "host", "news_source_uid": "", "news_source_url": "",
    "news_daily_hot_read_enabled": False, "news_hot_sources": "weibo,hackernews",
    "news_hot_result_count": 10,
    "meal_checkin_enabled": True, "meal_lunch_time": "12:00",
    "meal_dinner_time": "18:00", "meal_care_followup_minutes": 45,
    "date_checkin_enabled": True, "date_checkin_time": "09:00",
    "important_date_lookahead_days": 7,
    "web_exploration_enabled": False, "web_exploration_interests": "",
    "web_exploration_min_interval_hours": 8, "web_exploration_result_count": 8,
    "external_event_self_link_enabled": True,
    "external_event_self_link_cooldown_hours": 12, "external_event_self_link_weight": 1.5,
    "screen_glance_enabled": False, "screen_glance_daily_limit": 1,
    "screen_glance_cooldown_minutes": 240, "screen_glance_goodnight_enabled": False,
    "screen_glance_goodnight_delay_minutes": 45, "screen_glance_followup_enabled": False,
    "screen_glance_followup_after_minutes": 45,
    "screen_glance_followup_cooldown_minutes": 180,
    "voice_action_enabled": True, "voice_action_max_chars": 30,
    "voice_action_cooldown_minutes": 60,
    "poke_action_enabled": True, "poke_action_daily_limit": 1,
    "poke_action_cooldown_minutes": 30,
    "appointment_lead_minutes": 30, "appointment_lag_minutes": 0,
    "appointment_pre_silence_minutes": 20,
    "enable_llm_proactive_persona_judge": False,
    "proactive_persona_judge_threshold": 62,
    "proactive_persona_judge_cache_minutes": 180,
    "proactive_persona_judge_exempt_purposes": "",
    "generation_history_limit": 8, "history_max_chars": 8192,
    "important_dates": "[]", "style_prompt": "",
    "silence_feedback_penalty": 0.2, "silence_min_confidence": 0.66,
    "unanswered_pause_after": 0, "unanswered_slowdown_start": 1,
    "unanswered_max_interval_multiplier": 2.2,
    "balance_awareness_enabled": False, "balance_include_amount_in_message": False,
    "balance_currency_label": "元", "balance_check_interval_minutes": 60,
    "balance_low_threshold": 10, "balance_critical_threshold": 3,
    "balance_low_percent_threshold": 15, "balance_critical_percent_threshold": 5,
    "balance_message_cooldown_hours": 24,
}
PURPOSES = [("affection", "想念与亲近"), ("care", "情绪关怀"), ("play", "轻松互动"),
            ("repair", "关系修复"), ("chat", "日常话题"), ("greeting", "问候与纪念"),
            ("followup", "接回旧话题"), ("invitation", "共同活动邀请"),
            ("reminder", "约定与提醒"), ("meal", "饭点问候"), ("life", "分享自己的生活"),
            ("creation", "作品与阅读"), ("news", "外部资讯"),
            ("environment", "环境与状态变化"), ("screen", "已授权屏幕观察")]
WEIGHTS = {"affection": 2.4, "care": 1.8, "play": 1.2, "repair": 0.6, "chat": 2.0,
           "greeting": 1.4, "followup": 0.8, "invitation": 1.0, "reminder": 1.6,
           "meal": 0.5, "life": 1.5, "creation": 0.9, "news": 0.7,
           "environment": 1.1, "screen": 0.4}
BLOCKED = {"screen": "authorization_denied", "news": "model_task_unregistered"}
PAUSED = {"meal": "2026-10-02T12:00:00+08:00"}
OFF = {"creation"}
for name, _label in PURPOSES:
    settings[name + ".enabled"] = name not in OFF
    settings[name + ".weight"] = WEIGHTS[name]
    settings[name + ".pause_until"] = PAUSED.get(name, "")

status = {
    "settings": settings, "edit_token": "n" * 64,
    "effective": {"allowed": True, "reason": None, "automatic_allowed": True,
                  "automatic_reason": None, "model_registered": True,
                  "readonly_fields": []},
    "purposes": {name: {"label": label, "allowed": name not in BLOCKED,
                        "reason": BLOCKED.get(name)} for name, label in PURPOSES},
    "host_state": "running",
}

TEMPLATE = pathlib.Path("docs/page-designs/contact-rhythm-preview.html")
DEST = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else TEMPLATE
CSS_MARK = "/* ===== contact-page.css 原样内联 ===== */"
JS_MARK = "/* ===== contact-page.js 原样内联（预览与真页面同一个文件） ===== */"
HEAD_MARK = "/* ===== tokens.css 整份内联（含 :root 尺寸/字号令牌） ===== */"
REPLY_MARK = "const REPLY = "


def build_head():
    return (HEAD_MARK + "\n" + tokens + "\n\n" + SHELL_CSS + "\n\n"
            + CSS_MARK + "\n" + css)


def splice(previous):
    """把令牌、样式与脚本换进上一份生成页，其余（假桥、按钮、说明）原样保留。

    为什么需要这条路：模板原先指向仓库外的一个临时目录
    （/sessions/sharp-great-euler/scratch/…），换一台机器就没有了，
    于是「改完样式重新生成预览」根本没有能执行的办法——预览会一直停在
    上一次生成的那一版，而它照样打得开，没人察觉得到里面的页面是旧的。
    生成页自己就是一份完整模板：头部 <style> 整块重建，
    脚本按 JS_MARK 替换那一段即可。

    data-theme-ready：tokens.css 里有首屏引导闸门
    （:root:not([data-theme-ready]) body{visibility:hidden}，
    还有同款的 data-room-ready 闸门——体素包就绪前 body 也隐藏）。
    真页面由引导脚本在样式生效前写好这些标记；预览没有引导脚本，
    必须在 <html> 上直接带上，否则整页 visibility:hidden——
    DOM 都在、控制台干净，就是什么都看不见。"""
    import re
    m = re.search(r"<html\b[^>]*>", previous)
    if m:
        tag = m.group(0)
        add = "".join(f' {a}' for a in ("data-theme-ready", "data-room-ready")
                      if a not in tag)
        if add:
            previous = (previous[:m.start()] + tag[:-1] + add + ">"
                        + previous[m.end():])
    style_at = previous.index("<style>") + len("<style>")
    style_end = previous.index("</style>", style_at)
    reply_at = previous.index(REPLY_MARK) + len(REPLY_MARK)
    reply_end = previous.index(";", reply_at)
    js_at = previous.index(JS_MARK) + len(JS_MARK)
    js_end = previous.index("</script>", js_at)
    reply = json.dumps({"status": status}, ensure_ascii=False, separators=(",", ":"))
    return (previous[:style_at] + "\n" + build_head() + previous[style_end:reply_at]
            + reply + previous[reply_end:js_at] + "\n" + js + previous[js_end:])


if DEST.exists():
    out = splice(DEST.read_text(encoding="utf-8"))
elif TEMPLATE.exists():
    out = splice(TEMPLATE.read_text(encoding="utf-8"))
else:
    raise SystemExit("没有可以续写的生成页：" + str(DEST) +
                     "（模板已不再依赖仓库外的临时目录，但首次仍需一份带壳的生成页）")
DEST.write_bytes((out.rstrip("\n") + "\n").encode("utf-8"))
print("已生成", DEST, len(out), "字节")
