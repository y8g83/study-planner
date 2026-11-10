"""FR6 persistence tests (test plan rows S1-S20).

Every test uses its own temporary directory; no test reads or writes the
real data directory under the user's home folder (NFR8).
"""

import json
import os
import stat
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
    """Tasks 1, 2, 3 in stored order; ``next_id = 5`` (FR6 AC5, AC6)."""
    return [task(1, title="Essay plan", subject="History"),
            task(2, title="Original title"),
            task(3, title="Lab report", subject="Physics")]


class StorageTestCase(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / ".study_planner"
        self.path = self.folder / "tasks.json"

    def write_raw(self, contents):
        """Write ``contents`` (bytes or str) as the data file."""
        self.folder.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, str):
            contents = contents.encode("utf-8")
        self.path.write_bytes(contents)

    def write_data(self, data):
        self.write_raw(json.dumps(data, ensure_ascii=False))

    def make_read_only(self):
        """Make the data file read-only, so replacing it fails."""
        os.chmod(self.path, stat.S_IREAD)
        self.addCleanup(os.chmod, self.path, stat.S_IREAD | stat.S_IWRITE)

    def folder_listing(self):
        return sorted(p.name for p in self.folder.iterdir())


class TestAC1MissingFile(StorageTestCase):

    def test_ac1_load_missing_file_empty_list_next_id_1(self):  # S1
        self.assertEqual(storage.load(self.path), ([], 1))
        self.assertFalse(self.folder.exists())

    def test_ac1_start_missing_file_creates_nothing(self):  # S2
        result = core.start(self.path)
        self.assertTrue(result.ok)
        self.assertEqual(result.planner.tasks, [])
        self.assertEqual(result.planner.next_id, 1)
        self.assertFalse(result.planner.unsaved)
        self.assertFalse(self.folder.exists())

    def test_ac1_first_save_creates_folder_and_file(self):  # S3
        planner = core.start(self.path).planner
        planner.tasks.append(task(1))
        planner.next_id = 2
        self.assertTrue(planner.save())
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),
                         {"next_id": 2, "tasks": [task(1)]})
        reloaded = core.start(self.path).planner
        self.assertEqual((reloaded.tasks, reloaded.next_id), ([task(1)], 2))
        self.assertFalse(reloaded.unsaved)

    def test_ac1_saved_file_exact_format(self):  # S4
        storage.save(self.path, [task(1)], 2)
        self.assertEqual(self.path.read_text(encoding="utf-8"), (
            '{\n  "next_id": 2,\n  "tasks": [\n    {\n      "id": 1,\n'
            '      "title": "Read chapter",\n'
            '      "subject": "Mathematics",\n'
            '      "description": "",\n'
            '      "due_date": "2026-11-20",\n'
            '      "priority": "Medium",\n'
            '      "status": "Pending"\n    }\n  ]\n}\n'))


class TestAC2ValidFile(StorageTestCase):

    def test_ac2_tasks_load_in_file_order_with_next_id(self):  # S5
        tasks = [task(2, subject="Économie"), task(5), task(3)]
        self.write_data({"next_id": 7, "tasks": tasks})
        loaded, next_id = storage.load(self.path)
        self.assertEqual([t["id"] for t in loaded], [2, 5, 3])
        self.assertEqual(loaded, tasks)
        self.assertEqual(loaded[0]["subject"], "Économie")
        self.assertEqual(next_id, 7)


def _valid_file():
    return {"next_id": 4, "tasks": [task(1), task(2), task(3)]}


def _with_task_change(**changes):
    data = _valid_file()
    data["tasks"][1].update(changes)
    return json.dumps(data)


def _without_description():
    data = _valid_file()
    del data["tasks"][0]["description"]
    return json.dumps(data)


