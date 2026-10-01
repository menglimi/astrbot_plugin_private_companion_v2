"""Publish returned nodes and their media atomically under the outer private input."""

from dataclasses import replace

from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.dependencies import link
from companion_v2.sources.models import SourceRecord

from .models import (CapturedForward, ForwardDescriptor, ForwardNodeDescriptor, ForwardNodeMediaDescriptor,
                     ForwardImageEvent, OWNER, NODE_OWNER)


def forward_reference(parent, position):
    identifier = "input-forward-" + digest([parent, position])
    return SourceRef(identifier, OWNER, parent.scope, VersionRef(identifier, 1), parent.issued_at, parent.expires_at)


def node_reference(parent, path):
    identifier = "forward-node-" + digest([parent, path])
    return SourceRef(identifier, NODE_OWNER, parent.scope, VersionRef(identifier, 1), parent.issued_at, parent.expires_at)


def prepare_forward(sources, parent, audience, captured):
    if type(captured) is not CapturedForward:
        raise TaskError("forward_manifest_invalid", "forward publication needs an immutable capture")
    root = forward_reference(parent, captured.position)
    descriptors, records = [], []
    for node in captured.nodes:
        reference = node_reference(root, node.path)
        images = tuple(i.descriptor for i in node.images)
        audios = tuple(i.descriptor for i in getattr(node, "audios", ()))
        videos = tuple(i.descriptor for i in getattr(node, "videos", ()))
        original = digest([node.path, node.resource_hash, node.sender_id, node.sender_name, node.sent_at, node.text, images])
        if audios or videos:
            original = digest([original, audios, videos])
        body = sources.prepare_message(SourceRecord(reference, audience, original, node.text))
        # Redact each text field separately, retaining keyed conflicts even if
        # only the display name contains a credential. Never redact encoded JSON.
        name = sources.prepare_message(SourceRecord(reference, audience, original, node.sender_name))
        body = replace(body, content_hash=digest([body.content_hash, name.content_hash]))
        values = (node.path, node.resource_hash, node.sender_id, name.payload,
                  node.sent_at, body.content_hash, digest(body.payload), len(body.payload), images)
        descriptors.append(ForwardNodeMediaDescriptor(*values, audios=audios, videos=videos)
                           if audios or videos else ForwardNodeDescriptor(*values))
        records.append(body)
    return ForwardDescriptor(captured.position, captured.resource_hash, tuple(descriptors)), tuple(records)


