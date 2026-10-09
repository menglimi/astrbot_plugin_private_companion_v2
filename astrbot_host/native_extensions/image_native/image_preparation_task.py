"""Strict local preparation profile; not a replacement for public ActionRequest.

Only already resolved, explicitly selected inputs are accepted in this slice.
Identity and access are checked out of band by the host, never by these fields.
"""
from __future__ import annotations

import json
from typing import Any, Mapping


TASK_VERSION = "image.preparation.task.v1"
MASK_TASK_VERSION = "image.preparation.task.v2"
CROP_TASK_VERSION = "image.preparation.task.v3"
RESULT_VERSION = "image.preparation.result.v1"
REFERENCE_ROLES = frozenset({
    "identity", "outfit", "pose", "style", "background", "edit_source", "continuity", "edit_mask",
})


class PreparationError(ValueError):
    def __init__(self, code: str, field: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.field = field


def json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PreparationError("invalid_task") from exc


def object_fields(value: Any, required: set[str], optional: set[str], field: str) -> dict:
    if not isinstance(value, dict) or required - value.keys() or value.keys() - required - optional:
        raise PreparationError("invalid_task", field)
    return value


def text(value: Any, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or (not empty and not value.strip()):
        raise PreparationError("invalid_task", field)
    return value


def choice(value: Any, values: set[str] | frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in values:
        raise PreparationError("unsupported_feature", field)
    return value


def array(value: Any, field: str) -> list:
    if not isinstance(value, list):
        raise PreparationError("invalid_task", field)
    return value


def string_list(value: Any, field: str) -> list[str]:
    items = array(value, field)
    for item in items:
        text(item, field)
    if len(set(items)) != len(items):
        raise PreparationError("invalid_task", field)
    return items


def parse_task(payload: Mapping[str, Any]) -> dict:
    # Copy before the first await; caller mutations cannot change the prepared task.
    task = json.loads(json_bytes(payload))
    if not isinstance(task, dict):
        raise PreparationError('invalid_task', 'task')
    object_fields(task, {
        "version", "task_id", "revision", "operation", "purpose", "user_request",
        "subjects", "requirements", "inputs", "edit_source_input_id",
        "reference_policy", "allow_optional_omission", "prompt_mode", "raw_prompt",
    }, {"parameters", "edit_region"} if task.get('version') in {MASK_TASK_VERSION, CROP_TASK_VERSION} else {"parameters"}, "task")
    if "parameters" in task and not isinstance(task["parameters"], dict):
        raise PreparationError("invalid_task", "parameters")
    choice(task["version"], {TASK_VERSION, MASK_TASK_VERSION, CROP_TASK_VERSION}, "version")
    for key in ("task_id", "revision", "purpose", "user_request"):
        text(task[key], key)
    choice(task["operation"], {"generate", "edit"}, "operation")
    choice(task["reference_policy"], {"none", "specified"}, "reference_policy")
    choice(task["prompt_mode"], {"composed", "raw"}, "prompt_mode")
    if type(task["allow_optional_omission"]) is not bool:
        raise PreparationError("invalid_task", "allow_optional_omission")
    subjects: set[str] = set()
    for subject in array(task["subjects"], "subjects"):
        object_fields(subject, {"subject_id", "description", "entity_ref"}, set(), "subjects")
        sid = text(subject["subject_id"], "subject_id")
        text(subject["description"], "description")
        if subject["entity_ref"] is not None:
            text(subject["entity_ref"], "entity_ref")
        if sid in subjects:
            raise PreparationError("invalid_task", "subject_id")
        subjects.add(sid)

    def check_subjects(value: Any) -> None:
        if set(string_list(value, "subject_ids")) - subjects:
            raise PreparationError("unresolved_subject", "subject_ids")

    requirements: set[str] = set()
    for requirement in array(task["requirements"], "requirements"):
        object_fields(requirement, {"requirement_id", "subject_ids", "text", "polarity"}, set(), "requirements")
        rid = text(requirement["requirement_id"], "requirement_id")
        if rid in requirements:
            raise PreparationError("invalid_task", "requirement_id")
        requirements.add(rid)
        check_subjects(requirement["subject_ids"])
        text(requirement["text"], "requirements.text")
        choice(requirement["polarity"], {"positive", "negative"}, "polarity")
    inputs: dict[str, dict] = {}
    for item in array(task["inputs"], "inputs"):
        object_fields(item, {"input_id", "resource_ref", "usages"}, set(), "inputs")
        iid = text(item["input_id"], "input_id")
        if iid in inputs:
            raise PreparationError("invalid_task", "input_id")
        inputs[iid] = item
        resource = object_fields(item["resource_ref"], {"asset_id", "version"}, set(), "resource_ref")
        text(resource["asset_id"], "asset_id")
        text(resource["version"], "resource.version")
        usages = array(item["usages"], "usages")
        if not usages:
            raise PreparationError("invalid_task", "usages")
        for usage in usages:
            object_fields(usage, {"role", "subject_ids", "required", "preserve", "ignore"}, set(), "usages")
            choice(usage["role"], REFERENCE_ROLES, "role")
            if usage['role'] == 'edit_mask' and task['version'] not in {MASK_TASK_VERSION, CROP_TASK_VERSION}:
                raise PreparationError('unsupported_feature', 'edit_mask')
            check_subjects(usage["subject_ids"])
            if usage["role"] in {"identity", "outfit", "pose"} and not usage["subject_ids"]:
                raise PreparationError("unresolved_subject", "usages.subject_ids")
            if type(usage["required"]) is not bool:
                raise PreparationError("invalid_task", "required")
            string_list(usage["preserve"], "preserve")
            string_list(usage["ignore"], "ignore")
            if set(usage["preserve"]) & set(usage["ignore"]):
                raise PreparationError("invalid_task", "preserve")
            if task["reference_policy"] == "none" and usage["role"] not in {"edit_source", "edit_mask"}:
                raise PreparationError("invalid_task", "reference_policy")
    source = task["edit_source_input_id"]
    sources = [iid for iid, item in inputs.items()
               if any(u["role"] == "edit_source" for u in item["usages"])]
    if task["operation"] == "edit":
        if not isinstance(source, str) or sources != [source] or not any(
            u["role"] == "edit_source" and u["required"] for u in inputs[source]["usages"]
        ):
            raise PreparationError("missing_edit_source", "edit_source_input_id")
    elif source is not None or sources:
        raise PreparationError("invalid_task", "edit_source_input_id")
    if task['version'] in {MASK_TASK_VERSION, CROP_TASK_VERSION}:
        region = object_fields(task.get('edit_region'),
            {'mask_input_id', 'coordinates', 'white', 'preserve_outside'} |
            ({'processing'} if task['version'] == CROP_TASK_VERSION else set()), set(), 'edit_region')
        masks = [iid for iid, item in inputs.items() if any(u['role'] == 'edit_mask' for u in item['usages'])]
        mask_id = region['mask_input_id']
        if (task['operation'] != 'edit' or not isinstance(mask_id, str) or masks != [mask_id]
                or mask_id == source or region['coordinates'] != 'source_pixels'
                or region['white'] != 'edit' or region['preserve_outside'] is not True):
            raise PreparationError('invalid_task', 'edit_region')
        usages = inputs[mask_id]['usages']
        if (len(usages) != 1 or not usages[0]['required'] or usages[0]['subject_ids']
                or usages[0]['preserve'] or usages[0]['ignore']):
            raise PreparationError('invalid_task', 'edit_mask')
        if task['version'] == CROP_TASK_VERSION:
            processing = object_fields(region['processing'], {'crop', 'size'}, set(), 'processing')
            crop, size = processing['crop'], processing['size']
            if (not isinstance(crop, list) or len(crop) != 4
                    or any(type(v) is not int or v < 0 for v in crop) or min(crop[2:]) < 1
                    or not isinstance(size, list) or len(size) != 2
                    or any(type(v) is not int or not 64 <= v <= 4096 or v % 8 for v in size)
                    or len(inputs[source]['usages']) != 1):
                raise PreparationError('invalid_task', 'processing')
    raw = task["raw_prompt"]
    if task["prompt_mode"] == "raw":
        if task["allow_optional_omission"]:
            raise PreparationError("invalid_task", "allow_optional_omission")
        object_fields(raw, {"profile", "positive", "negative"}, set(), "raw_prompt")
        text(raw["profile"], "raw_prompt.profile")
        text(raw["positive"], "raw_prompt.positive")
        text(raw["negative"], "raw_prompt.negative", empty=True)
    elif raw is not None:
        raise PreparationError("invalid_task", "raw_prompt")
    return task
