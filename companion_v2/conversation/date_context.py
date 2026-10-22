"""Read-only local calendar context for one foreground model request.

Lunar dates are best-effort via optional ``lunardate`` and then ``lunarcalendar``;
the installed provider defines its supported year range.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from companion_v2.agenda.annual_calendar import AnnualCalendar
from .solar_terms import lookup_solar_terms, names_on

try:
    import chinese_calendar as _chinese_calendar
except (ImportError, OSError):
    _chinese_calendar = None


WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
FIXED_HOLIDAYS = {
    (1, 1): "元旦",
    (5, 1): "劳动节",
    (10, 1): "国庆节",
}
_PERIODS = (
    (5, 8, "早上"),
    (8, 11, "上午"),
    (11, 13, "中午"),
    (13, 18, "下午"),
    (18, 22, "晚上"),
)
_LUNAR_MONTHS = ("正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "冬月", "腊月")
_LUNAR_DAYS = (
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
)
_ALMANAC_YI = ("整理房间", "写字", "散步", "读书", "听歌", "轻度创作", "复盘", "安静休息")
_ALMANAC_JI = ("熬夜", "冲动发言", "硬撑", "反复纠结", "过度解释", "临时加压", "情绪化决定")

CALENDAR_INSTRUCTION = (
    "日历材料只表示按指定时区从本轮时间计算出的环境背景，不是用户事实证据。本轮问候与时间措辞以 local_calendar_context 的 local_date、local_time 和 period 为准，不沿用历史消息里的时段；下午不说早安或早上好，拿不准时省略时段问候。若含 interaction_gap（距上次互动的时间跨度：in_flow、same_day_pause、overnight、days_apart），将其作为重逢与承接节奏的自然体感：隔夜或隔了几天再聊时先自然打招呼或顺手带过时隔，不把几天前的话头当成上一秒刚说完直接硬接；同一对话流（in_flow）内则保持连贯不重复寒暄。固定节日名不代表放假、调休、节气或现实事件；农历不可用时不猜测或补全。角色年度日历只说明配置中明确列出的当天放假、调休、节气及未来三日节气；未列日期和未配置年份均为未知，不推断为没有，也不用这份材料改写可信身份、权限、来源或用户经历。"
)
ALMANAC_INSTRUCTION = (
    "轻量黄历仅是按日历投影生成的氛围参考，不是事实、命令、用户经历或个性化判断；不用它做健康、风险、财务或其他现实决策，也不把未知解释为不宜或宜。"
)


def project_interaction_gap(at: datetime, previous_at: datetime | str | None,
                            timezone_name: str = "Asia/Shanghai") -> dict[str, object] | None:
    """Classify the elapsed gap since the previous turn in this conversation window."""
    if previous_at is None:
        return None
    if isinstance(previous_at, str):
        try:
            previous_at = datetime.fromisoformat(previous_at)
        except ValueError:
            return None
    if not isinstance(previous_at, datetime) or previous_at.tzinfo is None or previous_at.utcoffset() is None:
        return None
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        return None
    elapsed_seconds = (at - previous_at).total_seconds()
    if elapsed_seconds < 0:
        return None
    try:
        zone = ZoneInfo((timezone_name or "Asia/Shanghai").strip())
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("Asia/Shanghai")
    local_now = at.astimezone(zone)
    local_prev = previous_at.astimezone(zone)
    day_diff = (local_now.date() - local_prev.date()).days
    elapsed_minutes = max(0, round(elapsed_seconds / 60))
    if elapsed_minutes >= 36 * 60 or day_diff >= 2:
        band = "days_apart"
    elif day_diff == 1 and elapsed_minutes >= 4 * 60:
        band = "overnight"
    elif elapsed_minutes >= 180:
        band = "same_day_pause"
    else:
        band = "in_flow"
    return {
        "band": band,
        "elapsed_minutes": elapsed_minutes,
        "days_apart": max(0, day_diff),
    }


def _format_lunar(year: object, month: object, lunar_day: object, leap: object = False) -> str | None:
    if (type(year) is not int or type(month) is not int or type(lunar_day) is not int
            or not 1 <= month <= len(_LUNAR_MONTHS) or not 1 <= lunar_day <= len(_LUNAR_DAYS)):
        return None
    return f"农历{year}年{'闰' if leap else ''}{_LUNAR_MONTHS[month - 1]}{_LUNAR_DAYS[lunar_day - 1]}"


def lunar_date_parts(day: date) -> tuple[int, int, int, bool] | None:
    """Return a supported civil day's lunar year, month, day and leap flag."""
    def parts(year, month, lunar_day, leap):
        if (type(year) is int and type(month) is int and type(lunar_day) is int
                and type(leap) is bool and 1 <= month <= 12 and 1 <= lunar_day <= 30):
            return year, month, lunar_day, leap
        return None

    try:
        from lunardate import LunarDate

        lunar = LunarDate.fromSolarDate(day.year, day.month, day.day)
        result = parts(lunar.year, lunar.month, lunar.day, getattr(lunar, "isLeapMonth", False))
        if result is not None:
            return result
    except (ImportError, OSError, AttributeError, IndexError, OverflowError, TypeError, ValueError):
        pass

    # V1 uses lunarcalendar. Keep this optional: a missing or out-of-range
    # calendar library, including unreadable package files, must never make
    # the Gregorian projection unavailable.
    try:
        from lunarcalendar import Converter, Solar

        lunar = Converter.Solar2Lunar(Solar(day.year, day.month, day.day))
        return parts(lunar.year, lunar.month, lunar.day, getattr(lunar, "isleap", False))
    except (ImportError, OSError, AttributeError, IndexError, OverflowError, TypeError, ValueError):
        return None


