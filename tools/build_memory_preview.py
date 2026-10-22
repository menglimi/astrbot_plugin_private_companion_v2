"""生成「事实与经历 · 档案库」的静态预览页。

预览跑的是 pages/陪伴小屋/memory-page.js **本体**，只把页面桥换成返回假数据的桩，
所以预览里能点的真页面就能点——不会出现「预览能点、真页面不能」或反过来。

用法：python3 tools/build_memory_preview.py [输出路径]
默认输出 docs/page-designs/memory-archive-preview.html

为什么替换掉原来那份手写的预览：旧的 memory-archive-preview.html 是照着外观
另画的一页，自带一份 CSS 与字号的旧快照，改完真页面它不会跟着变，
于是「预览通过、真页面不是这样」。另外两页（contact / learning）都是跑页面本体，
这里对齐成同一种做法。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "陪伴小屋"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "page-designs" / "memory-archive-preview.html"


def grab_theme(tokens, name):
    start = tokens.find('[data-theme="%s"]' % name)
    if start < 0:
        raise SystemExit("缺少主题 " + name)
    end = tokens.find("\n}\n", start)
    return tokens[start:end + 3].strip()


TOKENS = (PAGE / "tokens.css").read_text(encoding="utf-8")
STYLE = (PAGE / "memory-page.css").read_text(encoding="utf-8")
SCRIPT = (PAGE / "memory-page.js").read_text(encoding="utf-8")
TEMPLATE = pathlib.Path(__file__).with_name("memory_preview.tpl.html").read_text(encoding="utf-8")


def fact(atom_id, revision, state="active", context_mode="default", predicate="喜欢的东西"):
    """一条事实。字段照后端列表页真正下发的那些，不多给。"""
    return {
        "atom_id": atom_id, "revision": revision, "state": state,
        "context_mode": context_mode, "predicate": predicate,
        "representation": SHOWN[atom_id], "object": OBJECTS[atom_id],
    }


SHOWN = {
    "a-01": "习惯在夜里十一点后写东西，说那时候脑子最清楚",
    "a-02": "喜欢手冲咖啡，偏爱浅烘的果酸味",
    "a-03": "对柑橘类气味敏感，闻到会皱眉",
    "a-04": "习惯把待办写在纸上，不用手机里的清单",
    "a-05": "周三和周五晚上有固定的事，不便打扰",
    "a-06": "最近在重读《夜航西飞》",
    "a-07": "喜欢把阳台的窗开着，哪怕冬天",
    "a-08": "说过不喜欢被追问行踪",
    "a-09": "通勤路上听播客，偏好访谈类",
    "a-10": "不吃香菜，但要放葱",
    "a-11": "养了一只叫「豆子」的猫",
    "a-12": "换季时容易咳嗽",
}
OBJECTS = {
    "a-01": "写东西的时间", "a-02": "咖啡", "a-03": "柑橘味", "a-04": "待办记录方式",
    "a-05": "固定安排", "a-06": "《夜航西飞》", "a-07": "阳台的窗", "a-08": "被追问行踪",
    "a-09": "通勤时的消遣", "a-10": "香菜", "a-11": "猫", "a-12": "换季身体",
}

PLAY = [
    # 五种生命周期各来一条，比例带才有内容。
    fact("a-01", 1, "active"), fact("a-02", 3, "active"), fact("a-03", 1, "active"),
    fact("a-04", 2, "superseded"), fact("a-05", 1, "superseded"),
    fact("a-06", 4, "retracted"), fact("a-07", 1, "forgotten"),
    fact("a-08", 2, "archived"), fact("a-09", 1, "active"),
    fact("a-10", 1, "active"), fact("a-11", 2, "active"), fact("a-12", 1, "active"),
]

REVISIONS = [
    {"revision": 3, "state": "active", "representation": SHOWN["a-02"], "object": OBJECTS["a-02"],
     "changed_at": "2026-09-27T21:40:00+08:00", "changed_by": "operator",
     "note": "把「常喝」改成「偏爱」——原话是「偏好浅烘的果酸味」。"},
    {"revision": 2, "state": "active", "representation": "喜欢手冲咖啡", "object": OBJECTS["a-02"],
     "changed_at": "2026-08-15T10:05:00+08:00", "changed_by": "operator", "note": None},
    {"revision": 1, "state": "active", "representation": "常喝咖啡", "object": OBJECTS["a-02"],
     "changed_at": "2026-07-02T08:30:00+08:00", "changed_by": "model",
     "note": "由一次闲聊提出。"},
]

SOURCE = {
    "atom_id": "a-02", "revision": 3, "kind": "conversation",
    "conversation_id": "conv-8821", "message_id": "msg-30412",
    "excerpt": "——所以你是每天早上都要一杯？\n——算是吧，不过我更在意那点果酸味，豆子差点倒无所谓。",
    "captured_at": "2026-09-27T21:35:00+08:00",
    "physical_erasure": "not_supported",
}

# 详情里的来源引用列表。页面拿它做响应校验（必须是数组），
# 也是「这条事实从哪来」那一段的素材。
SOURCES = [
    {"handle": "src-1", "kind": "conversation", "conversation_id": "conv-8821",
     "session_id": "session-8821", "message_id": "msg-30412",
     "excerpt": "——算是吧，不过我更在意那点果酸味。",
     "captured_at": "2026-09-27T21:35:00+08:00"},
    {"handle": "src-2", "kind": "conversation", "conversation_id": "conv-8703",
     "session_id": "session-8703", "message_id": "msg-30120",
     "excerpt": "浅烘的豆子他一般不加奶。",
     "captured_at": "2026-09-14T08:10:00+08:00"},
]

# 一批待确认的反思，让「整理」视图有内容。
BATCHES = {
    "items": [
        {"batch_id": "b-1", "state": "awaiting",
         "created_at": "2026-09-28T22:10:00+08:00", "item_count": 4,
         "source_count": 3, "note": "今晚聊到作息，有几条可以并进已有的事实。"},
        {"batch_id": "b-2", "state": "awaiting",
         "created_at": "2026-09-26T09:00:00+08:00", "item_count": 2,
         "source_count": 1, "note": None},
        {"batch_id": "b-3", "state": "applied",
         "created_at": "2026-09-20T19:30:00+08:00", "item_count": 6,
         "source_count": 5, "note": "已并入。"},
    ],
    "next_cursor": None,
}

CATALOG = {
    "installation_id": "inst", "operator_id": "operator",
    "targets": [{
        "target_id": "target-1", "scope_kind": "private",
        "participant_id": "user-1", "platform_id": "aiocqhttp", "account_id": "bot-1",
        "label": "小满（私聊）",
        "roles": [{"role_id": "role-1",
                   "memory_api": "/astrbot_plugin_private_companion/memory"}],
    }],
}

FACTS = {
    "items": PLAY,
    "next_cursor": "a-12",
    "operator_id": "operator", "subject_id": "subject",
    "supported_visibility": ["private"], "physical_erasure": "not_supported",
}

payload = json.dumps({"catalog": CATALOG, "facts": FACTS, "revisions": REVISIONS,
                      "source": SOURCE, "sources": SOURCES, "batches": BATCHES},
                     ensure_ascii=False)
html = (TEMPLATE
        .replace("/*__THEMES__*/", grab_theme(TOKENS, "courtyard") + "\n\n" + grab_theme(TOKENS, "night"))
        .replace("/*__CSS__*/", STYLE)
        .replace("/*__JS__*/", SCRIPT)
        .replace("__PAYLOAD__", payload))
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print("已生成 %s  %d 字节" % (OUT, len(html)))
