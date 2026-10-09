from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from companion_v2.decision.client import LayaClientError, LayaDecisionClient, _LOCAL_ROUTERS
from companion_v2.decision.contract import DecisionContractError, deterministic_skip_reason, parse_decision
from companion_v2.decision.prompt import DECISION_QUESTIONS, build_state
from companion_v2.decision.store import LayaSettingsStore


def decision_document():
    return {
        "turn_state": "complete",
        "action": "reply",
        "reply_intent": "answer",
        "reply_style": "normal",
        "reply_form": "text",
        "segment_mode": "single",
        "tool_need": "none",
        "reason_codes": [],
    }


def laya_result(overrides=None):
    values = {**decision_document(), **(overrides or {})}
    return {"answers": {key: {"type": "choice", "choice": value}
                        for key, value in values.items() if key != "reason_codes"},
            "model": "multilingual", "usage": {"input_tokens": 12, "output_tokens": 7}}


def test_laya_contract_is_exact_and_numeric_free():
    document = decision_document()
    assert parse_decision(document).document() == document
    with pytest.raises(DecisionContractError):
        parse_decision({**document, "wait_seconds": 2})
    with pytest.raises(DecisionContractError):
        parse_decision({**document, "reason_codes": [2]})


def test_laya_questions_use_official_choice_types_without_numeric_controls():
    assert set(DECISION_QUESTIONS) == set(decision_document()) - {"reason_codes"}
    assert all(question["type"] == "choice" for question in DECISION_QUESTIONS.values())
    assert all("criteria" in question for question in DECISION_QUESTIONS.values())
    assert "seconds" not in str(DECISION_QUESTIONS).lower()
    state = build_state({"message_kind": "text", "user_text": "还没说完，稍等"})
    assert json.loads(state)["facts"]["user_text"] == "还没说完，稍等"


def test_robot_message_and_quote_are_rule_owned():
    for field in ("is_bot_message", "sender_is_bot", "quoted_bot_message", "quotes_bot_message",
                  "has_bot_quote", "referenced_bot_message", "reply_to_bot_message"):
        assert deterministic_skip_reason({field: True}) == "robot_message_reference"
    assert deterministic_skip_reason({"message_kind": "command"}) == "explicit_event_rule"
    assert deterministic_skip_reason({"message_kind": "text", "user_text": "你好"}) is None


def test_runtime_facts_skip_bot_authored_events_and_quotes():
    from types import SimpleNamespace as NS
    from companion_v2.conversation.generation import LocalReplyGenerator

    request = NS(
        event=NS(
            principal=NS(native_account_id="200"),
            scope=NS(account_id="100", kind=NS(value="group")),
            quotes=(NS(sender_id="100"),),
            forwards=(),
        ),
        images=(), audios=(), videos=(),
        context=NS(materials=(NS(purpose="current_source", payload="hello"),)),
    )
    facts = LocalReplyGenerator._laya_facts(request)
    assert facts["quoted_bot_message"] is True
    assert deterministic_skip_reason(facts) == "robot_message_reference"

    request.event.principal.native_account_id = "100"
    facts = LocalReplyGenerator._laya_facts(request)
    assert facts["is_bot_message"] is True
    assert deterministic_skip_reason(facts) == "robot_message_reference"


def test_model_page_and_single_runtime_share_laya_storage_key(tmp_path):
    from types import SimpleNamespace as NS
    from astrbot_host.model_api import ModelWebAPI

    settings = NS(profile_id="private-profile", role_id="role-a")
    controller = NS(data_root=tmp_path, settings=settings,
                    resolved_settings=lambda: settings)
    page_service = ModelWebAPI(controller)._laya_service()
    runtime_store = LayaSettingsStore(tmp_path, settings.profile_id, settings.role_id)
    assert page_service.store.path == runtime_store.path


def test_model_page_and_multi_runtime_share_target_storage_key(tmp_path):
    from types import SimpleNamespace as NS
    from astrbot_host.model_api import ModelWebAPI

    controller = NS(data_root=tmp_path, target_id="target-a", role_id="role-a")
    page_service = ModelWebAPI(controller)._laya_service()
    runtime_store = LayaSettingsStore(tmp_path, "target-a", "role-a")
    assert page_service.store.path == runtime_store.path


def test_multi_runtime_maps_dynamic_private_scope_to_configured_template():
    from types import SimpleNamespace as NS
    from astrbot_host.multi_controller import laya_target_id_for_scope
    from astrbot_host.multi_settings import MultiHostSettings
    from companion_v2.foundation.refs import ScopeKind
    from tests.multi_host_support import multi_config

    explicit = MultiHostSettings.parse(multi_config())
    exact_scope = NS(kind=ScopeKind.PRIVATE, platform="qq-main", account_id="100", native_scope_id="200")
    assert laya_target_id_for_scope(explicit, exact_scope) == "first"

    template = {"target_id": "all-private", "platform_id": "qq-main", "account_id": "100",
                "bot_id": "bot-a", "participant_id": "*"}
    second = {"target_id": "second", "platform_id": "qq-second", "account_id": "101",
              "bot_id": "bot-b", "participant_id": "200"}
    configured = MultiHostSettings.parse(multi_config(targets=[template, second]))
    dynamic_scope = NS(kind=ScopeKind.PRIVATE, platform="qq-main", account_id="100", native_scope_id="999")
    assert laya_target_id_for_scope(configured, dynamic_scope) == "all-private"


