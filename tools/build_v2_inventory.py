"""Rebuild the V2 surface inventory from the codebase itself.

Three artifacts come out of this, all from the same extraction, so none of them can
drift from the others:

* ``docs/V2_CONFIG_SURFACE_20260928.csv``  -- one row per registered field
* ``docs/V2_SURFACE_INVENTORY_20260928.md`` -- the human-readable inventory
* ``docs/V2_SURFACE_PREVIEW_20260928.html`` -- the self-contained review draft

Run it from the repository root::

    python3 tools/build_v2_inventory.py

Why a script rather than hand-maintained tables: the "already wired" figure has been
mis-stated twice, both times because a field name is built at runtime
(``"cycle_" + key + "_days"``) and a plain grep cannot see it. Anything that has to
count 320 fields needs to read the registry, not the source text.
"""

from __future__ import annotations

import ast
import collections
import csv
import importlib
import json
import os
import pkgutil
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Fields the maintainers decided not to expose. Kept here rather than inferred,
# because "no control" is not the same as "forgotten" and only a human knows which.
INTENDED_OMISSIONS = frozenset({
    # Six phase mood words: the defaults carry enough, extra inputs add no value.
    "cycle_menstrual_mood", "cycle_follicular_mood", "cycle_pre_ovulation_mood",
    "cycle_ovulation_mood", "cycle_luteal_mood", "cycle_pms_mood",
    # Mood dynamics that are hard to reason about from outside.
    "mood_cross_window", "mood_interest_window_minutes", "mood_neutral_band",
    # Saving this one revokes a grant, so it cannot be a plain switch on a page.
    "online_status_enabled",
})

# Fields built from a template, so the literal name never appears in the page source.
DYNAMIC_FAMILIES = (
    ("role.state", re.compile(r"^cycle_(menstrual|follicular|pre_ovulation|ovulation|luteal|pms)_(days|energy|prompt)$"),
     "state-maintenance.js（动态族）"),
)

# Fields whose only control lives somewhere the name check cannot key on.
BORROWED_COVERAGE = {
    "humanized_state_intensity": "app.js",
    "planning_weather_location": "perception-native-page.js",
}


# Module-level factories that take one positional argument. Calling them with the
# value the production assembly passes is the only way to see the fields they
# register; skipping them silently lost 120 model-routing fields on the first pass.
def _segmentation_policy():
    from companion_v2.conversation.segmentation import SegmentationPolicy
    return SegmentationPolicy()


def _model_profiles():
    """Every task profile the tree constructs, by (kind constant, lane)."""
    from companion_v2.execution.models import Lane
    from companion_v2.model_gateway.models import ModelTaskProfile

    found: set[tuple[str, str]] = set()
    for path in (ROOT / "companion_v2").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "ModelTaskProfile" not in text:
            continue
        dotted = str(path.relative_to(ROOT).with_suffix("")).replace(os.sep, ".")
        try:
            module = importlib.import_module(dotted)
        except Exception:
            continue
        for match in re.finditer(r"ModelTaskProfile\(\s*([A-Z_]+)\s*,\s*Lane\.(\w+)", text):
            kind = getattr(module, match.group(1), None)
            lane = getattr(Lane, match.group(2), None)
            if isinstance(kind, str) and lane is not None:
                found.add((kind, match.group(2)))
    return tuple(ModelTaskProfile(kind, getattr(Lane, lane), "default", "audit")
                 for kind, lane in sorted(found))


# Keyed by ``module:function``: one module may expose more than one provider, and the
# key identifies *which* one needs arguments rather than assuming the module has one.
PARAMETERIZED = {
    "companion_v2.conversation.reply_settings:configuration_fields": lambda: (_segmentation_policy(), True, 0.0, None),
    "companion_v2.model_gateway.routing:configuration_fields": lambda: (_model_profiles(),),
}


