import unittest
from concurrent import futures
from typing import Literal

import ipywidgets as widgets
import pyiron_workflow as pwf

from pyironflow import entry, executors, executors_lib, executors_panel


def needs_workers(max_workers: int, kind: bool = False) -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor(max_workers=max_workers)


def needs_a_flag(flag: bool) -> pwf.ExecutorInstructions:
    return executors_lib.thread_pool_executor_instructions()


def mode_pool(mode: Literal["a", "b"] = "a") -> pwf.ExecutorInstructions:
    return executors_lib.thread_pool_executor_instructions()


def pick_mode(mode: Literal["a", "b"]) -> pwf.ExecutorInstructions:
    return executors_lib.thread_pool_executor_instructions()


def bad_default(max_workers: int = "4") -> futures.ThreadPoolExecutor:  # type: ignore[assignment]
    return futures.ThreadPoolExecutor()


class _PanelTestCase(unittest.TestCase):
    def setUp(self):
        creators = executors.find_creators([executors_lib])
        creators.update(
            needs_workers=needs_workers,
            needs_a_flag=needs_a_flag,
            mode_pool=mode_pool,
            pick_mode=pick_mode,
            bad_default=bad_default,
        )
        self.registry = executors.ExecutorRegistry(creators)
        self.addCleanup(self.registry.close)
        self.created, self.deleted = [], []
        self.panel = executors_panel.ExecutorsPanel(
            self.registry, self.created.append, self._delete
        )

    def _delete(self, name):
        self.deleted.append(name)
        self.registry.delete(name, [])
        self.panel.refresh()


class TestLayout(_PanelTestCase):
    def test_create_above_browse_each_its_own_section(self):
        self.assertEqual(
            (self.panel.create_section, self.panel.browse_section),
            self.panel.gui.children,
        )
        self.assertEqual(
            (executors_panel.CREATE_TITLE,), self.panel.create_section.titles
        )
        self.assertEqual(
            (executors_panel.BROWSE_TITLE,), self.panel.browse_section.titles
        )

    def test_open_create_expands_create(self):
        self.assertIsNone(self.panel.create_section.selected_index)
        self.panel.open_create()
        self.assertEqual(0, self.panel.create_section.selected_index)


