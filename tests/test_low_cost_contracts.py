from datetime import date, datetime, timedelta, timezone

import pytest

from companion_v2.agenda.annual_calendar import parse_annual_calendar
from companion_v2.conversation.content.authoring import authoring_prompt, parse_output as parse_content
from companion_v2.expression.learning import INSTRUCTION, parse_output as parse_learning
from companion_v2.integration.nai_image import map_nai_request
from companion_v2.knowledge.parsing import parse_knowledge_rows, parse_worldbook
from companion_v2.model_gateway.replacement_rules import build_rules, match_route
from companion_v2.proactive.external_materials import parse_news_response, parse_weather_response
from companion_v2.role_work.journal.self_review import INSTRUCTION as REVIEW_INSTRUCTION
from companion_v2.role_work.journal.self_review import parse_output as parse_review


def test_worldbook_and_knowledge_parsers_keep_valid_rows_and_report_bad_rows() -> None:
    worldbook = parse_worldbook({
        "entry_storage": [
            {
                "id": "mira",
                "__template_key": "member",
                "name": "Mira",
                "content": "喜欢雨天散步",
                "keywords": ["雨天"],
                "aliases": ["米拉"],
            },
            {"name": "", "content": ""},
        ]
    })
    assert worldbook.items[0].entry_id == "mira"
    assert worldbook.items[0].keywords == ("雨天",)
    assert worldbook.issues[0].code == "empty_entry"

    chunks = parse_knowledge_rows([
        {"text": "第一段", "metadata": '{"kb_doc_id":"doc-a","doc_name":"设定","chunk_index":"2"}'},
        {"text": "", "metadata": {}},
    ], knowledge_base_id="kb-a")
    assert chunks.items[0].chunk_index == 2
    assert chunks.items[0].document_name == "设定"
    assert chunks.issues[0].code == "text"


def test_annual_calendar_expands_holidays_and_keeps_makeup_and_terms_separate() -> None:
    calendar = parse_annual_calendar({
        "schema": "companion.annual-calendar.v1",
        "year": 2026,
        "holidays": [{"name": "合成假期", "start": "2026-10-01", "end": "2026-10-03"}],
        "makeup_workdays": [{"date": "2026-10-04", "name": "调休上班"}],
        "solar_terms": [{"date": "2026-10-08", "name": "寒露"}],
    })
    assert calendar.on(date(2026, 10, 2)).holiday == "合成假期"
    assert calendar.on(date(2026, 10, 4)).makeup_workday == "调休上班"
    assert calendar.on(date(2026, 10, 8)).solar_terms == ("寒露",)
    with pytest.raises(ValueError, match="schema"):
        parse_annual_calendar({"year": 2026})


def test_external_materials_normalize_and_deduplicate_provider_rows() -> None:
    weather, issues = parse_weather_response({
        "provider": "synthetic-weather",
        "location": {"name": "上海"},
        "observed_at": "2026-09-26T09:00:00+08:00",
        "current": {"temperature_c": 26, "condition": "小雨", "humidity_pct": 80},
        "alerts": [
            {
                "id": "alert-1", "title": "暴雨", "severity": "orange",
                "starts_at": "2026-09-26T08:00:00+08:00",
                "ends_at": "2026-09-26T12:00:00+08:00", "description": "合成预警",
            },
            {
                "id": "alert-1", "title": "重复", "severity": "orange",
                "starts_at": "2026-09-26T08:00:00+08:00",
                "ends_at": "2026-09-26T12:00:00+08:00",
            },
        ],
    })
    assert weather.location == "上海"
    assert len(weather.alerts) == 1
    assert issues[0].code == "duplicate_alert"

    news = parse_news_response({"items": [
        {"source": "合成源", "title": "消息 A", "url": "https://example.test/a?utm_source=x"},
        {"source": "合成源", "title": "消息 A（重复）", "url": "https://example.test/a"},
        {"title": "", "url": "https://example.test/b"},
    ]})
    assert len(news.items) == 1
    assert news.items[0].url.endswith("/a?utm_source=x")
    assert [issue.code for issue in news.issues] == ["duplicate_news_item", "invalid_news_item"]


