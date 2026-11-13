"""GUI tests on a withdrawn Tk root that is destroyed after each test.

The tests drive the window through its controls' variables, buttons and
callbacks, with real data files in temporary directories. Dialog answers
are scripted through the window's ``ask_choice`` hook. All tests are
skipped, with the reason, when no display is available.
"""

import json
import tempfile
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import helpers  # puts src/ on the import path
import core
import gui


def display_error():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        return str(exc)
    root.destroy()
    return None


NO_DISPLAY = display_error()
TODAY = date(2026, 11, 12)
SAVE_FAILED = core.render_message(core.SAVE_FAILED)
NO_MATCH = core.render_message(core.NO_MATCHING_TASKS)
NO_TASKS = core.render_message(core.NO_TASKS_YET)
RETRY = core.render_message(core.EXIT_RETRY)
DISCARD = core.render_message(core.EXIT_DISCARD)
CANCEL_EXIT = core.render_message(core.EXIT_CANCEL)


def task(task_id, title="Read chapter", subject="Mathematics",
         description="", due_date="2026-11-20", priority="Medium",
         status="Pending"):
    return {"id": task_id, "title": title, "subject": subject,
            "description": description, "due_date": due_date,
            "priority": priority, "status": status}


def three_tasks():
    return [task(1, title="Essay plan", subject="History"),
            task(2, title="Read Chapter 1", due_date="2026-11-10"),
            task(3, title="Lab report", subject="Physics")]


def fr7_dataset():
    return [task(1, title="Revise Algebra", subject="Mathematics"),
            task(2, title="Essay draft", subject="History",
                 description="Check sources for the Tudor period"),
            task(3, title="Lab report", subject="Biology",
                 description="Include algebra-based calculations")]


def fr8_dataset():
    return [task(1, subject="Mathematics", priority="High"),
            task(2, subject="History", status="In Progress"),
            task(3, subject="Biology", priority="High", status="Completed"),
            task(4, subject="mathematics", priority="Low")]


def fr9_dataset():
    return [task(1, subject="Mathematics", priority="High",
                 due_date="2026-11-20"),
            task(2, subject="History", status="In Progress",
                 due_date="2026-11-10"),
            task(3, subject="biology", priority="High", status="Completed",
                 due_date="2026-11-10"),
            task(4, subject="Mathematics", priority="Low",
                 due_date="2026-11-05"),
            task(5, subject="Art", due_date="2026-11-20")]


def failing_save():
    return mock.patch.object(core.storage, "save",
                             side_effect=PermissionError("read-only"))


