"""CLI tests: scripted input, captured output and real data files.

Each test runs ``cli.main`` on a data file in its own temporary directory.
The fake console records every prompt and output line, so tests can check
both the exact text and the order in which questions are asked.
"""

import json
import re
import tempfile
import unittest
from datetime import date
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


TODAY = date(2026, 11, 12)
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
        self.status = cli.main(self.path, console.read, console.write,
                               lambda: TODAY)
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

    def test_ac2_selected_values_on_empty_list(self):
        console = self.run_cli("2", "Lab report", "Biology", "",
                               "2026-11-30", "High", "Completed", "0")
        self.assertIn("Task 1 added.", console.lines)
        self.assertEqual(self.saved_data(), {"next_id": 2, "tasks": [task(
            1, title="Lab report", subject="Biology", due_date="2026-11-30",
            priority="High", status="Completed")]})

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

    def test_ac5_last_task_deleted_id_not_reused(self):
        self.write_data([task(3)], 5)
        console = self.run_cli("4", "3", "y", "1", "2", "New", "History", "",
                               "2026-12-01", "", "", "0")
        self.assertIn("Task 3 deleted.", console.lines)
        self.assertIn("No tasks yet.", console.lines)
        self.assertIn("Task 5 added.", console.lines)
        self.assertEqual([t["id"] for t in self.saved_data()["tasks"]], [5])

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

    def test_ac6_failed_save_shows_status_and_warning(self):
        with failing_save():
            console = self.run_cli("5", "2", "Completed", "0", "2")
        changed = console.lines.index("Task 2 status changed to Completed.")
        self.assertEqual(console.lines[changed + 1], SAVE_FAILED)
        self.assertIn(UNSAVED, console.lines[changed:])
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
        console = self.run_cli("10", "", "0")
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
        self.assertEqual(console.lines[1:12], [
            "Study Planner", "1. View tasks", "2. Add task",
            "3. Edit task", "4. Delete task", "5. Change task status",
            "6. Search tasks", "7. Filter tasks", "8. Sort tasks",
            "9. Summary", "0. Exit"])


# --- FR7-FR10 through the menu -------------------------------------------

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


ROW = re.compile(r"(\d+) +\| ")
NO_MATCH = core.render_message(core.NO_MATCHING_TASKS)
NO_TASKS = core.render_message(core.NO_TASKS_YET)

# Menu answers for each filter and sort.
STATUS, PRIORITY, SUBJECT = ("7", "1"), ("7", "2"), ("7", "3")
SORT = {None: ("8", "0"), core.SORT_DUE_DATE: ("8", "1"),
        core.SORT_PRIORITY: ("8", "2"), core.SORT_STATUS: ("8", "3"),
        core.SORT_SUBJECT: ("8", "4")}


class ListView:
    """One list view as shown: its view lines, row IDs and message."""

    def __init__(self, lines, start):
        self.search, self.filters, self.sort = lines[start:start + 3]
        self.ids = []
        self.message = None
        for line in lines[start + 3:]:
            if line == "" or line.startswith("Choose an option"):
                break
            if line in (NO_MATCH, NO_TASKS):
                self.message = line
            match = ROW.match(line)
            if match:
                self.ids.append(int(match.group(1)))


class ViewCLITestCase(CLITestCase):

    def start_with(self, tasks, next_id):
        self.write_data(tasks, next_id)
        self.before = self.path.read_bytes()

    def views(self, console):
        return [ListView(console.lines, index)
                for index, line in enumerate(console.lines)
                if line.startswith("Search: ")]

    def last_view(self, *answers):
        console = self.run_cli(*answers, "0")
        return self.views(console)[-1]

    def assertFileUnchanged(self):
        self.assertEqual(self.path.read_bytes(), self.before)


