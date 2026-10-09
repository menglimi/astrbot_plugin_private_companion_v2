"""Use-then-de-prioritise rotation over one scope's adopted expression rules.

Adoption used to be order-only: the reply context pinned the eight
most-recently-adopted rules, so a role with twenty adopted rules repeated the
same handful forever and the rest were learned but never used.

The mechanism is taken from the V1 dream-fragment pool
(``astrbot_plugin_private_companion/dreaming.py:325`` effective weight,
``:442`` weighted unique sampling), adapted to one ordered, replayable read:

* each adopted rule keeps ``injections`` and ``last_injected_at``;
* a rule that was never used outranks any used rule, so every new rule gets its
  first turn instead of waiting behind favourites;
* a used rule's weight is ``pow(0.72, waited_hours / 24)`` -- the V1 decay --
  times a frequency factor ``4 / (4 + injections)`` with a small floor, so a rule
  that keeps being drawn becomes less likely each time without ever being locked
  out of the rotation;
* selection is a weighted sample without replacement, which spreads turns
  across the whole pool instead of always taking the top few;
* ``MIN_EFFECTIVE_WEIGHT`` is zero by default: "used often" lowers the chance
  but never removes a rule the operator adopted, and the caller bounds the
  sample size so the per-turn read stays fixed.

The sample is drawn once at capture time with an explicit seed and stored in the
sealed snapshot, so re-reading a turn reproduces exactly the same rules.
"""

from datetime import datetime
import json
import random

from companion_v2.execution.models import digest, stamp


PREFIX = "role.expression.rotation.v1:"
DECAY_PER_DAY = 0.72
UNUSED_WEIGHT = 5.0
FREQUENCY_HALF_LIFE = 4.0
FREQUENCY_FLOOR = 0.05
# Zero by default: "used often" lowers the chance, it never removes a rule the
# operator adopted. Raise it only to drop rules that have gone cold entirely.
MIN_EFFECTIVE_WEIGHT = 0.0


def _entry(value):
    """Return ``(scope_key, injections, last_injected_at)``; damage reads as unused."""
    try:
        document = json.loads(value)
    except (TypeError, ValueError):
        return None
    if type(document) is not dict or set(document) != {
            "signal_id", "scope_key", "injections", "last_injected_at"}:
        return None
    scope_key, injections, raw = document["scope_key"], document["injections"], document["last_injected_at"]
    if type(scope_key) is not str or type(injections) is not int or injections < 0:
        return None
    if raw is None:
        return scope_key, injections, None
    if type(raw) is not str:
        return None
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return (scope_key, injections, last) if last.tzinfo is not None else None


def metadata_key(owner_key, scope_key, signal_id):
    return PREFIX + digest([owner_key, scope_key, signal_id])


def usage(runtime, owner_key, scope_key):
    """One read of every counter for a scope, keyed by signal identifier."""
    result = {}
    rows = runtime.read_all("SELECT key, value FROM runtime_metadata WHERE key LIKE ?", (PREFIX + "%",))
    for row in rows:
        try:
            identifier = json.loads(row["value"])["signal_id"]
        except (TypeError, ValueError, KeyError):
            continue
        if type(identifier) is not str:
            continue
        if not row["key"].endswith(digest([owner_key, scope_key, identifier])):
            continue
        entry = _entry(row["value"])
        if entry is None or entry[0] != scope_key:
            continue
        result[identifier] = (entry[1], entry[2])
    return result


def effective_weight(entry, *, at):
    """V1's shape: an unused rule is fresh, a used rule decays, and use counts.

    ``pow(0.72, waited_days)`` is the V1 dream-fragment decay
    (``dreaming.py:330``) applied to "time since last used". The frequency factor
    is V1's ``usage_count`` saturation: a rule drawn ``n`` times has roughly
    ``4 / (4 + n)`` of the chance, so favourites fade instead of dominating and no
    adopted rule is ever locked out.
    """
    injections, last = entry
    if last is None:
        return UNUSED_WEIGHT
    waited_hours = max(0.0, (at - last).total_seconds() / 3600.0)
    frequency = FREQUENCY_HALF_LIFE / (FREQUENCY_HALF_LIFE + max(0, injections))
    return pow(DECAY_PER_DAY, waited_hours / 24.0) * max(FREQUENCY_FLOOR, frequency)


def _rank(candidates, *, usage_map, at):
    """Least recently used first, then by how often, then by identifier.

    Note this is the rotation order, not the selection weight: for rotation the
    rule waiting longest should be offered first, while the sampling weight below
    decides how likely each rule is to be drawn.
    """
    ranked = []
    for signal_id, run_id in candidates:
        injections, last = usage_map.get(signal_id, (0, None))
        waited = float("inf") if last is None else max(0.0, (at - last).total_seconds() / 3600.0)
        ranked.append((-waited, injections, signal_id, run_id))
    return tuple(sorted(ranked))


def order(candidates, *, usage_map, at, decay_hours):
    """Deterministic full ordering, most deserving first; used by review and tests.

    ``decay_hours`` names the operator-visible recovery window: how long a used
    rule stays behind the others before it is a fair pick again. The decay curve
    itself is the V1 constant, so this only documents the window the operator
    configures; the ordering below already reflects it through ``last_injected_at``.
    """
    del decay_hours
    return tuple((signal_id, run_id) for _, _, signal_id, run_id
                 in _rank(candidates, usage_map=usage_map, at=at))


def sample(candidates, *, usage_map, at, count, seed):
    """Weighted sample without replacement, seeded so a turn stays replayable."""
    remaining = [(signal_id, run_id) for _, _, signal_id, run_id
                 in _rank(candidates, usage_map=usage_map, at=at)]
    picked = []
    generator = random.Random(digest(["expression-style-rotation.v1", seed]))
    while remaining and len(picked) < max(0, count):
        eligible = [(item, effective_weight(usage_map.get(item[0], (0, None)), at=at)) for item in remaining]
        eligible = [(item, weight) for item, weight in eligible if weight >= MIN_EFFECTIVE_WEIGHT]
        if not eligible:
            break
        chosen = generator.choices([item for item, _ in eligible], weights=[weight for _, weight in eligible], k=1)[0]
        picked.append(chosen)
        remaining = [item for item in remaining if item[0] != chosen[0]]
    return tuple(picked)


def record(runtime, *, owner_key, scope_key, signal_ids, at, connection=None):
    """Count one confirmed injection per rule, optionally inside its receipt transaction."""
    if not signal_ids:
        return
    moment = stamp(at)
    def write(active_connection):
        for signal_id in sorted(set(signal_ids)):
            key = metadata_key(owner_key, scope_key, signal_id)
            row = active_connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
            entry = _entry(row["value"]) if row is not None else None
            injections = entry[1] if entry is not None and entry[0] == scope_key else 0
            active_connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, json.dumps({"signal_id": signal_id, "scope_key": scope_key,
                                  "injections": injections + 1, "last_injected_at": moment},
                                 ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
    if connection is not None:
        write(connection)
    else:
        with runtime.transaction() as active_connection:
            write(active_connection)