@unittest.skipIf(NO_DISPLAY, f"no display for Tkinter: {NO_DISPLAY}")
class GUITestCase(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / ".study_planner"
        self.path = self.folder / "tasks.json"
        self.errors = []
        self.answers = []
        self.dialogs = []
        self.today = TODAY

    def write_data(self, tasks, next_id):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"next_id": next_id,
                                         "tasks": tasks}),
                             encoding="utf-8")
        self.before = self.path.read_bytes()

    def saved_data(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def ask(self, parent, title, message, choices, stacked=False):
        self.dialogs.append((title, message, tuple(choices)))
        return self.answers.pop(0)

    def open_app(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(self.destroy, root)
        self.app = gui.start(root, self.path,
                             lambda title, text: self.errors.append(text),
                             today=lambda: self.today, ask_choice=self.ask)
        return self.app

    @staticmethod
    def destroy(root):
        try:
            root.destroy()
        except tk.TclError:
            pass

    def closed(self):
        try:
            self.app.root.winfo_exists()
        except tk.TclError:
            return True
        return False

    def assertFileUnchanged(self):
        self.assertEqual(self.path.read_bytes(), self.before)

    def row(self, task_id):
        return self.app.tree.item(str(task_id), "values")

    def secondary(self, task_id):
        return [self.app.tree.item(child, "values")[1]
                for child in self.app.tree.get_children(str(task_id))]

    def submit_form(self, form, **values):
        form.window.withdraw()
        for name, value in values.items():
            form.vars[name].set(value)
        form.save()
        return form

    def add(self, **values):
        return self.submit_form(self.app.add_task(), **values)

    def edit(self, task_id, **values):
        self.app.select(task_id)
        return self.submit_form(self.app.edit_task(), **values)

    def change_status(self, task_id, status):
        self.app.select(task_id)
        form = self.app.change_status()
        form.window.withdraw()
        initial = form.status.get()
        form.status.set(status)
        form.save()
        return initial

    def window_exists(self, form):
        try:
            return bool(form.window.winfo_exists())
        except tk.TclError:
            return False


class TestFR1AddGUI(GUITestCase):

    def test_ac1_dropdowns_start_at_defaults_and_task_appended(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        form = self.app.add_task()
        form.window.withdraw()
        self.assertEqual(form.vars["priority"].get(), "Medium")
        self.assertEqual(form.vars["status"].get(), "Pending")
        self.submit_form(form, title="Revise Algebra", subject="Mathematics",
                         due_date="2026-11-25")
        self.assertEqual(self.app.feedback.get(), "Task 5 added.")
        self.assertFalse(self.window_exists(form))
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 5])
        data = self.saved_data()
        self.assertEqual(data["next_id"], 6)
        self.assertEqual(data["tasks"][3], task(
            5, title="Revise Algebra", due_date="2026-11-25"))
        self.assertEqual(self.app.root.title(), gui.APP_TITLE)

    def test_ac2_selected_values_on_empty_list(self):
        self.open_app()
        self.add(title="Lab", subject="Biology", due_date="2026-11-30",
                 priority="High", status="Completed")
        self.assertEqual(self.saved_data()["tasks"], [task(
            1, title="Lab", subject="Biology", due_date="2026-11-30",
            priority="High", status="Completed")])

    def test_ac3_blank_title_shown_in_form_through_core(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        form = self.add(title="   ", subject="History",
                        due_date="2026-11-25")
        self.assertTrue(self.window_exists(form))
        self.assertEqual(form.errors.get(),
                         "Title must not be empty after trimming.")
        self.assertEqual(form.vars["subject"].get(), "History")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3])
        self.assertFileUnchanged()

    def test_ac4_failed_save_warning_and_title_indicator(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        with failing_save():
            self.add(title="Essay", subject="History",
                     due_date="2026-11-25")
        self.assertEqual(self.app.feedback.get(),
                         f"Task 5 added.\n{SAVE_FAILED}")
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 5])
        self.assertFileUnchanged()

    def test_form_choices_are_read_only_drop_downs(self):
        self.open_app()
        form = self.app.add_task()
        form.window.withdraw()
        for name, values in (("priority", core.PRIORITIES),
                             ("status", core.STATUSES)):
            box = form.boxes[name]
            self.assertEqual(tuple(box["values"]), values)
            self.assertEqual(str(box["state"]), "readonly")


class TestFR2EditGUI(GUITestCase):

    def setUp(self):
        super().setUp()
        self.write_data(three_tasks(), 5)
        self.open_app()

    def test_ac1_prefilled_form_submits_changed_fields_only(self):
        self.app.select(2)
        form = self.app.edit_task()
        form.window.withdraw()
        self.assertEqual(form.values(), {
            "title": "Read Chapter 1", "subject": "Mathematics",
            "description": "", "due_date": "2026-11-10",
            "priority": "Medium"})
        self.assertNotIn("status", form.vars)
        form.vars["title"].set("Read Chapter 2")
        form.vars["priority"].set("High")
        self.assertEqual(form.changed_values(), {"title": "Read Chapter 2",
                                                 "priority": "High"})
        form.save()
        self.assertEqual(self.app.feedback.get(),
                         "Task 2 updated. Changed fields: title, priority.")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3])
        saved = self.saved_data()["tasks"][1]
        self.assertEqual((saved["id"], saved["title"], saved["priority"],
                          saved["status"]),
                         (2, "Read Chapter 2", "High", "Pending"))

    def test_form_prefilled_with_non_default_priority(self):
        tasks = three_tasks()
        tasks[1]["priority"] = "High"
        self.write_data(tasks, 5)
        self.open_app()
        self.app.select(2)
        form = self.app.edit_task()
        form.window.withdraw()
        self.assertEqual(form.vars["priority"].get(), "High")
        self.assertEqual(form.changed_values(), {})

    def test_ac2_errors_in_form_nothing_changed(self):
        form = self.edit(2, title="Read Chapter 2", due_date="10/11/2026")
        self.assertTrue(self.window_exists(form))
        self.assertEqual(form.errors.get(),
                         "Due date must use the YYYY-MM-DD format.")
        self.assertEqual(self.row(2)[1], "Read Chapter 1")
        self.assertFileUnchanged()

    def test_ac5_spaces_only_change_is_a_noop(self):
        self.app.planner.unsaved = True
        with mock.patch.object(core.storage, "save") as save:
            form = self.edit(2, title=" Read Chapter 1 ")
        save.assert_not_called()
        self.assertEqual(form.changed_values(), {"title": " Read Chapter 1 "})
        self.assertEqual(self.app.feedback.get(),
                         "No changes were made to task 2.")
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)

    def test_ac6_failed_save_keeps_edit(self):
        with failing_save():
            self.edit(2, due_date="2026-11-12")
        self.assertEqual(self.app.feedback.get(),
                         f"Task 2 updated. Changed fields: due date.\n"
                         f"{SAVE_FAILED}")
        self.assertEqual(self.row(2)[2], "2026-11-12")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3])
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)
        self.assertFileUnchanged()

    def test_secondary_row_selects_its_task(self):
        child = self.app.tree.get_children("2")[0]
        self.app.tree.selection_set(child)
        form = self.app.edit_task()
        form.window.withdraw()
        self.assertEqual(form.task["id"], 2)

    def test_no_selection_asks_for_one(self):
        self.assertIsNone(self.app.edit_task())
        self.assertEqual(self.app.feedback.get(), gui.SELECT_TASK)