class TestFR7SearchCLI(ViewCLITestCase):

    def setUp(self):
        super().setUp()
        self.start_with(fr7_dataset(), 4)

    def test_ac1_and_ac2_search_results(self):
        for query, expected in (("REVISE", [1]), ("tudor", [2]),
                                ("BIO", [3]), ("algebra", [1, 3])):
            with self.subTest(query=query):
                view = self.last_view("6", query)
                self.assertEqual(view.ids, expected)
                self.assertFileUnchanged()

    def test_ac3_no_match_and_empty_list(self):
        self.assertEqual(self.last_view("6", "physics").message, NO_MATCH)
        self.start_with([], 1)
        view = self.last_view("6", "essay")
        self.assertEqual((view.ids, view.message), ([], NO_TASKS))

    def test_ac4_empty_whitespace_and_trimmed_queries(self):
        for query, expected, search_line in (
                ("", [1, 2, 3], "Search: none"),
                ("   ", [1, 2, 3], "Search: none"),
                ("  essay draft  ", [2], 'Search: "essay draft"'),
                ("essay  draft", [], 'Search: "essay  draft"')):
            with self.subTest(query=query):
                view = self.last_view("6", query)
                self.assertEqual(view.ids, expected)
                self.assertEqual(view.search, search_line)
        self.assertEqual(view.message, NO_MATCH)

    def test_ac5_search_and_subject_filter(self):
        for subject, expected in (("", [1, 3]), ("Mathematics", [1]),
                                  ("Biology", [3])):
            with self.subTest(subject=subject):
                view = self.last_view("6", "algebra", *SUBJECT, subject)
                self.assertEqual(view.ids, expected)
        view = self.last_view("6", "essay", *SUBJECT, "Mathematics")
        self.assertEqual(view.message, NO_MATCH)
        self.assertFileUnchanged()

    def test_ac6_casefold_sharp_s(self):
        self.start_with(fr7_dataset() + [task(4, title="Straße survey",
                                              subject="Geography")], 5)
        self.assertEqual(self.last_view("6", "STRASSE").ids, [4])
        self.assertFileUnchanged()

    def test_ac7_search_persists_and_resets_on_restart(self):
        console = self.run_cli(
            "6", "algebra",
            "2", "Algebra quiz", "Mathematics", "", "2026-11-20", "", "",
            "1",
            "2", "History notes", "Mathematics", "", "2026-11-20", "", "",
            "1", "6", "", "0")
        views = self.views(console)
        self.assertEqual(views[0].search, 'Search: "algebra"')
        self.assertEqual(views[0].ids, [1, 3])
        self.assertIn("Task 4 added.", console.lines)
        self.assertEqual(views[1].ids, [1, 3, 4])
        self.assertIn("Task 5 added.", console.lines)
        self.assertEqual(views[2].ids, [1, 3, 4])
        self.assertEqual(views[3].search, "Search: none")
        self.assertEqual(views[3].ids, [1, 2, 3, 4, 5])
        restarted = self.last_view("1")
        self.assertEqual(restarted.search, "Search: none")
        self.assertEqual(restarted.ids, [1, 2, 3, 4, 5])
        self.assertEqual(set(self.saved_data()), {"next_id", "tasks"})

    def test_search_does_not_restrict_typed_ids(self):
        console = self.run_cli("6", "algebra", "5", "2", "Completed", "0")
        self.assertIn("Task 2 status changed to Completed.", console.lines)


