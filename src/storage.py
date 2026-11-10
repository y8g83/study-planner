"""JSON storage for the Study Planner: strict loading and safe saving (FR6).

Only the shared core calls this module. Every function takes the complete
data-file path explicitly, so tests can use an isolated temporary directory.
Nothing is created when data is loaded; the data directory is created by the
first save that needs it (NFR8).
"""

import json
import os
import tempfile
from datetime import date
from pathlib import Path

import core

TOP_LEVEL_KEYS = ("next_id", "tasks")
TASK_KEYS = ("id", "title", "subject", "description", "due_date", "priority",
             "status")


class InvalidDataError(Exception):
    """The data file breaks a rule of FR6 Section 2 and is rejected whole."""


def default_data_path():
    """Return the data-file path ``~/.study_planner/tasks.json``."""
    return Path.home() / ".study_planner" / "tasks.json"


# --- Loading -----------------------------------------------------------------

def _reject_duplicate_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise InvalidDataError(f"duplicate key {key!r}")
        data[key] = value
    return data


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_positive_int(value):
    return _is_int(value) and value > 0


def _is_stored_text(value, allow_empty):
    if not isinstance(value, str) or value != value.strip():
        return False
    return allow_empty or value != ""


def _is_stored_date(value):
    if not isinstance(value, str) or not core.DATE_SHAPE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_task(task, position):
    where = f"task {position}"
    if not isinstance(task, dict) or set(task) != set(TASK_KEYS):
        raise InvalidDataError(f"{where}: keys are not exactly {TASK_KEYS}")
    if not _is_positive_int(task["id"]):
        raise InvalidDataError(f"{where}: id is not a positive integer")
    for key in ("title", "subject"):
        if not _is_stored_text(task[key], allow_empty=False):
            raise InvalidDataError(f"{where}: invalid {key}")
    if not _is_stored_text(task["description"], allow_empty=True):
        raise InvalidDataError(f"{where}: invalid description")
    if not _is_stored_date(task["due_date"]):
        raise InvalidDataError(f"{where}: invalid due_date")
    if task["priority"] not in core.PRIORITIES:
        raise InvalidDataError(f"{where}: priority is not canonical")
    if task["status"] not in core.STATUSES:
        raise InvalidDataError(f"{where}: status is not canonical")


def validate_data(data):
    """Raise ``InvalidDataError`` unless ``data`` meets FR6 Section 2."""
    if not isinstance(data, dict) or set(data) != set(TOP_LEVEL_KEYS):
        raise InvalidDataError(f"top level is not exactly {TOP_LEVEL_KEYS}")
    tasks = data["tasks"]
    if not isinstance(tasks, list):
        raise InvalidDataError("tasks is not a list")
    for position, task in enumerate(tasks, start=1):
        _check_task(task, position)
    ids = [task["id"] for task in tasks]
    if len(set(ids)) != len(ids):
        raise InvalidDataError("duplicate task IDs")
    next_id = data["next_id"]
    if not _is_positive_int(next_id):
        raise InvalidDataError("next_id is not a positive integer")
    if ids and next_id <= max(ids):
        raise InvalidDataError("next_id is not greater than every task ID")


def load(path):
    """Load the data file at ``path``; return ``(tasks, next_id)``.

    A missing file gives an empty list and ``next_id = 1``; nothing is
    created. An invalid file raises ``InvalidDataError`` and is never
    modified. Other ``OSError`` exceptions from reading are not caught.
    """
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return [], 1
    try:
        data = json.loads(raw.decode("utf-8"),
                          object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, ValueError) as exc:
        raise InvalidDataError(f"not valid UTF-8 JSON: {exc}") from None
    validate_data(data)
    return data["tasks"], data["next_id"]


# --- Saving ------------------------------------------------------------------

def to_json(tasks, next_id):
    """Return the exact file contents for ``tasks`` and ``next_id``."""
    data = {
        "next_id": next_id,
        "tasks": [{key: task[key] for key in TASK_KEYS} for task in tasks],
    }
    validate_data(data)
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8")


def save(path, tasks, next_id):
    """Save the complete data to ``path`` through a temporary file.

    The new contents are written to a temporary file in the same folder,
    flushed to disk, and only then moved over the real file with
    ``os.replace``, so the previous file stays intact until replacement.
    Any failure raises ``OSError`` and leaves no temporary file behind.
    Data that would not pass ``load`` raises ``InvalidDataError`` before
    anything is written.
    """
    contents = to_json(tasks, next_id)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent,
                                         prefix=f".{path.name}.",
                                         suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as temp_file:
            temp_file.write(contents)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise
