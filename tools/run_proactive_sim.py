# -*- coding: utf-8 -*-
"""跑一次真正的主动消息链路，打印"将要发出去的 envelope"，默认一条都不发。

为什么要它：主动消息最容易出问题的地方不是"发不发得出去"，而是"如果发出去，
发的是什么"——收件人是谁、正文是不是模型刚写的那句、来源归因有没有落到最后
一片、语音和戳一戳挂在第几片、回执记的是不是同一份 payload。这些都能在
``background_deliveries`` 里查到，但没人愿意为一次人工核对去读 SQLite。

这个脚本把生产链路整条跑起来，只把两个外部端口换成可打印的替身：

1. 新闻来源（``--source fixture`` 回放 ``fixtures/proactive/`` 里的录制样本，
   ``--source live-feed`` 走真网络）；
2. 平台发送：``RecordingSender`` 按生产 sender 的调用顺序走完，把 envelope
   完整打印出来，然后**拒绝**真的发送。

默认就是 dry-run：``--live`` 之外任何参数组合都不会产生平台副作用。``--live``
还要求额外的两道显式同意（环境开关 + 明确指定收件对象），见 ``--help``。

用法：
    <AstrBot Python> -X utf8 tools/run_proactive_sim.py                     # 回放录制样本
    <AstrBot Python> -X utf8 tools/run_proactive_sim.py --json              # 同上，机器可读
    <AstrBot Python> -X utf8 tools/run_proactive_sim.py --source live-feed  # 真取一次资讯
    <AstrBot Python> -X utf8 tools/run_proactive_sim.py --record-fixture    # 重新录制样本
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
# 让脚本在只有 PYTHONPATH 指向插件目录时也能跑：插件目录提供 companion_v2/astrbot_host，
# 仓库根再保证 tests/ 里的夹具可复用。
for entry in (str(ROOT.parent), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

FIXTURES = ROOT / "fixtures" / "proactive"
LIVE_ENV_SWITCH = "COMPANION_V2_PROACTIVE_SIM_LIVE"


def _clock():
    """干跑用的时钟读数：始终是当前 UTC 墙上时间。"""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# 端口替身
# --------------------------------------------------------------------------


class Article:
    """``ParseBatch`` 条目：字段名与 ``external_materials.NewsItem`` 一致。"""

    def __init__(self, source, identifier, title, url, summary, published_at):
        self.source, self.identifier, self.title = source, identifier, title
        self.url, self.summary, self.published_at = url, summary, published_at


def _replayed(item, published_at):
    return Article(item.source, item.identifier, item.title, item.url, item.summary, published_at)


class FixtureNewsPort:
    """回放 ``fixtures/proactive/`` 里的录制样本；解析仍走真解析器。"""

    kind = "rss"

    def __init__(self, manifest, alignment):
        self.manifest, self.alignment, self.calls = manifest, alignment, 0
        from astrbot_host.news import DEFAULT_AI_NEWS_FEED_LABEL
        from astrbot_host.news_parsing import parse_rss_news

        self.source_label = manifest.get("source_label") or DEFAULT_AI_NEWS_FEED_LABEL
        self.fingerprint = "run-proactive-sim-fixture-v1"
        self._bytes = (FIXTURES / manifest["sample"]).read_bytes()
        self._parse = parse_rss_news

    async def fetch(self):
        self.calls += 1
        from companion_v2.proactive.external_materials import ParseBatch

        batch = self._parse(self._bytes, source_label=self.source_label)
        shift = self.alignment - datetime.fromisoformat(self.manifest["recorded_at"])
        return ParseBatch(tuple(_replayed(item, item.published_at + shift if item.published_at else None)
                                for item in batch.items), batch.issues)


class LiveFeedNewsPort:
    """真取一次资讯：生产端口原样，只有网络这一跳是真的。"""

    def __init__(self, router, values):
        self.calls = 0
        self.port = router.for_settings(values)
        self.source_label = getattr(self.port, "source_label", "")
        self.fingerprint = "run-proactive-sim-live-feed-v1"
        self.kind = getattr(self.port, "kind", "rss")

    async def fetch(self):
        self.calls += 1
        return await self.port.fetch()


class RecordingSender:
    """生产 sender 接口的干跑替身：记录 envelope，绝不落到平台。

    ``outcome`` 决定这次干跑给链路的回执：``delivered`` 让整条链（含分片推进）
    走完，``not_sent`` 停在第一片以便逐条核对。两种都**没有**真的发送。
    """

    def __init__(self, binding, *, now, outcome="delivered"):
        self.binding, self.now, self.outcome = binding, now, outcome
        self.supports_images = True
        self.envelopes, self.attempts = [], []
        self.rejections = []

    def local_sender(self):
        from companion_v2.delivery.models import LocalSender

        return LocalSender(self.binding, self.send, supports_images=self.supports_images)

    def receipt(self, envelope, status):
        from companion_v2.delivery.models import DeliveryReceipt

        # 回执时间取"派发之后"的当前读数，与生产 sender 的 now() 语义一致。
        at = self.now()
        dispatched = getattr(envelope, "dispatched_at", None)
        del dispatched
        return DeliveryReceipt(envelope.part_id, envelope.operation_id, envelope.context.key,
            envelope.payload_hash, self.binding, status, "dry-run:" + envelope.part_id,
            "dry-run-platform:" + envelope.part_id if status in ("delivered", "accepted") else None,
            at if status == "delivered" else None)

    def render(self, envelope):
        from companion_v2.delivery.components import build_component_plan
        from companion_v2.delivery.media import ImageDeliveryEnvelope

        images = envelope.images if isinstance(envelope, ImageDeliveryEnvelope) else ()
        position = envelope.image_position if isinstance(envelope, ImageDeliveryEnvelope) else "after_text"
        segment = ({"type": "record", "data": {"file": "rendered-voice:" + envelope.part_id}}
                   if envelope.voice is not None else None)
        plan = build_component_plan(
            envelope.text, images, segment,
            position=(envelope.voice.position if envelope.voice is not None else "after_media"),
            image_position=position,
            voice_only=(envelope.voice is not None and envelope.voice.delivery_mode == "voice_only"),
            speech=(envelope.voice.speech if envelope.voice is not None else None),
            order=(envelope.plan.order if envelope.plan is not None else ()),
            mentions=(envelope.plan.mentions if envelope.plan is not None else ()),
            faces=(envelope.plan.faces if envelope.plan is not None else ()),
        )
        return {"kinds": list(plan.kinds), "text_hidden": plan.text_hidden,
                "components": [{"kind": component.kind,
                                "value": component.value if component.kind == "text" else None}
                               for component in plan.components]}

    def document(self, envelope):
        from companion_v2.delivery.media import ImageDeliveryEnvelope, image_manifest

        images = envelope.images if isinstance(envelope, ImageDeliveryEnvelope) else ()
        scope = envelope.context.scope
        return {
            "part_id": envelope.part_id,
            "operation_id": envelope.operation_id,
            "sequence": envelope.sequence,
            "target": {"platform": scope.platform, "bot_id": scope.bot_id,
                       "account_id": scope.account_id, "kind": scope.kind.value,
                       "native_scope_id": scope.native_scope_id,
                       "conversation_id": scope.conversation_id,
                       "session_id": scope.session_id,
                       "recipients": [subject.subject_id
                                      for subject in envelope.context.audience.recipients]},
            "text": envelope.text,
            "text_lines": envelope.text.split("\n"),
            "payload_hash": envelope.payload_hash,
            "sender_binding": {"capability": envelope.sender.capability,
                               "provider": envelope.sender.provider,
                               "version": envelope.sender.version,
                               "generation": envelope.sender.generation},
            "plan": envelope.plan.document() if envelope.plan is not None else None,
            "voice": envelope.voice.document() if envelope.voice is not None else None,
            "poke": envelope.poke.document() if envelope.poke is not None else None,
            "images": [image_manifest(image) for image in images],
            "image_position": (envelope.image_position
                               if isinstance(envelope, ImageDeliveryEnvelope) else "after_text"),
            "rendered": self.render(envelope),
        }

    async def send(self, envelope):
        """与生产 sender 同序：先过栅栏（并读一次派发读数），再"调用平台"，最后给回执。"""
        record = self.document(envelope)
        if envelope.before_dispatch is None:
            raise RuntimeError("干跑 envelope 没有派发栅栏")
        envelope.before_dispatch()
        # 生产 sender 的 now() 是"平台确认时刻"；这里取栅栏之后的读数，
        # 保证它落在 dispatched_at 与当前时钟之间。
        record["confirmed_at"] = self.now().isoformat()
        self.envelopes.append(record)
        record["dry_run_outcome"] = self.outcome
        self.attempts.append(record)
        return self.receipt(envelope, self.outcome)


# --------------------------------------------------------------------------
# 组装与运行
# --------------------------------------------------------------------------


def _fixture_manifest():
    path = FIXTURES / "news_feed_sample.json"
    if not path.is_file():
        raise SystemExit("缺少 fixtures/proactive/news_feed_sample.json；先跑 --record-fixture")
    return json.loads(path.read_text(encoding="utf-8"))


def record_fixture(*, url=None, user_agent="CompanionV2FixtureRecorder/1.0", quiet=False):
    """重新录制一份真实样本。原始响应体与归一化清单一起落盘。"""
    import urllib.request

    from astrbot_host.news import DEFAULT_AI_NEWS_FEED_LABEL, DEFAULT_AI_NEWS_FEED_URL
    from astrbot_host.news_parsing import parse_rss_news

    target = url or DEFAULT_AI_NEWS_FEED_URL
    request = urllib.request.Request(target, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise SystemExit("资讯源返回 %s，未录制" % response.status)
        raw = response.read(1024 * 1024)
        content_type = response.headers.get("Content-Type", "")
    recorded_at = datetime.now(timezone.utc)
    batch = parse_rss_news(raw, source_label=DEFAULT_AI_NEWS_FEED_LABEL)
    if not batch.items:
        raise SystemExit("资讯源没有返回可解析条目，未录制")
    stamp_text = recorded_at.strftime("%Y%m%d")
    sample = "news_feed_%s_%s.xml" % (target.rsplit("/", 1)[-1].split(".")[0] or "feed", stamp_text)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / sample).write_bytes(raw)
    items = [{"source": item.source, "identifier": item.identifier, "title": item.title,
              "url": item.url, "summary": item.summary,
              "published_at": item.published_at.isoformat() if item.published_at else None}
             for item in batch.items]
    newest = max((item for item in items if item["published_at"]),
                 key=lambda item: item["published_at"])
    manifest = {
        "sample": sample,
        "recorded_by": "tools/run_proactive_sim.py --record-fixture",
        "recorded_at": recorded_at.isoformat(),
        "request": {"method": "GET", "url": target, "status": 200,
                    "content_type": content_type, "user_agent": user_agent},
        "stored_bytes": len(raw), "stored_sha256": hashlib.sha256(raw).hexdigest(),
        "source_label": DEFAULT_AI_NEWS_FEED_LABEL,
        "parse_issues": [{"index": issue.index, "code": issue.code} for issue in batch.issues],
        "items": items, "article": dict(newest),
        "clock_alignment": {
            "note": ("清单保存真实录制的绝对时间；消费它的用例/脚本整体平移时间轴，"
                     "使最新一条落在运行时钟附近，从而落在 24h 取源窗口内。"
                     "原始响应体未做任何改写。"),
        },
    }
    (FIXTURES / "news_feed_sample.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if not quiet:
        print("已录制 %s（%d 字节，%d 条，最新 %s）"
              % (sample, len(raw), len(items), newest["published_at"]))
        print("原始响应体未改写；User-Agent 是 %r，生产端口默认不发这个头。" % user_agent)
    return manifest


class PendingSender:
    """宿主装配期先占位的 sender：真身要在宿主建好之后（拿到它的时钟）才注入。

    ``CompanionApplication`` 只读 ``binding`` / ``supports_images`` 并调用 ``send``，
    所以这里把 ``send`` 转发到一个后填的槽位，装配顺序就不再受时钟来源约束。
    """

    supports_images = True

    def __init__(self, binding):
        self.binding = binding
        self.target = None

    async def send(self, envelope):
        if self.target is None:
            raise RuntimeError("干跑 sender 还没有绑定")
        return await self.target.send(envelope)


def _host_kwargs(binding, runtime, generate):
    """合成宿主的装配参数：真注册表、真 provider 契约、只换模型回答与 sender。"""
    from companion_v2.conversation.flow import ConversationPolicy
    from companion_v2.conversation.messages import REPLY_KIND
    from companion_v2.configuration.registry import FieldRegistry
    from companion_v2.execution.models import Lane, ProviderBinding, SupervisorLimits
    from companion_v2.identity_policy.personas import RuntimeIdentity
    from companion_v2.model_gateway.models import Amount, BudgetPolicy, LocalProvider, ModelTaskProfile
    from companion_v2.model_gateway.routing import configuration_fields
    from companion_v2.proactive.service import contact_profile

    profiles = (ModelTaskProfile(REPLY_KIND, Lane.FOREGROUND, "primary", "补充任务提示",
                                 max_output_tokens=100),
                contact_profile("primary", max_output_tokens=100))
    provider = LocalProvider(ProviderBinding("model.text", "primary", "1", "model-1"),
                             ("text", "tools"), 100, lambda _envelope: Amount(100, 100), generate)
    return {
        "runtime": runtime,
        "runtime_identity": RuntimeIdentity("companion", "runtime-1", "astrbot", "host"),
        "profiles": profiles,
        "registry": FieldRegistry(version="sim.v1", fields=configuration_fields(profiles)),
        "providers": (provider,),
        "budget": BudgetPolicy(*(Amount(100000, 100000) for _ in range(5))),
        "sender": PendingSender(binding),
        "limits": SupervisorLimits(foreground_slots=4, background_slots=1, queued_per_lane=64,
                                   retained_tasks=256),
        "policy": ConversationPolicy(0, 0, 180, 0),
        "split": lambda text: tuple(text.splitlines(keepends=True)),
    }


async def run_simulation(args):
    """跑一次链路，返回 (envelope 文档, 链路状态, 提示信息)。"""
    from companion_v2.adapters.astrbot.application import AstrBotCompanionHost
    from astrbot_host.news import configured_news_port
    from companion_v2.execution.models import ProviderBinding, TaskContext, digest
    from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef
    from companion_v2.foundation.refs import SubjectKind, SubjectRef
    from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
    from companion_v2.identity_policy.object_access import ObjectAccessPolicy
    from companion_v2.identity_policy.personas import ConversationRoute, PersonaBinding, PersonaDirectory, PersonaSelector, SelectorKind
    from companion_v2.identity_policy.repository import PersistentIdentityDirectory
    from companion_v2.proactive.configuration import GROUP, target_for
    from companion_v2.storage.runtime import StorageRuntime
    from companion_v2.model_gateway.models import ProviderResponse, Amount

    notes = []
    # 用真时钟：这条链的门槛（idle_seconds、机会窗口、投递回执区间）都是"按秒"的，
    # 确定时钟要么停在门槛之前、要么需要脚本自己不停推它。干跑的要点不是可复现的
    # 时间轴，而是"如果发出去会是什么"，所以让时间自然走。
    clock = _clock
    temporary = TemporaryDirectory(prefix="companion-v2-proactive-sim-")
    runtime = StorageRuntime.open(data_root=Path(temporary.name) / "data", installation_id="proactive-sim")
    try:
        run_at = clock()
        installation = "proactive-sim"
        scope = ScopeRef(installation, "sim", ScopeKind.PRIVATE, args.target, args.bot_id,
                         args.account_id, "conversation-" + args.target, "session-" + args.target)
        identity = PersistentIdentityDirectory(runtime)
        policy = ObjectAccessPolicy(runtime)
        personas = PersonaDirectory(runtime)
        principal = AuthenticatedHostPrincipal(installation, "host", "sim", "sim-user",
                                               args.bot_id, args.account_id)
        subject = SubjectRef(installation, SubjectKind.HUMAN, "sim-user")
        identity.bind(binding_id="sim-user", principal=principal, subject=subject,
                      valid_from=run_at, expected_revision=identity.revision)
        policy.set_tier(subject, AuthorizationTier.IMPORTANT, expected_revision=policy.revision,
                        observed_at=run_at)
        actor = identity.resolve_authenticated(principal, observed_at=run_at).unwrap()
        personas.register_route(ConversationRoute(scope, user=actor.subject), observed_at=run_at)
        role = SubjectRef(installation, SubjectKind.BOT, "persona-a")
        personas.set_binding(PersonaBinding("base", PersonaSelector(installation, SelectorKind.BOT,
                                   bot_id=args.bot_id), role, 0, run_at, "sim", "admin"),
                             expected_revision=0, observed_at=run_at)
        for capability in ("text", "proactive.contact"):
            identity.issue_grant(grant_id="sim-" + capability, subject=actor.subject, scope=scope,
                capability=capability, tier=AuthorizationTier.IMPORTANT, valid_from=run_at,
                expires_at=None, expected_revision=identity.revision)

        binding = ProviderBinding("message.delivery", "dry-run", "1", "dry-run-1")

        async def route_model(envelope):
            """一轮对话走普通回复，主动消息走封存草稿；两条都由同一个 provider 提供。"""
            from companion_v2.conversation.foreground import BackgroundPromptTrigger, ModelDraft

            if isinstance(envelope.original.event, BackgroundPromptTrigger):
                return ProviderResponse("generated", draft=ModelDraft(json.dumps(
                    {"decision": "send",
                     "text": "刚看到一条资讯，想到你也在关注这个方向。",
                     "decision_confidence": 0.9}, ensure_ascii=False), ()),
                    usage=Amount(15, 40), receipt_ref="sim-contact")
            # 单行回复：干跑只关心主动消息那一条链，回复分片会把它挡在排程之前。
            return ProviderResponse("generated", draft=ModelDraft("我记下了，晚点再聊。", ()),
                                    usage=Amount(15, 40), receipt_ref="sim-reply")

        kwargs = _host_kwargs(binding, runtime, route_model)
        from companion_v2.model_gateway.models import Lane
        from companion_v2.conversation.messages import REPLY_KIND

        class Ports:
            """宿主端口：只做合成事件到 V2 输入的字段映射，不做任何外部调用。"""

            def event_id(self, event): return event["id"]
            def scope(self, event): return event["scope"]
            def audience(self, event): return AudienceRef(event["scope"], (event["actor"].subject,))
            def payload(self, event): return event["text"]
            def payload_hash(self, event): return digest(event["text"])
            def received_at(self, event): return event["at"]
            def conversation_route(self, event):
                return ConversationRoute(event["scope"], user=event["actor"].subject)
            def authenticated_principal(self, event):
                from companion_v2.foundation.outcome import Outcome
                return Outcome.success(event["actor"].principal)
            def role_instruction(self, event, context): return event["prompt"]

        ports = Ports()
        kwargs["event_port"] = ports
        kwargs["identity_port"] = ports
        kwargs["role_port"] = ports

        if args.source == "fixture":
            manifest = _fixture_manifest()
            lead = (datetime.fromisoformat(manifest["recorded_at"])
                    - datetime.fromisoformat(manifest["article"]["published_at"]))
            port = FixtureNewsPort(manifest, alignment=clock() + lead)
            notes.append("新闻来源：回放录制样本 %s（%d 条，最新 %s）"
                         % (manifest["sample"], len(manifest["items"]),
                            manifest["article"]["published_at"]))
        else:
            router = configured_news_port()
            port = LiveFeedNewsPort(router, {"news_source_kind": "host"})
            notes.append("新闻来源：真取一次（host 路由 → %s）" % (port.source_label or "未知"))

        options = dict(kwargs)
        options.pop("runtime", None)
        host = AstrBotCompanionHost(runtime, news_port=port, **options)
        app = host.application
        # 回执时刻必须与运行期自己的时钟同源：投递校验要求
        # dispatched_at <= delivered_at <= tasks.now()，而 dispatched_at 取的是宿主
        # 时钟（真运行是墙上时钟）。拿另一个读数去签回执，会被判成
        # message_receipt_time，整条消息落进 unknown。
        recorder = RecordingSender(binding, now=app.now, outcome=args.outcome)
        options["sender"].target = recorder
        await app.start(expected_task_generation=0, expected_model_generation=0)
        # 目标 (installation, window, role, scope, subject) 由真解析器算出来，
        # 脚本不手写它，避免和运行期解析结果漂移。
        role_binding = app.tasks.identity.resolve_role(scope, observed_at=clock()).unwrap()
        context = TaskContext(actor, role_binding, AudienceRef(scope, (actor.subject,)))
        target = target_for(context)
        snapshot = app.configuration.read(actor, target=target, group_id=GROUP,
                                          observed_at=clock()).unwrap()
        owner = app.configuration.registry.group(GROUP)[0].owner_id
        app.configuration.patch(actor, target=target, group_id=GROUP,
            expected_edit_token=snapshot.edit_token,
            changes={GROUP + ".enabled": True, GROUP + ".automatic_enabled": True,
                     GROUP + ".interval_seconds": 60, GROUP + ".idle_seconds": 60,
                     GROUP + ".chat.enabled": False, GROUP + ".news_share_enabled": True,
                     GROUP + ".news_source_kind": "json",
                     GROUP + ".news_source_url": "https://news.example/feed",
                     GROUP + ".news_check_interval_minutes": 15},
            reset_to_inherit=(), operation=_operation(target, owner=owner),
            observed_at=clock()).unwrap()

        event = {"id": "sim-input-1", "scope": scope, "actor": actor,
                 "text": "我先随便说一句，晚点再聊。", "at": clock(), "prompt": "这是原角色人格。"}
        batch = host.receive(event).unwrap()
        app.notify()
        for _ in range(400):
            await asyncio.sleep(0.05)
            row = app.flow.row(batch)
            if row["state"] in ("complete", "blocked", "closed") or app.state == "faulted":
                break
        if app.state == "faulted":
            raise SystemExit("宿主在会话阶段就故障了：%s" % app.failure_code)
        if args.debug:
            flow = app.flow.row(batch)
            print("[debug] 会话阶段：state=%s reason=%s" % (flow["state"], flow["reason"]), file=sys.stderr)

        app.notify()
        # 排程由宿主自己的驱动循环按秒推进；干跑里同时主动踢它几次，这样脚本的
        # 运行时间不取决于机器负载。（不要在这之前手工调用 select/_plan 做"探针"：
        # 它们会推进排程游标或落地机会记录，真正的 advance 就会跳过这一次机会。）
        # 干跑必须真的等：``idle_seconds`` 说的是"最近一轮对话之后过了多久"，
        # 而墙上时钟不会因为我们不等就跳过去。默认给 120 秒预算，够 idle + 一片投递。
        deadline = monotonic() + args.budget_seconds
        while monotonic() < deadline:
            try:
                app.contact_schedule.advance()
            except Exception as error:  # noqa: BLE001 - 干跑要报出真正的原因，不是静默超时
                raise SystemExit("排程推进失败：%s %s"
                                 % (getattr(error, "code", type(error).__name__), error)) from error
            rows = app.runtime.read_all("SELECT * FROM background_deliveries", ())
            if (rows and all(row["state"] in ("delivered", "failed", "unknown", "cancelled")
                             for row in rows) and not app.contact_schedule.active_handles):
                break
            await asyncio.sleep(0.05)
        if app.state == "faulted":
            raise SystemExit("宿主在主动消息阶段故障了：%s" % app.failure_code)
        if port.calls == 0:
            notes.append("取源端口一次都没被调用：预算内没等到可用契机"
                         "（idle 未满、免打扰、已经排过，或来源本身被关掉）。")
        if args.debug:
            # 只读诊断放在链路跑完之后：任何"探针"式调用都会吃掉这一次机会。
            events = app.contact_schedule.news_events
            preferences = app.proactive.preferences.read(context, observed_at=clock()).unwrap()
            print("[debug] 取源调用=%s" % port.calls, file=sys.stderr)
            print("[debug] 诊断=%s"
                  % json.dumps(events.diagnostic(context, preferences), ensure_ascii=False),
                  file=sys.stderr)
            print("[debug] 任务=%s"
                  % [(item["kind"], item["state"]) for item in
                     app.runtime.read_all("SELECT kind, state FROM execution_tasks", ())], file=sys.stderr)

        contacts = app.runtime.read_all("SELECT * FROM proactive_contacts", ())
        rows = app.runtime.read_all("SELECT * FROM background_deliveries ORDER BY delivery_id", ())
        claimed = {row["delivery_id"] for row in rows}
        documents = [envelope for envelope in recorder.envelopes if envelope["part_id"] in claimed]
        state = {
            "host": {"state": app.state, "failure_code": app.failure_code},
            "news_source_calls": port.calls,
            "contacts": [{"contact_id": contact["contact_id"],
                          "task_id": contact["task_id"],
                          "purpose": json.loads(contact["record_json"])["purpose"],
                          "decision": json.loads(contact["record_json"])["decision"],
                          "body": contact["body"]}
                         for contact in contacts],
            "deliveries": [{"delivery_id": row["delivery_id"], "state": row["state"],
                            "receipt_ref": row["receipt_ref"], "platform_ref": row["platform_ref"],
                            "payload_hash": row["payload_hash"]} for row in rows],
            "suppression": _suppression_report(app, context, clock),
        }
        if not documents:
            notes.append("这条链这次没有产生任何 envelope；上面的 suppression 字段说明原因。")
        return documents, state, notes
    finally:
        try:
            await app.close()
        except NameError:
            pass
        runtime.close()
        temporary.cleanup()


def _operation(target, *, owner):
    """配置操作的身份：作用域取自目标，owner 取自该配置组自己的 owner_id。"""
    from companion_v2.foundation.refs import OperationRef, VersionRef

    identifier = "sim-operation"
    return OperationRef(identifier, owner, target.authorization_scope,
                        VersionRef(identifier, 1), identifier)


def _suppression_report(app, context, clock):
    try:
        preferences = app.proactive.preferences.read(context, observed_at=clock()).unwrap()
        return {"automatic_enabled": preferences.values["automatic_enabled"],
                "news_share_enabled": preferences.values["news_share_enabled"],
                "idle_seconds": preferences.values["idle_seconds"],
                "chat_reason": preferences.reason("chat"),
                "news_reason": preferences.reason("news")}
    except Exception as error:  # 只影响报告，不影响链路结论
        return {"unavailable": type(error).__name__}


def _print_human(documents, state, notes):
    print("=" * 78)
    print("主动消息干跑：以下 envelope **没有**发出去，只供人工核对文案与目标。")
    print("=" * 78)
    for note in notes:
        print("· " + note)
    print("-" * 78)
    for index, document in enumerate(documents, 1):
        target = document["target"]
        print("[%d/%d] %s  第 %d 片" % (index, len(documents), document["part_id"], document["sequence"]))
        print("  目标      ：%s %s / 会话 %s" % (target["kind"], target["native_scope_id"],
                                                target["native_scope_id"]))
        print("  收件人    ：%s" % "、".join(target["recipients"]))
        print("  会话标识  ：platform=%s bot=%s account=%s conversation=%s"
              % (target["platform"], target["bot_id"], target["account_id"], target["conversation_id"]))
        print("  正文      ：")
        for line in document["text_lines"]:
            print("    | " + line)
        print("  payload   ：%s" % document["payload_hash"])
        print("  渲染态    ：%s%s" % (" + ".join(document["rendered"]["kinds"]),
                                      "（正文被语音替代）" if document["rendered"]["text_hidden"] else ""))
        if document["voice"] is not None:
            print("  语音      ：%r（%s，%s）" % (document["voice"]["speech"],
                                                 document["voice"]["position"],
                                                 document["voice"]["delivery_mode"]))
        if document["poke"] is not None:
            print("  戳一戳    ：%d 次" % document["poke"]["count"])
        if document["images"]:
            print("  图片      ：%d 张，位置 %s" % (len(document["images"]), document["image_position"]))
        print("  干跑结果  ：%s（合成回执，平台并没有收到任何东西）" % document["dry_run_outcome"])
        print("-" * 78)
    if not documents:
        print("（没有 envelope）")
    print("链路状态：host=%s 资讯取源 %d 次，联系人 %d 条，投递 %d 条"
          % (state["host"]["state"], state["news_source_calls"],
             len(state["contacts"]), len(state["deliveries"])))
    if state["suppression"]:
        print("压制读数：%s" % json.dumps(state["suppression"], ensure_ascii=False))
    for row in state["deliveries"]:
        print("  投递 %s：%s（回执 %s）" % (row["delivery_id"][:24], row["state"], row["receipt_ref"]))


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="跑一次主动消息链路，打印将要发送的 envelope；默认不发。")
    parser.add_argument("--source", choices=("fixture", "live-feed"), default="fixture",
                        help="新闻来源：回放录制样本（默认）或真取一次")
    parser.add_argument("--outcome", choices=("delivered", "not_sent"), default="delivered",
                        help="干跑回执：delivered 让整条链走完（默认），not_sent 停在第一片")
    parser.add_argument("--json", action="store_true", help="输出机器可读的 JSON")
    parser.add_argument("--record-fixture", action="store_true",
                        help="重新录制 fixtures/proactive/ 里的资讯样本后退出")
    parser.add_argument("--feed-url", default=None, help="与 --record-fixture 连用，覆盖默认源")
    parser.add_argument("--target", default="sim-native", help="干跑用的合成窗口标识")
    parser.add_argument("--bot-id", default="sim-bot", help="干跑用的合成 bot 标识")
    parser.add_argument("--account-id", default="sim-account", help="干跑用的合成账号标识")
    parser.add_argument("--live", action="store_true",
                        help="走真 sender 发送。需要同时设置 %s=1 并给出 --live-target" % LIVE_ENV_SWITCH)
    parser.add_argument("--live-target", default="", help="--live 时必须明确写出的收件对象")
    parser.add_argument("--debug", action="store_true",
                        help="打印会话与投递的阶段读数，便于排查链路为什么停下")
    parser.add_argument("--budget-seconds", type=float, default=120.0,
                        help="等这条链跑完的墙上时间预算（idle 门槛是真实秒数）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(argv)
    if args.record_fixture:
        record_fixture(url=args.feed_url)
        return 0
    if args.live:
        if os.environ.get(LIVE_ENV_SWITCH) != "1":
            raise SystemExit("--live 需要显式环境开关：%s=1" % LIVE_ENV_SWITCH)
        if not args.live_target:
            raise SystemExit("--live 必须用 --live-target 明确写出收件对象")
        raise SystemExit("真发送端口尚未接线：本脚本只提供干跑；"
                         "接线前请用插件自己的管理员投递测试（/setup/proactive-diagnostic）。")
    documents, state, notes = asyncio.run(run_simulation(args))
    if args.json:
        print(json.dumps({"envelopes": documents, "state": state, "notes": notes},
                         ensure_ascii=False, indent=2))
    else:
        _print_human(documents, state, notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
