"""Persona listing: degrade to "no choice" rather than to a wrong choice.

AstrBot persona enumerators vary by version and may be asynchronous, so the
adapter has to handle both while preserving these failure boundaries:

* Returning **[]** is safe. The guide reads it as "follow the conversation's own
  persona", which is the single-persona case and correct for most installations.
* Returning a **wrong name** is not. The operator picks from the list, the choice
  becomes the persona id, and the ``role_id`` -- the memory owner -- is derived
  from it. A bogus entry silently splits or merges memory.

So the tests below care most about the shapes that must *not* produce entries:
the ``[%None]`` sentinel, blank strings, and records with no usable identifier.
"""

import asyncio
import unittest

from astrbot_host.persona_catalog import available_personas, persona_choices, _name_of


def list_personas(context):
    return asyncio.run(available_personas(context))


def choose_personas(context, *, selected=""):
    return asyncio.run(persona_choices(context, selected=selected))


class Manager:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class Context:
    def __init__(self, manager):
        self.persona_manager = manager


class EnumerationTests(unittest.TestCase):
    def test_a_host_that_exposes_nothing_yields_no_choices(self):
        """The safe answer: the guide falls back to the conversation's persona."""
        for manager in (Manager(), None, Manager(get_personas="not callable")):
            with self.subTest(manager=manager):
                self.assertEqual(list_personas(Context(manager)), [])

    def test_a_missing_context_is_not_an_error(self):
        self.assertEqual(list_personas(None), [])

    def test_each_known_enumerator_shape_is_tried_in_turn(self):
        for attribute in ("get_personas", "get_all_personas", "list_personas", "get_persona_list"):
            with self.subTest(attribute=attribute):
                manager = Manager(**{attribute: lambda: ["晚星", "朝雾"]})
                self.assertEqual(list_personas(Context(manager)), ["晚星", "朝雾"])

    def test_astrbot_async_persona_enumerator_is_awaited(self):
        class AsyncManager:
            async def get_all_personas(self):
                return [{"name": "晚星"}, {"name": "朝雾"}]

        self.assertEqual(list_personas(Context(AsyncManager())), ["晚星", "朝雾"])

    def test_records_are_read_by_name_id_or_plain_string(self):
        manager = Manager(get_personas=lambda: [
            {"name": "晚星"}, {"persona_id": "朝雾"}, "余晖", {"id": "初雪"}])
        # Sorted by code point, which puts 晚 (U+665A) before 朝 (U+671D).
        self.assertEqual(list_personas(Context(manager)),
                         ["余晖", "初雪", "晚星", "朝雾"])

    def test_a_mapping_of_personas_is_accepted(self):
        manager = Manager(personas={"晚星": {...}, "朝雾": {...}})
        self.assertEqual(list_personas(Context(manager)), ["晚星", "朝雾"])

    def test_the_none_sentinel_is_never_offered_as_a_choice(self):
        """It means 'no persona', which a person cannot meaningfully select."""
        manager = Manager(get_personas=lambda: ["晚星", "[%None]"])
        self.assertEqual(list_personas(Context(manager)), ["晚星"])

    def test_blank_and_unusable_entries_are_dropped(self):
        manager = Manager(get_personas=lambda: ["", "   ", {}, None, {"name": "  "}, "晚星"])
        self.assertEqual(list_personas(Context(manager)), ["晚星"])

    def test_duplicates_collapse_so_one_persona_is_one_role(self):
        manager = Manager(get_personas=lambda: ["晚星", "晚星", {"name": "晚星"}])
        self.assertEqual(list_personas(Context(manager)), ["晚星"])

    def test_a_failing_enumerator_does_not_raise(self):
        """A host-specific error while listing must not take first run down with it."""
        def explode():
            raise RuntimeError("host changed its mind")

        self.assertEqual(list_personas(Context(Manager(get_personas=explode))), [])

    def test_a_later_enumerator_is_used_when_the_first_returns_nothing(self):
        manager = Manager(get_personas=lambda: [], list_personas=lambda: ["晚星"])
        self.assertEqual(list_personas(Context(manager)), ["晚星"])


class ChoiceTests(unittest.TestCase):
    def test_astrbot_v3_personas_take_precedence_over_legacy_database_personas(self):
        manager = Manager(personas_v3=[Manager(name="默认"), Manager(name="星河")],
                          get_personas=lambda: ["legacy-only"])
        self.assertEqual(list_personas(Context(manager)), ["星河", "默认"])

    def test_the_conversation_persona_leads_the_list(self):
        manager = Manager(get_personas=lambda: ["朝雾", "晚星"])
        choices = choose_personas(Context(manager), selected="晚星")
        self.assertEqual([item["value"] for item in choices], ["晚星", "朝雾"])

    def test_a_selected_persona_missing_from_the_list_is_still_offered(self):
        """Otherwise the bound voice would have no representation in its own picker."""
        choices = choose_personas(Context(Manager()), selected="晚星")
        self.assertEqual([item["value"] for item in choices], ["晚星"])

    def test_no_selection_means_no_extra_entry(self):
        choices = choose_personas(Context(Manager(get_personas=lambda: ["晚星"])), selected="")
        self.assertEqual([item["value"] for item in choices], ["晚星"])

    def test_the_sentinel_selection_is_not_prepended(self):
        choices = choose_personas(Context(Manager()), selected="[%None]")
        self.assertEqual(choices, [])

    def test_each_choice_carries_a_label_for_the_page(self):
        choices = choose_personas(Context(Manager(get_personas=lambda: ["晚星"])))
        self.assertEqual(choices[0]["label"], "晚星")

    def test_the_identity_helper_reads_the_same_keys_the_list_offers(self):
        self.assertEqual(_name_of({"persona_id": "晚星"}), "晚星")
        self.assertEqual(_name_of({"id": "晚星"}), "晚星")


if __name__ == "__main__":
    unittest.main()
