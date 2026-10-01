"""Revalidate group originals and expose only metadata for historical attachments."""

import json

from companion_v2.execution.models import TaskError, digest


def _forward_history(materials):
    roots, nodes = {}, {}
    for material in materials:
        if material.source is None:
            continue
        if material.purpose.startswith("forwarded_records:"):
            roots[material.contribution_id] = json.loads(material.payload)
        elif material.purpose.startswith("forwarded_node:"):
            root_id = material.purpose.split(":", 1)[1]
            nodes.setdefault(root_id, []).append(json.loads(material.payload))
    return [{**payload, "nodes": sorted(nodes.get(root_id, ()), key=lambda item: tuple(item["node_path"]))}
            for root_id, payload in roots.items()]


def input_media(messages, context, event, record, at):
    images, quotes, forwards = (getattr(event, "images", ()), getattr(event, "quotes", ()),
                                getattr(event, "forwards", ()))
    expected = digest([record.payload, images]) if images else digest(record.payload)
    for field in ("audios", "videos"):
        if manifest := getattr(event, field, ()):
            expected = digest([expected, manifest])
    if quotes:
        expected = digest([expected, quotes])
    if forwards:
        expected = digest([expected, forwards])
    if expected != event.input_hash:
        raise TaskError("group_input_changed", "group input body and attachments differ from their original fingerprint")
    sources, attachments, quotations, forward_materials = [], [], [], []
    if images:
        for image in messages.images.read(context, (event,), at):
            attachments.append({**json.loads(messages.images.metadata(event, image.descriptor)),
                                "view": "historical_metadata_only"})
            sources.extend(view.source for view in image.evidence_images)
    if getattr(event, "audios", ()):
        for audio in messages.audio.read(context, (event,), at):
            attachments.append({**json.loads(messages.audio.metadata(event, audio.descriptor)),
                                "view": "historical_metadata_only"})
            sources.append(audio.source)
    if getattr(event, "videos", ()):
        for video in messages.videos.read(context, (event,), at):
            attachments.append({**json.loads(messages.videos.metadata(event, video.descriptor)),
                                "view": "historical_metadata_only"})
            sources.append(video.source)
            sources.extend(frame.source for frame in video.frames)
    if quotes:
        materials, originals, _, _, _ = messages.quotes.read_all(context, event, at)
        for material in materials:
            if material.source is not None:
                sources.append(material.source)
            if material.purpose.startswith("quoted_message:"):
                quotations.append(json.loads(material.payload))
            elif material.purpose.startswith(("quoted_image:", "quoted_audio:", "quoted_video:")):
                attachments.append({**json.loads(material.payload), "view": "historical_metadata_only"})
        forward_materials.extend(materials)
        sources.extend(view.source for image in originals for view in image.evidence_images)
    if forwards:
        materials, originals, _, _, _ = messages.forwards.read_all(context, event, at)
        forward_materials.extend(materials)
        sources.extend(material.source for material in materials if material.source is not None)
        sources.extend(view.source for image in originals for view in image.evidence_images)
    attachments.extend({**json.loads(material.payload), "view": "historical_metadata_only"}
                       for material in forward_materials
                       if material.purpose.startswith(("forwarded_image:", "forwarded_audio:", "forwarded_video:")))
    forwarded_records = _forward_history(forward_materials)
    return ({**({"attachments": attachments} if attachments else {}),
             **({"quotations": quotations} if quotations else {}),
             **({"forwarded_records": forwarded_records} if forwarded_records else {})},
            tuple(dict.fromkeys(sources)))
