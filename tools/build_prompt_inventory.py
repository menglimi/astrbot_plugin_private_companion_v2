"""Build the prompt inventory workbook from the source tree and the dated markdown list.

Reads every module-level prompt constant (Chinese string literals) plus the
``ModelTaskProfile`` task phrases, joins them with the reviewed purpose/gate rows
from ``docs/PROMPTS_INVENTORY_20261018.md`` (plus a small curated table for prompts
that the markdown mentions only in passing), and writes one workbook with the full
default prompt texts.

Run with the bundled Python (openpyxl), from the repository root:
    python tools/build_prompt_inventory.py
"""

from __future__ import annotations

import ast
import math
import pathlib
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = ("companion_v2", "astrbot_host")
DOC = ROOT / "docs" / "PROMPTS_INVENTORY_20261018.md"
OUTPUT = ROOT / "docs" / "PROMPTS_INVENTORY_20261018.xlsx"
CJK = re.compile(r"[\u4e00-\u9fff]")

USER_TEXT_NAMES = {
    "MODEL_FAILURE_NOTICE", "DENIED_REPLY", "CONFIRM_WORD", "CONFIRM_WORDS", "PRODUCT_DISPLAY_NAME",
    "MANAGED_PAGE_MESSAGE", "PREFERENCE_HEADING", "BIND_COMMAND", "CONFIRM_COMMAND", "UNBIND_COMMAND",
    "_MANUAL_INVALID", "_NO_CONNECTION", "_RUNTIME_MISSING", "_WAKEUP_DEFAULT_MESSAGE",
    "_WAKEUP_DYNAMIC_MESSAGE_HINT", "_REALITY_TOUCH_CONFIRMATION_TEXT",
    "_REALITY_TOUCH_CAMERA_CONFIRMATION_TEXT", "MEMORY_OWNER_DISPLAY_NAME", "DEFAULT_AI_NEWS_FEED_LABEL",
}
USER_TEXT_PREFIXES = ("CATEGORY_",)
MARKER_NAMES = {
    "ASSET", "NO_REPLY_BOUNDARY", "DEFAULT_DISCOMFORT_TYPES", "ADDRESS_MARKER", "MARKED",
    "WORKER_QR_PAYLOAD_START", "WORKER_QR_PAYLOAD_END",
}

