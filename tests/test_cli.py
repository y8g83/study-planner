"""CLI tests: scripted input, captured output and real data files.

Each test runs ``cli.main`` on a data file in its own temporary directory.
The fake console records every prompt and output line, so tests can check
both the exact text and the order in which questions are asked.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # puts src/ on the import path
import cli
import core


def task(task_id, title="Read chapter", subject="Mathematics",
         description="", due_date="2026-11-20", priority="Medium",
         status="Pending"):
    return {"id": task_id, "title": title, "subject": subject,
            "description": description, "due_date": due_date,
            "priority": priority, "status": status}


def three_tasks():
    return [task(1, title="Essay plan", subject="History"),
            task(2, title="Original title", due_date="2026-11-10"),
            task(3, title="Lab report", subject="Physics")]


def failing_save():
    return mock.patch.object(core.storage, "save",
                             side_effect=PermissionError("read-only"))


# Expected tables of FR11 AC1 (default view) and AC6 (layout boundaries).
DEFAULT_VIEW = """\
ID | Title                          | Due Date   | Priority | Status
-------------------------------------------------------------------------
1  | Revise Algebra                 | 2026-11-20 | Medium   | Pending
     Subject: Mathematics
2  | Essay draft                    | 2026-11-20 | Medium   | Pending
     Subject: History
     Check sources for the Tudor period
3  | Lab report                     | 2026-11-20 | Medium   | Pending
     Subject: Biology
     Include algebra-based calculations
""".splitlines()

LAYOUT_BOUNDARIES = """\
ID | Title                          | Due Date   | Priority | Status
-------------------------------------------------------------------------
1  | AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA | 2026-11-20 | Medium   | Pending
     Subject: Mathematics
2  | Prepare revision notes for the | 2026-11-20 | Medium   | In Progress
   | final exam                     |            |          |
     Subject: History
3  | Supercalifragilisticexpialidoc | 2026-11-20 | High     | Pending
   | iousrevisionplan               |            |          |
     Subject: Biology
10 | Short                          | 2026-11-20 | Medium   | Pending
     Subject: mathematics
     Read the assigned chapter carefully the assigned chapter carefully
     the assigned chapter carefully
""".splitlines()


SAVE_FAILED = core.render_message(core.SAVE_FAILED)
UNSAVED = core.render_message(core.UNSAVED_INDICATOR)


class FakeConsole:
    """Feeds scripted answers and records prompts and output lines."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []
        self.lines = []
        self.events = []

    def read(self, prompt=""):
        self.prompts.append(prompt)
        self.events.append(("prompt", prompt))
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def write(self, text=""):
        self.lines.append(text)
        self.events.append(("line", text))