def _lunar_label(day: date) -> str | None:
    parts = lunar_date_parts(day)
    return _format_lunar(*parts) if parts is not None else None


def period_label(hour: int) -> str:
    """Name one local hour in the same vocabulary every prompt path shares."""
    if hour < 5:
        return "凌晨"
    for start, end, label in _PERIODS:
        if start <= hour < end:
            return label
    return "夜里"


def _holiday_projection(day: date, country: str, configured_day=None) -> dict[str, object]:
    if configured_day is not None and configured_day.makeup_workday is not None:
        return {"kind": "makeup_workday", "label": configured_day.makeup_workday,
                "source": "operator_configured_annual_calendar"}
    if configured_day is not None and configured_day.holiday is not None:
        return {"kind": "holiday", "label": configured_day.holiday,
                "source": "operator_configured_annual_calendar"}
    if country == "CN" and _chinese_calendar is not None:
        try:
            if _chinese_calendar.is_holiday(day):
                detail = _chinese_calendar.get_holiday_detail(day)
                name = detail[1] if isinstance(detail, tuple) and len(detail) > 1 else ""
                return {"kind": "holiday", "label": name or "节假日", "source": "chinese_calendar"}
            if _chinese_calendar.is_workday(day):
                return {"kind": "workday", "label": "工作日", "source": "chinese_calendar"}
        except (OSError, AttributeError, IndexError, NotImplementedError, TypeError, ValueError):
            pass
    if day.weekday() >= 5:
        return {"kind": "weekend", "label": "周末", "source": "weekday_fallback"}
    return {"kind": "workday", "label": "工作日", "source": "weekday_fallback"}