# Gate rows for prompts the markdown only mentions in passing. Keyed by a path
# suffix plus the constant name so duplicate names (PROMPT, INSTRUCTION, MEANING)
# stay apart.
CURATED = {
    ("adapters/astrbot/model_wire.py", "REPLY_CONTRACT_EXAMPLE"): (
        "输出契约内嵌的有效示例（一条 observed claim）", "output_format=conversation 时随契约拼接", "system 第 2 条"),
    ("adapters/astrbot/reply_stream.py", "STREAM_REPLY_INSTRUCTION"): (
        "流式字段顺序契约", "streaming_mode=incremental", "system 第 2 条与末段"),
    ("conversation/addressing.py", "ADDRESSING_REFLECTION_INSTRUCTION"): (
        "反思阶段复核称呼是否合适", "memory.reflect 任务", "独立任务 system"),
    ("conversation/agenda_tools.py", "CONTINUATION_INSTRUCTION"): (
        "工具续作的回执解释", "私聊工具轮，恒与 TOOL_INSTRUCTION 同拼", "工具说明"),
    ("conversation/diagnostic_tools.py", "DIAGNOSTIC_INSTRUCTION"): (
        "诊断材料的证据等级", "私聊工具轮", "工具说明"),
    ("conversation/humanized_expression.py", "GUIDED_PROMPT"): (
        "guided 档的一句话风格", "prompt_style_mode=guided", "system"),
    ("conversation/humanized_expression.py", "DEFAULT_PROMPT"): (
        "日常表达正文", "enable_humanized_expression 且档位不是 constraint", "system"),
    ("conversation/media/image_narration.py", "DIRECT_IMAGE_INSTRUCTION"): (
        "原图直读的边界", "使用回复模型且开启私聊看图自识别", "system"),
    ("conversation/media/review.py", "_INSTRUCTION"): (
        "群图安全分类器指令", "群聊成图且审核模式非 off", "独立任务 system"),
    ("conversation/media/review.py", "_BOUNDARIES"): (
        "各分类标签的判定边界", "同上", "独立任务 system"),
    ("conversation/media/understanding.py", "VIDEO_INSTRUCTION"): (
        "视频转述材料口径（无引用）", "无引用路径，实际用 video/narration 的同名常量", "—"),
    ("conversation/media/understanding.py", "FILE_INSTRUCTION"): (
        "文件正文不是发送者陈述", "材料含文件阅读正文", "system"),
    ("conversation/media/video/narration.py", "VIDEO_INSTRUCTION"): (
        "视频转述材料的边界", "有视频且走转述路径", "system"),
    ("conversation/media/video/narration.py", "DIRECT_VIDEO_INSTRUCTION"): (
        "原生视频直读边界", "回复路由支持 video 输入", "system"),
    ("conversation/participation_prompts.py", "DENOISE_LINE"): (
        "群聊人格降噪", "群聊且 enable_group_persona_denoise", "system"),
    ("conversation/pokes.py", "MODEL_REPLY_PROMPT"): (
        "戳一戳的模型回应", "戳一戳 model_reply_enabled", "独立任务 system"),
    ("conversation/segmentation.py", "DEFAULT_PROMPT"): (
        "模型分段协议（{{split_marker}}）", "分段 enabled 且 llm_controlled，自定义为空", "system"),
    ("conversation/self_review_context.py", "SELF_REVIEW_INSTRUCTION"): (
        "短期表达建议只约束自己", "仅宿主背景段注入已采纳建议；V2 链路只有材料", "system"),
    ("conversation/text_processing.py", "FRAMEWORK_GUARD_REPLACEMENT"): (
        "框架泄漏的替换文案", "framework_error_guard_enabled 且命中堆栈", "后处理"),
    ("conversation/text_processing.py", "REALITY_PROMISE_GUARD_REPLACEMENT"): (
        "越权承诺的替换文案", "群聊且 enable_group_reality_promise_guard", "后处理"),
    ("conversation/group_timing.py", "ADDRESS_MARKER"): (
        "提及机器人的标记", "群聊判定时使用", "标记"),
    ("expression/reactions.py", "SEARCH_INSTRUCTION"): (
        "表情检索 intent 的写法", "工具目录含表情检索", "工具说明"),
    ("expression/learning.py", "INSTRUCTION"): (
        "表达学习的观察规则", "无引用（仅测试）；实际用 style_service.PROMPT", "—"),
    ("memory/group/slang.py", "CANDIDATE_PROMPT"): (
        "群内词义候选抽取", "群内词义整理任务", "独立任务 system"),
    ("memory/group/slang.py", "EXTERNAL_NOTE"): (
        "外部检索只作参考", "有外部检索结果", "system"),
    ("proactive/prompt_templates.py", "EXPRESSION_INSTRUCTION"): (
        "主动正文的日常表达风格", "每次主动联系", "system"),
    ("proactive/prompt_templates.py", "NEWS_SHARING_INSTRUCTION"): (
        "新闻分享口吻与边界", "目的为新闻或来源含资讯", "system"),
    ("proactive/prompt_templates.py", "LENGTH_INSTRUCTION"): (
        "主动正文字数上限（{chars}）", "非新闻且强度档位给出字数", "system"),
    ("proactive/prompt_templates.py", "NEWS_LENGTH_INSTRUCTION"): (
        "新闻全文合计字数（{chars}）", "新闻分支且给出字数", "system"),
    ("proactive/news_context.py", "UNAVAILABLE_INSTRUCTION"): (
        "没有可验证资讯时的说明", "资讯目的且无可用来源", "system"),
    ("proactive/balance_events.py", "MEANING"): (
        "经费状态不是用户欠款", "余额来源作为证据注入时", "材料"),
    ("proactive/news_events.py", "MEANING"): (
        "外部资讯未经独立核实", "资讯来源作为证据注入时", "材料"),
    ("proactive/official_alert_events.py", "MEANING"): (
        "预警覆盖范围不等于对方所在地", "官方预警作为证据注入时", "材料"),
    ("proactive/weather_events.py", "MEANING"): (
        "天气观测只代表角色所在地", "天气来源作为证据注入时", "材料"),
    ("proactive/weather_change_events.py", "MEANING"): (
        "天气变化只说明两次观测差异", "天气变化作为证据注入时", "材料"),
    ("role_work/life/rest_gate.py", "BACKLOG_INSTRUCTION"): (
        "休息期积压私聊的补看说明", "生产无调用者（仅测试）", "—"),
    ("role_work/state/cycle_prompts.py", "VARIATION"): (
        "周期方案变体的说明", "cycle_enabled 且 variation_enabled", "system"),
    ("role_work/journal/self_review.py", "INSTRUCTION"): (
        "自评候选的完整指令", "无生产引用；实际用 self_review_service.PROMPT", "—"),
    ("astrbot_host/core_reply_perception.py", "_POLICY"): (
        "感知与自然表达的固定策略", "每次核心请求（有 prepared 且幂等去重）", "system"),
    ("astrbot_host/core_reply_context.py", "CURRENT_TIME_INSTRUCTION"): (
        "本轮时间口径与报时边界", "每次构建感知（附在表达指引里）", "user 上下文"),
    ("astrbot_host/core_reply_context.py", "SENT_CONTINUATION_INSTRUCTION"): (
        "已发主动消息的承接口径", "私聊且有投递记录", "system"),
    ("astrbot_host/fish_audio.py", "DRAMA_DIRECTION"): (
        "Drama 3 表演与语气指令", "fishaudio Provider 且模型 drama-3", "system"),
    ("native_extensions/together/common.py", "BASE_REALTIME_PROMPT"): (
        "实时共处的基础说话规则", "together 房间内任一轮对话", "system"),
    ("native_extensions/together/common.py", "CALL_CONNECTED_CONTEXT_PROMPT"): (
        "通话已接通", "mode=call（work/watch 接通时也加）", "system"),
    ("native_extensions/together/common.py", "CALL_ROOM_CONTEXT_PROMPT"): (
        "房间通话上下文", "mode=call 且无麦克风帧", "system"),
    ("native_extensions/together/common.py", "CALL_CAMERA_CONTEXT_PROMPT"): (
        "摄像头单帧只作可见线索", "通话且本轮带帧且有视觉 Provider", "system"),
    ("native_extensions/together/common.py", "CLIENT_TIME_CONTEXT_PROMPT"): (
        "用浏览器上报时间", "mode=call 且 15 分钟内有上报", "system"),
    ("native_extensions/together/common.py", "WORK_COLLABORATION_CONTEXT_PROMPT"): (
        "工作协同的推进与证据", "mode=work 且语音已接通", "system"),
    ("native_extensions/together/common.py", "CALL_PROACTIVE_PROMPT"): (
        "静默时是否开口", "通话静默到阈值且开启主动找话题", "system"),
    ("native_extensions/together/common.py", "CALL_IDLE_HANGUP_PROMPT"): (
        "静默时是否结束通话", "通话静默且关闭主动找话题", "system"),
    ("native_extensions/together/common.py", "CALL_PROACTIVE_CONTINUE_PROMPT"): (
        "继续等待还是说话", "通话静默且允许挂断", "system"),
    ("native_extensions/together/common.py", "WATCH_SHARED_CONTEXT_PROMPT"): (
        "共看的信息来源与不剧透", "mode=watch", "system"),
    ("native_extensions/together/common.py", "WATCH_COMMENT_PROMPT"): (
        "此刻是否值得评论", "watch 帧触发且 auto_comment 为真", "system"),
    ("native_extensions/together/common.py", "WATCH_KNOWLEDGE_PROMPT"): (
        "观前无剧透背景卡", "watch.prepare_knowledge 且有视频页材料", "system"),
    ("native_extensions/together/common.py", "WATCH_MEMORY_PROMPT"): (
        "把已播片段整理成共同记忆", "新事件≥6 或到刷新间隔或影片结束", "system"),
    ("native_extensions/together/common.py", "NOVEL_SHARED_CONTEXT_PROMPT"): (
        "共读按已读边界回答", "mode=novel", "system"),
    ("native_extensions/together/common.py", "SHARED_EXPERIENCE_MEMORY_PROMPT"): (
        "共同经历是否值得记住", "条件恒假：record_shared_experiences 硬编码为 False", "—"),
    ("native_extensions/together/common.py", "STT_CORRECTION_PROMPT"): (
        "只纠明显转写错误", "speech.stt_correction_enabled 且转写可疑", "system"),
    ("native_extensions/together/common.py", "CALL_DIRECT_SPEECH_PROMPT"): (
        "外语语音块与可见正文", "通话且直接多语种 TTS", "system"),
    ("adapters/astrbot/memory_owner.py", "MEMORY_OWNER_DISPLAY_NAME"): (
        "记忆宿主适配器对外显示名称", "初始化记忆所有者时展示", "展示文案"),
    ("agenda/calendar.py", "INSTRUCTION"): (
        "日历材料与状态字段的归属及冲突协商边界", "日历查询或日程背景存在时", "system / 工具说明"),
    ("agenda/planning_output.py", "INSTRUCTION"): (
        "日程规划任务的范围、时区作息、天气日历边界与输出格式", "calendar.plan 规划任务执行时", "独立任务 system"),
    ("agenda/weather_tools.py", "INSTRUCTION"): (
        "天气实况工具只代表角色所在地及读取时机", "天气工具开放时", "工具说明"),
    ("conversation/behavior/prompts.py", "INSTRUCTION"): (
        "群聊互动习惯的观察、学习、定向互动与反馈边界", "群聊启用互动习惯学习或应用时", "system / 工具说明"),
    ("conversation/date_context.py", "CALENDAR_INSTRUCTION"): (
        "本地日历、时段问候、节假日与年度日历的口径边界", "感知开启日历背景时", "system / user 上下文"),
    ("conversation/date_context.py", "ALMANAC_INSTRUCTION"): (
        "轻量黄历仅作氛围参考、不做现实决策的边界", "感知开启日历与轻量黄历时", "system / user 上下文"),
    ("conversation/forwards/models.py", "INSTRUCTION"): (
        "合并转发记录的多层身份、时间与媒体归属边界", "本轮输入含合并转发记录时", "system"),
    ("conversation/growth_context.py", "ROLE_GROWTH_INSTRUCTION"): (
        "角色技能、长期目标与定性进展的背景参考边界", "当前角色存在已确认成长目标时", "system"),
    ("conversation/life_context.py", "LIFE_INSTRUCTION"): (
        "角色生活记录（睡眠、阅读、日记、梦境摘要）的引用边界", "当前角色存在可用生活记录时", "system"),
    ("conversation/media/audio/models.py", "INSTRUCTION"): (
        "本轮单声道 PCM 语音附件的听辨与身份归属边界", "本轮输入包含语音附件且直传音频时", "system"),
    ("conversation/media/generated.py", "INSTRUCTION"): (
        "本轮生成/编辑图片产物的归因与投递边界", "本轮工具返回生成或编辑图片时", "system"),
    ("conversation/media/screen.py", "INSTRUCTION"): (
        "按需采集的设备屏幕原件（screen_capture）的观察边界", "本轮挂载设备屏幕原件时", "system"),
    ("conversation/media/video/models.py", "INSTRUCTION"): (
        "视频抽帧清单（sampled/all_decoded）与未检音轨的边界", "本轮视频以抽帧形式提供时", "system"),
    ("conversation/open_items_context.py", "INSTRUCTION"): (
        "私聊未完话头的按需承接与完成核销边界", "私聊存在未到期 open_loop 备忘时", "system"),
    ("conversation/participation.py", "INSTRUCTION"): (
        "群聊旁听与参与选择（choose reply/skip）协议", "群聊未明确点名且由模型判定参与时", "system / 工具说明"),
    ("conversation/quotes/forward_models.py", "INSTRUCTION"): (
        "引用消息内嵌合并转发的三层归属与时间边界", "本轮引用消息中包含合并转发时", "system"),
    ("conversation/quotes/models.py", "INSTRUCTION"): (
        "引用历史消息的原发送者、时间与媒体归属边界", "本轮输入包含引用消息时", "system"),
    ("conversation/relationship_context.py", "RELATIONSHIP_INSTRUCTION"): (
        "经审阅采用的主观关系理解背景及其使用边界", "私聊存在已采用关系理解记录时", "system"),
    ("conversation/tool_loop.py", "TOOL_INSTRUCTION"): (
        "对话工具调用、回执状态解释与未完话头备忘规范", "V2 对话链路开放工具调用时", "system / 工具说明"),
    ("conversation/tool_loop.py", "GAME_PLAY_INSTRUCTION"): (
        "桌边游戏互动氛围、角色小动作与公平模式边界", "当前会话处于桌边小游戏对局时", "system"),
    ("expression/reaction_preferences.py", "ASSET"): (
        "用户提及表情包/贴纸/梗图的正则词表", "解析用户本轮是否要求或禁止发表情时", "正则标记"),
    ("expression/style_service.py", "PROMPT"): (
        "从授权聊天样本提炼可复用情境表达与语法习惯的规则", "role.expression.learn 表达学习任务执行时", "独立任务 system"),
    ("product/__init__.py", "PRODUCT_DISPLAY_NAME"): (
        "插件产品对外显示名称", "管理端与插件元数据展示时", "展示文案"),
    ("relationships/profile.py", "INSTRUCTION"): (
        "操作者维护的私聊对象相处资料背景及隐私边界", "私聊对象配置了相处画像资料时", "system"),
    ("relationships/tools.py", "INSTRUCTION"): (
        "主观关系理解与情绪片段提案（propose）的证据与审阅边界", "私聊工具轮开放关系提案工具时", "工具说明"),
    ("role_profile/context.py", "INSTRUCTION"): (
        "角色自身及世界观稳定档案的延续与使用边界", "当前角色配置了角色档案时", "system"),
    ("role_work/growth/tools.py", "INSTRUCTION"): (
        "角色成长目标提案、修订与列表查询的工具边界", "开放角色成长工具时", "工具说明"),
    ("role_work/life/rest_gate.py", "NO_REPLY_BOUNDARY"): (
        "识别用户表达无需回复/先去休息的句尾边界正则", "睡眠门控判断用户本轮是否放行休息时", "正则标记"),
    ("role_work/state/cycle.py", "DEFAULT_DISCOMFORT_TYPES"): (
        "生理周期默认可选不适类型列表", "周期配置初始化与默认候选读取时", "配置常量"),
    ("screen/pipeline.py", "SCREEN_INSTRUCTION"): (
        "识屏管线对屏幕原件的解读范围与反馈意图（attention/silence）边界", "识屏管线带屏幕材料进入对话/判断时", "system"),
    ("astrbot_host/binding.py", "BIND_COMMAND"): (
        "触发私聊伴侣绑定的口令文案", "用户在聊天窗口发送绑定命令时", "命令匹配文案"),
    ("native_extensions/reality/common.py", "MANAGED_PAGE_MESSAGE"): (
        "现实触及能力引导至陪伴小屋的提示文案", "旧入口或未托管页面访问现实触及功能时", "用户提示文案"),
    ("native_extensions/reality/mihome_device_profiles.py", "CATEGORY_AIR_FRYER"): (
        "米家设备分类标签：空气炸锅", "米家设备画像展示与归类时", "设备类别标签"),
    ("native_extensions/reality/mihome_device_profiles.py", "CATEGORY_TH_SENSOR"): (
        "米家设备分类标签：温湿度计", "米家设备画像展示与归类时", "设备类别标签"),
    ("native_extensions/reality/mihome_device_profiles.py", "CATEGORY_DOOR_SENSOR"): (
        "米家设备分类标签：门磁传感器", "米家设备画像展示与归类时", "设备类别标签"),
    ("native_extensions/reality/mihome_device_profiles.py", "CATEGORY_GAS_SENSOR"): (
        "米家设备分类标签：燃气传感器", "米家设备画像展示与归类时", "设备类别标签"),
    ("native_extensions/reality/reality_touch_camera.py", "_REALITY_TOUCH_CAMERA_CONFIRMATION_TEXT"): (
        "现实触及摄像头授权确认口令文案", "管理员开启摄像头能力二次确认时", "授权确认文案"),
    ("native_extensions/reality/wakeup_alarm.py", "_WAKEUP_DEFAULT_MESSAGE"): (
        "起床闹钟静态模式默认播报文本", "闹钟触发且未启用动态生成或生成降级时", "默认用户文案"),
    ("native_extensions/reality/wakeup_alarm.py", "_WAKEUP_DYNAMIC_MESSAGE_HINT"): (
        "起床闹钟动态生成模式的界面说明文案", "管理端展示闹钟动态文案配置项时", "界面提示文案"),
    ("native_extensions/reality/wakeup_alarm.py", "_REALITY_TOUCH_CONFIRMATION_TEXT"): (
        "现实触及闹钟授权确认口令文案", "管理员开启现实触及能力二次确认时", "授权确认文案"),
    ("astrbot_host/news.py", "DEFAULT_AI_NEWS_FEED_LABEL"): (
        "默认 AI 资讯源显示名称", "资讯源未自定义名称时展示", "默认标签文案"),
    ("astrbot_host/qzone_client.py", "_MANUAL_INVALID"): (
        "手动配置 QZone Cookie 格式无效的错误提示", "QZone 客户端校验手动 Cookie 失败时", "错误提示文案"),
    ("astrbot_host/qzone_client.py", "_NO_CONNECTION"): (
        "缺少可用 OneBot 连接且无手动 Cookie 的错误提示", "QZone 客户端获取凭据无可用连接时", "错误提示文案"),
    ("astrbot_host/qzone_client.py", "_RUNTIME_MISSING"): (
        "OneBot 未返回有效 QZone 凭据的错误提示模板", "QZone 客户端从 OneBot 取回凭据缺失字段时", "错误提示文案"),
}


