"""Optional current-weather contact from an explicit role location."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from companion_v2.agenda.planning_config import configured_weather_location, configured_weather_max_age
from companion_v2.agenda.weather_material import MAX_AGE, planning_weather_material
from companion_v2.conversation.messages import source_from_document
from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.proactive.external_materials import WeatherSnapshot
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord

from .configuration import local_time
from .contact_models import ContactIntent
from .diagnostic_models import DiagnosticSourceError
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


SOURCE_OWNER = "proactive.weather"
DIAGNOSTIC_PREFIX = "proactive.weather.test:"
WINDOW = timedelta(minutes=45)
RETRY = timedelta(minutes=5)
MEANING = ("这是管理员配置的角色所在地的一次当前天气观测，不代表对方所在地、未来天气、"
           "官方预警或角色已经外出。")


class WeatherContactEvents:
    def __init__(self, contacts, role_state, port):
        if contacts.runtime is not role_state.runtime:
            raise ValueError("weather contacts must share the original role runtime")
        self.contacts, self.role_state, self.port = contacts, role_state, port
        self.runtime = contacts.runtime
        self.retry_at = {}
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)

    def close(self):
        self.guard.close()
        self.retry_at.clear()

    def _max_age(self, context, at):
        """The window this window's planning settings currently allow."""
        settings, _ = self.role_state.settings(context)
        return configured_weather_max_age(settings)

    def _slot(self, context, preferences, at):
        if not preferences.values["weather_checkin_enabled"] or preferences.reason("environment"):
            return None
        settings, _ = self.role_state.settings(context)
        location = configured_weather_location(settings["planning_weather_location"])
        if location is None:
            return None
        zone = ZoneInfo(preferences.values["quiet_timezone"])
        wall = local_time(preferences.values["weather_checkin_time"])
        day = at.astimezone(zone).date()
        opened = datetime.combine(day, wall, tzinfo=zone).astimezone(timezone.utc)
        resolved = opened.astimezone(zone)
        if (resolved.date() != day or resolved.time().replace(tzinfo=None) != wall
                or not opened <= at < opened + WINDOW):
            return None
        opportunity = Opportunity("weather-" + digest([context.key, day.isoformat()]),
            context.scope, opened, opened + WINDOW)
        marker = {"local_date": day.isoformat(), "opened_at": stamp(opened),
                  "expires_at": stamp(opportunity.expires_at), "location_hash": digest(location)}
        return opportunity, marker, location

    def select(self, context, preferences, at):
        if self.port is None or self.retry_at.get(context.key, at) > at:
            return None
        slot = self._slot(context, preferences, at)
        if slot is None:
            return None
        opportunity, marker, _ = slot
        task_id = self.contacts.task_id(context, opportunity)
        if (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,))):
            return None
        return opportunity, marker

    @staticmethod
    def _body(material):
        return {"event": "role_location_current_weather", **material, "meaning": MEANING}

    @staticmethod
    def _reference(context, slot, body, sampled_at, expires_at):
        identifier = "contact-weather-source-" + digest([context.key, slot, body, stamp(sampled_at)])
        return SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1), sampled_at, expires_at)

    def _project(self, context, opportunity, slot, material, at, max_age):
        body = self._body(material)
        expires = min(opportunity.expires_at, datetime.fromisoformat(material["valid_until"]))
        if expires <= at:
            return None
        reference = self._reference(context, slot, body, at, expires)
        # The freshness window that produced this payload is part of its receipt, so a
        # later settings change cannot invalidate an observation that was already current.
        payload = json.dumps({**body, "_receipt": {"context": json.loads(encode(context)), "slot": slot,
                                                   "max_age_seconds": int(max_age.total_seconds())}},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        require(self.contacts.sources.publish(SourceRecord(reference, context.audience, digest(payload), payload),
            observed_at=at))
        require(self.contacts.sources.validate_reference_for_audience(
            reference, recipient=context.actor.subject, observed_at=at))
        return reference

    async def prepare(self, context, slot):
        if self.port is None:
            return None
        at = self.contacts.tasks.now()
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        current = self._slot(context, preferences, at)
        if current is None or current[1] != slot:
            return None
        opportunity, _, location = current
        try:
            snapshot = await asyncio.wait_for(self.port.fetch(location), timeout=6)
        except Exception:
            self.retry_at[context.key] = self.contacts.tasks.now() + RETRY
            return None
        at = self.contacts.tasks.now()
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        current = self._slot(context, preferences, at)
        if current is None or current[1] != slot:
            return None
        max_age = self._max_age(context, at)
        material = planning_weather_material(snapshot, location, at, max_age=max_age)
        if material is None:
            self.retry_at[context.key] = at + RETRY
            return None
        source = self._project(context, opportunity, slot, material, at, max_age)
        if source is None:
            return None
        self.retry_at.pop(context.key, None)
        marker = {"slot": slot, "source": json.loads(encode(source))}
        thought = Thought("weather-checkin-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
            "角色所在地有一条新鲜的当前天气观测。只有与原对话自然相关时才简短提及，也可以跳过。",
            EvidenceSnapshot(context.scope, at, (source,)), 1.0)
        return opportunity, (ContactIntent("environment", thought),), marker

    async def diagnostic_candidate(self, context, preferences, *, test_id):
        """Fetch the configured location now, independently of the daily check-in slot."""
        settings, _ = self.role_state.settings(context)
        location = configured_weather_location(settings["planning_weather_location"])
        if self.port is None or location is None:
            raise DiagnosticSourceError("contact_weather_unavailable", "真实天气设备或角色所在地未配置", stage="weather_fetch")
        try:
            snapshot = await asyncio.wait_for(self.port.fetch(location), timeout=6)
        except Exception as error:
            raise DiagnosticSourceError("contact_weather_unavailable",
                "本次真实天气接口获取失败：" + type(error).__name__, stage="weather_fetch") from error
        at = self.contacts.tasks.now()
        max_age = self._max_age(context, at)
        material = planning_weather_material(snapshot, location, at, max_age=max_age)
        if material is None:
            raise DiagnosticSourceError("contact_weather_unavailable", "天气接口返回的地点或观测时效无效", stage="weather_fetch")
        identifier = "weather-diagnostic-" + digest([context.key, test_id])
        expires = min(at + WINDOW, datetime.fromisoformat(material["valid_until"]))
        slot = {"diagnostic_id": identifier, "opened_at": stamp(at), "expires_at": stamp(expires),
                "location_hash": digest(location)}
        opportunity = Opportunity(identifier, context.scope, at, expires)
        with self.runtime.transaction() as connection:
            connection.execute("INSERT INTO runtime_metadata(key, value) VALUES (?, ?)",
                (DIAGNOSTIC_PREFIX + identifier, encode({"context_key": context.key, "slot": slot,
                    "material": material, "provider": getattr(self.port, "provider", None)})))
        stages = [{"stage": "weather_fetch", "state": "passed",
                   "detail": f"本次已获取{location.name}的{snapshot.provider}真实天气观测"}]
        try:
            source = self._project(context, opportunity, slot, material, at, max_age)
        except TaskError as error:
            raise DiagnosticSourceError(error.code, str(error), stage="trusted_candidate", stages=stages) from error
        if source is None:
            raise DiagnosticSourceError("contact_weather_unavailable", "本次天气观测已过期", stage="trusted_candidate", stages=stages)
        marker = {"slot": slot, "source": json.loads(encode(source))}
        thought = Thought("weather-test-thought-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
            "这是刚从真实天气接口取得的角色所在地天气。可以自然分享自己的感受，不把它当作对方所在地，也不编造出行经历。",
            EvidenceSnapshot(context.scope, at, (source,)), 1.0)
        return (opportunity, (ContactIntent("environment", thought),), marker), stages

    def _diagnostic_slot(self, context, slot, at):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                    (DIAGNOSTIC_PREFIX + slot["diagnostic_id"],))
        original = json.loads(row["value"]) if row is not None else None
        settings, _ = self.role_state.settings(context)
        location = configured_weather_location(settings["planning_weather_location"])
        if (original is None or original["context_key"] != context.key or original["slot"] != slot
                or location is None or digest(location) != slot["location_hash"]
                or original["provider"] != getattr(self.port, "provider", None)
                or not datetime.fromisoformat(slot["opened_at"]) <= at < datetime.fromisoformat(slot["expires_at"])):
            raise ValueError("diagnostic weather original or location changed")
        opportunity = Opportunity(slot["diagnostic_id"], context.scope,
            datetime.fromisoformat(slot["opened_at"]), datetime.fromisoformat(slot["expires_at"]))
        return (opportunity, slot, location), original["material"]

    def _validate_source(self, record, at):
        try:
            body = json.loads(record.payload)
            receipt = body.pop("_receipt")
            if (type(body) is not dict or type(receipt) is not dict
                    or set(receipt) != {"context", "slot", "max_age_seconds"}):
                raise ValueError("invalid weather source receipt")
            recorded = receipt["max_age_seconds"]
            if (type(recorded) is not int or isinstance(recorded, bool)
                    or not 0 < recorded <= int(MAX_AGE.total_seconds())):
                raise ValueError("invalid recorded weather freshness window")
            context = TaskContext.restore(receipt["context"])
            preferences = require(self.contacts.preferences.read(context, observed_at=at))
            original = None
            if type(receipt["slot"]) is dict and "diagnostic_id" in receipt["slot"]:
                current, original = self._diagnostic_slot(context, receipt["slot"], at)
            else:
                current = self._slot(context, preferences, at)
            if current is None or current[1] != receipt["slot"]:
                raise ValueError("original weather slot changed")
            opportunity, slot, location = current
            snapshot = WeatherSnapshot(body["provider"], location.name,
                datetime.fromisoformat(body["observed_at"]), body["temperature_c"], body["condition"],
                body["humidity_pct"], body["wind_kph"], (), body.get("weather_code"))
            # Reapply the window recorded with this payload, never the current setting.
            material = planning_weather_material(snapshot, location, record.reference.issued_at,
                                                 max_age=timedelta(seconds=recorded))
            if material is None or body != self._body(material) or (original is not None and material != original):
                raise ValueError("original weather observation changed")
            expires = min(opportunity.expires_at, datetime.fromisoformat(material["valid_until"]))
            expected = self._reference(context, slot, body, record.reference.issued_at, expires)
            if (record.reference != expected or record.audience != context.audience
                    or record.content_hash != digest(record.payload)):
                raise ValueError("original weather source changed")
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_weather_source_changed", "original weather observation is no longer current") from error

    def validate(self, context, marker, at):
        if type(marker) is not dict or set(marker) != {"slot", "source"}:
            raise TaskError("contact_weather_invalid", "weather contact needs its original observation")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        try:
            current = (self._diagnostic_slot(context, marker["slot"], at)[0]
                       if type(marker["slot"]) is dict and "diagnostic_id" in marker["slot"] else
                       self._slot(context, preferences, at))
        except (KeyError, TypeError, ValueError) as error:
            raise TaskError("contact_weather_expired", "original diagnostic weather opportunity changed") from error
        if current is None or current[1] != marker["slot"]:
            raise TaskError("contact_weather_expired", "original weather opportunity is no longer current")
        try:
            source = source_from_document(marker["source"])
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_weather_invalid", "weather source reference is invalid") from error
        if source.scope != context.scope or source.owner != SOURCE_OWNER:
            raise TaskError("contact_weather_invalid", "weather source belongs to another window")
        require(self.contacts.sources.validate_reference_for_audience(
            source, recipient=context.actor.subject, observed_at=at))
