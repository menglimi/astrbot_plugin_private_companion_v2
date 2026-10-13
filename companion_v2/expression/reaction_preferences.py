"""Per-speaker reaction boundaries and feedback from confirmed deliveries."""

import json
import re
from datetime import datetime

from companion_v2.conversation.messages import source_from_document
from companion_v2.execution.models import TaskError, digest


ASSET = r"(?:表情包|表情|反应图|贴纸|梗图|斗图)"
OPT_OUT = (
    rf"(?:别|不要|不用再|停止).{{0,8}}(?:发|用).{{0,8}}{ASSET}",
    rf"(?:不想看|不需要|关闭|停用).{{0,6}}{ASSET}",
    rf"{ASSET}.{{0,6}}(?:以后)?(?:别|不要|不用再).{{0,4}}(?:发|用)",
)
OPT_IN = (
    rf"(?:继续|恢复|重新开启|重新启用).{{0,6}}(?:自动)?(?:发|用)?{ASSET}",
    rf"(?:开启|启用|打开).{{0,6}}(?:自动)?{ASSET}",
)
REQUEST = (
    rf"^(?:请|给我|帮我|来|发|找|想看|要看).{{0,12}}{ASSET}(?:吧|呀|啊|看看)?$",
    rf"^{ASSET}(?:来|发|找)?(?:一张|一个|吧|呀|啊|看看)?$",
)
NEGATIVE = (
    rf"(?:刚才|上一张|那张|这张).{{0,10}}(?:{ASSET})?.{{0,8}}(?:不合适|不贴切|不喜欢|尴尬|难看)",
    rf"{ASSET}.{{0,8}}(?:不合适|不贴切|不喜欢|尴尬|难看)",
)
POSITIVE = (
    rf"(?:刚才|上一张|那张|这张).{{0,10}}(?:{ASSET})?.{{0,8}}(?:不错|合适|贴切|喜欢|好笑|好用)",
    rf"{ASSET}.{{0,8}}(?:不错|合适|贴切|喜欢|好笑|好用)",
    r"^(?:太贴了|太适合了|这张可以|好好笑|笑死了?|绝了)$",
)
REACTION_FEEDBACK_WINDOW_SECONDS = 15 * 60


def matches(patterns, text):
    compact = re.sub(r"\s+", "", text or "").casefold()
    return any(re.search(pattern, compact) for pattern in patterns)