class TestCreate(_PanelTestCase):
    def test_nothing_to_create_until_a_creator_is_chosen(self):
        self.assertIsNone(self.panel.creator.value)
        self.assertEqual(list(self.registry.creators), list(self.panel.creator.options))
        self.assertEqual({}, self.panel.fields)
        self.assertEqual((), self.panel.fields_box.children)
        self.assertTrue(self.panel.create_button.disabled)

    def test_a_forced_create_without_a_creator_does_nothing(self):
        self.panel.create_button.click()  # disabled in the GUI, but click() still fires
        self.assertEqual([], self.created)
        self.assertEqual((), self.panel.error.outputs)

    def test_a_forced_create_with_a_missing_value_does_nothing(self):
        self.panel.creator.value = "needs_workers"
        self.panel.create_button.click()
        self.assertEqual([], self.created)
        self.assertEqual({}, self.registry.created)

    def test_choosing_a_creator_builds_prefilled_fields(self):
        self.panel.creator.value = "thread_pool_executor"
        self.assertEqual("thread_pool_executor_0", self.panel.name.value)
        self.assertEqual(["max_workers", "thread_name_prefix"], list(self.panel.fields))
        self.assertEqual(
            (
                self.panel.name,
                self.panel.fields["max_workers"].row,
                self.panel.fields["thread_name_prefix"].row,
            ),
            self.panel.fields_box.children,
        )
        self.assertEqual("None", self.panel.fields["max_workers"].widget.value)
        self.assertEqual("", self.panel.fields["thread_name_prefix"].widget.value)
        self.assertFalse(self.panel.create_button.disabled)

    def test_rows_name_the_parameter_and_its_hint(self):
        self.panel.creator.value = "thread_pool_executor"
        label = self.panel.fields["max_workers"].row.children[0].children[0]
        self.assertEqual(f"max_workers: {entry.hint_name(int | None)}", label.value)

    def test_unchoosing_the_creator_clears_the_fields(self):
        self.panel.creator.value = "thread_pool_executor"
        self.panel.creator.value = None
        self.assertEqual({}, self.panel.fields)
        self.assertTrue(self.panel.create_button.disabled)

    def test_field_kinds_follow_the_hint(self):
        self.panel.creator.value = "needs_workers"
        self.assertIsInstance(self.panel.fields["max_workers"].widget, widgets.Text)
        self.assertEqual("", self.panel.fields["max_workers"].widget.value)
        self.assertIsInstance(self.panel.fields["kind"].widget, widgets.Checkbox)
        self.assertFalse(self.panel.fields["kind"].widget.value)

    def test_a_required_blank_field_blocks_create(self):
        self.panel.creator.value = "needs_workers"
        self.assertTrue(self.panel.create_button.disabled)
        self.panel.fields["max_workers"].widget.value = "2"
        self.assertFalse(self.panel.create_button.disabled)

    def test_a_required_checkbox_always_has_a_value(self):
        self.panel.creator.value = "needs_a_flag"
        self.assertFalse(self.panel.create_button.disabled)
        self.panel.fields["flag"].widget.value = True
        self.panel.create_button.click()
        self.assertEqual({"flag": True}, self.created[0].kwargs)

    def test_a_bad_entry_blocks_create_and_says_why(self):
        self.panel.creator.value = "thread_pool_executor"
        field = self.panel.fields["max_workers"]
        field.widget.value = "lots"
        self.assertTrue(self.panel.create_button.disabled)
        self.assertIn("lots", field.message.value)
        field.widget.value = "3"
        self.assertEqual("", field.message.value)
        self.assertFalse(self.panel.create_button.disabled)

    def test_a_default_that_does_not_fit_shows_an_error(self):
        self.panel.creator.value = "bad_default"
        self.assertTrue(self.panel.create_button.disabled)
        self.assertNotEqual("", self.panel.fields["max_workers"].message.value)

    def test_a_blank_or_held_name_blocks_create(self):
        self.registry.create("taken", "thread_pool_executor_instructions", {})
        self.panel.creator.value = "thread_pool_executor_instructions"
        for name in ["  ", "taken"]:
            with self.subTest(name=name):
                self.panel.name.value = name
                self.assertTrue(self.panel.create_button.disabled)
        self.panel.name.value = "free"
        self.assertFalse(self.panel.create_button.disabled)

    def test_create_adds_reports_and_resets(self):
        self.panel.creator.value = "thread_pool_executor"
        self.panel.fields["max_workers"].widget.value = "2"
        self.panel.create_button.click()
        (created,) = self.created
        self.assertEqual("thread_pool_executor_0", created.name)
        self.assertEqual({"max_workers": 2}, created.kwargs)  # blank = default
        self.assertIs(created, self.registry.created["thread_pool_executor_0"])
        self.assertEqual("thread_pool_executor", self.panel.creator.value)
        self.assertEqual("thread_pool_executor_1", self.panel.name.value)
        self.assertEqual(("thread_pool_executor_0",), self.panel.browse.options)

    def test_a_raising_creator_shows_its_error(self):
        self.panel.creator.value = "thread_pool_executor"
        self.panel.fields["max_workers"].widget.value = "0"
        self.panel.create_button.click()
        self.assertEqual([], self.created)
        self.assertEqual({}, self.registry.created)
        (shown,) = self.panel.error.outputs
        self.assertIn("max_workers must be greater than 0", shown["text"])

    def test_choosing_again_clears_an_old_error(self):
        self.panel.creator.value = "thread_pool_executor"
        self.panel.fields["max_workers"].widget.value = "0"
        self.panel.create_button.click()
        self.panel.creator.value = "thread_pool_executor_instructions"
        self.assertEqual((), self.panel.error.outputs)

    def test_a_dropdown_field_parses_its_choice(self):
        self.panel.creator.value = "mode_pool"
        field = self.panel.fields["mode"].widget
        self.assertIsInstance(field, widgets.Dropdown)
        self.assertEqual(("'a'", "'b'"), field.options)
        self.assertEqual("'a'", field.value)
        field.value = "'b'"
        self.panel.create_button.click()
        self.assertEqual({"mode": "b"}, self.created[0].kwargs)

    def test_a_required_dropdown_starts_unchosen(self):
        self.panel.creator.value = "pick_mode"
        self.assertIsNone(self.panel.fields["mode"].widget.value)
        self.assertTrue(self.panel.create_button.disabled)
        self.panel.fields["mode"].widget.value = "'a'"
        self.assertFalse(self.panel.create_button.disabled)