def test_expression_learning_and_content_drafts_require_known_evidence() -> None:
    learning = parse_learning({
        "summary": "合成样本显示短句较多",
        "signals": [{
            "dimension": "sentence_rhythm",
            "observation": "两条消息使用短句",
            "proposal": "可观察是否偏好短句",
            "confidence": 0.5,
            "evidence_handles": ["m1", "m2"],
        }],
    }, allowed_evidence={"m1", "m2"})
    assert learning.signals[0].confidence == 0.5
    assert "只观察表达形式" in INSTRUCTION
    with pytest.raises(ValueError, match="invalid_evidence"):
        parse_learning({
            "summary": "", "signals": [{
                "dimension": "emoji", "observation": "一次", "proposal": "长期使用",
                "confidence": 1, "evidence_handles": ["unknown"],
            }],
        }, allowed_evidence={"m1"})

    prompt = authoring_prompt("draft", "写一段合成产品介绍", {"src-1": "产品材料"})
    assert "保存到原生 Content" in prompt
    draft = parse_content({
        "title": "合成标题", "work_type": "短篇", "body": "合成正文",
    }, action="draft")
    assert (draft.title, draft.work_type, draft.body) == ("合成标题", "短篇", "合成正文")


def test_self_review_is_expiring_evidence_bound_guidance() -> None:
    now = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
    output = parse_review({
        "summary": "本轮有一项表达不确定性的改进机会",
        "guidance": [{
            "kind": "try_next_time",
            "observation": "一次回答没有说明来源仍待核对",
            "next_action": "遇到未知结果时明确标注待核对",
            "confidence": 0.8,
            "evidence_handles": ["turn-1"],
            "expires_at": (now + timedelta(days=1)).isoformat(),
        }],
    }, allowed_evidence={"turn-1"}, now=now)
    assert output.guidance[0].expires_at > now
    assert "待审候选" in REVIEW_INSTRUCTION
    with pytest.raises(ValueError, match="invalid_expiry"):
        parse_review({
            "summary": "", "guidance": [{
                "kind": "keep", "observation": "x", "next_action": "y", "confidence": 1,
                "evidence_handles": ["turn-1"], "expires_at": now.isoformat(),
            }],
        }, allowed_evidence={"turn-1"}, now=now)


def test_nai_mapping_is_deterministic_and_rejects_unsupported_values() -> None:
    request = map_nai_request(
        model="nai-v4",
        positive_prompt="1girl, rainy street",
        negative_prompt="low quality",
        parameters={"width": 832, "height": 1216, "seed": 42, "steps": 28},
    )
    assert request["model"] == "nai-v4"
    assert request["parameters"]["uc"] == "low quality"
    assert request["parameters"]["seed"] == 42
    with pytest.raises(ValueError, match="unsupported"):
        map_nai_request(model="nai-v4", positive_prompt="x", negative_prompt="", parameters={"api_key": "secret"})
    with pytest.raises(ValueError, match="multiples"):
        map_nai_request(model="nai-v4", positive_prompt="x", negative_prompt="", parameters={"width": 801})


def test_keyword_and_cross_midnight_time_rules_are_ordered_without_provider_calls() -> None:
    result = build_rules([
        {"id": "night", "provider_id": "cheap", "model": "small", "priority": 3,
         "time_window": {"timezone": "Asia/Shanghai", "start": "22:00", "end": "02:00", "weekdays": [0]}},
        {"id": "urgent", "provider_id": "fast", "model": "large", "priority": 5,
         "keywords": ["紧急"], "match_mode": "contains"},
    ])
    assert not result.issues
    urgent = match_route(result.rules, "这很紧急", datetime(2026, 9, 26, 14, tzinfo=timezone.utc))
    assert (urgent.rule_id, urgent.provider_id, urgent.reason) == ("urgent", "fast", "keyword")
    night = match_route(result.rules, "普通消息", datetime(2026, 9, 28, 17, 30, tzinfo=timezone.utc))
    assert night.rule_id == "night"
    with pytest.raises(ValueError, match="aware"):
        match_route(result.rules, "普通消息", datetime(2026, 9, 28, 18))