# FR6 AC3 table (one row per rule), then the other Section 2 rules.
INVALID_FILES = {
    "S6 empty file": "",
    "S6 duplicate top-level key":
        '{"next_id": 4, "next_id": 4, "tasks": []}',
    "S6 extra top-level key":
        json.dumps({**_valid_file(), "backup": []}),
    "S6 next_id is true": json.dumps({"next_id": True, "tasks": []}),
    "S6 next_id not greater than every ID":
        json.dumps({"next_id": 3, "tasks": [task(3)]}),
    "S6 task missing description": _without_description(),
    "S6 task ID 0": _with_task_change(id=0),
    "S6 duplicate task IDs": _with_task_change(id=1),
    "S6 empty title": _with_task_change(title=""),
    "S6 description with outer whitespace":
        _with_task_change(description=" notes "),
    "S6 due date 2026-02-30": _with_task_change(due_date="2026-02-30"),
    "S6 priority not canonical": _with_task_change(priority="high"),
    "S7 not JSON": "not json",
    "S7 invalid UTF-8": b'{"next_id": 1, "tasks": []}\xff',
    "S7 UTF-8 byte-order mark": b'\xef\xbb\xbf{"next_id": 1, "tasks": []}',
    "S7 NaN": '{"next_id": NaN, "tasks": []}',
    "S7 top level is a list": "[]",
    "S7 tasks is not a list": json.dumps({"next_id": 1, "tasks": {}}),
    "S7 task is not an object": json.dumps({"next_id": 2, "tasks": [1]}),
    "S7 extra task key": _with_task_change(notes=""),
    "S7 duplicate task key": (
        '{"next_id": 2, "tasks": [{"id": 1, "id": 1, "title": "T", '
        '"subject": "S", "description": "", "due_date": "2026-11-20", '
        '"priority": "Medium", "status": "Pending"}]}'),
    "S7 next_id 0": json.dumps({"next_id": 0, "tasks": []}),
    "S7 next_id is text": json.dumps({"next_id": "4", "tasks": []}),
    "S7 next_id is a float": json.dumps({"next_id": 4.0, "tasks": []}),
    "S7 task ID is true": _with_task_change(id=True),
    "S7 task ID is negative": _with_task_change(id=-2),
    "S7 task ID is text": _with_task_change(id="2"),
    "S7 title not a string": _with_task_change(title=7),
    "S7 title with outer whitespace": _with_task_change(title=" Essay"),
    "S7 empty subject": _with_task_change(subject=""),
    "S7 subject with outer whitespace": _with_task_change(subject="Maths "),
    "S7 description not a string": _with_task_change(description=None),
    "S7 due date with spaces": _with_task_change(due_date=" 2026-11-20"),
    "S7 due date wrong format": _with_task_change(due_date="2026-1-20"),
    "S7 due date non-ASCII digits":
        _with_task_change(due_date="٢٠٢٦-١١-٢٠"),
    "S7 due date not a string": _with_task_change(due_date=20261120),
    "S7 status not canonical": _with_task_change(status="in progress"),
    "S7 unknown priority": _with_task_change(priority="Urgent"),
}


class TestAC3InvalidFiles(StorageTestCase):

    def assert_rejected_unchanged(self, contents):
        self.write_raw(contents)
        before = self.path.read_bytes()
        result = core.start(self.path)
        self.assertEqual(result.outcome, core.INVALID_STORED_DATA)
        self.assertFalse(result.ok)
        self.assertIsNone(result.planner)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.folder_listing(), ["tasks.json"])

    def test_ac3_invalid_files_rejected_and_unchanged(self):  # S6, S7
        for name, contents in INVALID_FILES.items():
            with self.subTest(name):
                self.assert_rejected_unchanged(contents)

    def test_ac3_storage_raises_invalid_data_error(self):  # S6, S7
        for name, contents in INVALID_FILES.items():
            with self.subTest(name):
                self.write_raw(contents)
                with self.assertRaises(storage.InvalidDataError):
                    storage.load(self.path)

    def test_ac3_rule_boundaries_still_valid(self):  # S8
        valid = {
            "empty description": _with_task_change(description=""),
            "next_id far above every ID":
                json.dumps({"next_id": 99, "tasks": [task(1)]}),
            "leap day": _with_task_change(due_date="2028-02-29"),
            "past date": _with_task_change(due_date="2025-01-15"),
            "internal spaces kept": _with_task_change(title="Read  notes"),
        }
        for name, contents in valid.items():
            with self.subTest(name):
                self.write_raw(contents)
                self.assertTrue(core.start(self.path).ok)


class TestAC4EmptyTaskList(StorageTestCase):

    def test_ac4_next_id_read_and_file_not_rewritten(self):  # S9
        self.write_raw('{"next_id": 4, "tasks": []}')
        before = self.path.read_bytes()
        mtime = self.path.stat().st_mtime_ns
        result = core.start(self.path)
        self.assertEqual((result.planner.tasks, result.planner.next_id),
                         ([], 4))
        self.assertFalse(result.planner.unsaved)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)


