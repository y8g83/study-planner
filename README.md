# Study Planner

A Python application that helps students organise study tasks, coursework
deadlines, priorities and completion progress. It has a text-based (CLI)
version; a Tkinter (GUI) version is planned. Both use one shared core module
for validation, task rules, messages and storage, so neither interface
implements business rules itself.

## Current status

| Component | Status |
|---|---|
| Task operations: add, edit, delete, change status (`src/core.py`) | Implemented and tested |
| Task list view (`src/core.py`) | Implemented and tested |
| Input validation (`src/core.py`) | Implemented and tested |
| JSON persistence (`src/storage.py`, coordinated by `src/core.py`) | Implemented and tested |
| Text-based interface (`src/cli.py`) | Implemented and tested |
| Search, filter, sort and progress summary | Planned |
| Tkinter interface (GUI) | Planned |

## Implemented features

### Task operations

- **Add:** a new task receives the next unused ID and is appended to the
  list. Priority defaults to `Medium` and status to `Pending`.
- **Edit:** the title, subject, description, due date and priority of a task
  can be changed. All new values are validated together, and the edit is
  applied completely or not at all. The confirmation names the changed
  fields; if nothing would change, nothing is saved.
- **Delete:** removes one task after confirmation (`y` or `yes`); the other
  tasks keep their order, and deleted IDs are never reused.
- **Change status:** the only way to change a status. Choosing the current
  status again changes and saves nothing.
- A task ID is checked, and the task looked up, before any further question
  is asked.
- **View:** the task list in stored order, including changes not yet saved.

### Input validation

- A task has a title, subject, description, due date, priority and status.
- Title and subject are required and are trimmed of surrounding whitespace;
  the description is optional.
- The due date must use the exact `YYYY-MM-DD` format and be a real calendar
  date.
- Priority is `High`, `Medium` or `Low` (default `Medium`). Status is
  `Pending`, `In Progress` or `Completed` (default `Pending`). Values are
  matched case-insensitively and stored in their canonical form.
- Separate validation rules apply to adding a task, editing a task (no
  defaults; the status is changed only through a status change), changing a
  status, and typed task IDs (a positive ASCII integer without signs, spaces,
  separators or leading zeros).
- All errors in a submission are reported together, in a fixed field order,
  with texts from one central message table. A rejected submission returns no
  values, so it can never be partly applied.

### Persistence

- Tasks and the next task ID are stored together in one UTF-8 JSON file at
  `~/.study_planner/tasks.json`.
- If the file does not exist, the planner starts with an empty task list and
  `next_id = 1`; loading creates nothing, and the file is created by the
  first successful save.
- Loading is strict: the whole file is rejected if it is not valid JSON,
  contains duplicate keys, has missing or additional keys, holds an invalid
  field value or duplicate task IDs, or if `next_id` is not greater than every
  task ID. An invalid file is never overwritten.
- Every change is saved automatically. Saving writes to a temporary file in
  the same folder, flushes it to disk and then replaces the data file in one
  step, so the previous file stays intact if a save fails. After a failed
  save, all changes remain in memory, a warning is shown and the data is
  marked as unsaved until the next successful save.

Example data file:

```json
{
  "next_id": 2,
  "tasks": [
    {
      "id": 1,
      "title": "Read chapter 3",
      "subject": "Mathematics",
      "description": "",
      "due_date": "2026-11-20",
      "priority": "Medium",
      "status": "Pending"
    }
  ]
}
```

## Requirements

- Python 3.12
- No third-party packages: the application uses only the Python standard
  library, and the planned GUI uses Tkinter, which is included with the
  standard Python installers.

## Setup

```
git clone https://github.com/y8g83/study-planner.git
cd study-planner
```

No installation step is needed.

## Running the text-based version

From the repository root:

```
python src/cli.py
```

The main menu offers:

```
1. View tasks
2. Add task
3. Edit task
4. Delete task
5. Change task status
0. Exit
```

- Tasks are listed in a table with the columns ID, Title, Due Date, Priority
  and Status; the subject and any description appear beneath each task.
- To edit a task, enter its ID, then the numbers of the fields to change,
  separated by commas (for example `1,5` for title and priority).
- While changes are unsaved, the menu shows `Unsaved changes`. Exiting then
  offers **Retry saving**, **Exit without saving** and **Cancel exit**.
- If the data file is invalid, the application shows an error and does not
  start; the file is left unchanged.
- Unexpected errors are reported with a short message, and their details are
  written to standard error.
- The unsaved-changes prompt cannot be shown when the program is ended
  forcibly, for example with Ctrl+C.

## Running the tests

From the repository root:

```
python -m unittest discover -s tests
```

No `PYTHONPATH` setting is required: `tests/helpers.py` adds `src/` to the
import path. Tests that use a data file create it in a temporary directory
and never read or write the real data file.

| Test module | Covers |
|---|---|
| `tests/test_validation.py` | Input validation and message texts |
| `tests/test_storage.py` | Loading, saving and the unsaved state |
| `tests/test_core.py` | Task operations, the list view and operation messages |
| `tests/test_cli.py` | The text-based interface, with scripted input |

## Code style

The code follows PEP 8 and is checked with `pycodestyle`, a development tool
that is not needed to run the application:

```
python -m pip install pycodestyle
python -m pycodestyle src tests
```

## Project structure

```
study-planner/
├── src/
│   ├── core.py          Shared core: task operations, validation, messages,
│   │                    persistence coordination
│   ├── storage.py       JSON loading and saving
│   └── cli.py           Text-based interface
├── tests/
│   ├── helpers.py       Puts src/ on the import path
│   ├── test_validation.py
│   ├── test_storage.py
│   ├── test_core.py
│   └── test_cli.py
├── report/
│   ├── main.tex         Coursework report (LaTeX)
│   └── references.bib
└── docs/                Documentation (currently empty)
```