class TestFR3DeleteGUI(GUITestCase):

    def setUp(self):
        super().setUp()
        self.write_data(three_tasks(), 5)
        self.open_app()

    def delete(self, task_id, answer):
        self.answers.append(answer)
        self.app.select(task_id)
        self.app.delete_task()

    def test_ac1_confirm_deletes(self):
        self.delete(2, gui.CONFIRM)
        self.assertEqual(self.dialogs, [
            ("Delete task", 'Delete task 2 "Read Chapter 1"?',
             (gui.CONFIRM, gui.CANCEL))])
        self.assertEqual(self.app.feedback.get(), "Task 2 deleted.")
        self.assertEqual(self.app.displayed_ids(), [1, 3])
        data = self.saved_data()
        self.assertEqual([t["id"] for t in data["tasks"]], [1, 3])
        self.assertEqual(data["next_id"], 5)

    def test_ac2_cancel_or_close_changes_nothing(self):
        for answer in (gui.CANCEL, None):
            with self.subTest(answer=answer):
                self.delete(2, answer)
                self.assertEqual(self.app.feedback.get(),
                                 "Deletion cancelled.")
                self.assertEqual(self.app.displayed_ids(), [1, 2, 3])
                self.assertFileUnchanged()

    def test_ac5_last_task_deleted_id_not_reused(self):
        self.write_data([task(3)], 5)
        self.open_app()
        self.delete(3, gui.CONFIRM)
        self.assertEqual(self.app.message.get(), NO_TASKS)
        self.add(title="New", subject="History", due_date="2026-12-01")
        self.assertEqual(self.app.displayed_ids(), [5])

    def test_ac6_failed_save_keeps_deletion(self):
        with failing_save():
            self.delete(2, gui.CONFIRM)
        self.assertEqual(self.app.feedback.get(),
                         f"Task 2 deleted.\n{SAVE_FAILED}")
        self.assertEqual(self.app.displayed_ids(), [1, 3])
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)
        self.assertFileUnchanged()


