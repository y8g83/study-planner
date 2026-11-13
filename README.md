# Study Planner

A Python application that helps students organise study tasks, coursework
deadlines, priorities and completion progress. It has a text-based (CLI)
version and a Tkinter (GUI) version. Both use one shared core module for
validation, task rules, messages and storage, so neither interface
implements business rules itself.

## Current status

| Component | Status |
|---|---|
| Task operations: add, edit, delete, change status (`src/core.py`) | Implemented and tested |
| Task list view (`src/core.py`) | Implemented and tested |
| Input validation (`src/core.py`) | Implemented and tested |
| JSON persistence (`src/storage.py`, coordinated by `src/core.py`) | Implemented and tested |
| Search, filters, merge sort and summary (`src/core.py`) | Implemented and tested |
| Text-based interface (`src/cli.py`) | Implemented and tested |
| Tkinter interface (`src/gui.py`) | Implemented and tested |

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
- **View:** the task list, including changes not yet saved. Without a
  search, filter or sort, tasks appear in stored order.

### Search, filters, sort and summary

- **Search:** a task matches when the query appears in its title,
  description or subject, ignoring letter case (`casefold()`). The query is
  trimmed; an empty query shows every task.
- **Filters:** by status, priority and subject, one value each. The subject
  must match exactly, ignoring letter case and surrounding spaces, so `Math`
  does not match `Mathematics`. Search and all active filters combine with
  AND.
- **Sort:** by due date, priority, status or subject (case-insensitive);
  priority, status and subject use the due date as the second key, and
  equal tasks keep their stored order. Sorting uses the application's own
  stable merge sort, which returns a new list and never reorders the stored
  tasks.
- Search, filters and sort last for the current session only; they are
  never saved and reset when the application restarts.
- If there are no tasks at all, `No tasks yet.` is shown; if tasks exist but
  none match, `No tasks match the current search and filters.`
- **Summary:** `Total`, `Completed`, `Remaining`, `Overdue` and `Completion`
  for every task in memory, regardless of search, filters and sort. A task
  is overdue when its due date is before today and it is not completed. The
  completion percentage is rounded half-up to one decimal place.

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
  library, including Tkinter for the GUI, which is included with the
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
6. Search tasks
7. Filter tasks
8. Sort tasks
9. Summary
0. Exit
```

- Tasks are listed in a table with the columns ID, Title, Due Date, Priority
  and Status; the subject and any description appear beneath each task.
- To edit a task, enter its ID, then the numbers of the fields to change,
  separated by commas (for example `1,5` for title and priority).
- The `Search:`, `Filters:` and `Sort:` lines above the list show the
  current view settings, for example `Filters: status=Pending, priority=High`.
  An empty search query clears the search.
- To filter, choose the status, priority or subject filter, then enter a
  value. For status and priority, an empty answer or `All` clears the
  filter; for the subject, only an empty answer clears it, so a subject
  named `All` can still be filtered.
- While changes are unsaved, the menu shows `Unsaved changes`. Exiting then
  offers **Retry saving**, **Exit without saving** and **Cancel exit**.
- If the data file is invalid, the application shows an error and does not
  start; the file is left unchanged.
- Unexpected errors are reported with a short message, and their details are
  written to standard error.
- The unsaved-changes prompt cannot be shown when the program is ended
  forcibly, for example with Ctrl+C.

## Running the GUI version

From the repository root:

```
python src/gui.py
```

- The task list is shown from start-up, with the subject and any description
  on grey rows beneath each task. Select a task, then use **Edit task**,
  **Delete task** or **Change status**; double-clicking a task also opens
  it for editing.
- The add and edit forms show validation errors inside the form and keep
  the entered values. The edit form starts with the task's current values;
  only changed fields are submitted.
- Search, the status, priority and subject filters, and **Sort by** apply
  as soon as they change. **Clear subject** removes the subject filter, so
  a subject named `All` can still be filtered.
- The **Summary** panel updates after every change; **Refresh**
  recalculates it with the current date.
- While changes are unsaved, the window title shows `(unsaved)`. **Exit**
  and the window's close button then offer **Retry saving**, **Exit without
  saving** and **Cancel exit**.
- If the data file is invalid, an error is shown and the window does not
  open; the file is left unchanged.
- Unexpected errors are reported with a short message and their details are
  written to standard error. When the GUI is started with `pythonw` or by
  double-clicking, standard error is not visible; start it with `python`
  from a terminal to see the details.

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
| `tests/test_core.py` | Task operations, search, filters, merge sort, summary, the list view and messages |
| `tests/test_cli.py` | The text-based interface, with scripted input |
| `tests/test_gui.py` | The GUI on a hidden Tk window; skipped when no display is available |

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
│   ├── core.py          Shared core: task operations, validation, search,
│   │                    filters, merge sort, summary, messages,
│   │                    persistence coordination
│   ├── storage.py       JSON loading and saving
│   ├── cli.py           Text-based interface
│   └── gui.py           Tkinter interface
├── tests/
│   ├── helpers.py       Puts src/ on the import path
│   ├── test_validation.py
│   ├── test_storage.py
│   ├── test_core.py
│   ├── test_cli.py
│   └── test_gui.py
├── report/
│   ├── main.tex         Coursework report (LaTeX)
│   └── references.bib
└── docs/                Documentation (currently empty)
```