class TestBrowse(_PanelTestCase):
    def test_details_of_a_created_executor(self):
        self.registry.create("p", "thread_pool_executor", {"max_workers": 2})
        self.panel.refresh()
        self.panel.browse.value = "p"
        details = self.panel.details.value
        self.assertIn("<b>p</b>", details)
        self.assertIn("ThreadPoolExecutor", details)
        self.assertIn("pyironflow.executors_lib.thread_pool_executor", details)
        self.assertIn("max_workers = 2", details)

    def test_details_of_an_external_executor(self):
        self.registry.adopt(executors_lib.thread_pool_executor_instructions())
        self.panel.refresh()
        self.panel.browse.value = "external_0"
        self.assertIn(executors_panel.EXTERNAL_CREATOR, self.panel.details.value)

    def test_details_escape_html(self):
        self.registry.create("<i>x</i>", "thread_pool_executor_instructions", {})
        self.panel.refresh()
        self.panel.browse.value = "<i>x</i>"
        self.assertIn("&lt;i&gt;x&lt;/i&gt;", self.panel.details.value)

    def test_a_refresh_keeps_a_surviving_selection(self):
        self.registry.create("p", "thread_pool_executor_instructions", {})
        self.panel.refresh()
        self.panel.browse.value = "p"
        self.registry.create("q", "thread_pool_executor_instructions", {})
        self.panel.refresh()
        self.assertEqual(("p", "q"), self.panel.browse.options)
        self.assertEqual("p", self.panel.browse.value)

    def test_delete_takes_two_clicks(self):
        self.registry.create("p", "thread_pool_executor_instructions", {})
        self.panel.refresh()
        self.panel.browse.value = "p"
        self.panel.delete_button.click()
        self.assertEqual([], self.deleted)
        self.assertEqual(
            executors_panel.CONFIRM_DELETE, self.panel.delete_button.description
        )
        self.assertEqual("danger", self.panel.delete_button.button_style)
        self.panel.delete_button.click()
        self.assertEqual(["p"], self.deleted)
        self.assertEqual((), self.panel.browse.options)
        self.assertEqual("", self.panel.details.value)
        self.assertEqual(executors_panel.DELETE, self.panel.delete_button.description)
        self.assertTrue(self.panel.delete_button.disabled)

    def test_changing_the_selection_disarms_delete(self):
        self.registry.create("p", "thread_pool_executor_instructions", {})
        self.registry.create("q", "thread_pool_executor_instructions", {})
        self.panel.refresh()
        self.panel.browse.value = "p"
        self.panel.delete_button.click()
        self.panel.browse.value = "q"
        self.assertEqual(executors_panel.DELETE, self.panel.delete_button.description)
        self.assertEqual("", self.panel.delete_button.button_style)
        self.panel.delete_button.click()
        self.assertEqual([], self.deleted)

    def test_delete_is_disabled_without_a_selection(self):
        self.assertTrue(self.panel.delete_button.disabled)
        self.panel.delete_button.click()  # disabled in the GUI, but click() still fires
        self.panel.delete_button.click()
        self.assertEqual([], self.deleted)
        self.assertEqual(executors_panel.DELETE, self.panel.delete_button.description)


if __name__ == "__main__":
    unittest.main()
