"""Optional companion providers discovered through the AstrBot registry."""

from typing import Any

OPTIONAL_PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "plugin_id": "astrbot_plugin_private_companion",
        "capability_id": "private_core_legacy",
        "label": "旧版陪伴核心",
        "description": "仅显示旧版插件的运行状态，旧版资料与执行仍由原插件管理。",
        "furniture": {"id": "legacy-core", "name": "陪伴核心台", "panel_id": "legacy-core"},
    },
    {
        "plugin_id": "astrbot_plugin_content_companion",
        "capability_id": "content",
        "label": "创作与 QQ 空间",
        "description": "创作项目、作品版本、封面与 QQ 空间联动。",
        "furniture": {"id": "content", "name": "创作书架", "panel_id": "content"},
    },
    {
        "plugin_id": "astrbot_plugin_image_companion",
        "capability_id": "image",
        "label": "生图与相册",
        "description": "生成、编辑、参考图和原件保留。",
        "furniture": {"id": "image", "name": "画面工作室", "panel_id": "image"},
    },
    {
        "plugin_id": "astrbot_plugin_reality_companion",
        "capability_id": "reality",
        "label": "现实触及",
        "description": "摄像头、米家、移动端和现实设备来源。",
        "furniture": {"id": "reality", "name": "现实设备台", "panel_id": "reality"},
    },
    {
        "plugin_id": "astrbot_plugin_screen_companion",
        "capability_id": "screen",
        "label": "屏幕陪伴",
        "description": "授权范围内的屏幕采集、识别和观察记录。",
        "furniture": {"id": "screen", "name": "屏幕台", "panel_id": "screen"},
    },
    {
        "plugin_id": "astrbot_plugin_together_companion",
        "capability_id": "together",
        "label": "共处与实时活动",
        "description": "共读、观影、通话和实时房间。",
        "furniture": {"id": "together", "name": "共处电话", "panel_id": "together"},
    },
    {
        "plugin_id": "astrbot_plugin_game_companion",
        "capability_id": "game",
        "label": "共同游玩",
        "description": "棋类、派对和多人游戏房间。",
        "furniture": {"id": "game", "name": "游戏棋桌", "panel_id": "game"},
    },
    {
        "plugin_id": "astrbot_plugin_live_stream_companion",
        "capability_id": "live",
        "label": "直播与表演",
        "description": "直播事件、Live2D、SoulLink 和角色呈现。",
        "furniture": {"id": "live", "name": "直播与表演", "panel_id": "live"},
    },
)