class ReactionPreferences:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.messages = service.app.messages

    @staticmethod
    def actor(context):
        return digest(["reaction-speaker.v1", context.scope.key,
                       context.actor.principal.native_account_id])

    def prepare(self, context, batch_id):
        self.service.check(context)
        owner, actor = self.service.owner(context), self.actor(context)
        rows = self.messages.runtime.read_all(
            "SELECT event_key,event_json FROM conversation_inputs WHERE batch_id=? AND withdrawn=0 ORDER BY position",
            (batch_id,))
        requested = False
        for row in rows:
            event = json.loads(row["event_json"])
            if event["principal"]["native_account_id"] != context.actor.principal.native_account_id:
                continue
            source = source_from_document(event["source"])
            record = self.messages._read_source(source, context, "text", self.service.app.now())
            if not isinstance(record.payload, str):
                continue
            text = record.payload[:2000]
            out = matches(OPT_OUT, text)
            if out:
                requested = False
            elif matches(REQUEST, text):
                requested = True
            self._observe(owner, actor, row["event_key"], text,
                          datetime.fromisoformat(event["received_at"]).timestamp())
        with self.store.db() as db:
            db.execute("INSERT OR REPLACE INTO reaction_turns VALUES (?,?,?,?)",
                       (batch_id, owner, actor, int(requested)))

    def prepare_native(self, context, turn_id, *, event_id, text, at):
        self.service.check(context)
        owner, actor = self.service.owner(context), self.actor(context)
        self._observe(owner, actor, "native:" + digest([context.key, event_id]), text, at.timestamp())
        requested = matches(REQUEST, text) and not matches(OPT_OUT, text)
        with self.store.db() as db:
            db.execute("INSERT OR REPLACE INTO reaction_turns VALUES (?,?,?,?)",
                       (turn_id, owner, actor, int(requested)))

    def _observe(self, owner, actor, event_key, text, received_at):
        out, enabled = matches(OPT_OUT, text), matches(OPT_IN, text)
        signal = "negative" if out or matches(NEGATIVE, text) else "positive" if matches(POSITIVE, text) else ""
        with self.store.db() as db:
            if not db.execute("""INSERT OR IGNORE INTO reaction_inputs
                (owner,event_key,actor,received_at,signal) VALUES (?,?,?,?,?)""",
                (owner, event_key, actor, received_at, signal or None)).rowcount:
                return
            if out or enabled:
                db.execute("""INSERT INTO reaction_preferences VALUES (?,?,?)
                    ON CONFLICT(owner,actor) DO UPDATE SET auto_disabled=excluded.auto_disabled""",
                    (owner, actor, int(out)))
            if not signal:
                return
            self._assign_feedback(db, owner, actor, event_key, received_at, signal)

    @staticmethod
    def _assign_feedback(db, owner, actor, event_key, received_at, signal):
        if db.execute("SELECT 1 FROM reaction_deliveries WHERE owner=? AND feedback_event=?",
                      (owner, event_key)).fetchone():
            return
        target = db.execute("""SELECT batch,id,feedback_event FROM reaction_deliveries
            WHERE owner=? AND actor=? AND delivered_at<=? AND delivered_at>=?
            ORDER BY delivered_at DESC, batch DESC LIMIT 1""",
            (owner, actor, received_at, received_at - REACTION_FEEDBACK_WINDOW_SECONDS)).fetchone()
        if target is None or target["feedback_event"] is not None:
            return
        if not db.execute("""UPDATE reaction_deliveries SET feedback_event=?,feedback_signal=?
            WHERE owner=? AND id=? AND batch=? AND feedback_event IS NULL""",
            (event_key, signal, owner, target["id"], target["batch"])).rowcount:
            return
        delta = 1 if signal == "positive" else -1
        db.execute("""INSERT INTO reaction_affinity (owner,actor,id,score,positive_count,negative_count)
            VALUES (?,?,?,?,?,?) ON CONFLICT(owner,actor,id) DO UPDATE SET
            score=MIN(8,MAX(-8,score+excluded.score)),
            positive_count=positive_count+excluded.positive_count,
            negative_count=negative_count+excluded.negative_count""",
            (owner, actor, target["id"], delta, int(delta > 0), int(delta < 0)))

    def reconcile_delivery(self, owner, actor, delivered_at):
        with self.store.db() as db:
            rows = db.execute("""SELECT event_key,received_at,signal FROM reaction_inputs
                WHERE owner=? AND actor=? AND signal IS NOT NULL
                AND received_at>=? AND received_at<=?
                ORDER BY received_at,event_key""",
                (owner, actor, delivered_at, delivered_at + REACTION_FEEDBACK_WINDOW_SECONDS)).fetchall()
            for row in rows:
                self._assign_feedback(db, owner, actor, row["event_key"],
                                      row["received_at"], row["signal"])

    def state(self, context, batch_id=None):
        owner, actor = self.service.owner(context), self.actor(context)
        with self.store.db() as db:
            row = db.execute("SELECT auto_disabled FROM reaction_preferences WHERE owner=? AND actor=?",
                             (owner, actor)).fetchone()
            turn = db.execute("SELECT explicit_request FROM reaction_turns WHERE batch=? AND owner=? AND actor=?",
                              (batch_id, owner, actor)).fetchone() if batch_id else None
        return bool(row and row["auto_disabled"]), bool(turn and turn["explicit_request"])

    def allowed(self, context, batch_id=None):
        disabled, requested = self.state(context, batch_id)
        return not disabled or requested

    def available(self, context, batch_id, settings):
        disabled, requested = self.state(context, batch_id)
        if disabled and not requested:
            return False
        if batch_id is None or requested:
            return True
        cooldown = settings["reactions_cooldown_seconds"]
        if cooldown:
            with self.store.db() as db:
                last = db.execute("SELECT MAX(delivered_at) FROM reaction_deliveries WHERE owner=?",
                                  (self.service.owner(context),)).fetchone()[0]
            if last is not None and self.service.app.now().timestamp() - last < cooldown:
                return False
        sample = int(digest(["reaction-auto.v1", batch_id])[:16], 16) / 2**64
        return sample < settings["reactions_trigger_probability"]

    def require_allowed(self, context, batch_id):
        if not self.allowed(context, batch_id):
            raise TaskError("reaction_auto_disabled", "automatic reaction images are paused for this speaker")

    def scores(self, context):
        with self.store.db() as db:
            return {row["id"]: row["score"] for row in db.execute(
                "SELECT id,score FROM reaction_affinity WHERE owner=? AND actor=?",
                (self.service.owner(context), self.actor(context)))}

    def instruction(self, context, batch_id):
        disabled, requested = self.state(context, batch_id)
        if disabled and requested:
            return "此会话平时暂停自动发表情；用户本轮明确提出请求，可仅为本轮按回应意图选图。"
        if disabled:
            return "此会话用户已要求暂停自动发表情；本轮不检索或发送图库表情。"
        return "用户对表情的评价只影响后续选图；不要把图库候选当作已发送图片。"