class CLITestCase(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / ".study_planner"
        self.path = self.folder / "tasks.json"

    def write_data(self, tasks, next_id):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"next_id": next_id,
                                         "tasks": tasks}),
                             encoding="utf-8")

    def saved_data(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def run_cli(self, *answers):
        console = FakeConsole(answers)
        self.status = cli.main(self.path, console.read, console.write)
        return console

    def assertPromptNotShown(self, console, text):
        self.assertFalse(any(text in prompt for prompt in console.prompts),
                         f"unexpected prompt containing {text!r}")


class TestFR6StartAndSave(CLITestCase):

    def test_ac1_missing_file_add_creates_file_restart_loads(self):
        console = self.run_cli("2", "Revise Algebra", "Mathematics", "",
                               "2026-11-20", "", "", "0")
        self.assertEqual(self.status, 0)
        self.assertIn("Task 1 added.", console.lines)
        self.assertNotIn(UNSAVED, console.lines)
        self.assertEqual(self.saved_data(), {"next_id": 2, "tasks": [task(
            1, title="Revise Algebra")]})
        console = self.run_cli("1", "0")
        self.assertIn("1  | Revise Algebra                 | 2026-11-20 | "
                      "Medium   | Pending", console.lines)

    def test_ac1_missing_file_view_creates_nothing(self):
        console = self.run_cli("1", "0")
        self.assertIn("No tasks yet.", console.lines)
        self.assertFalse(self.folder.exists())

    def test_ac2_file_order_and_accented_subject_kept(self):
        self.write_data([task(2, title="Two"),
                         task(5, title="Five", subject="Économie"),
                         task(3, title="Three")], 7)
        console = self.run_cli("1", "0")
        rows = [line for line in console.lines if " | 2026-" in line]
        self.assertEqual([row.split()[0] for row in rows], ["2", "5", "3"])
        self.assertIn("     Subject: Économie", console.lines)
        self.assertNotIn(UNSAVED, console.lines)

    def test_ac3_invalid_file_does_not_start_and_is_unchanged(self):
        valid = {"next_id": 2, "tasks": [task(1)]}
        cases = {
            "empty file": "",
            "extra top-level key": json.dumps({**valid, "backup": []}),
            "non-canonical priority": json.dumps(
                {"next_id": 2, "tasks": [task(1, priority="high")]}),
        }
        for name, contents in cases.items():
            with self.subTest(name):
                self.folder.mkdir(parents=True, exist_ok=True)
                self.path.write_text(contents, encoding="utf-8")
                before = self.path.read_bytes()
                console = self.run_cli("0")
                self.assertEqual(self.status, 1)
                self.assertEqual(console.lines, [core.render_message(
                    core.INVALID_STORED_DATA, path=self.path)])
                self.assertEqual(console.prompts, [])
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(sorted(p.name for p in
                                        self.folder.iterdir()),
                                 ["tasks.json"])

    def test_ac4_empty_list_keeps_next_id_and_file(self):
        self.write_data([], 4)
        before = self.path.read_bytes()
        console = self.run_cli("1", "2", "Essay", "History", "",
                               "2026-11-25", "", "", "0")
        self.assertIn("No tasks yet.", console.lines)
        self.assertIn("Task 4 added.", console.lines)
        self.assertNotEqual(self.path.read_bytes(), before)

    def test_ac4_viewing_does_not_rewrite_file(self):
        self.write_data([], 4)
        before = self.path.read_bytes()
        self.run_cli("1", "0")
        self.assertEqual(self.path.read_bytes(), before)

    def test_ac6_failed_save_indicator_then_retry_by_next_change(self):
        self.write_data(three_tasks(), 5)
        before = self.path.read_bytes()
        console = FakeConsole(["3", "2", "1", "Updated title"])
        app = cli.StudyPlannerCLI(core.start(self.path).planner,
                                  console.read, console.write)
        with failing_save():
            app.run()
        self.assertIn("Task 2 updated. Changed fields: title.",
                      console.lines)
        self.assertIn(SAVE_FAILED, console.lines)
        self.assertEqual(console.lines.count(UNSAVED), 1)
        self.assertEqual(self.path.read_bytes(), before)

        console.answers = ["5", "3", "In Progress", "0"]
        app.run()
        self.assertEqual(console.lines.count(UNSAVED), 2)
        last_menu = len(console.lines) - console.lines[::-1].index(
            "Study Planner") - 1
        self.assertNotIn(UNSAVED, console.lines[last_menu:])
        tasks = self.saved_data()["tasks"]
        self.assertEqual(tasks[1]["title"], "Updated title")
        self.assertEqual(tasks[2]["status"], "In Progress")


class TestFR6Exit(CLITestCase):

    def unsaved_session(self, *answers):
        """Start with saved data, make an edit fail to save, then answer."""
        self.write_data(three_tasks(), 5)
        self.before = self.path.read_bytes()
        console = FakeConsole(["3", "2", "1", "Updated title"])
        self.app = cli.StudyPlannerCLI(core.start(self.path).planner,
                                       console.read, console.write)
        with failing_save():
            self.app.run()
        console.answers = list(answers)
        return console

    def exit_choices_shown(self, console):
        return console.lines.count(core.render_message(core.EXIT_UNSAVED))

    def test_ac7_retry_succeeds_and_exits(self):
        console = self.unsaved_session("0", "1")
        self.assertEqual(self.app.run(), 0)
        self.assertIn(core.render_message(core.ALL_SAVED), console.lines)
        self.assertEqual(self.saved_data()["tasks"][1]["title"],
                         "Updated title")
        self.assertFalse(self.app.planner.unsaved)

    def test_ac7_retry_fails_and_choices_shown_again(self):
        console = self.unsaved_session("0", "1", "3", "0", "2")
        with failing_save():
            self.assertEqual(self.app.run(), 0)
        self.assertIn(core.render_message(core.RETRY_FAILED), console.lines)
        self.assertEqual(self.exit_choices_shown(console), 3)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac7_exit_without_saving_states_loss(self):
        console = self.unsaved_session("0", "2")
        self.assertEqual(self.app.run(), 0)
        self.assertIn("2. " + core.render_message(core.EXIT_DISCARD),
                      console.lines)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac7_cancel_returns_to_menu_unsaved(self):
        console = self.unsaved_session("0", "3", "1", "0", "2")
        self.app.run()
        after_cancel = console.lines[console.lines.index(
            core.render_message(core.EXIT_UNSAVED)):]
        self.assertIn(UNSAVED, after_cancel)
        self.assertIn("2  | Updated title                  | 2026-11-10 | "
                      "Medium   | Pending", after_cancel)

    def test_ac7_nothing_unsaved_exits_without_prompt(self):
        self.write_data(three_tasks(), 5)
        console = self.run_cli("0")
        self.assertEqual(self.status, 0)
        self.assertEqual(console.prompts, ["Choose an option: "])
        self.assertNotIn(core.render_message(core.EXIT_UNSAVED),
                         console.lines)


class TestFR1Add(CLITestCase):

    def test_ac1_empty_priority_and_status_use_defaults(self):
        self.write_data(three_tasks(), 5)
        console = self.run_cli("2", "Revise Algebra", "Mathematics", "",
                               "2026-11-25", "", "", "0")
        self.assertIn("Task 5 added.", console.lines)
        self.assertNotIn(SAVE_FAILED, console.lines)
        data = self.saved_data()
        self.assertEqual(data["next_id"], 6)
        self.assertEqual(data["tasks"][:3], three_tasks())
        self.assertEqual(data["tasks"][3], task(
            5, title="Revise Algebra", due_date="2026-11-25"))

    def test_ac3_blank_title_reports_error_through_core(self):
        self.write_data(three_tasks(), 5)
        before = self.path.read_bytes()
        console = self.run_cli("2", "   ", "History", "", "2026-11-25",
                               "", "", "0")
        self.assertIn("Title must not be empty after trimming.",
                      console.lines)
        self.assertEqual(self.path.read_bytes(), before)

    def test_all_errors_reported_together(self):
        console = self.run_cli("2", "", "", "", "2026-02-30", "Urgent", "",
                               "0")
        start = console.lines.index(
            "Title must not be empty after trimming.")
        self.assertEqual(console.lines[start:start + 4], [
            "Title must not be empty after trimming.",
            "Subject must not be empty after trimming.",
            "Due date must be a real calendar date.",
            "Priority must exactly match one of the permitted values."])
        self.assertFalse(self.path.exists())

    def test_ac4_failed_save_shows_id_and_warning(self):
        self.write_data(three_tasks(), 5)
        with failing_save():
            console = self.run_cli("2", "Essay", "History", "",
                                   "2026-11-25", "", "", "0", "2")
        added = console.lines.index("Task 5 added.")
        self.assertEqual(console.lines[added + 1], SAVE_FAILED)
        self.assertIn(UNSAVED, console.lines[added:])


class TestFR2Edit(CLITestCase):

    def setUp(self):
        super().setUp()
        tasks = three_tasks()
        tasks[1]["title"] = "Read Chapter 1"
        self.write_data(tasks, 5)
        self.before = self.path.read_bytes()

    def test_ac1_selected_fields_changed(self):
        console = self.run_cli("3", "2", "1,5", "Read Chapter 2", "High",
                               "0")
        self.assertIn("Task 2 updated. Changed fields: title, priority.",
                      console.lines)
        self.assertEqual(console.prompts[3:5], [
            "New title (current: Read Chapter 1): ",
            "New priority (current: Medium): "])
        saved = self.saved_data()["tasks"][1]
        self.assertEqual((saved["id"], saved["title"], saved["priority"]),
                         (2, "Read Chapter 2", "High"))

    def test_ac2_both_errors_reported_nothing_changed(self):
        console = self.run_cli("3", "2", "1, 4, 5", "Read Chapter 2",
                               "10/11/2026", "Urgent", "0")
        self.assertIn("Due date must use the YYYY-MM-DD format.",
                      console.lines)
        self.assertIn(
            "Priority must exactly match one of the permitted values.",
            console.lines)
        self.assertFalse(any(line.startswith("Task 2 updated")
                             for line in console.lines))
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac3_leading_zero_rejected_before_field_question(self):
        console = self.run_cli("3", "007", "0")
        self.assertIn(core.render_message(
            core.INVALID_TASK_ID_FORMAT, field=core.TASK_ID), console.lines)
        self.assertPromptNotShown(console, "Fields to edit")
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac4_missing_task_rejected_before_field_question(self):
        console = self.run_cli("3", "4", "0")
        self.assertIn("No task with ID 4 exists.", console.lines)
        self.assertPromptNotShown(console, "Fields to edit")
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac5_noop_edit_saves_nothing(self):
        console = self.run_cli("3", "2", "1,5", " Read Chapter 1 ",
                               "medium", "0")
        self.assertIn("No changes were made to task 2.", console.lines)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac6_failed_save_shows_changed_field_and_warning(self):
        with failing_save():
            console = self.run_cli("3", "2", "4", "2026-11-12", "0", "2")
        changed = console.lines.index(
            "Task 2 updated. Changed fields: due date.")
        self.assertEqual(console.lines[changed + 1], SAVE_FAILED)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_invalid_field_selection_changes_nothing(self):
        for selection in ("", "6", "title", "1,,2", "0"):
            with self.subTest(selection=selection):
                console = self.run_cli("3", "2", selection, "0")
                self.assertIn(cli.INVALID_FIELD_SELECTION, console.lines)
                self.assertPromptNotShown(console, "New ")
                self.assertEqual(self.path.read_bytes(), self.before)


class TestFR3Delete(CLITestCase):

    def setUp(self):
        super().setUp()
        self.write_data(three_tasks(), 5)
        self.before = self.path.read_bytes()

    def test_ac1_confirmed_deletion(self):
        console = self.run_cli("4", "2", "y", "0")
        self.assertIn('Delete task 2 "Original title"? (y/n): ',
                      console.prompts)
        self.assertIn("Task 2 deleted.", console.lines)
        data = self.saved_data()
        self.assertEqual([t["id"] for t in data["tasks"]], [1, 3])
        self.assertEqual(data["next_id"], 5)

    def test_ac2_cancelled_deletion_saves_nothing(self):
        for answer in ("n", "", "no"):
            with self.subTest(answer=answer):
                console = self.run_cli("4", "2", answer, "0")
                self.assertIn("Deletion cancelled.", console.lines)
                self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac3_plus_sign_rejected_before_confirmation(self):
        console = self.run_cli("4", "+2", "0")
        self.assertIn(core.render_message(
            core.INVALID_TASK_ID_FORMAT, field=core.TASK_ID), console.lines)
        self.assertPromptNotShown(console, "Delete task")
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac4_missing_task_rejected_before_confirmation(self):
        console = self.run_cli("4", "4", "0")
        self.assertIn("No task with ID 4 exists.", console.lines)
        self.assertPromptNotShown(console, "Delete task")

    def test_ac6_failed_save_keeps_deletion_in_memory(self):
        with failing_save():
            console = self.run_cli("4", "2", "yes", "1", "0", "2")
        deleted = console.lines.index("Task 2 deleted.")
        self.assertEqual(console.lines[deleted + 1], SAVE_FAILED)
        rows = [line for line in console.lines if " | 2026-" in line]
        self.assertEqual([row.split()[0] for row in rows], ["1", "3"])
        self.assertEqual(self.path.read_bytes(), self.before)


class TestFR4Status(CLITestCase):

    def setUp(self):
        super().setUp()
        self.write_data(three_tasks(), 5)
        self.before = self.path.read_bytes()

    def test_ac1_lowercase_status_stored_canonical(self):
        console = self.run_cli("5", "2", "in progress", "0")
        self.assertIn("Task 2 status changed to In Progress.",
                      console.lines)
        self.assertEqual(self.saved_data()["tasks"][1]["status"],
                         "In Progress")

    def test_ac3_same_status_saves_nothing(self):
        console = self.run_cli("5", "2", "pending", "0")
        self.assertIn("Task 2 already has status Pending; the status is "
                      "unchanged.", console.lines)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac4_invalid_status_rejected(self):
        for text in ("inprogress", "In  Progress"):
            with self.subTest(text=text):
                console = self.run_cli("5", "2", text, "0")
                self.assertIn("Status must exactly match one of the "
                              "permitted values.", console.lines)
                self.assertEqual(self.path.read_bytes(), self.before)

    def test_ac5_bad_ids_rejected_before_status_question(self):
        for text, expected in (
                ("abc", core.render_message(core.INVALID_TASK_ID_FORMAT,
                                            field=core.TASK_ID)),
                ("9", "No task with ID 9 exists.")):
            with self.subTest(text=text):
                console = self.run_cli("5", text, "0")
                self.assertIn(expected, console.lines)
                self.assertPromptNotShown(console, "New status")
                self.assertEqual(self.path.read_bytes(), self.before)


class TestTaskTable(CLITestCase):

    def test_default_view_exact_table(self):
        self.write_data([
            task(1, title="Revise Algebra", subject="Mathematics"),
            task(2, title="Essay draft", subject="History",
                 description="Check sources for the Tudor period"),
            task(3, title="Lab report", subject="Biology",
                 description="Include algebra-based calculations")], 4)
        console = self.run_cli("1", "0")
        start = console.lines.index(cli.format_task_table(
            self.saved_data()["tasks"])[0])
        self.assertEqual(console.lines[start:start + 10], DEFAULT_VIEW)

    def test_layout_boundaries(self):
        lines = cli.format_task_table([
            task(1, title="A" * 30),
            task(2, title="Prepare revision notes for the final exam",
                 subject="History", status="In Progress"),
            task(3, title="Supercalifragilisticexpialidociousrevisionplan",
                 subject="Biology", priority="High"),
            task(10, title="Short", subject="mathematics",
                 description="Read" + " the assigned chapter carefully" * 3),
        ])
        self.assertEqual(lines, LAYOUT_BOUNDARIES)
        self.assertLessEqual(max(map(len, lines)), 80)

    def test_wide_ids_widen_the_id_column(self):
        lines = cli.format_task_table([task(12345)])
        self.assertTrue(lines[0].startswith("ID    | Title"))
        self.assertTrue(lines[2].startswith("12345 | Read chapter"))
        self.assertEqual(lines[3], "        Subject: Mathematics")


class TestMenuAndErrors(CLITestCase):

    def test_invalid_menu_option(self):
        console = self.run_cli("9", "", "0")
        self.assertEqual(console.lines.count(cli.INVALID_OPTION), 2)
        self.assertEqual(self.status, 0)

    def test_end_of_input_ends_session(self):
        console = self.run_cli("2", "Essay")
        self.assertEqual(self.status, 1)
        self.assertFalse(self.path.exists())
        self.assertEqual(console.lines[-1], "")

    def test_internal_error_logged_without_task_content(self):
        self.write_data(three_tasks(), 5)
        error = RuntimeError("secret task title")
        with mock.patch.object(core.Planner, "list_view",
                               side_effect=error):
            with self.assertLogs("study_planner", "ERROR") as logs:
                console = self.run_cli("1", "0")
        self.assertIn(core.render_message(core.INTERNAL_ERROR),
                      console.lines)
        self.assertEqual(self.status, 0)
        output = "\n".join(logs.output)
        self.assertIn("RuntimeError", output)
        self.assertIn('File "', output)
        self.assertNotIn("secret task title", output)
        self.assertNotIn("secret task title", "\n".join(console.lines))

    def test_internal_error_at_start_up(self):
        with mock.patch.object(core.storage, "load",
                               side_effect=RuntimeError("boom")):
            with self.assertLogs("study_planner", "ERROR"):
                console = self.run_cli("0")
        self.assertEqual(self.status, 1)
        self.assertEqual(console.lines, [core.render_message(
            core.INTERNAL_ERROR)])

    def test_menu_lists_options(self):
        console = self.run_cli("0")
        self.assertEqual(console.lines[1:8], [
            "Study Planner", "1. View tasks", "2. Add task",
            "3. Edit task", "4. Delete task", "5. Change task status",
            "0. Exit"])


if __name__ == "__main__":
    unittest.main()
