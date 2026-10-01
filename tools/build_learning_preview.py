"""生成「学习与反思 · 培育轨道」的静态预览页。

预览跑的是 pages/陪伴小屋/learning-page.js **本体**，只把页面桥换成返回假数据的桩，
所以预览里能点的真页面就能点——不会出现「预览能点、真页面不能」或反过来。

用法：python3 tools/build_learning_preview.py [输出路径]
默认输出 docs/page-designs/learning-track-preview.html
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "陪伴小屋"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "page-designs" / "learning-track-preview.html"


def grab_theme(tokens, name):
    start = tokens.find('[data-theme="%s"]' % name)
    if start < 0:
        raise SystemExit("缺少主题 " + name)
    end = tokens.find("\n}\n", start)
    return tokens[start:end + 3].strip()


TOKENS = (PAGE / "tokens.css").read_text(encoding="utf-8")
STYLE = (PAGE / "learning-page.css").read_text(encoding="utf-8")
SCRIPT = (PAGE / "learning-page.js").read_text(encoding="utf-8")
TEMPLATE = pathlib.Path(__file__).with_name("learning_preview.tpl.html").read_text(encoding="utf-8")


def record(identifier, state, kind, title, note, sources, updated, actions, extra=None):
    """一条成长记录，形状照 `RoleGrowthManagement._project()` 的返回。

    来源失效的那一条把 title/description/progress_note 传成 None——
    这正是后端的行为，不是漏填：读不到来源就不返回内容。
    """
    row = {
        "growth_id": identifier, "revision": 3, "kind": kind, "state": state,
        "title": title,
        "description": None if title is None else title + "——由互动中提出的长期方向。",
        "progress_note": note, "source_count": sources, "unavailable_reason": None,
        "proposed_by": "user-1",
        "confirmed_by": None if state == "proposed" else "user-1",
        "changed_by": "user-1",
        "created_at": "2026-08-14T09:20:00+08:00", "updated_at": updated,
        "actions": actions, "view_token": "v" * 64,
    }
    row.update(extra or {})
    return row


# 五个状态各一条，让轨道的每一段都有内容；另加一条来源失效的，好看到风险色。
ITEMS = [
    record("g-skill-1", "proposed", "skill", "手冲咖啡的注水节奏",
           "开始练闷蒸，水柱还不太稳。", 2, "2026-09-26T21:10:00+08:00",
           ["confirm", "revise", "withdraw", "retire"]),
    record("g-goal-1", "proposed", "goal", "读完《夜航西飞》",
           "停在第三章。", 1, "2026-09-27T08:05:00+08:00",
           ["confirm", "revise", "withdraw", "retire"]),
    record("g-skill-2", "active", "skill", "按镜头语言描述画面",
           "本周试了三次，讲得比上月具体。", 4, "2026-09-28T19:40:00+08:00",
           ["revise", "pause", "retire"]),
    record("g-goal-2", "active", "goal", "把阳台改成能坐下来写字的地方",
           "量了尺寸，还没定桌子。", 3, "2026-09-29T10:15:00+08:00",
           ["revise", "pause", "complete", "retire"]),
    record("g-skill-3", "paused", "skill", "认得几种常见的鸟叫",
           "冬天鸟少，先搁着。", 2, "2026-09-12T07:30:00+08:00",
           ["resume", "revise", "retire"]),
    record("g-goal-3", "achieved", "goal", "把《小王子》重读一遍",
           "读完了，写了一段话。", 5, "2026-09-05T22:00:00+08:00", ["retire"]),
    record("g-skill-4", "retired", "skill", "背五十音",
           "已经不用特意练了。", 1, "2026-06-20T12:00:00+08:00", ["retire"]),
    # 来源失效：后端把标题、描述、进展全部置 null，只留引用与版本。
    record("g-goal-4", "active", "goal", None, None, 3, "2026-09-18T16:45:00+08:00",
           ["retire"], {"title": None, "description": None, "progress_note": None,
                        "unavailable_reason": "growth_source_expired"}),
]

REVIEWS = [
    {"review_id": "r-1", "growth_id": "g-goal-2", "base_revision": 3,
     "growth_title": "把阳台改成能坐下来写字的地方",
     "progress_note": "比我预想的费时间，不过量完尺寸之后心里有数了。这周打算先定桌子，"
                      "再看灯的位置——上次你说过别把灯装在右手边。",
     "receipt_stream": "receipts", "created_at": "2026-09-28T21:30:00+08:00",
     "unavailable_reason": None, "actions": ["accept", "reject"], "view_token": "w" * 64},
    {"review_id": "r-2", "growth_id": "g-skill-2", "base_revision": 3,
     "growth_title": "按镜头语言描述画面",
     "progress_note": "今天试着只看一秒就说，说得比看很久还准。",
     "receipt_stream": "receipts", "created_at": "2026-09-29T11:05:00+08:00",
     "unavailable_reason": None, "actions": ["accept", "reject"], "view_token": "w" * 64},
    # 依据过期：后端只给 reject，不给 accept。
    {"review_id": "r-3", "growth_id": "g-goal-1", "base_revision": 1,
     "growth_title": "读完《夜航西飞》", "progress_note": None, "receipt_stream": None,
     "created_at": "2026-09-20T09:00:00+08:00",
     "unavailable_reason": "source_expired", "actions": ["reject"], "view_token": "w" * 64},
]

ACCESS = {
    "settings": {"read_enabled": True, "proposals_enabled": True},
    "effective": {"read_enabled": {"allowed": True, "reason": None},
                  "proposals_enabled": {"allowed": True, "reason": None}},
    "edit_token": "a" * 64,
}

LIST = {"items": ITEMS, "next_cursor": None, "context_key": "ctx", "role_id": "chengxi",
        "profile_id": "profile-1", "operator_name": "operator", "access": ACCESS}
PROGRESS = {"items": REVIEWS, "next_cursor": None, "context_key": "ctx", "role_id": "chengxi"}

payload = json.dumps({"list": LIST, "progress": PROGRESS}, ensure_ascii=False)
html = (TEMPLATE
        .replace("/*__THEMES__*/", grab_theme(TOKENS, "courtyard") + "\n\n" + grab_theme(TOKENS, "night"))
        .replace("/*__CSS__*/", STYLE)
        .replace("/*__JS__*/", SCRIPT)
        .replace("__PAYLOAD__", payload))
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print("已生成 %s  %d 字节" % (OUT, len(html)))
