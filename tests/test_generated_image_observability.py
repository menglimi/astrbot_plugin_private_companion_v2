import unittest
from types import SimpleNamespace

from companion_v2.conversation.media.generated import GeneratedImages
from companion_v2.execution.models import TaskError


class Runtime:
    def __init__(self):
        self.calls = []

    def read_one(self, query, parameters):
        self.calls.append((query, parameters))
        if "FROM runtime_metadata m" in query:
            return {"total": 0}
        return {"total": 2}

    def read_all(self, query, parameters):
        self.calls.append((query, parameters))
        if "FROM runtime_metadata m" in query:
            return []
        return [
            {"action": "image.generate", "state": "succeeded", "error_code": None,
             "created_at": "2026-10-07T10:00:00+00:00", "finished_at": "2026-10-07T10:00:03+00:00"},
            {"action": "image.edit", "state": "unknown", "error_code": "external_result_unknown",
             "created_at": "2026-10-07T09:00:00+00:00", "finished_at": None},
        ]


class Messages:
    def __init__(self):
        self.runtime = Runtime()
        self.authorized = []

    def authorize(self, context, at):
        self.authorized.append((context, at))


class GeneratedImageObservabilityTests(unittest.TestCase):
    def test_page_returns_only_safe_invocation_fields_for_the_authorized_context(self):
        messages = Messages()
        context = SimpleNamespace(key="private-role-context")
        page = GeneratedImages(messages).observability_page(context, "now", limit=10)
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["items"][0]["elapsed_ms"], 3000)
        self.assertEqual(page["items"][1]["state"], "unknown")
        self.assertEqual(messages.authorized, [(context, "now")])
        self.assertEqual(messages.runtime.calls[0][1], (context.key, "image.edit", "image.generate", "image.mask_edit"))
        self.assertNotIn("arguments_json", page["items"][0])

    def test_page_size_is_bounded(self):
        with self.assertRaises(TaskError):
            GeneratedImages(Messages()).observability_page(SimpleNamespace(key="context"), "now", limit=51)


if __name__ == "__main__":
    unittest.main()
