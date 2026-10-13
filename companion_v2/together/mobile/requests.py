"""Mobile protocol journal, independent of the unchanged native room port."""

from __future__ import annotations

import json
import math
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode


class MobileRoomRequests:
    """Reuse a live room or unconfirmed operation across retries and reconnects.

    Only request identity and outcome metadata are stored here. Room tickets,
    pairing credentials and device uploads remain with their existing owners.
    """

    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def _key(user_id, mode):
        return "together.mobile.request:" + digest([user_id, mode])

    @staticmethod
    def _load(row):
        if row is None:
            return None
        try:
            record = json.loads(row["value"])
            if (type(record) is not dict or record.get("schema") != "companion.mobile-room-request.v1"
                    or type(record.get("request_id")) is not str
                    or not record["request_id"].startswith("mobile-room-")
                    or type(record.get("context_key")) is not str
                    or record.get("state") not in {"pending", "succeeded", "failed"}
                    or type(record.get("expires_at")) not in {int, float}
                    or not math.isfinite(record["expires_at"])):
                raise ValueError("invalid mobile room request")
            return record
        except (ValueError, TypeError, KeyError) as error:
            raise TaskError("mobile_together_request_state_invalid",
                            "the original mobile room request cannot be verified") from error

    def begin(self, user_id, context_key, mode, *, now, room_available=None):
        key = self._key(user_id, mode)
        with self.runtime.transaction() as connection:
            record = self._load(connection.execute(
                "SELECT value FROM runtime_metadata WHERE key=?", (key,)).fetchone())
            replace = (record is None or record["state"] == "failed"
                       or (record["state"] == "succeeded" and 0 < record["expires_at"] <= now))
            if (not replace and record["state"] == "succeeded" and record["context_key"] == context_key
                    and room_available is not None):
                replace = room_available(record["request_id"]) is False
            if not replace:
                if record["context_key"] != context_key:
                    raise TaskError("mobile_v2_context_changed",
                                    "the original mobile room belongs to another private context")
                return record["request_id"]
            record = {"schema": "companion.mobile-room-request.v1",
                      "request_id": "mobile-room-" + uuid4().hex,
                      "context_key": context_key, "state": "pending", "expires_at": 0}
            connection.execute(
                "INSERT INTO runtime_metadata(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, encode(record)))
            return record["request_id"]

    def finish(self, user_id, mode, request_id, response):
        key = self._key(user_id, mode)
        with self.runtime.transaction() as connection:
            record = self._load(connection.execute(
                "SELECT value FROM runtime_metadata WHERE key=?", (key,)).fetchone())
            if record is None or record["request_id"] != request_id:
                return
            if response.get("state") == "succeeded" and response.get("effect") == "committed":
                expiry = (response.get("result", {}).get("room") or {}).get("expires_at")
                if type(expiry) in {int, float} and math.isfinite(expiry) and expiry > 0:
                    record.update(state="succeeded", expires_at=expiry)
            elif response.get("state") == "failed" and response.get("effect") == "not_committed":
                record.update(state="failed", expires_at=0)
            # Unknown outcomes, exceptions and cancellation retain the same ID.
            connection.execute("UPDATE runtime_metadata SET value=? WHERE key=?", (encode(record), key))
