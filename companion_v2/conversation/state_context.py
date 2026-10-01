"""Seal references to state, rechecking permissions and simulation expiry at every consumer."""

from datetime import datetime
import json

from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.identity_policy.private_domain import source_ref
from companion_v2.role_work.state import humanized, mood
from companion_v2.role_work.state.cycle_prompts import reply_instruction


class ConversationStateContext:
    def __init__(self, service):
        self.service = service

    def capture(self, context, at):
        with self.service.runtime.transaction():
            return self._capture(context, at)

    def _capture(self, context, at):
        try:
            state = self.service.read(context, at=at)
            if state["state"] == "disabled" or state["state"] == "unknown" and "sleep_execution" not in state:
                return None
            activities = self.service.activity_context(context)
            return {"revision": state["revision"], "hash": digest(state), "activity_hash": digest(activities),
                "projection_version": 3, "storage": self.service.records.storage(context),
                "sleep": self.service.body_clock.reference(context),
                "source": self.service.publish_projection(context, state, at=at),
                "captured_at": stamp(at), "activities": [{"id": a["id"], "revision": a["revision"]} for a in activities["items"]],
                "activity_unavailable": activities.get("state") == "unavailable", "activity_partial": activities["partial"],
                "humanized_intensity": self._intensity(context)}
        except TaskError:
            return None

    def _intensity(self, context):
        """Seal the expression dial with the state it applies to, so a replay is
        byte-identical and a later configuration edit cannot rewrite an old turn."""
        try:
            values, _token = self.service.settings(context)
            value = values.get(humanized.INTENSITY_FIELD)
        except (TaskError, ValueError, KeyError):
            return None
        return value if type(value) is int and 0 <= value <= 100 else None

    def contributions(self, snapshot, context, at, *, historical=False):
        if snapshot is None:
            return ()
        old_fields = {"revision", "hash", "activity_hash"}
        fields = old_fields | {"captured_at", "activities", "activity_unavailable", "activity_partial"}
        if type(snapshot) is not dict:
            raise TaskError("state_snapshot_invalid", "invalid role state reference")
        # The expression dial is additive: a batch sealed before it existed simply
        # omits the key, and the replay then injects no state expression at all.
        sealed_fields = set(snapshot)
        sealed_fields.discard("humanized_intensity")
        intensity = snapshot.get("humanized_intensity")
        if (sealed_fields not in (old_fields, fields, fields | {"projection_version"},
                fields | {"projection_version", "storage", "sleep", "source"})
                or intensity is not None and (type(intensity) is not int or not 0 <= intensity <= 100)
                or "projection_version" in snapshot and (type(snapshot["projection_version"]) is not int
                    or snapshot["projection_version"] not in (2, 3))
                or snapshot.get("projection_version") == 3 and snapshot.get("storage") not in ("role", "window")
                or "storage" in snapshot and snapshot.get("projection_version") != 3):
            raise TaskError("state_snapshot_invalid", "invalid role state reference")
        if historical and "captured_at" in snapshot:
            state = self.service.read_revision(context, snapshot["revision"],
                captured_at=datetime.fromisoformat(snapshot["captured_at"]), observed_at=at,
                storage=snapshot.get("storage", "window"), sleep_reference=snapshot.get("sleep"),
                include_sleep=snapshot.get("projection_version") == 3)
            activities = ({"items": [], "partial": False, "state": "unavailable"} if snapshot["activity_unavailable"] else
                self.service.activity_context(context, references=snapshot["activities"], partial=snapshot["activity_partial"]))
        else:
            if self.service.records.storage(context) != snapshot.get("storage", "window"):
                raise TaskError("role_state_changed", "role body storage changed after capture")
            state = self.service.read(context, at=at, cycle_at=(datetime.fromisoformat(snapshot["captured_at"])
                if snapshot.get("projection_version") in (2, 3) else None))
            activities = self.service.activity_context(context)
        if state.get("revision") != snapshot["revision"] or digest(state) != snapshot["hash"] or digest(activities) != snapshot["activity_hash"]:
            raise TaskError("role_state_changed", "original role state or actual activity changed")
        record = self.service.records.version(context, "current", snapshot["revision"], storage=snapshot.get("storage", "window")) if snapshot["revision"] else None
        source = source_ref(record["sources"][0]) if record else None
        if snapshot.get("projection_version") == 3:
            source = source_ref(snapshot["source"])
            self.service.access.evidence(context, (source,), at=at)
            require(self.service.access.sources.validate_reference_for_audience(source, recipient=context.actor.subject,
                observed_at=at, expected_content_hash=digest(encode(state))))
        # Activity sources can be newer than the last maintenance and need independent provenance.
        activity_sources = tuple(dict.fromkeys(source_ref(ref) for item in activities["items"] for ref in item["sources"]))
        return (ContextContribution("role-state", "role.state", "role_state", ContributionState.READY,
                                    encode({"simulation": state, "activities": activities,
                                            **({"observed_at": snapshot["captured_at"]}
                                               if snapshot.get("projection_version") in (2, 3) else {})}), source),
                # The sealed dial travels next to the state it applies to; the
                # prompt block it produces is bounded and expressive only.
                ContextContribution("role-state-humanized", "role.state", "role_state_intensity",
                                    ContributionState.READY, encode({"intensity": intensity}), source),
                ) + tuple(
            ContextContribution("state-activity-source-" + str(index), ref.owner, "activity_source_reference",
                ContributionState.READY, "上述实际活动的原材料引用，不证明额外经历。", ref) for index, ref in enumerate(activity_sources))

    @staticmethod
    def instruction(materials):
        blocks, simulations, intensity = [], [], None
        for item in materials:
            if item.purpose == "role_state":
                simulations.append(json.loads(item.payload)["simulation"])
            elif item.purpose == "role_state_intensity":
                try:
                    intensity = json.loads(item.payload)["intensity"]
                except (ValueError, KeyError, TypeError):
                    intensity = None
        for simulation in simulations:
            dynamics = simulation.get("mood_dynamics") or {}
            blocks.append(reply_instruction(simulation))
            blocks.append(mood.prompts.reply(simulation.get("values", {}).get("mood"), dynamics,
                                             neutral=dynamics.get("neutral", True)))
        if intensity:
            # Zero injects nothing at all; a positive dial adds one bounded block.
            blocks.extend(humanized.instruction(simulation, intensity=intensity) for simulation in simulations)
        return "".join(blocks)