def test_local_router_adapter_calls_predict_and_maps_choices(monkeypatch):
    _LOCAL_ROUTERS.clear()
    calls = []

    class Router:
        def __init__(self, **kwargs):
            assert kwargs == {"default": "multilingual", "max_loaded": 1}

        def predict(self, state, questions):
            calls.append((state, questions))
            return laya_result()

    monkeypatch.setitem(sys.modules, "laya", types.SimpleNamespace(Router=Router))
    client = LayaDecisionClient(mode="local")
    result = asyncio.run(client.decide({"message_kind": "text", "user_text": "你好"}))
    assert result.document() == decision_document()
    assert len(calls) == 1
    assert set(calls[0][1]) == set(DECISION_QUESTIONS)
    assert json.loads(calls[0][0])["facts"]["user_text"] == "你好"
    _LOCAL_ROUTERS.clear()


def test_local_router_import_error_is_actionable(monkeypatch):
    _LOCAL_ROUTERS.clear()
    monkeypatch.delitem(sys.modules, "laya", raising=False)
    original_import = __import__

    def missing(name, *args, **kwargs):
        if name == "laya":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", missing)
    client = LayaDecisionClient(mode="local")
    with pytest.raises(LayaClientError) as error:
        asyncio.run(client.decide({"message_kind": "text", "user_text": "hello"}))
    assert error.value.code == "laya_package_missing"


def test_remote_adapter_uses_systemone_contract_and_parses_answers(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return json.dumps(laya_result(), ensure_ascii=False).encode("utf-8")

    def open_url(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("companion_v2.decision.client.urlopen", open_url)
    client = LayaDecisionClient(mode="remote", endpoint="http://127.0.0.1:8000/v1",
                                api_key="private-key", timeout_seconds=17)
    result = asyncio.run(client.decide({"message_kind": "text", "user_text": "你好"}))
    assert result.document() == decision_document()
    assert captured["url"] == "http://127.0.0.1:8000/v1/systemone"
    assert captured["headers"]["Authorization"] == "Bearer private-key"
    assert "model" not in captured["body"]
    assert set(captured["body"]["questions"]) == set(DECISION_QUESTIONS)
    assert captured["timeout"] == 17


def test_remote_adapter_rejects_openai_chat_shape(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return b'{"choices":[]}'

    monkeypatch.setattr("companion_v2.decision.client.urlopen", lambda *_args, **_kwargs: Response())
    client = LayaDecisionClient(mode="remote", endpoint="https://example.test")
    with pytest.raises(LayaClientError) as error:
        asyncio.run(client.decide({"message_kind": "text", "user_text": "hello"}))
    assert error.value.code == "laya_response_invalid"


def test_store_reports_runtime_and_keeps_api_key_secret(tmp_path, monkeypatch):
    store = LayaSettingsStore(tmp_path, "target", "role")
    status = store.read()
    assert status["default_model"] == "multilingual"
    assert status["mode"] == "local"
    assert status["python_executable"] == str(__import__("pathlib").Path(sys.executable).resolve())
    status = store.update(status["revision"], {"mode": "remote", "endpoint": "http://127.0.0.1:8000",
                                               "api_key": "secret"})
    assert status["api_key_set"] is True
    assert "secret" not in str(status)
    with pytest.raises(ValueError):
        store.update(status["revision"], {"mode": "unknown"})


def test_store_detects_complete_multilingual_hub_snapshot(tmp_path, monkeypatch):
    from companion_v2.decision import store as laya_store

    cache = tmp_path / "hub"
    model = cache / "models--convaiinnovations--laya" / "snapshots" / "revision" / "multilingual"
    monkeypatch.setattr(laya_store, "_model_cache_dir", lambda: cache)
    store = LayaSettingsStore(tmp_path, "target", "role")

    (model / "rl_agent_config.json").parent.mkdir(parents=True)
    (model / "rl_agent_config.json").touch()
    assert store.read()["model_cache_ready"] is False

    for relative in ("model.safetensors", "tokenizer/tokenizer.json", "encoder/config.json"):
        path = model / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    assert store.read()["model_cache_ready"] is True


def test_old_mode_less_laya_settings_migrate_to_multilingual(tmp_path):
    store = LayaSettingsStore(tmp_path, "target", "role")
    store.directory.mkdir(parents=True)
    store.path.write_text(json.dumps({"endpoint": "http://localhost:8000/v1", "model": "laya",
                                      "api_key": "old-secret", "revision": "old"}), encoding="utf-8")
    values = store.raw()
    assert values["mode"] == "remote"
    assert values["api_key"] == "old-secret"
    assert store.read()["default_model"] == "multilingual"
