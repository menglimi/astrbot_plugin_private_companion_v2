import unittest

from unified_person_registry import UnifiedPersonRegistry


def _identity(subject):
    return {
        "companion_instance_id": "companion",
        "bot_account_id": "webchat:bot",
        "adapter_instance_id": "webchat",
        "subject_namespace": "webchat:user",
        "platform_subject_id": subject,
    }


class PersonMergeTests(unittest.TestCase):
    def test_merge_moves_links_without_detaching_and_marks_source_merged(self):
        store = {}
        registry = UnifiedPersonRegistry(store)
        left = registry.create_or_link(_identity("left"), operation_id="create-left")
        right = registry.create_or_link(_identity("right"), operation_id="create-right")
        self.assertTrue(left["ok"] and right["ok"])
        source, target = left["person_id"], right["person_id"]

        result = registry.merge_person(source, target, operation_id="merge-one")

        self.assertTrue(result["ok"])
        self.assertEqual(result["moved_identity_links"], 1)
        links = store["unified_person"]["identity_links"].values()
        self.assertTrue(all(link["person_id"] == target for link in links))
        self.assertEqual(store["unified_person"]["profiles"][source]["profile_status"], "merged")
        self.assertEqual(store["unified_person"]["profiles"][source]["merged_into"], target)
        # nothing was detached
        self.assertEqual(store["unified_person"]["detached_identity_links"], {})


if __name__ == "__main__":
    unittest.main()
