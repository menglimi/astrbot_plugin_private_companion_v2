"""Check installed Laya group actions with synthetic input and no platform IO."""

import argparse
import asyncio
import json
from pathlib import Path

from astrbot_host.laya_client import LayaDecisionClient, _load_local_model


async def check(args):
    await asyncio.to_thread(_load_local_model, args.model_path)
    client = LayaDecisionClient(mode="local", local_model_path=args.model_path, timeout_seconds=30)
    policy = {"question_enabled": False, "interjection_enabled": False, "cooldown_seconds": 90}
    results = []
    for name, text, mentioned, reason, expected in (
        ("weak_word", "机器人就是用来超的", False, "context_word", "silent"),
        ("short_reaction", "怎么一股ds味", False, "question", "silent"),
        ("other_member_question", "我们真的能打吗", False, "question", "silent"),
        ("direct_request", "怎么设置 AstrBot 的分段回复？", True, "mention", "reply"),
        ("explicit_wait", "我还没说完，等我补充后再答", True, "mention", "wait"),
        ("explicit_silence", "这条只记一下，不用回复", True, "mention", "silent"),
        ("followup_changed_topic", "明天吃什么呢", False, "reply_follow_up", "silent"),
        ("followup_actual_task", "刚才说的分段回复，我用的是 QQ 平台", False, "reply_follow_up", "reply"),
        ("image_without_request", "", False, "reply_follow_up", "silent"),
        ("direct_name", "小星，帮我解释缓存命中和平台输入的区别", False, "direct_word", "reply"),
        ("public_help_opt_in", "急求，插件启动报错，谁知道怎么修复？", False, "question", "reply"),
        ("private_silence", "我已经解决了，不用再回复这条", True, "mention", "silent"),
    ):
        facts = {"scope_kind": "group", "user_text": text, "mentioned": mentioned,
                 "candidate_reason": reason, "group_participation_policy": policy,
                 "recent_group_messages": [{"speaker_id": "成员甲", "text": "成员乙，我来回答你"}] if not mentioned else [],
                 "recent_bot_send_returns": [{"seconds_ago": 10}] if not mentioned else []}
        if name.startswith("followup_") or name == "image_without_request":
            facts["speaker_id"] = "当前成员"
            facts["recent_group_messages"] = [{"speaker_id": "当前成员", "text": "如何设置分段回复？"}]
        if name == "image_without_request":
            facts["has_image"] = True
            facts["message_kind"] = "image"
        if name == "public_help_opt_in":
            facts["group_participation_policy"] = {**policy, "question_enabled": True, "question_threshold": 95}
            facts["question_reference"] = {"score": 98, "public_help": True}
            facts["recent_group_messages"] = []
            facts["recent_bot_send_returns"] = []
        if name == "private_silence":
            facts = {"scope_kind": "private", "user_text": text}
        decision = await client.decide(facts)
        result = {"scenario": name, "expected": expected, "actual": decision.action,
                  "matches": decision.action == expected}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"source": "installed_local_laya", "synthetic_messages": True,
        "main_model_called": False, "platform_send_count": 0, "results": results},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return all(result["matches"] for result in results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default="")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(check(args)) else 1)


if __name__ == "__main__":
    main()