class TestFR4StatusGUI(GUITestCase):

    def test_ac1_drop_down_starts_at_current_status(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        self.assertEqual(self.change_status(2, "In Progress"), "Pending")
        self.assertEqual(self.app.feedback.get(),
                         "Task 2 status changed to In Progress.")
        self.assertEqual(self.row(2)[4], "In Progress")
        self.assertEqual(self.saved_data()["tasks"][1]["status"],
                         "In Progress")

    def test_ac2_all_six_transitions(self):
        for old in core.STATUSES:
            for new in core.STATUSES:
                if old == new:
                    continue
                with self.subTest(old=old, new=new):
                    tasks = three_tasks()
                    tasks[1]["status"] = old
                    self.write_data(tasks, 5)
                    self.open_app()
                    self.assertEqual(self.change_status(2, new), old)
                    self.assertEqual(self.saved_data()["tasks"][1]["status"],
                                     new)

    def test_ac3_same_status_saves_nothing(self):
        tasks = three_tasks()
        tasks[1]["status"] = "Completed"
        self.write_data(tasks, 5)
        self.open_app()
        self.change_status(2, "Completed")
        self.assertEqual(self.app.feedback.get(), "Task 2 already has status "
                         "Completed; the status is unchanged.")
        self.assertFileUnchanged()

    def test_ac4_drop_down_offers_only_permitted_values(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        self.app.select(2)
        form = self.app.change_status()
        form.window.withdraw()
        self.assertEqual(tuple(form.box["values"]), core.STATUSES)
        self.assertEqual(str(form.box["state"]), "readonly")

    def test_ac6_failed_save_keeps_status(self):
        tasks = three_tasks()
        tasks[1]["status"] = "In Progress"
        self.write_data(tasks, 5)
        self.open_app()
        with failing_save():
            self.assertEqual(self.change_status(2, "Completed"),
                             "In Progress")
        self.assertEqual(self.app.feedback.get(),
                         f"Task 2 status changed to Completed.\n{SAVE_FAILED}")
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)
        self.assertFileUnchanged()


class TestFR6StartGUI(GUITestCase):

    def test_ac1_missing_file_add_creates_file_restart_loads(self):
        self.open_app()
        self.assertEqual(self.app.root.title(), gui.APP_TITLE)
        self.assertEqual(self.app.message.get(), NO_TASKS)
        self.assertFalse(self.folder.exists())
        self.add(title="Revise Algebra", subject="Mathematics",
                 due_date="2026-11-20")
        self.assertEqual(self.saved_data(), {"next_id": 2, "tasks": [task(
            1, title="Revise Algebra")]})
        self.open_app()
        self.assertEqual(self.app.displayed_ids(), [1])
        self.assertEqual(self.app.root.title(), gui.APP_TITLE)

    def test_ac2_file_order_and_accented_subject_kept(self):
        self.write_data([task(2), task(5, subject="Économie"), task(3)], 7)
        self.open_app()
        self.assertEqual(self.app.displayed_ids(), [2, 5, 3])
        self.assertEqual(self.secondary(5), ["Subject: Économie"])
        self.assertEqual(self.app.planner.next_id, 7)

    def test_ac3_invalid_file_does_not_start_and_is_unchanged(self):
        for contents in ("", json.dumps({"next_id": 2, "tasks": [
                task(1, priority="high")]})):
            with self.subTest(contents=contents[:20]):
                self.folder.mkdir(parents=True, exist_ok=True)
                self.path.write_text(contents, encoding="utf-8")
                before = self.path.read_bytes()
                self.errors.clear()
                self.assertIsNone(self.open_app())
                self.assertEqual(self.errors, [core.render_message(
                    core.INVALID_STORED_DATA, path=self.path)])
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(sorted(p.name for p in
                                        self.folder.iterdir()),
                                 ["tasks.json"])

    def test_ac4_empty_list_keeps_next_id_and_file(self):
        self.write_data([], 4)
        self.open_app()
        self.assertEqual(self.app.message.get(), NO_TASKS)
        self.assertFileUnchanged()
        self.add(title="Essay", subject="History", due_date="2026-11-25")
        self.assertEqual(self.app.displayed_ids(), [4])

    def test_ac5_edit_saved_without_temporary_file(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        self.edit(2, title="Updated title")
        self.assertEqual(self.saved_data()["tasks"][1]["title"],
                         "Updated title")
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()),
                         ["tasks.json"])
        saved = self.path.read_bytes()
        self.edit(2, title="Updated title")
        self.assertEqual(self.path.read_bytes(), saved)

    def test_ac6_failed_save_then_next_change_saves_everything(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        with failing_save():
            self.edit(2, title="Updated title")
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)
        self.assertFileUnchanged()
        self.change_status(3, "In Progress")
        self.assertEqual(self.app.root.title(), gui.APP_TITLE)
        tasks = self.saved_data()["tasks"]
        self.assertEqual(tasks[1]["title"], "Updated title")
        self.assertEqual(tasks[2]["status"], "In Progress")

    def test_unexpected_error_at_start_up(self):
        with mock.patch.object(core.storage, "load",
                               side_effect=RuntimeError("boom")):
            with self.assertLogs("study_planner", "ERROR"):
                self.assertIsNone(self.open_app())
        self.assertEqual(self.errors, [core.render_message(
            core.INTERNAL_ERROR)])