def _may_be_called_bare(node) -> bool:
    """Whether a function can be invoked with no arguments, defaults included.

    Counting parameters is not the same as counting *required* parameters, and the
    difference silently removed two registries: the memory policy and the image-review
    settings both take defaults, so ``f()`` works and the "no arguments" test said no.
    """
    arguments = node.args
    positional = len(arguments.posonlyargs) + len(arguments.args)
    required_positional = positional - len(arguments.defaults)
    required_keyword = sum(1 for default in arguments.kw_defaults if default is None)
    return required_positional == 0 and required_keyword == 0


def _module_functions(path: Path) -> tuple[str, ...]:
    """Module-level functions in one file whose *name* suggests a field registry.

    Candidates only, and the filter is deliberately loose. The rule this replaces
    matched the literal ``def configuration_fields``, so when the growth module split
    its skills out into ``skill_configuration_fields`` two registered fields silently
    left the inventory -- the same failure that once undercounted by 269, one rename
    later. ``absorb`` now settles membership by return type; this pass exists only so
    the script does not have to import and call every function in the tree to find out.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return ()
    module_name = str(path.relative_to(ROOT).with_suffix("")).replace(os.sep, ".")
    names = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Two ways in. A registry listed in PARAMETERIZED needs arguments by design and
        # is named there. Everything else must be callable bare; a factory the caller
        # has to feed is not something this script can guess, and pretending otherwise
        # would put invented defaults into the inventory.
        listed = f"{module_name}:{node.name}" in PARAMETERIZED
        if not listed and not _may_be_called_bare(node):
            continue
        lowered = node.name.lower()
        if listed or "field" in lowered or "configuration" in lowered:
            names.append(node.name)
    return tuple(names)


def _describe(definition, source: str) -> dict:
    group = (definition.group_id.value if hasattr(definition.group_id, "value")
             else str(definition.group_id))
    default = definition.default
    return {
        "group": group,
        "short": definition.field_id[len(group) + 1:],
        "consumer": definition.consumer_id,
        "owner": definition.owner_id,
        "kind": definition.kind.value,
        "default": default if isinstance(default, (str, int, float, bool)) else "",
        "layers": "/".join(layer.value if hasattr(layer, "value") else str(layer)
                           for layer in definition.layers),
        "apply": (definition.apply_mode.value if hasattr(definition.apply_mode, "value")
                  else str(definition.apply_mode)),
        "source": source,
    }


def load_registry() -> tuple[dict[str, dict], list[str]]:
    """Read every registered field, and report providers that refused to answer.

    Returning the failures matters: an extraction that silently skips a module is
    indistinguishable from a module with no fields, and that is how the first
    inventory undercounted by 269.
    """
    sys.path.insert(0, str(ROOT))
    try:
        import stub_astrbot  # noqa: F401  present only inside the sandbox
    except ImportError:
        pass
    import companion_v2
    # Imported here, not at module scope: outside the sandbox this module has to stay
    # importable so the script can report the missing stub instead of failing on import.
    from collections.abc import Iterable

    from companion_v2.configuration.registry import FieldDefinition

    fields: dict[str, dict] = {}
    skipped: list[str] = []
    contributed: dict[str, int] = {}

    def absorb(module_name: str, function_name: str) -> None:
        """Call one candidate provider and keep whatever fields it declares.

        A provider is recognised by what it *returns*, not by what it is called. The
        name-based rule this replaces matched the literal ``def configuration_fields``
        and so walked straight past ``skill_configuration_fields`` in the growth
        module: two registered fields that had never once appeared in the inventory.
        """
        try:
            imported = importlib.import_module(module_name)
        except Exception as error:
            skipped.append(f"{module_name}: import failed ({error})")
            return
        factory = getattr(imported, function_name, None)
        if not callable(factory):
            return
        key = f"{module_name}:{function_name}"
        try:
            arguments = PARAMETERIZED[key]() if key in PARAMETERIZED else ()
            produced = factory(*arguments)
        except Exception as error:
            skipped.append(f"{key}: call failed ({error})")
            return
        if isinstance(produced, (str, bytes)) or not isinstance(produced, Iterable):
            return
        rows = tuple(produced)
        if not rows or not all(isinstance(item, FieldDefinition) for item in rows):
            return
        added = 0
        for definition in rows:
            # Registry duplicates are a real code smell, not a counting artefact.
            if definition.field_id in fields:
                continue
            fields[definition.field_id] = _describe(definition, module_name)
            added += 1
        contributed[key] = added

    # Collect by discovery, never by a hand-kept list. ``_module_functions`` nominates
    # candidates by name; ``absorb`` settles the question by calling them and checking
    # the return type, so an oddly named provider and a second provider inside one module
    # are both picked up without an edit here.
    declared: set[str] = set()
    for root in (ROOT / "companion_v2", ROOT / "astrbot_host"):
        for path in root.rglob("*.py"):
            module_name = str(path.relative_to(ROOT).with_suffix("")).replace(os.sep, ".")
            for function_name in _module_functions(path):
                declared.add(f"{module_name}:{function_name}")

    for key in sorted(declared):
        module_name, function_name = key.rsplit(":", 1)
        absorb(module_name, function_name)

    # A candidate that answered with field rows but contributed none of them is a
    # duplicate registration: the ids were already claimed by another provider. That is
    # a fact worth printing, not a reason to stop the build, so it stays out of
    # ``skipped``. A candidate that answered with something other than field rows was
    # never a provider and is dropped without comment.
    duplicates = sorted(key for key, added in contributed.items() if not added)
    return fields, sorted(skipped), duplicates


def load_pages() -> dict[str, str]:
    corpus = {}
    for path in (ROOT / "pages").rglob("*"):
        if path.suffix in (".js", ".html", ".css") and path.is_file():
            try:
                corpus[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8")
            except OSError:
                pass
    return corpus


def pages_for(short: str, corpus: dict[str, str]) -> list[str]:
    """Where a field's control lives, tolerating the three shapes a name takes.

    A short name appears as a quoted string in a field list, as a bare or quoted
    object key, or as a computed key suffix. Missing any of those is how a wired
    field gets reported as missing.
    """
    tail = short.split(".")[-1]
    patterns = (
        r"['\"]" + re.escape(short) + r"['\"]",
        r"\b" + re.escape(tail) + r"\s*:",
        r"['\"]" + re.escape(tail) + r"['\"]",
    )
    return sorted(path for path, text in corpus.items()
                  if any(re.search(pattern, text) for pattern in patterns))


def classify(field_id: str, meta: dict, corpus: dict[str, str]) -> tuple[str, str]:
    """Return (state, where) with exactly one state per field.

    The order matters: an intended omission outranks a detection, because the six
    ``cycle_*_mood`` fields are both built by the page template *and* deliberately
    left as read-only. Counting them twice is what makes a tally stop adding up.
    """
    short = meta["short"]
    if short in INTENDED_OMISSIONS:
        return "intended", "有意不接（不设控件）"
    if short in BORROWED_COVERAGE:
        return "covered", BORROWED_COVERAGE[short]
    for group, pattern, note in DYNAMIC_FAMILIES:
        if meta["group"] == group and pattern.match(short):
            return "covered", note
    found = pages_for(short, corpus)
    return ("covered", "; ".join(found)) if found else ("missing", "")


def load_routes() -> list[tuple[str, str]]:
    routes = set()
    for path in sorted((ROOT / "astrbot_host").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.Return)):
                continue
            elements = node.value.elts if isinstance(node.value, (ast.Tuple, ast.List)) else None
            for item in elements or []:
                if not (isinstance(item, ast.Tuple) and len(item.elts) >= 3):
                    continue
                first = item.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    routes.add((path.name, first.value))
                elif (isinstance(first, ast.BinOp) and isinstance(first.op, ast.Add)
                      and isinstance(first.left, ast.Name) and isinstance(first.right, ast.Constant)):
                    routes.add((path.name, f"{first.left.id} + {first.right.value!r}"))
    return sorted(routes)


def load_tables() -> list[str]:
    tables = set()
    for path in (ROOT / "companion_v2" / "storage").rglob("*.py"):
        tables |= set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)",
                                 path.read_text(encoding="utf-8")))
    return sorted(tables)


def load_plugin_schema() -> dict[str, dict]:
    """The AstrBot plugin config leaves, which are a *separate* surface from the registry.

    Two different mechanisms hold operator settings: the registry (role/window scoped,
    read back through the configuration service) and ``_conf_schema.json`` (plugin
    install scoped, read by AstrBot itself). A count that names only one of them is
    wrong, and merging them into one list hides which mechanism a setting uses.
    """
    path = ROOT / "_conf_schema.json"
    if not path.exists():
        return {}
    schema = json.loads(path.read_text(encoding="utf-8"))
    leaves: dict[str, dict] = {}

    def walk(node, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        for name, spec in node.items():
            full = f"{prefix}.{name}" if prefix else name
            if not isinstance(spec, dict):
                continue
            if spec.get("type") == "object":
                walk(spec.get("items", {}), full)
            elif "type" in spec:
                leaves[full] = {"kind": spec.get("type", ""),
                                "default": spec.get("default", ""),
                                "description": (spec.get("description") or "").split("\n")[0][:120]}
            else:
                walk(spec, full)

    walk(schema, "")
    return leaves


def main() -> int:
    fields, skipped, duplicates = load_registry()
    plugins = load_plugin_schema()
    corpus = load_pages()
    routes = load_routes()
    tables = load_tables()

    rows = []
    for field_id, meta in sorted(fields.items()):
        state, where = classify(field_id, meta, corpus)
        rows.append({**meta, "field_id": field_id, "state": state, "where": where})

    out = ROOT / "docs" / "V2_CONFIG_SURFACE_20260928.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        # The repo contract is LF; csv defaults to CRLF and would rewrite every line.
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["field_id", "group", "short", "kind", "layers", "apply", "owner",
                         "consumer", "default", "source", "state", "where"])
        for row in rows:
            writer.writerow([row["field_id"], row["group"], row["short"], row["kind"],
                             row["layers"], row["apply"], row["owner"], row["consumer"],
                             row["default"], row["source"], row["state"], row["where"]])

    plugin_out = ROOT / "docs" / "V2_PLUGIN_CONFIG_20260928.csv"
    with plugin_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["path", "kind", "default", "description"])
        for path, meta in sorted(plugins.items()):
            writer.writerow([path, meta["kind"], meta["default"], meta["description"]])

    tally = collections.Counter(row["state"] for row in rows)
    per_group = collections.defaultdict(collections.Counter)
    for row in rows:
        per_group[row["group"]][row["state"]] += 1

    print(f"registry {len(fields)}  covered={tally['covered']} "
          f"missing={tally['missing']} intended={tally['intended']}")
    print(f"plugin   {len(plugins)}")
    print(f"total    {len(fields) + len(plugins)}")
    print(f"routes   {len(routes)}")
    print(f"tables   {len(tables)}")
    for note in skipped:
        print(f"SKIPPED  {note}")
    for name in duplicates:
        print(f"DUPLICATE {name}: every field already registered elsewhere")
    print(f"wrote    {out.relative_to(ROOT)}")
    print(f"wrote    {plugin_out.relative_to(ROOT)}")

    # A tally that does not add up means two states overlapped, which is exactly the
    # mistake this script exists to prevent.
    assert sum(tally.values()) == len(fields)
    assert set(tally) <= {"covered", "missing", "intended"}
    # An unaccounted provider means the total is a guess. Fail instead of printing one.
    assert not skipped, f"providers unaccounted for: {skipped}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
