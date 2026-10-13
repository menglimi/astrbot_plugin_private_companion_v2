"""Album projection of images accepted through AstrBot's native tool ledger."""

import json

from companion_v2.execution.models import TaskError
from companion_v2.conversation.messages import source_from_document
from companion_v2.conversation.native_tool_results import PREFIX, operation_row
from companion_v2.conversation.native_tool_media import read_native_images


def images(owner, row, context, at):
    external = owner.messages.tools.external
    result, material = external.snapshot(row, context, at)
    if result["state"] != "succeeded" or material is None:
        return ()
    from companion_v2.conversation.external_tools import _SourceAccess
    descriptor = external._descriptor(row)
    return read_native_images(owner.messages, context, material.source, row["action"], row.get("images", []),
        capability=descriptor.binding.capability, authorizer=_SourceAccess(external, descriptor, context), at=at)


def _selection(owner, context):
    from .generated import IMAGE_ACTIONS
    return ("""FROM runtime_metadata m JOIN execution_tasks t ON t.task_id = json_extract(m.value, '$.task_id')
        WHERE substr(m.key, 1, ?) = ? AND json_extract(m.value, '$.origin_key') = ?
        AND json_extract(m.value, '$.action') IN (?,?,?)""", (len(PREFIX), PREFIX, context.key, *sorted(IMAGE_ACTIONS)))


def page(owner, context, at, *, before=None, limit=24):
    from .generated import GeneratedAlbumImage
    selection, values = _selection(owner, context)
    selection += " AND json_extract(m.value, '$.state') = 'succeeded'"
    if before is not None:
        selection += " AND (t.created_at < ? OR (t.created_at = ? AND json_extract(m.value, '$.invocation_id') <= ?))"
        values += (before["created_at"], before["created_at"], before["invocation_id"])
    rows = owner.runtime.read_all("SELECT json_extract(m.value, '$.invocation_id') AS invocation_id " + selection
        + " ORDER BY t.created_at DESC, invocation_id DESC LIMIT 128", values)
    items = []
    for selected in rows:
        row = operation_row(owner.runtime, selected["invocation_id"])
        try:
            captured = images(owner, row, context, at)
        except TaskError:
            continue
        parent = source_from_document(json.loads(row["result_source_json"]))
        for image in captured:
            if before is not None and (row["created_at"], row["invocation_id"], image.descriptor.position) >= (
                    before["created_at"], before["invocation_id"], before["position"]):
                continue
            items.append(GeneratedAlbumImage("generated-image:" + row["invocation_id"] + ":" + str(image.descriptor.position),
                row["created_at"], row["action"], image.descriptor, image.content, parent=parent))
        if len(items) > limit:
            break
    return items, len(rows) == 128


def image(owner, context, at, invocation_id, position):
    from .generated import GeneratedAlbumImage, IMAGE_ACTIONS
    row = operation_row(owner.runtime, invocation_id)
    if row is None or row["origin_key"] != context.key or row["action"] not in IMAGE_ACTIONS:
        raise TaskError("generated_image_missing", "the native album image is unavailable")
    for captured in images(owner, row, context, at):
        if captured.descriptor.position == position:
            parent = source_from_document(json.loads(row["result_source_json"]))
            return GeneratedAlbumImage("generated-image:" + invocation_id + ":" + str(position),
                row["created_at"], row["action"], captured.descriptor, captured.content, parent=parent)
    raise TaskError("generated_image_missing", "the native album image is unavailable")


def diagnostics(owner, context, *, limit):
    selection, values = _selection(owner, context)
    count = owner.runtime.read_one("SELECT COUNT(*) AS total " + selection, values)
    rows = owner.runtime.read_all("SELECT json_extract(m.value, '$.invocation_id') AS invocation_id " + selection
        + " ORDER BY t.created_at DESC, invocation_id DESC LIMIT ?", (*values, limit))
    return int(count["total"]), [operation_row(owner.runtime, row["invocation_id"]) for row in rows]
