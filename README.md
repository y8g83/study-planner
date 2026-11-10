# Study Planner

A Python application that helps students organise study tasks, coursework
deadlines, priorities and completion progress. The project will provide a
text-based (CLI) version and a Tkinter (GUI) version. Both will use one shared
core module for validation, task rules and storage, so neither interface
implements business rules itself.

## Current status

| Component | Status |
|---|---|
| Input validation (`src/core.py`) | Implemented and tested |
| JSON persistence (`src/storage.py`, coordinated by `src/core.py`) | Implemented and tested |
| Task operations: add, edit, delete, change status | Planned |
| Search, filter, sort and progress summary | Planned |
| Text-based interface (CLI) | Planned |
| Tkinter interface (GUI) | Planned |

There is no application entry point yet; the implemented parts are exercised
through the automated tests.

## Implemented features

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
- Saving writes to a temporary file in the same folder, flushes it to disk and
  then replaces the data file in one step, so the previous file stays intact
  if a save fails. After a failed save, all changes remain in memory and the
  data is marked as unsaved until the next successful save.

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

## Running the tests

From the repository root:

```
python -m unittest discover -s tests
```

No `PYTHONPATH` setting is required: `tests/helpers.py` adds `src/` to the
import path. The storage tests use temporary directories and never read or
write the real data file.

| Test module | Covers |
|---|---|
| `tests/test_validation.py` | Input validation and message texts |
| `tests/test_storage.py` | Loading, saving and the unsaved state |

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
│   ├── core.py          Shared core: validation, messages, persistence coordination
│   └── storage.py       JSON loading and saving
├── tests/
│   ├── helpers.py       Puts src/ on the import path
│   ├── test_validation.py
│   └── test_storage.py
├── report/
│   ├── main.tex         Coursework report (LaTeX)
│   └── references.bib
└── docs/                Documentation (currently empty)
```