class ConversationForwards:
    def __init__(self, messages):
        self.messages, self.runtime = messages, messages.runtime

    @staticmethod
    def image_event(event, forward, node):
        root = forward_reference(event.source, forward.position)
        return ForwardImageEvent(event.event_id, event.principal, event.scope, node_reference(root, node.path),
            event.capability, node.content_hash, event.received_at, event.runtime_scope,
            node.images, node.path, node.sender_id, getattr(event, "original_sender", None),
            getattr(event, "original_message_id", None))

    @staticmethod
    def audio_event(event, forward, node):
        from .media_events import ForwardAudioEvent
        root = forward_reference(event.source, forward.position)
        return ForwardAudioEvent(event.event_id, event.principal, event.scope, node_reference(root, node.path),
            event.capability, node.content_hash, event.received_at, event.runtime_scope,
            audios=tuple(node.audios), node_path=node.path,
            displayed_sender=node.sender_id, displayed_name=node.sender_name,
            original_forwarder=event.forward_attribution["forwarded_by"],
            quoted_message_id=getattr(event, "original_message_id", None))

    @staticmethod
    def video_event(event, forward, node):
        from .media_events import ForwardVideoEvent
        root = forward_reference(event.source, forward.position)
        return ForwardVideoEvent(event.event_id, event.principal, event.scope, node_reference(root, node.path),
            event.capability, node.content_hash, event.received_at, event.runtime_scope,
            videos=tuple(node.videos), node_path=node.path,
            displayed_sender=node.sender_id, displayed_name=node.sender_name,
            original_forwarder=event.forward_attribution["forwarded_by"],
            quoted_message_id=getattr(event, "original_message_id", None))

    @staticmethod
    def metadata(event, forward):
        return encode({**event.forward_attribution, "position": forward.position,
            "resource_hash": forward.resource_hash, "manifest_hash": digest(forward),
            "node_paths": [n.path for n in forward.nodes], "coverage": "returned_nodes",
            "original_audience": "unknown", "forwarding_source_id": event.source.source_id})

    def _parent(self, context, event, at):
        self.messages.authorize(context, at)
        parent = self.messages._read_source(event.source, context, event.capability, at)
        if event.principal != context.actor.principal or parent.content_hash != event.input_hash:
            raise TaskError("forward_owner_mismatch", "forward snapshot must retain its outer input and participant")

    def publish(self, context, event, captured):
        if not isinstance(captured, tuple) or len(captured) != len(event.forwards):
            raise TaskError("forward_manifest_invalid", "forward capture does not match its input")
        with self.runtime.transaction():
            at = self.messages.tasks.now()
            self._parent(context, event, at)
            for item, expected in zip(captured, event.forwards):
                descriptor, records = prepare_forward(self.messages.sources, event.source, context.audience, item)
                if descriptor != expected:
                    raise TaskError("forward_content_changed", "forward cannot replace its admitted node manifest")
                reference = forward_reference(event.source, descriptor.position)
                payload = self.metadata(event, descriptor)
                require(self.messages.sources.publish(SourceRecord(reference, context.audience, digest(payload), payload),
                                                      observed_at=event.received_at))
                link(self.runtime, reference, (event.source,), at)
                for node, original, record in zip(descriptor.nodes, item.nodes, records):
                    require(self.messages.sources.publish(record, observed_at=event.received_at))
                    parent = node_reference(reference, node.path[:-2]) if len(node.path) > 1 else reference
                    link(self.runtime, record.reference, (parent,), at)
                    if original.images:
                        self.messages.images.publish(context, self.image_event(event, descriptor, node), original.images)
                    if getattr(original, "audios", ()):
                        self.messages.audio.publish(context, self.audio_event(event, descriptor, node), original.audios)
                    if getattr(original, "videos", ()):
                        self.messages.videos.publish(context, self.video_event(event, descriptor, node), original.videos)

    def read(self, context, event, at):
        contributions, images, positions, audios, videos = self.read_all(context, event, at)
        return contributions, images, positions

    def read_all(self, context, event, at):
        contributions, images, positions, audios, videos = [], [], {}, [], []
        with self.runtime.read_snapshot():
            self._parent(context, event, at)
            for forward in event.forwards:
                root = forward_reference(event.source, forward.position)
                record = self.messages._read_source(root, context, event.capability, at)
                payload = self.metadata(event, forward)
                if record.payload != payload or record.content_hash != digest(payload):
                    raise TaskError("forward_content_changed", "forward manifest differs from the original")
                contributions.append(ContextContribution(root.source_id, OWNER, "forwarded_records:" + event.source.source_id,
                    ContributionState.READY, payload, root, True))
                for node in forward.nodes:
                    reference = node_reference(root, node.path)
                    record = self.messages._read_source(reference, context, event.capability, at)
                    if (record.content_hash != node.content_hash or digest(record.payload) != node.text_hash
                            or len(record.payload) != node.text_size):
                        raise TaskError("forward_content_changed", "node text differs from its original")
                    metadata_value = {"text": record.payload, "node_path": node.path, "position": forward.position,
                        "displayed_sender": node.sender_id, "displayed_name": node.sender_name,
                        "displayed_time_unix": node.sent_at, "attribution": "forward_record_claim",
                        **event.forward_attribution, "original_audience": "unknown",
                        "parent_source_id": (node_reference(root, node.path[:-2]) if len(node.path) > 1 else root).source_id}
                    if getattr(node, "audios", ()):
                        metadata_value["audio_components"] = node.audios
                    if getattr(node, "videos", ()):
                        metadata_value["video_components"] = node.videos
                    metadata = encode(metadata_value)
                    contributions.append(ContextContribution(reference.source_id, NODE_OWNER, "forwarded_node:" + root.source_id,
                        ContributionState.READY, metadata, reference, True))
                    positions[reference] = (forward.position, *node.path)
                    if node.images:
                        parent = self.image_event(event, forward, node)
                        originals = self.messages.images.read(context, (parent,), at)
                        for image in originals:
                            contributions.extend(self.messages.images.contributions(parent, image, purpose="forwarded_image:"))
                        images.extend(originals)
                    if getattr(node, "audios", ()):
                        parent = self.audio_event(event, forward, node)
                        originals = self.messages.audio.read(context, (parent,), at)
                        for audio in originals:
                            contributions.append(self.messages.audio.contribution(parent, audio, purpose="forwarded_audio"))
                        audios.extend(originals)
                    if getattr(node, "videos", ()):
                        parent = self.video_event(event, forward, node)
                        originals = self.messages.videos.read(context, (parent,), at)
                        for video in originals:
                            contributions.extend(self.messages.videos.contributions(parent, video, purpose="forwarded_video"))
                        videos.extend(originals)
        return tuple(contributions), tuple(images), positions, tuple(audios), tuple(videos)