class TestAC5SafeSave(StorageTestCase):

    def setUp(self):
        super().setUp()
        storage.save(self.path, three_tasks(), 5)
        self.planner = core.start(self.path).planner

    def test_ac5_saved_change_reloads_exactly(self):  # S10
        self.planner.tasks[1]["title"] = "Updated title"
        self.assertTrue(self.planner.save())
        self.assertFalse(self.planner.unsaved)
        expected = three_tasks()
        expected[1]["title"] = "Updated title"
        self.assertEqual(storage.load(self.path), (expected, 5))

    def test_ac5_no_temporary_file_remains(self):  # S11
        self.planner.tasks[1]["title"] = "Updated title"
        self.planner.save()
        self.assertEqual(self.folder_listing(), ["tasks.json"])

    def test_ac5_same_data_saves_identical_bytes(self):  # S12
        before = self.path.read_bytes()
        self.planner.save()
        self.assertEqual(self.path.read_bytes(), before)

    def test_ac5_non_ascii_text_written_as_utf8(self):  # S13
        self.planner.tasks[0]["subject"] = "Économie"
        self.planner.save()
        self.assertIn("Économie".encode("utf-8"), self.path.read_bytes())
        self.assertEqual(storage.load(self.path)[0][0]["subject"],
                         "Économie")

    def test_ac5_invalid_data_never_written(self):  # S14
        before = self.path.read_bytes()
        bad = three_tasks()
        bad[0]["priority"] = "high"
        for tasks, next_id in ((bad, 5), (three_tasks(), 3)):
            with self.subTest(next_id=next_id):
                with self.assertRaises(storage.InvalidDataError):
                    storage.save(self.path, tasks, next_id)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.folder_listing(), ["tasks.json"])


class TestAC6FailedSaveAndRetry(StorageTestCase):

    def setUp(self):
        super().setUp()
        storage.save(self.path, three_tasks(), 5)
        self.saved = self.path.read_bytes()
        self.planner = core.start(self.path).planner

    def test_ac6_failed_save_keeps_change_and_file(self):  # S15
        self.make_read_only()
        self.planner.tasks[1]["title"] = "Updated title"
        self.assertFalse(self.planner.save())
        self.assertTrue(self.planner.unsaved)
        self.assertEqual(self.planner.tasks[1]["title"], "Updated title")
        self.assertEqual(self.path.read_bytes(), self.saved)
        self.assertEqual(self.folder_listing(), ["tasks.json"])

    def test_ac6_next_successful_save_clears_unsaved(self):  # S16
        self.make_read_only()
        self.planner.tasks[1]["title"] = "Updated title"
        self.planner.save()
        os.chmod(self.path, stat.S_IREAD | stat.S_IWRITE)
        self.planner.tasks[2]["status"] = "In Progress"
        self.assertTrue(self.planner.save())
        self.assertFalse(self.planner.unsaved)
        expected = three_tasks()
        expected[1]["title"] = "Updated title"
        expected[2]["status"] = "In Progress"
        self.assertEqual(storage.load(self.path), (expected, 5))

    def test_ac6_failed_retry_stays_unsaved(self):  # S17
        self.make_read_only()
        self.planner.tasks[1]["title"] = "Updated title"
        self.planner.save()
        self.planner.tasks[2]["status"] = "In Progress"
        self.assertFalse(self.planner.save())
        self.assertTrue(self.planner.unsaved)
        self.assertEqual(self.path.read_bytes(), self.saved)


class TestAC7ExitPrompt(StorageTestCase):

    def test_ac7_prompt_only_while_unsaved(self):  # S18
        storage.save(self.path, three_tasks(), 5)
        planner = core.start(self.path).planner
        self.assertFalse(planner.exit_needs_prompt)
        self.make_read_only()
        planner.save()
        self.assertTrue(planner.exit_needs_prompt)
        planner.save()  # Retry saving, still failing
        self.assertTrue(planner.exit_needs_prompt)
        os.chmod(self.path, stat.S_IREAD | stat.S_IWRITE)
        self.assertTrue(planner.save())  # Retry saving, now possible
        self.assertFalse(planner.exit_needs_prompt)


class TestNFR8DataLocation(StorageTestCase):

    def test_nfr8_default_path_in_home_folder(self):  # S19
        self.assertEqual(storage.default_data_path(),
                         Path.home() / ".study_planner" / "tasks.json")

    def test_nfr8_start_uses_default_path(self):  # S19
        with mock.patch.object(storage, "default_data_path",
                               return_value=self.path):
            result = core.start()
        self.assertEqual(result.planner.path, self.path)
        self.assertFalse(self.folder.exists())

    def test_nfr8_failed_folder_creation_is_failed_save(self):  # S20
        blocker = self.folder.parent / "blocker"
        blocker.write_text("not a folder", encoding="utf-8")
        planner = core.start(blocker / "tasks.json").planner
        planner.tasks.append(task(1))
        planner.next_id = 2
        self.assertFalse(planner.save())
        self.assertTrue(planner.unsaved)
        self.assertEqual(planner.tasks, [task(1)])
        self.assertEqual(blocker.read_text(encoding="utf-8"), "not a folder")


if __name__ == "__main__":
    unittest.main()