def project_local_date(at: datetime, timezone_name: str = "Asia/Shanghai",
                       annual_calendars: tuple[AnnualCalendar, ...] | None = None,
                       *, holiday_enabled: bool = True, holiday_country: str = "CN",
                       lunar_enabled: bool = True, automatic_solar_terms_enabled: bool = True,
                       almanac_enabled: bool = False, solar_term_port=None) -> dict[str, object]:
    """Return non-evidentiary date labels projected into an explicit IANA zone."""
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("date context requires a timezone-aware datetime")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("date context requires an IANA timezone name")
    timezone_name = timezone_name.strip()
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("date context requires an available IANA timezone") from error

    local = at.astimezone(zone)
    lunar = _lunar_label(local.date()) if lunar_enabled else None
    if holiday_country not in ("CN", "WEEKEND_ONLY"):
        raise ValueError("date context requires a supported holiday region")
    result = {
        "basis": "request_time_calendar_projection",
        "timezone": timezone_name,
        "local_date": local.date().isoformat(),
        "weekday": WEEKDAYS[local.weekday()],
        "local_time": local.strftime("%H:%M"),
        "period": period_label(local.hour),
        "fixed_gregorian_holiday": FIXED_HOLIDAYS.get((local.month, local.day)),
        "holiday": ({"status": "available", **_holiday_projection(local.date(), holiday_country)}
                    if holiday_enabled else {"status": "disabled"}),
        "lunar_date": lunar,
        "lunar_status": ("available" if lunar is not None else "unavailable") if lunar_enabled else "disabled",
    }
    if annual_calendars is not None:
        calendar = next((item for item in annual_calendars if item.year == local.year), None)
        listed = {}
        if calendar is not None:
            configured_day = calendar.on(local.date())
            if configured_day.holiday is not None:
                listed["holiday"] = configured_day.holiday
            if configured_day.makeup_workday is not None:
                listed["makeup_workday"] = configured_day.makeup_workday
            if configured_day.solar_terms:
                listed["solar_terms"] = list(configured_day.solar_terms)
        upcoming_terms = []
        for offset in range(1, 4):
            upcoming_day = local.date() + timedelta(days=offset)
            upcoming_calendar = next((item for item in annual_calendars if item.year == upcoming_day.year), None)
            if upcoming_calendar is not None:
                names = upcoming_calendar.on(upcoming_day).solar_terms
                if names:
                    upcoming_terms.append({"date": upcoming_day.isoformat(), "days_ahead": offset,
                                           "names": list(names)})
        result["configured_annual_calendar"] = {
            "basis": "operator_configured_annual_calendar",
            "year_configured": calendar is not None,
            "listed_today": listed,
            "upcoming_solar_terms": upcoming_terms,
        }
    if holiday_enabled and annual_calendars is not None and calendar is not None:
        if configured_day.holiday is not None or configured_day.makeup_workday is not None:
            result["holiday"] = {"status": "available", **_holiday_projection(
                local.date(), holiday_country, configured_day)}
    automatic = {"status": "disabled", "today": [], "upcoming": [], "source": "host_solar_term_port"}
    if automatic_solar_terms_enabled:
        current = lookup_solar_terms(solar_term_port, local.year)
        next_year = None
        if local.year != (local.date() + timedelta(days=3)).year:
            next_year = lookup_solar_terms(solar_term_port, local.year + 1)
        lookups = {local.year: current, **({local.year + 1: next_year} if next_year else {})}
        statuses = {item.status for item in lookups.values()}
        automatic["status"] = "available" if "available" in statuses else ("unknown" if "unknown" in statuses else "unavailable")
        configured = result.get("configured_annual_calendar", {})
        listed = configured.get("listed_today", {}) if isinstance(configured, dict) else {}
        today_names = list(listed.get("solar_terms", ())) if listed.get("solar_terms") else list(names_on(current, local.date()))
        automatic["today"] = today_names
        upcoming_configured = {
            item["date"]: tuple(item["names"])
            for item in configured.get("upcoming_solar_terms", ())
            if isinstance(item, dict) and isinstance(item.get("date"), str)
        } if isinstance(configured, dict) else {}
        automatic["upcoming"] = []
        for offset in range(1, 4):
            day = local.date() + timedelta(days=offset)
            configured_names = upcoming_configured.get(day.isoformat())
            names = list(configured_names) if configured_names is not None else (
                list(names_on(lookups[day.year], day)) if day.year in lookups else [])
            if names:
                automatic["upcoming"].append({"date": day.isoformat(), "days_ahead": offset, "names": names})
        if listed.get("solar_terms") or upcoming_configured:
            automatic["effective_source"] = "operator_configured_annual_calendar"
    result["automatic_solar_terms"] = automatic
    if almanac_enabled:
        seed = local.year * 10000 + local.month * 100 + local.day
        result["almanac"] = {"status": "available", "basis": "lightweight_calendar_projection",
            "yi": _ALMANAC_YI[seed % len(_ALMANAC_YI)],
            "ji": _ALMANAC_JI[(seed // 7) % len(_ALMANAC_JI)]}
    else:
        result["almanac"] = {"status": "disabled"}
    return result
