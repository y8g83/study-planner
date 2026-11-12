"""Core task-operation tests: FR1-FR4, the list view and the messages.

Every test works on a planner whose data file lies in its own temporary
directory. A failed save is simulated by making ``storage.save`` raise
``OSError``.
"""

import json
import random
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import helpers  # puts src/ on the import path
import core
import storage


def task(task_id, title="Read chapter", subject="Mathematics",
         description="", due_date="2026-11-20", priority="Medium",
         status="Pending"):
    return {"id": task_id, "title": title, "subject": subject,
            "description": description, "due_date": due_date,
            "priority": priority, "status": status}


def three_tasks():
    """Tasks 1, 2, 3 in stored order (``next_id = 5``: ID 4 was deleted)."""
    return [task(1, title="Essay plan", subject="History"),
            task(2, title="Read Chapter 1", due_date="2026-11-10"),
            task(3, title="Lab report", subject="Physics")]


def failing_save():
    return mock.patch.object(storage, "save",
                             side_effect=PermissionError("read-only"))


class CoreTestCase(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / ".study_planner" / "tasks.json"

    def planner(self, tasks=None, next_id=5):
        tasks = three_tasks() if tasks is None else tasks
        return core.Planner(self.path, tasks, next_id)

    def saved_data(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def assertOthersUnchanged(self, planner, *task_ids):
        originals = {t["id"]: t for t in three_tasks()}
        for task_id in task_ids:
            index = planner._index_of(task_id)
            self.assertEqual(planner.tasks[index], originals[task_id])

    def assertNoSave(self, planner):
        self.assertFalse(self.path.exists())
        self.assertFalse(planner.unsaved)


class TestFR1AddTask(CoreTestCase):

    def test_ac1_defaults_next_id_appended_saved(self):
        planner = self.planner()
        result = planner.add_task("Revise Algebra", "Mathematics",
                                  "2026-11-25", priority="", status="")
        self.assertEqual(result.outcome, core.SUCCESS)
        self.assertEqual(result.lines(), ["Task 5 added."])
        self.assertTrue(result.saved)
        self.assertEqual(planner.tasks[-1], task(
            5, title="Revise Algebra", due_date="2026-11-25"))
        self.assertEqual(planner.next_id, 6)
        self.assertOthersUnchanged(planner, 1, 2, 3)
        self.assertEqual(self.saved_data()["next_id"], 6)
        self.assertFalse(planner.unsaved)

    def test_ac2_selected_values_kept_on_empty_list(self):
        planner = self.planner(tasks=[], next_id=1)
        result = planner.add_task("Lab report", "Biology", "2026-11-30",
                                  priority="High", status="Completed")
        self.assertEqual(result.task["id"], 1)
        self.assertEqual(planner.tasks[0]["priority"], "High")
        self.assertEqual(planner.tasks[0]["status"], "Completed")
        self.assertEqual(planner.next_id, 2)

    def test_ac3_blank_title_rejected_nothing_added(self):
        for title in ("", "   "):
            with self.subTest(title=title):
                planner = self.planner()
                result = planner.add_task(title, "History", "2026-11-25")
                self.assertEqual(result.outcome, core.INVALID)
                self.assertEqual(result.lines(), [
                    "Title must not be empty after trimming."])
                self.assertEqual(planner.tasks, three_tasks())
                self.assertEqual(planner.next_id, 5)
                self.assertNoSave(planner)

    def test_ac4_failed_save_keeps_task_and_warns(self):
        planner = self.planner()
        with failing_save():
            result = planner.add_task("Essay", "History", "2026-11-25")
        self.assertEqual(result.task["id"], 5)
        self.assertIs(result.saved, False)
        self.assertEqual(result.lines(), [
            "Task 5 added.",
            core.render_message(core.SAVE_FAILED)])
        self.assertEqual(planner.tasks[-1]["id"], 5)
        self.assertEqual(planner.next_id, 6)
        self.assertTrue(planner.unsaved)


class TestFR2EditTask(CoreTestCase):

    def test_ac1_title_and_priority_changed_in_place(self):
        planner = self.planner()
        result = planner.edit_task("2", {"title": "Read Chapter 2",
                                         "priority": "High"})
        self.assertEqual(result.outcome, core.SUCCESS)
        self.assertEqual(result.lines(), [
            "Task 2 updated. Changed fields: title, priority."])
        self.assertEqual(planner.tasks[1], task(
            2, title="Read Chapter 2", due_date="2026-11-10",
            priority="High"))
        self.assertOthersUnchanged(planner, 1, 3)
        self.assertEqual(planner.next_id, 5)
        self.assertTrue(result.saved)

    def test_ac2_invalid_values_reject_whole_edit(self):
        planner = self.planner()
        result = planner.edit_task("2", {"title": "Read Chapter 2",
                                         "due_date": "10/11/2026",
                                         "priority": "Urgent"})
        self.assertEqual(result.outcome, core.INVALID)
        self.assertEqual(result.lines(), [
            "Due date must use the YYYY-MM-DD format.",
            "Priority must exactly match one of the permitted values."])
        self.assertEqual(planner.tasks, three_tasks())
        self.assertNoSave(planner)

    def test_ac3_leading_zero_id_rejected(self):
        planner = self.planner()
        result = planner.find_task("007")
        self.assertEqual(result.outcome, core.INVALID)
        self.assertEqual(result.errors, (core.ValidationError(
            core.TASK_ID, core.INVALID_TASK_ID_FORMAT),))
        self.assertEqual(planner.tasks, three_tasks())
        self.assertNoSave(planner)

    def test_ac4_deleted_id_not_found(self):
        planner = self.planner()
        for operation in (planner.find_task,
                          lambda text: planner.edit_task(
                              text, {"title": "New"})):
            result = operation("4")
            self.assertEqual(result.outcome, core.NOT_FOUND)
            self.assertEqual(result.lines(), ["No task with ID 4 exists."])
        self.assertEqual(planner.tasks, three_tasks())
        self.assertNoSave(planner)

    def test_ac5_noop_edit_keeps_unsaved_state_and_saves_nothing(self):
        planner = self.planner()
        planner.unsaved = True
        with mock.patch.object(storage, "save") as save:
            result = planner.edit_task("2", {"title": " Read Chapter 1 ",
                                             "priority": "medium"})
        save.assert_not_called()
        self.assertEqual(result.outcome, core.NO_CHANGE)
        self.assertEqual(result.lines(),
                         ["No changes were made to task 2."])
        self.assertEqual(planner.tasks, three_tasks())
        self.assertTrue(planner.unsaved)

    def test_ac6_failed_save_keeps_edit_in_memory(self):
        planner = self.planner()
        with failing_save():
            result = planner.edit_task("2", {"due_date": "2026-11-12"})
        self.assertEqual(result.lines(), [
            "Task 2 updated. Changed fields: due date.",
            core.render_message(core.SAVE_FAILED)])
        self.assertEqual(planner.tasks[1]["due_date"], "2026-11-12")
        self.assertEqual(planner.tasks[1]["id"], 2)
        self.assertOthersUnchanged(planner, 1, 3)
        self.assertTrue(planner.unsaved)

    def test_rule_changed_fields_listed_in_field_order(self):
        planner = self.planner()
        result = planner.edit_task("2", {"priority": "Low",
                                         "subject": "Physics",
                                         "title": "Read Chapter 1"})
        self.assertEqual(result.params["fields"], "subject, priority")

    def test_rule_status_cannot_be_edited(self):
        with self.assertRaises(ValueError):
            self.planner().edit_task("2", {"status": "Completed"})


class TestFR3DeleteTask(CoreTestCase):

    def test_ac1_delete_keeps_order_and_next_id(self):
        planner = self.planner()
        result = planner.delete_task("2")
        self.assertEqual(result.lines(), ["Task 2 deleted."])
        self.assertTrue(result.saved)
        self.assertEqual([t["id"] for t in planner.tasks], [1, 3])
        self.assertOthersUnchanged(planner, 1, 3)
        self.assertEqual(planner.next_id, 5)
        self.assertEqual(self.saved_data()["next_id"], 5)

    def test_ac2_cancel_message_and_confirmation_rule(self):
        self.assertEqual(core.render_message(core.DELETION_CANCELLED),
                         "Deletion cancelled.")
        for answer in ("y", "Y", "yes", " YES ", "\tYes\n"):
            self.assertTrue(core.confirms_deletion(answer), answer)
        for answer in ("n", "", "no", "ye", "yes please", "1"):
            self.assertFalse(core.confirms_deletion(answer), answer)

    def test_ac3_plus_sign_rejected(self):
        planner = self.planner()
        result = planner.find_task("+2")
        self.assertEqual(result.errors, (core.ValidationError(
            core.TASK_ID, core.INVALID_TASK_ID_FORMAT),))
        self.assertEqual(planner.tasks, three_tasks())

    def test_ac4_deleted_id_not_found(self):
        planner = self.planner()
        result = planner.delete_task("4")
        self.assertEqual(result.outcome, core.NOT_FOUND)
        self.assertEqual(planner.tasks, three_tasks())
        self.assertNoSave(planner)

    def test_ac5_last_task_deleted_id_not_reused(self):
        planner = self.planner(tasks=[task(3)])
        planner.delete_task("3")
        self.assertEqual(planner.tasks, [])
        self.assertEqual(planner.next_id, 5)
        result = planner.add_task("New", "History", "2026-12-01")
        self.assertEqual(result.task["id"], 5)

    def test_ac6_failed_save_keeps_deletion(self):
        planner = self.planner()
        with failing_save():
            result = planner.delete_task("2")
        self.assertEqual(result.lines(), [
            "Task 2 deleted.", core.render_message(core.SAVE_FAILED)])
        self.assertEqual([t["id"] for t in planner.tasks], [1, 3])
        self.assertTrue(planner.unsaved)


class TestFR4ChangeStatus(CoreTestCase):

    def test_ac1_lowercase_status_stored_canonical(self):
        planner = self.planner()
        result = planner.change_status("2", "in progress")
        self.assertEqual(result.lines(),
                         ["Task 2 status changed to In Progress."])
        self.assertEqual(planner.tasks[1]["status"], "In Progress")
        self.assertEqual({k: v for k, v in planner.tasks[1].items()
                          if k != "status"},
                         {k: v for k, v in three_tasks()[1].items()
                          if k != "status"})
        self.assertOthersUnchanged(planner, 1, 3)
        self.assertTrue(result.saved)

    def test_ac2_all_six_transitions(self):
        for old in core.STATUSES:
            for new in core.STATUSES:
                if old == new:
                    continue
                with self.subTest(old=old, new=new):
                    tasks = three_tasks()
                    tasks[1]["status"] = old
                    planner = self.planner(tasks=tasks)
                    result = planner.change_status("2", new)
                    self.assertEqual(result.outcome, core.SUCCESS)
                    self.assertEqual(planner.tasks[1]["status"], new)
                    self.assertTrue(result.saved)

    def test_ac3_same_status_is_noop(self):
        tasks = three_tasks()
        tasks[1]["status"] = "Completed"
        planner = self.planner(tasks=tasks)
        result = planner.change_status("2", "completed")
        self.assertEqual(result.outcome, core.NO_CHANGE)
        self.assertEqual(result.lines(), [
            "Task 2 already has status Completed; the status is "
            "unchanged."])
        self.assertIsNone(result.saved)
        self.assertNoSave(planner)

    def test_ac4_invalid_status_rejected(self):
        for text in ("inprogress", "In  Progress"):
            with self.subTest(text=text):
                planner = self.planner()
                result = planner.change_status("2", text)
                self.assertEqual(result.lines(), [
                    "Status must exactly match one of the permitted "
                    "values."])
                self.assertEqual(planner.tasks, three_tasks())
                self.assertNoSave(planner)

    def test_ac5_malformed_and_unknown_ids_rejected(self):
        planner = self.planner()
        self.assertEqual(planner.change_status("abc", "Completed").errors,
                         (core.ValidationError(
                             core.TASK_ID, core.INVALID_TASK_ID_FORMAT),))
        self.assertEqual(planner.change_status("9", "Completed").lines(),
                         ["No task with ID 9 exists."])
        self.assertEqual(planner.tasks, three_tasks())
        self.assertNoSave(planner)

    def test_ac6_failed_save_keeps_status(self):
        tasks = three_tasks()
        tasks[1]["status"] = "In Progress"
        planner = self.planner(tasks=tasks)
        with failing_save():
            result = planner.change_status("2", "Completed")
        self.assertEqual(result.lines(), [
            "Task 2 status changed to Completed.",
            core.render_message(core.SAVE_FAILED)])
        self.assertEqual(planner.tasks[1]["status"], "Completed")
        self.assertTrue(planner.unsaved)


class TestFR6RetryAfterNextChange(CoreTestCase):

    def test_next_successful_change_saves_everything(self):
        planner = self.planner()
        with failing_save():
            planner.edit_task("2", {"title": "Updated title"})
        self.assertTrue(planner.unsaved)
        result = planner.change_status("3", "In Progress")
        self.assertTrue(result.saved)
        self.assertFalse(planner.unsaved)
        saved = self.saved_data()["tasks"]
        self.assertEqual(saved[1]["title"], "Updated title")
        self.assertEqual(saved[2]["status"], "In Progress")

    def test_rejected_submission_does_not_retry(self):
        planner = self.planner()
        planner.unsaved = True
        with mock.patch.object(storage, "save") as save:
            planner.add_task("", "History", "2026-11-25")
            planner.change_status("2", "Pending")
        save.assert_not_called()
        self.assertTrue(planner.unsaved)


class TestListView(CoreTestCase):

    def test_stored_order_and_copies(self):
        planner = self.planner()
        view = planner.list_view()
        self.assertIsNone(view.message)
        self.assertEqual([t["id"] for t in view.tasks], [1, 2, 3])
        view.tasks[0]["title"] = "Changed"
        self.assertEqual(planner.tasks, three_tasks())
        self.assertNoSave(planner)

    def test_empty_list_message(self):
        view = self.planner(tasks=[], next_id=1).list_view()
        self.assertEqual(view.tasks, [])
        self.assertEqual(core.render_message(view.message), "No tasks yet.")

    def test_unsaved_changes_are_listed(self):
        planner = self.planner()
        with failing_save():
            planner.add_task("Essay", "History", "2026-11-25")
        view = planner.list_view()
        self.assertEqual([t["id"] for t in view.tasks], [1, 2, 3, 5])
        self.assertTrue(planner.unsaved)


class TestMessages(unittest.TestCase):

    def test_fixed_texts(self):
        self.assertEqual(core.render_message(core.NO_MATCHING_TASKS),
                         "No tasks match the current search and filters.")
        self.assertEqual(core.render_message(core.INTERNAL_ERROR),
                         "An internal application error occurred. "
                         "Please try again.")
        self.assertEqual(core.render_message(core.UNSAVED_INDICATOR),
                         "Unsaved changes")

    def test_exit_discard_choice_states_loss(self):
        self.assertIn("since the last successful save will be lost",
                      core.render_message(core.EXIT_DISCARD))

    def test_operation_message_needs_its_parameters(self):
        for key in (core.TASK_ADDED, core.TASK_UPDATED,
                    core.STATUS_CHANGED, core.TASK_NOT_FOUND,
                    core.INVALID_STORED_DATA):
            with self.subTest(key=key):
                with self.assertRaises(core.MessageError):
                    core.render_message(key)


# --- FR7-FR10 datasets ------------------------------------------------------

def fr7_dataset():
    """FR7 shared dataset: tasks 1, 2, 3; ``next_id = 4``."""
    return [task(1, title="Revise Algebra", subject="Mathematics"),
            task(2, title="Essay draft", subject="History",
                 description="Check sources for the Tudor period"),
            task(3, title="Lab report", subject="Biology",
                 description="Include algebra-based calculations")]


def fr8_dataset():
    """FR8 base dataset: tasks 1-4, task 4's subject in lower case."""
    return [task(1, subject="Mathematics", priority="High"),
            task(2, subject="History", status="In Progress"),
            task(3, subject="Biology", priority="High", status="Completed"),
            task(4, subject="mathematics", priority="Low")]


def fr9_dataset():
    """FR9 dataset: five tasks with deliberate ties; ``next_id = 6``."""
    return [task(1, subject="Mathematics", priority="High",
                 due_date="2026-11-20"),
            task(2, subject="History", status="In Progress",
                 due_date="2026-11-10"),
            task(3, subject="biology", priority="High", status="Completed",
                 due_date="2026-11-10"),
            task(4, subject="Mathematics", priority="Low",
                 due_date="2026-11-05"),
            task(5, subject="Art", due_date="2026-11-20")]


def ids(tasks):
    return [t["id"] for t in tasks]


class ViewTestCase(CoreTestCase):
    """Planner on a saved data file, so unchanged bytes can be checked."""

    def start_with(self, tasks, next_id):
        storage.save(self.path, tasks, next_id)
        self.before = self.path.read_bytes()
        self.original = [dict(t) for t in tasks]
        self.next_id = next_id
        return core.start(self.path).planner

    def shown(self, planner):
        return ids(planner.list_view().tasks)

    def assertStoredUnchanged(self, planner):
        self.assertEqual(planner.tasks, self.original)
        self.assertEqual(planner.next_id, self.next_id)
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertFalse(planner.unsaved)


class TestFR7Search(ViewTestCase):

    def search(self, query, tasks=None, next_id=4):
        if tasks is None:
            tasks = fr7_dataset()
        planner = self.start_with(tasks, next_id)
        planner.view.search = query
        return planner

    def test_ac1_partial_case_insensitive_title_match(self):
        planner = self.search("REVISE")
        self.assertEqual(self.shown(planner), [1])
        self.assertStoredUnchanged(planner)

    def test_ac2_description_subject_and_two_fields(self):
        for query, expected in (("tudor", [2]), ("BIO", [3]),
                                ("algebra", [1, 3])):
            with self.subTest(query=query):
                planner = self.search(query)
                self.assertEqual(self.shown(planner), expected)
                self.assertStoredUnchanged(planner)

    def test_ac3_no_match_message(self):
        planner = self.search("physics")
        view = planner.list_view()
        self.assertEqual(view.tasks, [])
        self.assertEqual(view.message, core.NO_MATCHING_TASKS)
        self.assertStoredUnchanged(planner)

    def test_ac3_empty_list_message_takes_precedence(self):
        planner = self.search("essay", tasks=[], next_id=1)
        self.assertEqual(planner.list_view().message, core.NO_TASKS_YET)

    def test_ac4_empty_whitespace_and_trimmed_queries(self):
        for query, expected in (("", [1, 2, 3]), ("   ", [1, 2, 3]),
                                ("  essay draft  ", [2]),
                                ("essay  draft", [])):
            with self.subTest(query=query):
                planner = self.search(query)
                self.assertEqual(self.shown(planner), expected)
                self.assertStoredUnchanged(planner)
        self.assertEqual(planner.list_view().message,
                         core.NO_MATCHING_TASKS)

    def test_ac5_search_and_subject_filter_combine_with_and(self):
        for query, subject, expected in (
                ("algebra", None, [1, 3]),
                ("algebra", "Mathematics", [1]),
                ("algebra", "Biology", [3]),
                ("essay", "Mathematics", [])):
            with self.subTest(query=query, subject=subject):
                planner = self.search(query)
                planner.view.subject = subject
                self.assertEqual(self.shown(planner), expected)
                self.assertStoredUnchanged(planner)

    def test_ac6_casefold_matches_sharp_s(self):
        tasks = fr7_dataset() + [task(4, title="Straße survey",
                                      subject="Geography")]
        planner = self.search("STRASSE", tasks=tasks, next_id=5)
        self.assertEqual(self.shown(planner), [4])
        self.assertStoredUnchanged(planner)

    def test_ac7_search_persists_across_adds_and_clears(self):
        planner = self.search("algebra")
        self.assertEqual(self.shown(planner), [1, 3])
        self.assertEqual(core.search_line(planner.view),
                         'Search: "algebra"')
        self.assertEqual(planner.add_task(
            "Algebra quiz", "Mathematics", "2026-11-20").task["id"], 4)
        self.assertEqual(self.shown(planner), [1, 3, 4])
        planner.add_task("History notes", "History", "2026-11-20")
        self.assertEqual(self.shown(planner), [1, 3, 4])
        planner.view.search = ""
        self.assertEqual(self.shown(planner), [1, 2, 3, 4, 5])
        self.assertEqual(core.search_line(planner.view), "Search: none")
        restarted = core.start(self.path).planner
        self.assertEqual(restarted.view, core.ViewState())
        self.assertEqual(self.shown(restarted), [1, 2, 3, 4, 5])
        self.assertEqual(set(self.saved_data()), {"next_id", "tasks"})

    def test_search_does_not_restrict_operations_by_id(self):
        planner = self.search("algebra")
        self.assertEqual(planner.find_task("2").outcome, core.FOUND)

    def test_search_line_trims_keeps_case_and_escapes_quotes(self):
        for query, line in (("  Algebra  ", 'Search: "Algebra"'),
                            ('say "hi"', 'Search: "say \\"hi\\""'),
                            ("   ", "Search: none")):
            with self.subTest(query=query):
                self.assertEqual(core.search_line(
                    core.ViewState(search=query)), line)


class TestFR8Filters(ViewTestCase):

    def filtered(self, **filters):
        planner = self.start_with(fr8_dataset(), 5)
        for name, value in filters.items():
            setattr(planner.view, name, value)
        return planner

    def test_expected_results_table(self):
        for filters, expected in (
                ({}, [1, 2, 3, 4]),
                ({"status": "Pending"}, [1, 4]),
                ({"priority": "High"}, [1, 3]),
                ({"subject": "Mathematics"}, [1, 4]),
                ({"subject": "  MATHEMATICS  "}, [1, 4]),
                ({"subject": "Math"}, []),
                ({"subject": "   "}, [1, 2, 3, 4]),
                ({"status": "Pending", "priority": "High"}, [1]),
                ({"status": "Pending", "priority": "Low",
                  "subject": "Mathematics"}, [4]),
                ({"status": "Completed", "subject": "History"}, [])):
            with self.subTest(filters=filters):
                planner = self.filtered(**filters)
                view = planner.list_view()
                self.assertEqual(ids(view.tasks), expected)
                if not expected:
                    self.assertEqual(view.message, core.NO_MATCHING_TASKS)
                self.assertEqual(planner.tasks[3]["subject"], "mathematics")
                self.assertStoredUnchanged(planner)

    def test_ac5_filter_persists_across_adds_and_resets_on_restart(self):
        planner = self.filtered(status="Pending")
        self.assertEqual(self.shown(planner), [1, 4])
        self.assertEqual(planner.add_task(
            "Lab", "Physics", "2026-11-20", status="Pending").task["id"], 5)
        self.assertEqual(self.shown(planner), [1, 4, 5])
        planner.add_task("Quiz", "Physics", "2026-11-20",
                         status="Completed")
        self.assertEqual(self.shown(planner), [1, 4, 5])
        planner.view.status = None
        self.assertEqual(self.shown(planner), [1, 2, 3, 4, 5, 6])
        restarted = core.start(self.path).planner
        self.assertEqual(restarted.view, core.ViewState())
        self.assertEqual(self.shown(restarted), [1, 2, 3, 4, 5, 6])
        self.assertEqual(set(self.saved_data()), {"next_id", "tasks"})

    def test_ac7_empty_list_message_with_active_filter(self):
        planner = self.start_with([], 5)
        planner.view.status = "Pending"
        self.assertEqual(planner.list_view().message, core.NO_TASKS_YET)
        self.assertStoredUnchanged(planner)

    def test_ac8_subject_named_all_is_an_ordinary_subject(self):
        planner = self.start_with(fr8_dataset() + [task(5, subject="All")],
                                  6)
        planner.view.subject = "All"
        self.assertEqual(self.shown(planner), [5])
        planner.view.subject = None
        self.assertEqual(self.shown(planner), [1, 2, 3, 4, 5])
        self.assertStoredUnchanged(planner)


class TestFR8SetFilter(ViewTestCase):

    def setUp(self):
        super().setUp()
        self.planner = self.start_with(fr8_dataset(), 5)

    def test_ac4_invalid_value_names_filter_and_keeps_filters(self):
        self.planner.set_filter(core.FILTER_PRIORITY, "High")
        result = self.planner.set_filter(core.FILTER_STATUS, "Done")
        self.assertEqual(result.outcome, core.INVALID)
        self.assertEqual(result.lines(), [
            "Status filter must be one of: Pending, In Progress, "
            "Completed."])
        self.assertEqual(self.planner.view, core.ViewState(priority="High"))
        self.assertEqual(self.planner.set_filter(
            core.FILTER_PRIORITY, "Urgent").lines(),
            ["Priority filter must be one of: High, Medium, Low."])

    def test_ac4_invalid_value_keeps_the_same_filter(self):
        self.planner.set_filter(core.FILTER_STATUS, "Pending")
        self.planner.set_filter(core.FILTER_STATUS, "Done")
        self.assertEqual(self.planner.view.status, "Pending")

    def test_ac4_value_trimmed_and_normalised(self):
        self.assertTrue(self.planner.set_filter(core.FILTER_STATUS,
                                                "  pending  ").ok)
        self.assertEqual(self.planner.view.status, "Pending")
        self.planner.set_filter(core.FILTER_PRIORITY, "hIGH")
        self.assertEqual(self.planner.view.priority, "High")

    def test_ac1_empty_or_all_clears_status_and_priority(self):
        for name in (core.FILTER_STATUS, core.FILTER_PRIORITY):
            for answer in ("", "   ", "All", "all", " ALL "):
                with self.subTest(name=name, answer=answer):
                    self.planner.set_filter(name, "Pending" if name ==
                                            core.FILTER_STATUS else "High")
                    self.assertTrue(self.planner.set_filter(name,
                                                            answer).ok)
                    self.assertIsNone(getattr(self.planner.view, name))

    def test_ac8_subject_cleared_only_by_empty_answer(self):
        self.planner.set_filter(core.FILTER_SUBJECT, "  All  ")
        self.assertEqual(self.planner.view.subject, "All")
        self.planner.set_filter(core.FILTER_SUBJECT, "   ")
        self.assertIsNone(self.planner.view.subject)

    def test_setting_filters_changes_nothing_stored(self):
        self.planner.set_filter(core.FILTER_STATUS, "Pending")
        self.planner.set_filter(core.FILTER_SUBJECT, "Math")
        self.planner.set_search("x")
        self.planner.set_sort(core.SORT_SUBJECT)
        self.assertStoredUnchanged(self.planner)

    def test_filters_line_fixed_order(self):
        for view, line in (
                (core.ViewState(), "Filters: none"),
                (core.ViewState(status="Pending"), "Filters: status=Pending"),
                (core.ViewState(subject="Maths", priority="Low",
                                status="Completed"),
                 "Filters: status=Completed, priority=Low, subject=Maths")):
            with self.subTest(line=line):
                self.assertEqual(core.filters_line(view), line)

    def test_view_lines_and_search_setter(self):
        self.planner.set_search('  say "hi"  ')
        self.planner.set_sort(core.SORT_DUE_DATE)
        self.assertEqual(core.view_lines(self.planner.view), [
            'Search: "say \\"hi\\""', "Filters: none", "Sort: due date"])

    def test_unknown_sort_rejected(self):
        with self.assertRaises(ValueError):
            self.planner.set_sort("title")


class TestFR9Sort(ViewTestCase):

    def sorted_by(self, sort, **filters):
        planner = self.start_with(fr9_dataset(), 6)
        planner.view.sort = sort
        for name, value in filters.items():
            setattr(planner.view, name, value)
        return planner

    def test_ac1_to_ac5_expected_orders(self):
        for sort, expected in ((None, [1, 2, 3, 4, 5]),
                               (core.SORT_DUE_DATE, [4, 2, 3, 1, 5]),
                               (core.SORT_PRIORITY, [3, 1, 2, 5, 4]),
                               (core.SORT_STATUS, [4, 1, 5, 2, 3]),
                               (core.SORT_SUBJECT, [5, 3, 2, 4, 1])):
            with self.subTest(sort=sort):
                planner = self.sorted_by(sort)
                self.assertEqual(self.shown(planner), expected)
                self.assertEqual(ids(planner.tasks), [1, 2, 3, 4, 5])
                self.assertStoredUnchanged(planner)

    def test_ac5_plain_comparison_would_be_wrong(self):
        plain = sorted(fr9_dataset(),
                       key=lambda t: (t["subject"], t["due_date"]))
        self.assertEqual(ids(plain), [5, 2, 4, 1, 3])

    def test_ac6_filter_then_sort(self):
        planner = self.sorted_by(core.SORT_DUE_DATE, status="Pending")
        self.assertEqual(self.shown(planner), [4, 1, 5])
        self.assertStoredUnchanged(planner)

    def test_ac7_boundaries(self):
        key = core.sort_key(core.SORT_DUE_DATE)
        self.assertEqual(core.merge_sort([], key), [])
        single = [task(1)]
        result = core.merge_sort(single, key)
        self.assertEqual(result, single)
        self.assertIsNot(result, single)
        equal = [task(7), task(3), task(9)]
        for sort in core.SORT_FIELDS:
            with self.subTest(sort=sort):
                self.assertEqual(ids(core.merge_sort(
                    equal, core.sort_key(sort))), [7, 3, 9])

    def test_ac8_matches_builtin_sorted(self):
        generator = random.Random(44102)
        tasks = [task(n, subject=generator.choice(
                          ["Art", "art", "Biology", "history", "Économie"]),
                      due_date=f"2026-11-{generator.randint(1, 5):02d}",
                      priority=generator.choice(core.PRIORITIES),
                      status=generator.choice(core.STATUSES))
                 for n in range(1, 201)]
        datasets = (fr9_dataset(), tasks, [], [task(1)])
        for sort in core.SORT_FIELDS:
            for data in datasets:
                with self.subTest(sort=sort, size=len(data)):
                    key = core.sort_key(sort)
                    self.assertEqual(core.merge_sort(data, key),
                                     sorted(data, key=key))

    def test_ac8_keys_calculated_once_per_task(self):
        calls = []

        def key(item):
            calls.append(item["id"])
            return item["due_date"]

        core.merge_sort(fr9_dataset(), key)
        self.assertEqual(sorted(calls), [1, 2, 3, 4, 5])

    def test_merge_sort_never_mutates_input(self):
        data = fr9_dataset()
        snapshot = [dict(t) for t in data]
        core.merge_sort(data, core.sort_key(core.SORT_SUBJECT))
        self.assertEqual(data, snapshot)

    def test_ac9_changing_and_clearing_the_sort(self):
        planner = self.sorted_by(core.SORT_PRIORITY)
        self.assertEqual(core.sort_line(planner.view), "Sort: priority")
        planner.view.sort = core.SORT_STATUS
        self.assertEqual(self.shown(planner), [4, 1, 5, 2, 3])
        self.assertEqual(core.sort_line(planner.view), "Sort: status")
        planner.view.sort = None
        self.assertEqual(self.shown(planner), [1, 2, 3, 4, 5])
        self.assertEqual(core.sort_line(planner.view), "Sort: none")

    def test_sort_labels(self):
        self.assertEqual([core.sort_line(core.ViewState(sort=s))
                          for s in (None,) + core.SORT_FIELDS],
                         ["Sort: none", "Sort: due date", "Sort: priority",
                          "Sort: status", "Sort: subject"])

    def test_ac10_restart_has_no_sort(self):
        planner = self.sorted_by(core.SORT_SUBJECT)
        restarted = core.start(self.path).planner
        self.assertIsNone(restarted.view.sort)
        self.assertEqual(self.shown(restarted), [1, 2, 3, 4, 5])
        self.assertEqual(set(self.saved_data()), {"next_id", "tasks"})
        self.assertStoredUnchanged(planner)

    def test_ac11_sort_kept_after_add(self):
        planner = self.sorted_by(core.SORT_DUE_DATE)
        planner.add_task("New", "History", "2026-11-10")
        self.assertEqual(planner.view.sort, core.SORT_DUE_DATE)
        self.assertEqual(self.shown(planner), [4, 2, 3, 6, 1, 5])
        self.assertEqual(ids(planner.tasks), [1, 2, 3, 4, 5, 6])


class TestFR10Summary(ViewTestCase):

    def summary_lines(self, tasks, today):
        return core.summarise(tasks, today).lines()

    def test_ac1_fr9_dataset(self):
        self.assertEqual(self.summary_lines(fr9_dataset(),
                                            date(2026, 11, 12)), [
            "Total: 5", "Completed: 1", "Remaining: 4", "Overdue: 2",
            "Completion: 20.0%"])

    def test_ac2_task_due_today_not_overdue(self):
        summary = core.summarise(fr9_dataset(), date(2026, 11, 10))
        self.assertEqual(summary.overdue, 1)

    def test_ac3_empty_list(self):
        self.assertEqual(self.summary_lines([], date(2026, 11, 12)), [
            "Total: 0", "Completed: 0", "Remaining: 0", "Overdue: 0",
            "Completion: 0.0%"])

    def test_ac4_half_up_rounding(self):
        tasks = [task(n) for n in range(1, 17)]
        tasks[0]["status"] = "Completed"
        self.assertEqual(f"{100 / 16:.1f}", "6.2")
        self.assertEqual(core.summarise(tasks, date(2026, 11, 12))
                         .completion, "6.3%")

    def test_ac5_completed_tasks_never_overdue(self):
        tasks = [task(n, status="Completed", due_date="2026-01-01")
                 for n in (1, 2, 3)]
        self.assertEqual(self.summary_lines(tasks, date(2026, 11, 12)), [
            "Total: 3", "Completed: 3", "Remaining: 0", "Overdue: 0",
            "Completion: 100.0%"])

    def test_ac6_filters_search_and_sort_do_not_limit_summary(self):
        planner = self.start_with(fr9_dataset(), 6)
        planner.view.status = "Pending"
        planner.view.search = "zzz"
        planner.view.sort = core.SORT_SUBJECT
        self.assertEqual(planner.summary(date(2026, 11, 12)).lines(), [
            "Total: 5", "Completed: 1", "Remaining: 4", "Overdue: 2",
            "Completion: 20.0%"])

    def test_ac7_summary_reflects_unsaved_changes(self):
        planner = self.start_with(fr9_dataset(), 6)
        today = date(2026, 11, 12)
        self.assertEqual(planner.summary(today).completion, "20.0%")
        with failing_save():
            planner.change_status("4", "Completed")
        self.assertEqual(planner.summary(today).lines(), [
            "Total: 5", "Completed: 2", "Remaining: 3", "Overdue: 1",
            "Completion: 40.0%"])
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac8_supplied_dates(self):
        planner = self.start_with(fr9_dataset(), 6)
        self.assertEqual(planner.summary(date(2026, 11, 10)).overdue, 1)
        self.assertEqual(planner.summary(date(2026, 11, 12)).overdue, 2)

    def test_ac9_one_decimal_place(self):
        for completed, total, text in ((0, 0, "0.0%"), (3, 3, "100.0%"),
                                       (1, 3, "33.3%"), (2, 3, "66.7%"),
                                       (1, 8, "12.5%"), (1, 2, "50.0%")):
            with self.subTest(completed=completed, total=total):
                self.assertEqual(
                    core.completion_percentage(completed, total), text)

    def test_ac10_summary_changes_nothing(self):
        planner = self.start_with(fr9_dataset(), 6)
        planner.summary(date(2026, 11, 12))
        planner.summary(date(2026, 11, 12))
        self.assertStoredUnchanged(planner)


if __name__ == "__main__":
    unittest.main()