class TestFR6ExitGUI(GUITestCase):

    def unsaved_app(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        with failing_save():
            self.edit(2, title="Updated title")

    def test_ac7_retry_succeeds_and_closes(self):
        self.unsaved_app()
        self.answers.append(RETRY)
        self.app.exit()
        self.assertTrue(self.closed())
        self.assertEqual(self.dialogs[0][2], (RETRY, DISCARD, CANCEL_EXIT))
        self.assertEqual(self.saved_data()["tasks"][1]["title"],
                         "Updated title")

    def test_ac7_retry_fails_and_choices_shown_again(self):
        self.unsaved_app()
        self.answers.extend([RETRY, CANCEL_EXIT])
        with failing_save():
            self.app.exit()
        self.assertFalse(self.closed())
        self.assertEqual(len(self.dialogs), 2)
        self.assertIn(core.render_message(core.RETRY_FAILED),
                      self.dialogs[1][1])
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)
        self.assertFileUnchanged()

    def test_ac7_exit_without_saving_states_loss(self):
        self.unsaved_app()
        self.answers.append(DISCARD)
        self.app.exit()
        self.assertTrue(self.closed())
        self.assertIn("will be lost", DISCARD)
        self.assertFileUnchanged()

    def test_ac7_cancel_and_close_keep_window_and_changes(self):
        for answer in (CANCEL_EXIT, None):
            with self.subTest(answer=answer):
                self.unsaved_app()
                self.answers.append(answer)
                self.app.exit()
                self.assertFalse(self.closed())
                self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)
                self.assertEqual(self.row(2)[1], "Updated title")

    def test_ac7_nothing_unsaved_closes_without_prompt(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        self.app.exit()
        self.assertTrue(self.closed())
        self.assertEqual(self.dialogs, [])

    def test_ac7_x_button_offers_the_same_choices(self):
        self.unsaved_app()
        self.answers.append(CANCEL_EXIT)
        handler = self.app.root.protocol("WM_DELETE_WINDOW")
        self.app.root.tk.call(handler)
        self.assertEqual(self.dialogs[0][2], (RETRY, DISCARD, CANCEL_EXIT))
        self.assertFalse(self.closed())
        self.answers.append(DISCARD)
        self.app.root.tk.call(handler)
        self.assertTrue(self.closed())


class TestFR7SearchGUI(GUITestCase):

    def setUp(self):
        super().setUp()
        self.write_data(fr7_dataset(), 4)
        self.open_app()

    def test_ac1_ac2_ac4_queries(self):
        for query, expected in (("REVISE", [1]), ("tudor", [2]),
                                ("BIO", [3]), ("algebra", [1, 3]),
                                ("", [1, 2, 3]), ("   ", [1, 2, 3]),
                                ("  essay draft  ", [2]),
                                ("essay  draft", [])):
            with self.subTest(query=query):
                self.app.search.set(query)
                self.assertEqual(self.app.displayed_ids(), expected)
                self.assertEqual(self.app.message.get(),
                                 "" if expected else NO_MATCH)
        self.assertFileUnchanged()

    def test_ac3_no_match_and_empty_list_label(self):
        self.app.search.set("physics")
        self.assertEqual(self.app.message.get(), NO_MATCH)
        self.write_data([], 1)
        self.open_app()
        self.app.search.set("essay")
        self.assertEqual(self.app.message.get(), NO_TASKS)

    def test_ac5_search_with_subject_filter(self):
        for subject, expected in (("", [1, 3]), ("Mathematics", [1]),
                                  ("Biology", [3])):
            with self.subTest(subject=subject):
                self.app.search.set("algebra")
                self.app.subject_filter.set(subject)
                self.assertEqual(self.app.displayed_ids(), expected)
        self.app.search.set("essay")
        self.app.subject_filter.set("Mathematics")
        self.assertEqual(self.app.message.get(), NO_MATCH)

    def test_ac6_casefold_sharp_s(self):
        self.write_data(fr7_dataset() + [task(4, title="Straße survey",
                                              subject="Geography")], 5)
        self.open_app()
        self.app.search.set("STRASSE")
        self.assertEqual(self.app.displayed_ids(), [4])
        self.assertFileUnchanged()

    def test_ac7_search_persists_and_resets_on_restart(self):
        self.app.search.set("algebra")
        self.add(title="Algebra quiz", subject="Mathematics",
                 due_date="2026-11-20")
        self.assertEqual(self.app.displayed_ids(), [1, 3, 4])
        self.add(title="History notes", subject="History",
                 due_date="2026-11-20")
        self.assertEqual(self.app.displayed_ids(), [1, 3, 4])
        self.assertEqual(self.app.search.get(), "algebra")
        self.app.search.set("")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4, 5])
        self.open_app()
        self.assertEqual(self.app.search.get(), "")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4, 5])
        self.assertEqual(set(self.saved_data()), {"next_id", "tasks"})