class TestFR8FiltersCLI(ViewCLITestCase):

    def setUp(self):
        super().setUp()
        self.start_with(fr8_dataset(), 5)

    def test_ac1_individual_filters_and_clearing(self):
        console = self.run_cli("1", *STATUS, "Pending", "0")
        first, status = self.views(console)
        self.assertEqual((first.ids, first.filters),
                         ([1, 2, 3, 4], "Filters: none"))
        self.assertEqual((status.ids, status.filters),
                         ([1, 4], "Filters: status=Pending"))
        console = self.run_cli(*PRIORITY, "High", *PRIORITY, "", "0")
        high, cleared = self.views(console)
        self.assertEqual((high.ids, high.filters),
                         ([1, 3], "Filters: priority=High"))
        self.assertEqual((cleared.ids, cleared.filters),
                         ([1, 2, 3, 4], "Filters: none"))
        self.assertFileUnchanged()

    def test_ac1_all_clears_status_and_priority(self):
        for answer in ("All", "all", "  ALL  "):
            with self.subTest(answer=answer):
                view = self.last_view(*STATUS, "Pending", *STATUS, answer)
                self.assertEqual(view.filters, "Filters: none")

    def test_ac2_subject_matching_and_clearing(self):
        for subject, expected, line in (
                ("Mathematics", [1, 4], "subject=Mathematics"),
                ("  MATHEMATICS  ", [1, 4], "subject=MATHEMATICS"),
                ("Math", [], "subject=Math"),
                ("   ", [1, 2, 3, 4], "none")):
            with self.subTest(subject=subject):
                view = self.last_view(*SUBJECT, subject)
                self.assertEqual(view.ids, expected)
                self.assertEqual(view.filters, f"Filters: {line}")
                if not expected:
                    self.assertEqual(view.message, NO_MATCH)
                self.assertEqual(self.saved_data()["tasks"][3]["subject"],
                                 "mathematics")
                self.assertFileUnchanged()

    def test_ac3_filters_combine_with_and(self):
        view = self.last_view(*STATUS, "Pending", *PRIORITY, "High")
        self.assertEqual(view.ids, [1])
        self.assertEqual(view.filters,
                         "Filters: status=Pending, priority=High")
        view = self.last_view(*STATUS, "Pending", *PRIORITY, "Low",
                              *SUBJECT, "Mathematics")
        self.assertEqual(view.ids, [4])
        self.assertEqual(view.filters, "Filters: status=Pending, "
                                       "priority=Low, subject=Mathematics")
        view = self.last_view(*STATUS, "Completed", *SUBJECT, "History")
        self.assertEqual(view.message, NO_MATCH)
        self.assertFileUnchanged()

    def test_ac4_invalid_value_keeps_active_filters(self):
        console = self.run_cli(*PRIORITY, "High", *STATUS, "Done",
                               *STATUS, "  pending  ", "0")
        high, after_error, pending = self.views(console)
        self.assertEqual((high.ids, high.filters),
                         ([1, 3], "Filters: priority=High"))
        self.assertIn("Status filter must be one of: Pending, In Progress, "
                      "Completed.", console.lines)
        self.assertEqual((after_error.ids, after_error.filters),
                         ([1, 3], "Filters: priority=High"))
        self.assertEqual((pending.ids, pending.filters),
                         ([1], "Filters: status=Pending, priority=High"))
        self.assertFileUnchanged()

    def test_ac5_filter_persists_and_resets_on_restart(self):
        console = self.run_cli(
            *STATUS, "Pending",
            "2", "Lab", "Physics", "", "2026-11-20", "Medium", "Pending",
            "1",
            "2", "Quiz", "Physics", "", "2026-11-20", "Medium", "Completed",
            "1", *STATUS, "", "0")
        views = self.views(console)
        self.assertEqual([v.ids for v in views], [
            [1, 4], [1, 4, 5], [1, 4, 5], [1, 2, 3, 4, 5, 6]])
        self.assertEqual([v.filters for v in views], [
            "Filters: status=Pending"] * 3 + ["Filters: none"])
        self.assertIn("Task 5 added.", console.lines)
        self.assertIn("Task 6 added.", console.lines)
        restarted = self.last_view("1")
        self.assertEqual(restarted.filters, "Filters: none")
        self.assertEqual(restarted.ids, [1, 2, 3, 4, 5, 6])
        self.assertEqual(set(self.saved_data()), {"next_id", "tasks"})

    def test_ac7_filter_on_empty_list(self):
        self.start_with([], 5)
        view = self.last_view(*STATUS, "Pending")
        self.assertEqual(view.message, NO_TASKS)
        self.assertEqual(view.filters, "Filters: status=Pending")
        self.assertFileUnchanged()

    def test_ac8_subject_named_all(self):
        self.start_with(fr8_dataset() + [task(5, subject="All")], 6)
        console = self.run_cli(*SUBJECT, "All", *SUBJECT, "", "0")
        only_all, cleared = self.views(console)
        self.assertEqual(only_all.ids, [5])
        self.assertEqual(cleared.ids, [1, 2, 3, 4, 5])
        self.assertFileUnchanged()

    def test_invalid_filter_choice(self):
        console = self.run_cli("7", "4", "0")
        self.assertIn(cli.INVALID_OPTION, console.lines)
        self.assertEqual(self.views(console), [])


