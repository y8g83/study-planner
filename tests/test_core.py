"""Core task-operation tests: FR1-FR4, the list view and the messages.

Every test works on a planner whose data file lies in its own temporary
directory. A failed save is simulated by making ``storage.save`` raise
``OSError``.
"""

import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