class TestFR8FiltersGUI(GUITestCase):

    def setUp(self):
        super().setUp()
        self.write_data(fr8_dataset(), 5)
        self.open_app()

    def apply(self, status=core.ALL, priority=core.ALL, subject=""):
        self.app.status_filter.set(status)
        self.app.priority_filter.set(priority)
        self.app.subject_filter.set(subject)
        return self.app.displayed_ids()

    def test_expected_results_and_and_logic(self):
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
                self.assertEqual(self.apply(**filters), expected)
                self.assertEqual(self.app.message.get(),
                                 "" if expected else NO_MATCH)
        self.assertEqual(self.saved_data()["tasks"][3]["subject"],
                         "mathematics")
        self.assertFileUnchanged()

    def test_ac1_all_clears_and_selection_stays_visible(self):
        self.apply(status="Pending")
        self.assertEqual(self.app.status_box.get(), "Pending")
        self.assertEqual(self.apply(), [1, 2, 3, 4])
        self.assertEqual(self.app.planner.view, core.ViewState())

    def test_ac4_drop_downs_offer_only_valid_values_and_all(self):
        self.assertEqual(tuple(self.app.status_box["values"]),
                         (core.ALL,) + core.STATUSES)
        self.assertEqual(tuple(self.app.priority_box["values"]),
                         (core.ALL,) + core.PRIORITIES)
        for box in (self.app.status_box, self.app.priority_box):
            self.assertEqual(str(box["state"]), "readonly")

    def test_ac5_filter_persists_and_resets_on_restart(self):
        self.apply(status="Pending")
        self.add(title="Lab", subject="Physics", due_date="2026-11-20")
        self.assertEqual(self.app.displayed_ids(), [1, 4, 5])
        self.add(title="Quiz", subject="Physics", due_date="2026-11-20",
                 status="Completed")
        self.assertEqual(self.app.displayed_ids(), [1, 4, 5])
        self.assertEqual(self.app.status_filter.get(), "Pending")
        self.assertEqual(self.apply(), [1, 2, 3, 4, 5, 6])
        self.open_app()
        self.assertEqual(self.app.status_filter.get(), core.ALL)
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4, 5, 6])

    def test_ac7_empty_list_with_filter(self):
        self.write_data([], 5)
        self.open_app()
        self.apply(status="Pending")
        self.assertEqual(self.app.message.get(), NO_TASKS)
        self.assertFileUnchanged()

    def test_ac8_subject_all_and_clear_control(self):
        self.write_data(fr8_dataset() + [task(5, subject="All")], 6)
        self.open_app()
        self.assertEqual(self.apply(subject="All"), [5])
        self.app.clear_subject_filter()
        self.assertEqual(self.app.subject_filter.get(), "")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4, 5])
        self.assertFileUnchanged()


class TestFR9SortGUI(GUITestCase):

    def setUp(self):
        super().setUp()
        self.write_data(fr9_dataset(), 6)
        self.open_app()

    def test_sort_by_options(self):
        self.assertEqual(tuple(self.app.sort_box["values"]),
                         ("None", "Due date", "Priority", "Status",
                          "Subject"))
        self.assertEqual(self.app.sort.get(), "None")

    def test_ac1_to_ac5_orders(self):
        for label, expected in (("None", [1, 2, 3, 4, 5]),
                                ("Due date", [4, 2, 3, 1, 5]),
                                ("Priority", [3, 1, 2, 5, 4]),
                                ("Status", [4, 1, 5, 2, 3]),
                                ("Subject", [5, 3, 2, 4, 1])):
            with self.subTest(label=label):
                self.app.sort.set(label)
                self.assertEqual(self.app.displayed_ids(), expected)
        self.assertEqual([t["id"] for t in self.app.planner.tasks],
                         [1, 2, 3, 4, 5])
        self.assertFileUnchanged()

    def test_ac6_filter_then_sort(self):
        self.app.status_filter.set("Pending")
        self.app.sort.set("Due date")
        self.assertEqual(self.app.displayed_ids(), [4, 1, 5])

    def test_ac9_change_and_clear(self):
        self.app.sort.set("Priority")
        self.app.sort.set("Status")
        self.assertEqual(self.app.displayed_ids(), [4, 1, 5, 2, 3])
        self.app.sort.set("None")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4, 5])

    def test_ac10_restart_has_no_sort(self):
        self.app.sort.set("Subject")
        self.open_app()
        self.assertEqual(self.app.sort.get(), "None")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4, 5])

    def test_ac11_sort_kept_after_add(self):
        self.app.sort.set("Due date")
        self.add(title="New", subject="History", due_date="2026-11-10")
        self.assertEqual(self.app.sort.get(), "Due date")
        self.assertEqual(self.app.displayed_ids(), [4, 2, 3, 6, 1, 5])
        self.assertEqual([t["id"] for t in self.saved_data()["tasks"]],
                         [1, 2, 3, 4, 5, 6])


