"""Domain invariants for read-only native reads (Reality, Live, Together).

The generic native channel already seals every adopted read: the source keeps the
original scope, audience and owner, and the payload must hash to its own receipt. A
domain reader adds the checks only the domain knows:

- **no credential material ever reaches a model.** A device directory or a platform
  status may legitimately carry identifiers and account state, but a token, cookie or
  password must never enter the conversation, so any such key is refused outright
  rather than filtered quietly;
- **a live cursor advances.** ``after_event_id`` exists so a stopped or restarted
  listener does not re-deliver the same events. Re-reading an event that was already
  ingested is refused, because the design forbids replaying an unknown or repeated
  external action;
- **audience text stays material.** Viewer comments are ``untrusted`` references, never
  instructions, so a result that marks them as anything else is refused.

Durable state stays in ``runtime_metadata`` under a key prefix; this slice adds no table
and no schema version.
"""

from __future__ import annotations

import json

from companion_v2.execution.models import TaskError, digest


PREFIX = "native.read."
VERSION = 1
# Keys that would put a secret into the model's context. Matched case-insensitively on
# every object key at every depth of an adopted read result.
FORBIDDEN_KEYS = frozenset({
    "token", "access_token", "refresh_token", "api_key", "apikey", "secret", "password",
    "passwd", "cookie", "cookies", "session_key", "credential", "credentials", "private_key",
    "client_secret", "auth", "authorization", "signature", "signed_url",
})
LIVE_ACTIONS = frozenset({"live.status.read", "live.events.recent"})
REALITY_ACTIONS = frozenset({"reality.snapshot.read", "reality.device.list", "reality.device.status",
                             "reality.operation.lookup"})

READ_ACTIONS = LIVE_ACTIONS | REALITY_ACTIONS
# Actions whose payload is a page of externally authored text.
UNTRUSTED_MATERIAL = frozenset({"live.events.recent"})


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")
    else:
        yield value


def _keys(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield f"{path}.{key}" if path else str(key)
            yield from _keys(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _keys(item, f"{path}[{index}]")


def check_no_credentials(value, *, action):
    """Refuse a result that would carry a token, cookie or password into the context."""
    for key in _keys(value):
        leaf = key.rsplit(".", 1)[-1].split("[")[0].strip().lower()
        if leaf in FORBIDDEN_KEYS:
            raise TaskError("native_read_credential", f"{action} returned credential material at {key}")


def check_untrusted_material(value, *, action):
    """A page of viewer text must be marked as material, never as instructions."""
    if action not in UNTRUSTED_MATERIAL:
        return
    items = value.get("events") if isinstance(value, dict) else None
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise TaskError("native_read_untrusted", "a live event must be a document")
        marker = item.get("trust")
        if marker is not None and marker != "untrusted":
            raise TaskError("native_read_untrusted",
                            f"live event {index} claims trust={marker!r}; viewer text is only material")


def event_ids(value):
    """The event ids of one live page, in the order the provider returned them."""
    if not isinstance(value, dict) or not isinstance(value.get("events"), list):
        return ()
    identifiers = []
    for item in value["events"]:
        if not isinstance(item, dict) or type(item.get("event_id")) is not str or not item["event_id"]:
            raise TaskError("native_read_untrusted", "a live event needs its own stable event id")
        identifiers.append(item["event_id"])
    return tuple(identifiers)


class NativeReadJournal:
    """Per relationship and platform: which live events were already ingested."""

    def __init__(self, runtime, *, context):
        self.runtime, self.context = runtime, context

    def key(self, platform):
        return PREFIX + "cursor:" + digest([VERSION, self.context.key, platform])

    def read(self, platform):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (self.key(platform),))
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
        except ValueError:
            return None
        return value if type(value) is dict and value.get("version") == VERSION else None

    def advance(self, platform, *, event_ids, after_event_id):
        """Record a delivered page, refusing a replayed or out-of-order cursor.

        ``after_event_id`` is what the caller asked to continue from. Re-reading an event
        that was already delivered would re-ingest the same external activity, and the
        design forbids replaying it: the page is refused instead.
        """
        seen = sorted(set(event_ids))
        if len(seen) != len(event_ids):
            raise TaskError("native_read_replayed", "a live page repeated an event id")
        current = self.read(platform) or {"version": VERSION, "delivered": [], "cursor": None}
        delivered = list(current.get("delivered") or ())
        if after_event_id is not None and after_event_id not in delivered:
            # Continuing from an id this relationship never received means the caller is
            # quoting another listener's cursor; that is a replay by another name.
            raise TaskError("native_read_replayed", "the live cursor belongs to another delivered page")
        repeated = [identifier for identifier in event_ids if identifier in delivered]
        if repeated:
            raise TaskError("native_read_replayed", "an already delivered live event cannot be ingested again")
        merged = (delivered + list(event_ids))[-256:]
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (self.key(platform), json.dumps(
                    {"version": VERSION, "delivered": merged, "cursor": event_ids[-1] if event_ids else current.get("cursor")},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
        return merged[-1] if merged else None


class NativeReadConsumer:
    """The domain reader installed for the read-only native actions.

    It checks the domain invariants and then delegates to the registry's generic sealed
    source, because a read-only result has nothing to adopt beyond that sealed original.
    """

    def __init__(self, registry):
        # The registry binds its application after construction, so read it lazily.
        self.registry = registry

    def adopt(self, invocation, native):
        """Check one adopted read, then let the generic sealed source stand."""
        action = invocation.descriptor.tool.action
        result = native.result
        check_no_credentials(result, action=action)
        check_untrusted_material(result, action=action)
        if action == "live.events.recent":
            arguments = json.loads(invocation.arguments_json)
            platform = result.get("platform")
            if type(platform) is not str or not platform.strip():
                raise TaskError("native_read_untrusted", "a live page must name the platform it came from")
            if platform != arguments.get("platform"):
                raise TaskError("native_read_untrusted", "a live page belongs to another platform")
            application = self.registry.application
            if application is None:
                raise TaskError("native_read_untrusted", "the live journal needs its bound host application")
            journal = NativeReadJournal(application.runtime, context=invocation.context)
            journal.advance(platform, event_ids=event_ids(result), after_event_id=arguments.get("after_event_id"))
        return self.registry._source_response(invocation, native)


__all__ = ["FORBIDDEN_KEYS", "LIVE_ACTIONS", "NativeReadConsumer", "NativeReadJournal", "PREFIX",
           "READ_ACTIONS", "REALITY_ACTIONS", "UNTRUSTED_MATERIAL", "VERSION", "check_no_credentials",
           "check_untrusted_material", "event_ids"]