class TestFR9SortCLI(ViewCLITestCase):

    def setUp(self):
        super().setUp()
        self.start_with(fr9_dataset(), 6)

    def test_ac1_to_ac5_orders_and_labels(self):
        for sort, expected in ((None, [1, 2, 3, 4, 5]),
                               (core.SORT_DUE_DATE, [4, 2, 3, 1, 5]),
                               (core.SORT_PRIORITY, [3, 1, 2, 5, 4]),
                               (core.SORT_STATUS, [4, 1, 5, 2, 3]),
                               (core.SORT_SUBJECT, [5, 3, 2, 4, 1])):
            with self.subTest(sort=sort):
                view = self.last_view(*SORT[sort])
                self.assertEqual(view.ids, expected)
                self.assertEqual(view.sort, f"Sort: {sort or 'none'}")
                self.assertEqual(
                    [t["id"] for t in self.saved_data()["tasks"]],
                    [1, 2, 3, 4, 5])
                self.assertFileUnchanged()

    def test_ac6_filter_then_sort(self):
        view = self.last_view(*STATUS, "Pending", *SORT[core.SORT_DUE_DATE])
        self.assertEqual(view.ids, [4, 1, 5])
        self.assertFileUnchanged()

    def test_ac9_change_and_clear_the_sort(self):
        console = self.run_cli(*SORT[core.SORT_PRIORITY],
                               *SORT[core.SORT_STATUS], *SORT[None], "0")
        priority, status, cleared = self.views(console)
        self.assertEqual((status.ids, status.sort),
                         ([4, 1, 5, 2, 3], "Sort: status"))
        self.assertEqual((cleared.ids, cleared.sort),
                         ([1, 2, 3, 4, 5], "Sort: none"))

    def test_ac10_restart_has_no_sort(self):
        self.run_cli(*SORT[core.SORT_SUBJECT], "0")
        view = self.last_view("1")
        self.assertEqual((view.ids, view.sort), ([1, 2, 3, 4, 5],
                                                 "Sort: none"))
        self.assertEqual(set(self.saved_data()), {"next_id", "tasks"})

    def test_ac11_sort_kept_after_add(self):
        console = self.run_cli(*SORT[core.SORT_DUE_DATE],
                               "2", "New", "History", "", "2026-11-10", "",
                               "", "1", "0")
        view = self.views(console)[-1]
        self.assertEqual(view.ids, [4, 2, 3, 6, 1, 5])
        self.assertEqual(view.sort, "Sort: due date")
        self.assertEqual([t["id"] for t in self.saved_data()["tasks"]],
                         [1, 2, 3, 4, 5, 6])

    def test_invalid_sort_option(self):
        console = self.run_cli("8", "5", "0")
        self.assertIn(cli.INVALID_OPTION, console.lines)
        self.assertEqual(self.views(console), [])


class TestFR10SummaryCLI(ViewCLITestCase):

    def summary(self, console):
        start = console.lines.index(next(
            line for line in console.lines if line.startswith("Total: ")))
        return console.lines[start:start + 5]

    def test_ac1_and_ac9_labels_with_fixed_today(self):
        self.start_with(fr9_dataset(), 6)
        console = self.run_cli("9", "0")
        self.assertEqual(self.summary(console), [
            "Total: 5", "Completed: 1", "Remaining: 4", "Overdue: 2",
            "Completion: 20.0%"])
        self.assertFileUnchanged()

    def test_ac3_and_ac9_empty_list(self):
        self.assertEqual(self.summary(self.run_cli("9", "0")), [
            "Total: 0", "Completed: 0", "Remaining: 0", "Overdue: 0",
            "Completion: 0.0%"])
        self.assertFalse(self.path.exists())

    def test_ac4_half_up_percentage(self):
        tasks = [task(n) for n in range(1, 17)]
        tasks[0]["status"] = "Completed"
        self.start_with(tasks, 17)
        self.assertIn("Completion: 6.3%", self.run_cli("9", "0").lines)

    def test_ac5_and_ac9_all_completed(self):
        self.start_with([task(n, status="Completed", due_date="2026-01-01")
                         for n in (1, 2, 3)], 4)
        self.assertEqual(self.summary(self.run_cli("9", "0")), [
            "Total: 3", "Completed: 3", "Remaining: 0", "Overdue: 0",
            "Completion: 100.0%"])

    def test_ac6_filter_does_not_limit_summary(self):
        self.start_with(fr9_dataset(), 6)
        console = self.run_cli(*STATUS, "Pending", "9", "0")
        self.assertEqual(self.views(console)[0].ids, [1, 4, 5])
        self.assertIn("Total: 5", console.lines)
        self.assertIn("Overdue: 2", console.lines)

    def test_ac7_summary_reflects_unsaved_change(self):
        self.start_with(fr9_dataset(), 6)
        with failing_save():
            console = self.run_cli("5", "4", "Completed", "9", "0", "2")
        self.assertEqual(self.summary(console), [
            "Total: 5", "Completed: 2", "Remaining: 3", "Overdue: 1",
            "Completion: 40.0%"])
        self.assertFileUnchanged()

    def test_summary_uses_the_supplied_date(self):
        self.start_with(fr9_dataset(), 6)
        console = FakeConsole(["9", "0"])
        cli.main(self.path, console.read, console.write,
                 lambda: date(2026, 11, 10))
        self.assertIn("Overdue: 1", console.lines)

    def test_ac10_summary_changes_nothing(self):
        self.start_with(fr9_dataset(), 6)
        self.run_cli("9", "9", "0")
        self.assertFileUnchanged()