class TestFR10SummaryGUI(GUITestCase):

    def lines(self):
        return [var.get() for var in self.app.summary_lines]

    def test_ac1_and_ac9_labels(self):
        self.write_data(fr9_dataset(), 6)
        self.open_app()
        self.assertEqual(self.lines(), [
            "Total: 5", "Completed: 1", "Remaining: 4", "Overdue: 2",
            "Completion: 20.0%"])

    def test_ac3_and_ac9_empty_list(self):
        self.open_app()
        self.assertEqual(self.lines(), [
            "Total: 0", "Completed: 0", "Remaining: 0", "Overdue: 0",
            "Completion: 0.0%"])

    def test_ac4_half_up_percentage(self):
        tasks = [task(n) for n in range(1, 17)]
        tasks[0]["status"] = "Completed"
        self.write_data(tasks, 17)
        self.open_app()
        self.assertEqual(self.lines()[4], "Completion: 6.3%")

    def test_ac5_and_ac9_all_completed(self):
        self.write_data([task(n, status="Completed", due_date="2026-01-01")
                         for n in (1, 2, 3)], 4)
        self.open_app()
        self.assertEqual(self.lines()[2:], [
            "Remaining: 0", "Overdue: 0", "Completion: 100.0%"])

    def test_ac6_filters_do_not_limit_summary(self):
        self.write_data(fr9_dataset(), 6)
        self.open_app()
        self.app.status_filter.set("Pending")
        self.app.search.set("zzz")
        self.assertEqual(self.lines()[0], "Total: 5")
        self.assertEqual(self.lines()[3], "Overdue: 2")

    def test_ac7_summary_updates_after_unsaved_change(self):
        self.write_data(fr9_dataset(), 6)
        self.open_app()
        with failing_save():
            self.change_status(4, "Completed")
        self.assertEqual(self.lines(), [
            "Total: 5", "Completed: 2", "Remaining: 3", "Overdue: 1",
            "Completion: 40.0%"])
        self.assertFileUnchanged()

    def test_ac8_refresh_recalculates_with_current_date(self):
        self.write_data(fr9_dataset(), 6)
        self.today = date(2026, 11, 10)
        self.open_app()
        self.assertEqual(self.lines()[3], "Overdue: 1")
        self.today = date(2026, 11, 12)
        self.app.refresh_summary()
        self.assertEqual(self.lines()[3], "Overdue: 2")

    def test_ac10_summary_changes_nothing(self):
        self.write_data(fr9_dataset(), 6)
        self.open_app()
        self.app.refresh_summary()
        self.app.refresh_summary()
        self.assertFileUnchanged()

    def test_default_date_is_the_local_date(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(self.destroy, root)
        app = gui.StudyPlannerGUI(root, core.Planner(self.path, [], 1))
        self.assertEqual(app.today(), date.today())


class TestFR11ListGUI(GUITestCase):

    def test_ac1_rows_and_secondary_rows(self):
        self.write_data(fr7_dataset(), 4)
        self.open_app()
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3])
        self.assertEqual(self.row(1), ("1", "Revise Algebra", "2026-11-20",
                                       "Medium", "Pending"))
        self.assertEqual(self.secondary(1), ["Subject: Mathematics"])
        self.assertEqual(self.secondary(2), [
            "Subject: History", "Check sources for the Tudor period"])
        columns = [self.app.tree.heading(c[0], "text") for c in gui.COLUMNS]
        self.assertEqual(columns, ["ID", "Title", "Due Date", "Priority",
                                   "Status"])
        self.assertEqual(self.app.message.get(), "")
        self.assertFileUnchanged()

    def test_title_column_fixed_and_full_title_kept(self):
        title = "Prepare revision notes for the final exam " * 3
        self.write_data([task(1, title=title.strip())], 2)
        self.open_app()
        self.assertFalse(self.app.tree.column("title", "stretch"))
        self.assertEqual(self.row(1)[1], title.strip())

    def test_ac2_empty_list_label_with_and_without_filter(self):
        self.open_app()
        self.assertEqual(self.app.message.get(), NO_TASKS)
        self.app.status_filter.set("Pending")
        self.assertEqual(self.app.message.get(), NO_TASKS)
        self.assertFalse(self.folder.exists())

    def test_ac3_stored_order_after_add_edit_delete_restart(self):
        self.write_data([task(1, due_date="2026-11-30"),
                         task(2, due_date="2026-11-20"),
                         task(3, due_date="2026-11-10")], 4)
        self.open_app()
        self.add(title="Fourth", subject="History", due_date="2026-11-25")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4])
        self.edit(2, title="Renamed")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4])
        self.answers.append(gui.CONFIRM)
        self.app.select(2)
        self.app.delete_task()
        self.assertEqual(self.app.displayed_ids(), [1, 3, 4])
        self.open_app()
        self.assertEqual(self.app.displayed_ids(), [1, 3, 4])

    def test_ac4_sort_and_search_then_cleared(self):
        self.write_data([task(1, due_date="2026-11-30"),
                         task(2, due_date="2026-11-20"),
                         task(3, due_date="2026-11-10")], 4)
        self.open_app()
        self.app.sort.set("Due date")
        self.assertEqual(self.app.displayed_ids(), [3, 2, 1])
        self.app.sort.set("None")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3])
        self.app.search.set("zzz")
        self.assertEqual(self.app.message.get(), NO_MATCH)
        self.app.search.set("")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3])

    def test_ac5_unsaved_changes_listed(self):
        self.write_data(fr7_dataset(), 4)
        self.open_app()
        with failing_save():
            self.add(title="Quiz", subject="History", due_date="2026-11-25")
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3, 4])
        self.assertEqual(self.app.root.title(), gui.UNSAVED_TITLE)

    def test_selection_kept_after_refresh(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        self.app.select(2)
        self.app.search.set("chapter")
        self.assertEqual(self.app.tree.selection(), ("2",))


class TestDialogsAndErrors(GUITestCase):

    def test_choice_dialog_returns_choice_or_none_when_closed(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(self.destroy, root)
        dialog = gui.ChoiceDialog(root, "Delete task", "Delete?",
                                  (gui.CONFIRM, gui.CANCEL))
        dialog.window.withdraw()
        dialog.buttons[gui.CONFIRM].invoke()
        self.assertEqual(dialog.result, gui.CONFIRM)
        dialog = gui.ChoiceDialog(root, "Delete task", "Delete?",
                                  (gui.CONFIRM, gui.CANCEL))
        dialog.window.withdraw()
        dialog.window.tk.call(dialog.window.protocol("WM_DELETE_WINDOW"))
        self.assertIsNone(dialog.result)

    def test_form_cancel_changes_nothing(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        form = self.app.add_task()
        form.window.withdraw()
        form.vars["title"].set("Unsaved draft")
        form.window.destroy()
        self.assertEqual(self.app.displayed_ids(), [1, 2, 3])
        self.assertFileUnchanged()

    def test_callback_error_logged_without_task_content(self):
        self.write_data(three_tasks(), 5)
        self.open_app()
        error = RuntimeError("secret task title")
        with self.assertLogs("study_planner", "ERROR") as logs:
            self.app.root.report_callback_exception(RuntimeError, error,
                                                    None)
        self.assertEqual(self.app.feedback.get(),
                         core.render_message(core.INTERNAL_ERROR))
        self.assertIn("RuntimeError", "\n".join(logs.output))
        self.assertNotIn("secret task title", "\n".join(logs.output))

    def test_gui_does_not_import_storage(self):
        self.assertFalse(hasattr(gui, "storage"))


if __name__ == "__main__":
    unittest.main()
