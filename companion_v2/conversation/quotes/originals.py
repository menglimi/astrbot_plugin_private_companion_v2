"""Connect a quote to previously admitted V2 originals and confirmed deliveries."""

from dataclasses import replace
import json

from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.execution.models import TaskContext, TaskError, digest
from companion_v2.foundation.refs import ScopeKind, ScopeRef


def original_sources(messages, context, event, quote, text, at, *, publish):
    if context.scope.kind is ScopeKind.GROUP:
        from .group_originals import original_sources as group_sources
        return group_sources(messages, context, event, quote, text, at)
    # Only route metadata is enumerated. Message bodies are fetched by their
    # existing scoped-event primary key, including after a host /new session.
    from companion_v2.conversation.messages import event_from_document

    if quote.message_id == event.event_id:
        raise TaskError("quote_original_cycle", "an input cannot quote itself")
    references = []
    if quote.sender_id == event.principal.native_account_id:
        routes = messages.runtime.read_all("""SELECT record_json FROM conversation_routes
            WHERE json_extract(record_json, '$.scope.platform') = ?
            AND json_extract(record_json, '$.scope.account_id') = ?
            AND json_extract(record_json, '$.scope.native_scope_id') = ?
            AND json_extract(record_json, '$.scope.kind') = 'private'""",
            (event.scope.platform, event.scope.account_id, event.scope.native_scope_id))
        for row in routes:
            scope = ScopeRef.restore(json.loads(row["record_json"])["scope"])
            probe = InboundConversationEvent(quote.message_id, replace(event.principal, bot_id=scope.bot_id),
                scope, replace(event.source, scope=scope), event.capability, event.input_hash, event.received_at)
            original = messages.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE event_key = ?", (probe.scoped_key,))
            if original is None:
                continue
            if scope != context.scope:
                raise TaskError("quote_original_scope_mismatch", "known original belongs to another captured conversation")
            saved = event_from_document(json.loads(original["event_json"]), context)
            record = messages._read_source(saved.source, context, event.capability, at)
            if (record.payload != text or record.content_hash != saved.input_hash or getattr(saved, "quotes", ())
                    or getattr(saved, "forwards", ()) != getattr(quote, "forwards", ())):
                raise TaskError("quote_original_changed", "quote differs from the already admitted original")
            saved_audios = getattr(saved, "audios", ())
            saved_videos = getattr(saved, "videos", ())
            if (tuple(saved_audios) != getattr(quote, "audios", ())
                    or tuple(saved_videos) != getattr(quote, "videos", ())):
                raise TaskError("quote_original_changed", "quoted audio or video differs from its admitted original")
            originals = messages.images.read(context, (saved,), at)
            if (tuple(replace(i.descriptor, position=0) for i in originals)
                    != tuple(replace(i, position=0) for i in quote.images)):
                raise TaskError("quote_original_changed", "quoted images differ from the already admitted originals")
            references.extend((saved.source, *(view.source for i in originals for view in i.evidence_images)))
            if saved_audios:
                references.extend(audio.source for audio in messages.audio.read(context, (saved,), at))
            if saved_videos:
                videos = messages.videos.read(context, (saved,), at)
                references.extend(video.source for video in videos)
                references.extend(frame.source for video in videos for frame in video.frames)
            if getattr(saved, "forwards", ()):
                materials, _, _ = messages.forwards.read(context, saved, at)
                references.extend(m.source for m in materials if m.source is not None)
    else:
        platform_ref = "onebot-message:" + digest([event.scope.platform, event.scope.account_id])[:24] + ":" + quote.message_id
        rows = messages.runtime.read_all("""SELECT h.*, b.context_json, p.sequence FROM conversation_parts p
            JOIN conversation_batches b ON b.batch_id = p.batch_id
            JOIN conversation_sent_history h ON h.part_id = p.part_id
            WHERE p.platform_ref = ? AND p.state = 'delivered' LIMIT 2""", (platform_ref,))
        if len(rows) > 1:
            raise TaskError("quote_original_ambiguous", "original delivery is not unique")
        for row in rows:
            original = TaskContext.restore(json.loads(row["context_json"]))
            if original.key != context.key:
                raise TaskError("quote_original_scope_mismatch", "confirmed original belongs to another captured conversation")
            owner = messages.confirmed_reply_sources
            if owner is None:
                raise TaskError("quote_original_unavailable", "confirmed reply source owner is unavailable")
            reference = owner.reference(row)
            record = owner.materialize(context, reference) if publish else owner.validate(context, reference)
            images, manifest = messages.reply_images.for_part(row, messages.batch(row["batch_id"]), context, at)
            expected_text = record.payload + "".join("\n[图片 " + str(n) + "]\n" for n in range(1, len(images) + 1))
            if (expected_text != text or tuple(replace(i.descriptor, position=n) for n, i in enumerate(images, 1)) != quote.images
                    or getattr(quote, "forwards", ())):
                raise TaskError("quote_original_changed", "quote differs from the confirmed delivered text and images")
            references.append(reference)
            if manifest is not None:
                references.append(manifest)
    return tuple(references)