TASK_KIND_OVERRIDES = {
    ("media/image_narration.py", None): "conversation.image_narration",
    ("media/context_caption.py", None): "conversation.context_image_caption",
    ("media/review_service.py", None): "conversation.image_review",
    ("media/video/narration.py", None): "conversation.video_narration",
    ("screen/interpretation.py", None): "screen.interpretation",
    ("proactive/service.py", 67): "proactive.compose",
    ("proactive/service.py", 90): "proactive.judge",
    ("expression/review.py", None): "role.expression.review / contact_review",
    ("journal/writing.py", None): "role.journal.diary / dream / derive / select",
}


def task_kind_override(rel_path: str, line: int) -> str | None:
    for (suffix, exact_line), kind in TASK_KIND_OVERRIDES.items():
        if rel_path.endswith(suffix) and (exact_line is None or exact_line == line):
            return kind
    return None


def string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value for part in node.values
                       if isinstance(part, ast.Constant) and isinstance(part.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = string_value(node.left), string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def module_constants(tree: ast.Module) -> dict:
    values = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                value = string_value(statement.value)
                if value is not None:
                    values[target.id] = value
    return values


def collect_constants() -> list[dict]:
    rows = []

    def walk(path: pathlib.Path, body, prefix=""):
        for statement in body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id.isupper() and len(target.id) > 2:
                        value = string_value(statement.value)
                        if value is None or len(value) < 6 or not CJK.search(value):
                            continue
                        rows.append({
                            "file": path.relative_to(ROOT).as_posix(),
                            "line": statement.lineno,
                            "name": prefix + target.id,
                            "base_name": target.id,
                            "text": value,
                        })
            elif isinstance(statement, ast.ClassDef):
                walk(path, statement.body, prefix + statement.name + ".")
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(path, statement.body, prefix + statement.name + "()/")

    for base in SOURCES:
        for path in sorted((ROOT / base).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            walk(path, tree.body)
    return rows


def collect_named_constants() -> dict:
    """All module-level uppercase string constants, for resolving kind=NAME arguments."""
    values: dict = {}
    for base in SOURCES:
        for path in sorted((ROOT / base).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for statement in tree.body:
                if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                    target = statement.targets[0]
                    if isinstance(target, ast.Name) and target.id.isupper():
                        value = string_value(statement.value)
                        if value is not None:
                            values.setdefault(target.id, value)
    return values


def collect_task_profiles(global_constants: dict) -> list[dict]:
    rows = []
    for base in SOURCES:
        for path in sorted((ROOT / base).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            constants = {**global_constants, **module_constants(tree)}
            rel = path.relative_to(ROOT).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name != "ModelTaskProfile" or not node.args:
                    continue
                first = node.args[0]
                kind = string_value(first)
                if kind is None and isinstance(first, ast.Name):
                    kind = constants.get(first.id)
                kind = task_kind_override(rel, node.lineno) or kind
                prompt = string_value(node.args[3]) if len(node.args) > 3 else None
                expression = ""
                if len(node.args) > 3 and prompt is None:
                    expression = ast.unparse(node.args[3])
                for keyword in node.keywords:
                    if keyword.arg == "task_prompt":
                        prompt = string_value(keyword.value)
                        if prompt is None:
                            expression = ast.unparse(keyword.value)
                rows.append({"kind": kind or "（未解析）", "prompt": prompt or "",
                             "expression": expression,
                             "file": rel, "line": node.lineno})
    return rows


def collect_repository_text() -> str:
    chunks = []
    for base in SOURCES:
        for path in sorted((ROOT / base).rglob("*.py")):
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def relation_matches(doc_rel: str, const_rel: str) -> bool:
    if "/" not in doc_rel:
        return doc_rel == pathlib.PurePosixPath(const_rel).name
    return const_rel == doc_rel or const_rel.endswith("/" + doc_rel) or doc_rel.endswith("/" + const_rel)


def clean(text: str) -> str:
    """Drop markdown code ticks so the workbook reads as plain text."""
    return text.replace("`", "").strip()


def parse_doc_tables() -> tuple[list[dict], dict, list[dict]]:
    """Return reviewed rows, config-field rows and suspicious rows from the markdown."""
    lines = DOC.read_text(encoding="utf-8").splitlines()
    rows: list[dict] = []
    fields: list[dict] = []
    suspicious: list[dict] = []
    header: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            header = []
            continue
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if not cells or all(set(cell) <= set("-: ") for cell in cells):
            continue
        if cells[0] in ("名称", "字段", "项", "文本", "指令", "字段/项", "提示词", "段", "材料", "项目"):
            header = cells
            continue
        if not header:
            continue
        row = {header[index]: cells[index] for index in range(min(len(header), len(cells)))}
        if "现象" in row:
            suspicious.append({"name": cells[0], "位置": row.get("位置", ""), "现象": row["现象"]})
            continue
        if "默认" in header or "覆盖层级" in header:
            fields.append({"field": cells[0], "默认": row.get("默认", ""),
                           "作用": row.get("作用", ""), "层级": row.get("覆盖层级", ""),
                           "消费": row.get("消费点", "")})
            continue
        if "位置" not in header:
            continue
        match = re.search(r"([\w./\\-]+\.py):(\d+)", row.get("位置", ""))
        if not match:
            continue
        rel = match.group(1).replace("\\", "/")
        names = re.findall(r"`([^`]+)`", cells[0])
        tokens = []
        for item in names:
            tokens.extend(re.findall(r"[A-Z][A-Z0-9_]{2,}", item) or [item])
        if not tokens:
            tokens = [""]
        rows.append({
            "rel": rel, "line": int(match.group(2)), "names": tokens,
            "作用": clean(row.get("作用", "") or row.get("作用（1 句）", "")),
            "前提": clean(row.get("注入前提", "") or row.get("前提", "") or ""),
            "位置": clean(row.get("注入位置", "") or row.get("注入载体", "") or ""),
            "原文位置": clean(row.get("位置", "")),
        })
    for item in suspicious:
        item["name"] = clean(item["name"])
        item["现象"] = clean(item["现象"])
    return rows, {"fields": fields}, suspicious


def find_reviewed(row: dict, reviewed: list[dict]) -> dict | None:
    const_rel = row["file"]
    name = row["base_name"]
    for entry in reviewed:
        if name in entry["names"] and relation_matches(entry["rel"], const_rel):
            return entry
    near = [entry for entry in reviewed
            if relation_matches(entry["rel"], const_rel) and abs(entry["line"] - row["line"]) <= 10]
    if len(near) == 1:
        return near[0]
    same_file = [entry for entry in reviewed if relation_matches(entry["rel"], const_rel)]
    if len(same_file) == 1:
        return same_file[0]
    return None


def curated_for(row: dict) -> tuple | None:
    for (suffix, name), value in CURATED.items():
        if name == row["base_name"] and row["file"].endswith(suffix):
            return value
    return None


def domain_of(rel_path: str) -> str:
    parts = pathlib.PurePosixPath(rel_path).parts
    if parts[0] == "astrbot_host":
        if len(parts) > 2 and parts[1] == "native_extensions":
            return "宿主·" + parts[2]
        return "宿主"
    return parts[1] if len(parts) > 2 else "companion_v2"


def classify(name: str) -> str:
    if name in MARKER_NAMES:
        return "正则/标记"
    if name in USER_TEXT_NAMES or name.startswith(USER_TEXT_PREFIXES):
        return "用户文案/标签"
    return "提示词"


def infer_position(row: dict) -> str:
    rel = row["file"]
    cat = classify(row["base_name"])
    if cat == "用户文案/标签":
        return "展示/固定文案"
    if cat == "正则/标记":
        return "正则/控制标记"
    if any(k in rel for k in ("tools.py", "authoring_workflow.py", "reactions.py")):
        return "工具说明"
    if any(k in rel for k in (
        "planning_output.py", "context_caption.py", "image_narration.py",
        "video/narration.py", "review.py", "persona_judge.py", "growth/progress.py",
        "journal/", "screen/interpretation.py", "style_service.py",
    )):
        return "独立任务 system"
    if "core_reply_context.py" in rel:
        return "user <companion_v2_context>"
    return "system"


def first_sentence(text: str, limit: int = 90) -> str:
    flat = " ".join(text.split())
    for mark in ("。", "；"):
        index = flat.find(mark)
        if 0 < index < limit:
            return flat[:index]
    return flat[:limit]


def resolve_default(spec: str, constants: dict) -> str:
    if spec.startswith("const:"):
        _, basename, name = spec.split(":", 2)
        item = constants.get((basename.lower(), name))
        return item["text"] if item else "（未找到常量）"
    return spec


def style_sheet(sheet, widths: dict, wrap_columns: set, freeze: str = "A2") -> None:
    header_fill = PatternFill("solid", fgColor="1F3864")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    sheet.freeze_panes = freeze
    sheet.auto_filter.ref = sheet.dimensions
    for letter, width in widths.items():
        sheet.column_dimensions[letter].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            letter = get_column_letter(cell.column)
            cell.alignment = Alignment(vertical="top", wrap_text=letter in wrap_columns)
            cell.font = Font(size=10)
        longest = max((len(str(cell.value or "")) for cell in row
                       if get_column_letter(cell.column) in wrap_columns), default=0)
        if longest:
            sheet.row_dimensions[row[0].row].height = min(320, 15 * max(1, math.ceil(longest / 55)))


def main() -> None:
    constants_rows = collect_constants()
    constants = {(pathlib.Path(row["file"]).name.lower(), row["base_name"]): row for row in constants_rows}
    task_rows = collect_task_profiles(collect_named_constants())
    reviewed, config, suspicious = parse_doc_tables()
    repository = collect_repository_text()

    workbook = Workbook()
    about = workbook.active
    about.title = "说明"
    about_rows = [
        ("项目", "内容"),
        ("生成时间", "2026-10-18"),
        ("数据来源", "companion_v2/、astrbot_host/ 源码；docs/PROMPTS_INVENTORY_20261018.md；人工复核的条件表"),
        ("提示词常量", f"{len(constants_rows)} 条含中文的字符串常量（含少量用户可见文案、正则与标记，已分类）"),
        ("任务档", f"{len(task_rows)} 个 ModelTaskProfile"),
        ("可配置字段", "29 个页面/配置字段（含默认全文）"),
        ("可疑项", f"{len(suspicious)} 条"),
        ("列·作用", "该提示词让模型做什么；优先取人工复核过的一句话，缺失时取正文首句"),
        ("列·注入前提", "代码里真实的开关/材料/分支条件；未复核条目会标注全仓引用次数"),
        ("列·注入位置", "system / user 材料 / 工具说明 / 独立任务 / 后处理"),
        ("列·默认提示词全文", "原始字面值，含 {chars}、{{split_marker}} 等占位符，未做任何裁剪"),
        ("行号说明", "位置取当前源码 AST 行号；代码变动后会漂移，用常量名重新定位"),
    ]
    for row in about_rows:
        about.append(row)
    about.column_dimensions["A"].width = 20
    about.column_dimensions["B"].width = 110
    for cell in about[1]:
        cell.fill = PatternFill("solid", fgColor="1F3864")
        cell.font = Font(bold=True, color="FFFFFF")
    for row in about.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")

    sheet = workbook.create_sheet("提示词常量")
    sheet.append(("序号", "域", "类别", "提示词/常量", "位置（文件:行）", "作用", "注入前提",
                  "注入位置", "默认提示词全文", "字数"))
    for index, row in enumerate(constants_rows, 1):
        reviewed_row = find_reviewed(row, reviewed)
        curated = curated_for(row)
        if curated:
            purpose, gate, position = curated
        elif reviewed_row:
            purpose, gate, position = (
                reviewed_row["作用"],
                reviewed_row["前提"],
                reviewed_row["位置"] or infer_position(row),
            )
        else:
            references = len(re.findall(rf"\b{re.escape(row['base_name'])}\b", repository)) - 1
            purpose = first_sentence(row["text"])
            gate = "未标注；全仓引用 " + (f"{references} 处" if references > 0 else "0 处（仅定义）")
            position = ""
        sheet.append((index, domain_of(row["file"]), classify(row["base_name"]), row["name"],
                      f"{row['file']}:{row['line']}", purpose or first_sentence(row["text"]),
                      gate or "每次该任务执行", position, row["text"], len(row["text"])))
    style_sheet(sheet, {"A": 6, "B": 18, "C": 13, "D": 34, "E": 46, "F": 40, "G": 50, "H": 18,
                        "I": 90, "J": 8}, {"D", "F", "G", "H", "I"})

    field_specs = [
        ("conversation.reply.prompt", "（空）", "对话附加提示，追加进宿主 system", "安装/角色/窗口",
         "core_reply_context.py:232-248", "字段非空"),
        ("conversation.presentation.style_prompt", "（空）", "表达风格补充", "角色+窗口",
         "text_processing.py:253", "字段非空"),
        ("conversation.presentation.prompt_style_mode", "free", "free 不注入 / guided 注入内置句 / constraint 注入正文",
         "角色+窗口", "text_processing.py:256-262", "非 free"),
        ("conversation.presentation.enable_humanized_expression", "False", "日常表达块开关", "角色+窗口",
         "text_processing.py:262-265", "为真且档位不是 constraint"),
        ("conversation.presentation.humanized_expression_prompt", "const:humanized_expression.py:DEFAULT_PROMPT",
         "日常表达正文（constraint 档复用为风格正文）", "角色+窗口", "humanized_expression.py:73,78", "开关开启"),
        ("conversation.presentation.prompt", "const:segmentation.py:DEFAULT_PROMPT",
         "模型分段协议（包含 {{split_marker}}）", "角色+窗口", "segmentation.py:214-215",
         "分段开启且 llm_controlled，自定义为空"),
        ("conversation.presentation.file_understanding_prompt", "（空）", "文件说明方式偏好", "角色+窗口",
         "messages.py:574-577", "非空且本轮有文件正文"),
        ("conversation.presentation.video_understanding_prompt", "（空）", "视频转述偏好", "角色+窗口",
         "media/video/narration.py:96", "非空且需要转述"),
        ("conversation.presentation.private_image_vision_custom_prompt", "（空）", "私聊看图补充要求", "角色+窗口",
         "media/image_narration.py:142", "非空且走图片转述"),
        ("conversation.presentation.voice_extra_prompt", "（空）", "语音选句/朗读补充", "角色+窗口",
         "voice_reply.py:192", "非空且启用语音"),
        ("conversation.presentation.voice_primary_mention_prompt", "（空）", "核心用户被 @ 时的定向语音提示", "角色+窗口",
         "multi_session.py:818-823", "被 @ 且启用语音"),
        ("conversation.perception.guidance", "（空）", "管理员感知表达偏好", "角色+窗口",
         "core_reply_perception.py:213-217", "字段非空"),
        ("conversation.image_review.group_nsfw_image_review_custom_prompt", "（空）", "群图审核补充规则", "角色+窗口",
         "media/review.py:139-142", "字段非空"),
        ("conversation.group_participation.group_behavior_guidance", "（空）", "群互动习惯学习偏好", "安装/角色/窗口",
         "behavior/service.py:127-129", "字段非空"),
        ("proactive.contact.expression_prompt", "const:prompt_templates.py:EXPRESSION_INSTRUCTION",
         "主动表达风格模板", "安装+角色+关系+窗口", "proactive/prompts.py:386", "每次主动联系"),
        ("proactive.contact.news_sharing_prompt", "const:prompt_templates.py:NEWS_SHARING_INSTRUCTION",
         "新闻分享模板", "安装+角色+关系+窗口", "proactive/prompts.py:390", "目的为新闻或来源含资讯"),
        ("proactive.contact.length_prompt", "const:prompt_templates.py:LENGTH_INSTRUCTION",
         "主动正文 {chars} 字上限", "安装+角色+关系+窗口", "proactive/prompts.py:398", "非新闻且档位给出字数"),
        ("proactive.contact.news_length_prompt", "const:prompt_templates.py:NEWS_LENGTH_INSTRUCTION",
         "新闻全文合计字数", "安装+角色+关系+窗口", "proactive/prompts.py:398", "新闻分支且给出字数"),
        ("proactive.contact.style_prompt", "（空）", "主动风格补充（末尾追加）", "安装+角色+关系+窗口",
         "proactive/prompts.py:406-407", "字段非空"),
        ("proactive.contact.note", "（空）", "偏好说明，进 contact_intent.preference_note", "安装+角色+关系+窗口",
         "proactive/prompts.py:287", "字段非空"),
        ("role.state.planning_prompt", "（空）", "日程规划偏好（作为材料文本）", "角色+窗口",
         "agenda/planning_inputs.py:240", "字段非空且执行规划"),
        ("role.state.energy_expression_prompt", "（空）", "精力模拟表达倾向", "角色+窗口",
         "role_work/state/maintenance.py:104", "字段非空且精力字段开启"),
        ("role.state.hunger_expression_prompt", "（空）", "饥饿模拟表达倾向", "角色+窗口",
         "role_work/state/maintenance.py:106", "字段非空且饥饿字段开启"),
        ("role.state.health_expression_prompt", "（空）", "健康模拟表达倾向", "角色+窗口",
         "role_work/state/maintenance.py:108", "字段非空且健康字段开启"),
        ("role.state.cycle_expression_prompt", "（空）", "周期表达偏好（随材料下发）", "角色+窗口",
         "role_work/state/cycle.py:151", "字段非空且周期开启"),
        ("role.state.humanized_state_intensity", "50", "状态表达强度档（0 不注入）", "角色+窗口",
         "state_context.py:264-267", "大于 0"),
        ("role.life.diary_style_prompt", "（空）", "日记风格补充", "角色+窗口",
         "journal/writing.py:375", "字段非空，日记与梦境都追加"),
        ("role.life.dream_theme_candidates", "（空）", "梦境题材参考", "角色+窗口",
         "journal/prompts.py:62-65", "字段非空且写梦境"),
        ("model.conversation.reply.prompt", "（空：使用任务档默认句）", "对话任务补充提示，追加进核心 system",
         "安装/角色/窗口", "routing.py:212 → core_reply_context.py:232-248", "字段非空"),
        ("model.role.journal.diary/dream/derive/select.prompt",
         "保持原人格，按本次私人书写任务及素材语义生成。", "私人书写任务补充", "安装/角色/窗口",
         "journal/writing.py:40", "每次日记/梦境/衍生/选材任务"),
        ("model.memory.reflect.prompt", "按原人格整理已授权资料，有来源地更新认识，允许不修改。",
         "记忆反思任务补充", "安装/角色/窗口", "memory/reflection.py:37", "memory.reflect 任务"),
        ("model.calendar.plan.prompt",
         "沿原人格安排自己的生活；保留长期目标、当天小步和未完成事项，计划不是完成记录。",
         "日程规划任务补充", "安装/角色/窗口", "agenda/planning.py:34", "calendar.plan 任务"),
        ("model.content.authoring.draft.prompt", "（见 content/authoring_tasks.py 的 PROMPTS）",
         "创作任务补充", "安装/角色/窗口", "conversation/content/authoring_tasks.py:11", "每次创作调用"),
        ("qzone.topic_prompt_guidance", "（空）", "空间主题分类补充指引（未见消费点）", "安装/角色/窗口",
         "未找到消费点", "无"),
    ]
    field_sheet = workbook.create_sheet("可配置字段")
    about["B6"] = f"{len(field_specs)} 个页面/配置字段（含默认全文，空值显式标注）"
    field_sheet.append(("序号", "字段", "默认值/来源", "默认提示词全文", "作用", "覆盖层级", "消费位置", "注入前提"))
    for index, (field, default, purpose, layer, consumer, gate) in enumerate(field_specs, 1):
        if default == "（空）":
            source, full = "空字符串", "（默认空字符串，不注入）"
        elif default.startswith("const:"):
            source, full = "内置模板", resolve_default(default, constants)
        else:
            source, full = default, default
        field_sheet.append((index, field, source, full, purpose, layer, consumer, gate))
    style_sheet(field_sheet, {"A": 6, "B": 52, "C": 14, "D": 92, "E": 38, "F": 20, "G": 40, "H": 32},
                {"B", "D", "E", "G", "H"})

    task_gates = {
        "conversation.reply": "AstrBot 核心链每次回复",
        "conversation.poke_reply": "开启戳一戳模型回复",
        "proactive.compose": "主动联系机会开放",
        "proactive.judge": "开启 LLM 人格判定",
        "role.journal.diary": "日记日程被调度",
        "role.journal.dream": "睡眠回执后或管理端动作",
        "role.journal.derive": "父记录已保存且 derive 开启",
        "role.journal.select": "候选超上限",
        "role.self_review": "后台自评到期且证据足够",
        "role.growth.progress": "有活跃目标与完成回执",
        "role.expression.learn": "表达学习任务被调度",
        "role.expression.review": "有采纳规则且开启复核",
        "role.expression.contact_review": "同上（主动消息）",
        "role.state.maintain": "状态维护任务到期或被干预",
        "role.reading.consume": "阅读活动启动",
        "calendar.plan": "日程规划任务或用户干预",
        "memory.reflect": "记忆整理日程到期且有证据",
        "screen.interpretation": "识屏开关开启且采集成功",
        "content.authoring.draft": "明确要求写作并调用创作工具",
        "conversation.image_narration": "图片理解开启且本轮有图",
        "conversation.video_narration": "视频理解开启且本轮有视频",
        "conversation.context_image_caption": "群历史图片需要转述",
        "conversation.image_review": "群图审核模式非 off",
    }
    task_sheet = workbook.create_sheet("任务档")
    task_sheet.append(("序号", "任务 kind", "任务档默认提示（task_prompt）", "位置", "触发前提"))
    for index, row in enumerate(task_rows, 1):
        prompt = row["prompt"]
        if not prompt:
            prompt = ("（由运行时档提供：" + row["expression"] + "）") if row["expression"] else "（由运行时配置提供）"
        task_sheet.append((index, row["kind"], prompt, f"{row['file']}:{row['line']}",
                           task_gates.get(row["kind"], "见任务调度条件")))
    style_sheet(task_sheet, {"A": 6, "B": 34, "C": 86, "D": 52, "E": 30}, {"B", "C", "D", "E"})

    suspect_sheet = workbook.create_sheet("可疑未使用")
    suspect_sheet.append(("序号", "名称", "位置", "现象"))
    for index, row in enumerate(suspicious, 1):
        suspect_sheet.append((index, row["name"], row["位置"], row["现象"]))
    style_sheet(suspect_sheet, {"A": 6, "B": 46, "C": 48, "D": 96}, {"B", "C", "D"})

    workbook.save(OUTPUT)
    print(f"wrote {OUTPUT} constants={len(constants_rows)} tasks={len(task_rows)} "
          f"fields={len(field_specs)} suspicious={len(suspicious)}")


if __name__ == "__main__":
    main()