class TestFR11ViewLines(ViewCLITestCase):

    def test_ac1_view_lines_above_table(self):
        self.start_with(fr7_dataset(), 4)
        console = self.run_cli("1", "0")
        start = console.lines.index("Search: none")
        self.assertEqual(console.lines[start:start + 3],
                         ["Search: none", "Filters: none", "Sort: none"])
        self.assertEqual(console.lines[start + 3], DEFAULT_VIEW[0])

    def test_ac2_empty_list_with_and_without_filter(self):
        console = self.run_cli("1", *STATUS, "Pending", "0")
        plain, filtered = self.views(console)
        self.assertEqual((plain.ids, plain.message), ([], NO_TASKS))
        self.assertEqual((filtered.ids, filtered.message), ([], NO_TASKS))
        self.assertNotIn(DEFAULT_VIEW[0], console.lines)
        self.assertFalse(self.folder.exists())

    def test_ac3_stored_order_after_add_edit_delete_and_restart(self):
        self.start_with([task(1, due_date="2026-11-30"),
                         task(2, due_date="2026-11-20"),
                         task(3, due_date="2026-11-10")], 4)
        console = self.run_cli(
            "2", "Fourth", "History", "", "2026-11-25", "", "", "1",
            "3", "2", "1", "Renamed", "1",
            "4", "2", "y", "1", "0")
        added, edited, deleted = self.views(console)
        self.assertEqual(added.ids, [1, 2, 3, 4])
        self.assertEqual(edited.ids, [1, 2, 3, 4])
        self.assertIn("2  | Renamed                        | 2026-11-20 | "
                      "Medium   | Pending", console.lines)
        self.assertEqual(deleted.ids, [1, 3, 4])
        self.assertEqual(self.last_view("1").ids, [1, 3, 4])

    def test_ac5_unsaved_changes_listed_with_indicator(self):
        self.start_with(fr7_dataset(), 4)
        with failing_save():
            console = self.run_cli("2", "Quiz", "History", "", "2026-11-25",
                                   "", "", "1", "0", "2")
        view = self.views(console)[-1]
        self.assertEqual(view.ids, [1, 2, 3, 4])
        after_view = console.lines[console.lines.index(view.search):]
        self.assertIn(UNSAVED, after_view)
        self.assertFileUnchanged()

    def test_ac4_sort_and_search_then_cleared(self):
        self.start_with([task(1, due_date="2026-11-30"),
                         task(2, due_date="2026-11-20"),
                         task(3, due_date="2026-11-10")], 4)
        console = self.run_cli(*SORT[core.SORT_DUE_DATE], *SORT[None],
                               "6", "zzz", "6", "", "0")
        views = self.views(console)
        self.assertEqual([v.ids for v in views],
                         [[3, 2, 1], [1, 2, 3], [], [1, 2, 3]])
        self.assertEqual(views[2].message, NO_MATCH)
        self.assertFileUnchanged()


if __name__ == "__main__":
    unittest.main()
