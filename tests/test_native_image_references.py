"""Invocation-bound reference release for optional native image providers."""

import json
from types import SimpleNamespace as NS
import unittest

from astrbot_host.native_extensions.images import ImageReferenceLease
from companion_v2.execution.models import TaskError
from companion_v2.conversation.external_tools import ExternalToolExecutor
from companion_v2.foundation.refs import ScopeKind


def lease_for(action, arguments, tickets, recheck):
    lease = ImageReferenceLease.__new__(ImageReferenceLease)
    lease.invocation = NS(descriptor=NS(tool=NS(action=action)), arguments_json=json.dumps(arguments))
    lease.messages = object()
    lease.registry = NS(now=lambda: "checked-now")
    lease._tickets = list(tickets)
    lease._by_handle = {ticket["reference_handle"]: ticket for ticket in tickets}
    lease._used = []
    lease._recheck = recheck
    return lease


class NativeImageReferenceTests(unittest.TestCase):
    def tickets(self):
        return [{"reference_handle": "source-handle", "reference_id": "source-id", "content_hash": "a" * 64,
                 "position": 0, "used": False, "image": NS(content=b"source-bytes")},
                {"reference_handle": "mask-handle", "reference_id": "mask-id", "content_hash": "b" * 64,
                 "position": 1, "used": False, "image": NS(content=b"mask-bytes")}]

    def test_mask_sources_are_position_role_hash_bound_and_single_use(self):
        checked = []
        tickets = self.tickets()
        lease = lease_for("image.mask_edit", {"source_index": 0, "mask_index": 1}, tickets,
                          lambda ticket, at: checked.append((ticket["reference_handle"], at)))
        with self.assertRaises(TaskError) as wrong_role:
            lease.fetch("source-handle", "a" * 64, role="edit_mask")
        self.assertEqual(wrong_role.exception.code, "reference_binding_mismatch")
        with self.assertRaises(TaskError) as wrong_hash:
            lease.fetch("source-handle", "0" * 64, role="edit_source")
        self.assertEqual(wrong_hash.exception.code, "reference_binding_mismatch")
        self.assertEqual(lease.fetch("source-handle", "a" * 64, role="edit_source"), b"source-bytes")
        self.assertEqual(lease.fetch("mask-handle", "b" * 64, role="edit_mask"), b"mask-bytes")
        with self.assertRaises(TaskError) as replay:
            lease.fetch("source-handle", "a" * 64, role="edit_source")
        self.assertEqual(replay.exception.code, "reference_handle_consumed")
        self.assertEqual(checked, [("source-handle", "checked-now"), ("mask-handle", "checked-now")])

    def test_revoked_reference_is_rechecked_before_any_bytes_are_returned(self):
        tickets = self.tickets()
        lease = lease_for("image.edit", {"prompt": "edit"}, tickets,
            lambda ticket, at: (_ for _ in ()).throw(TaskError("message_withdrawn", "image withdrawn")))
        with self.assertRaises(TaskError) as revoked:
            lease.fetch("source-handle", "a" * 64, role="edit_source")
        self.assertEqual(revoked.exception.code, "message_withdrawn")
        self.assertTrue(tickets[0]["used"])

    def test_edit_reference_roles_follow_explicit_positions(self):
        tickets = self.tickets()
        lease = lease_for("image.edit", {"reference_roles": ["identity", "outfit"]}, tickets,
                          lambda ticket, at: None)
        self.assertEqual(lease.fetch("source-handle", "a" * 64, role="identity"), b"source-bytes")
        self.assertEqual(lease.fetch("mask-handle", "b" * 64, role="outfit"), b"mask-bytes")

    def test_explicit_input_index_selects_only_the_named_image_and_rebinds_its_role(self):
        tickets = self.tickets()
        lease = lease_for("image.edit", {"reference_indices": [1], "reference_roles": ["identity"]}, tickets,
                          lambda ticket, at: None)
        with self.assertRaises(TaskError) as unselected:
            lease.fetch("source-handle", "a" * 64, role="identity")
        self.assertEqual(unselected.exception.code, "reference_not_selected")
        self.assertEqual(lease.fetch("mask-handle", "b" * 64, role="identity"), b"mask-bytes")

    def test_explicit_input_index_rejects_missing_or_duplicate_positions(self):
        from astrbot_host.native_extensions.image_native.references import (
            ReferenceSelectionError, select_edit_tickets,
        )
        tickets = self.tickets()
        with self.assertRaises(ReferenceSelectionError) as missing:
            select_edit_tickets({"reference_indices": [2]}, tickets, {})
        self.assertEqual(missing.exception.code, "native_reference_index_unavailable")
        with self.assertRaises(ReferenceSelectionError) as duplicate:
            select_edit_tickets({"reference_indices": [1, 1]}, tickets, {})
        self.assertEqual(duplicate.exception.code, "invalid_reference_indices")

    def test_group_admission_rejects_mask_edit_even_if_a_model_submits_it(self):
        executor = ExternalToolExecutor.__new__(ExternalToolExecutor)
        descriptor = NS(tool=NS(action="image.mask_edit"))
        context = NS(scope=NS(kind=ScopeKind.GROUP))
        with self.assertRaises(TaskError) as rejected:
            executor._admit(descriptor, context, "checked-now")
        self.assertEqual(rejected.exception.code, "tool_not_available")


if __name__ == "__main__":
    unittest.main()
