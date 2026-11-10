"""Shared core of the Study Planner: validation, messages and task rules.

Both the text (CLI) and the Tkinter (GUI) versions call this module; neither
interface validates input or builds messages itself. This module implements
the task operations (FR1-FR4), input validation (FR5) and the list view, and
coordinates FR6 loading, saving and the unsaved state; ``storage`` does the
file work.
"""

import re
from dataclasses import dataclass, field
from datetime import date

import storage

# --- Field labels (exact, FR5) ---------------------------------------------

TITLE = "Title"
SUBJECT = "Subject"
DESCRIPTION = "Description"
DUE_DATE = "Due date"
PRIORITY = "Priority"
STATUS = "Status"
TASK_ID = "Task ID"

# Several errors are reported in this fixed field order.
FIELD_ORDER = (TITLE, SUBJECT, DESCRIPTION, DUE_DATE, PRIORITY, STATUS)

# --- Rule identifiers ------------------------------------------------------

REQUIRED = "required"
DATE_FORMAT = "date_format"
INVALID_CALENDAR_DATE = "invalid_calendar_date"
INVALID_CHOICE = "invalid_choice"
INVALID_TASK_ID_FORMAT = "invalid_task_id_format"
TASK_ID_MUST_BE_POSITIVE = "task_id_must_be_positive"

# --- Permitted values (canonical forms) and creation defaults --------------

PRIORITIES = ("High", "Medium", "Low")
STATUSES = ("Pending", "In Progress", "Completed")
DEFAULT_PRIORITY = "Medium"
DEFAULT_STATUS = "Pending"

# Fields that an edit (FR2) may change; status changes only through FR4.
EDITABLE_FIELDS = ("title", "subject", "description", "due_date", "priority")

# Field names as shown in messages about changed fields (FR2).
FIELD_NAMES = {
    "title": "title",
    "subject": "subject",
    "description": "description",
    "due_date": "due date",
    "priority": "priority",
}

# --- Message keys for operations, persistence and the list view ----------

TASK_ADDED = "task_added"
TASK_UPDATED = "task_updated"
NO_CHANGES = "no_changes"
TASK_DELETED = "task_deleted"
DELETION_CANCELLED = "deletion_cancelled"
STATUS_CHANGED = "status_changed"
STATUS_UNCHANGED = "status_unchanged"
TASK_NOT_FOUND = "task_not_found"
SAVE_FAILED = "save_failed"
UNSAVED_INDICATOR = "unsaved_indicator"
INVALID_STORED_DATA = "invalid_stored_data"
EXIT_UNSAVED = "exit_unsaved"
EXIT_RETRY = "exit_retry"
EXIT_DISCARD = "exit_discard"
EXIT_CANCEL = "exit_cancel"
RETRY_FAILED = "retry_failed"
ALL_SAVED = "all_saved"
NO_TASKS_YET = "no_tasks_yet"
NO_MATCHING_TASKS = "no_matching_tasks"
INTERNAL_ERROR = "internal_error"

# --- Central message table -------------------------------------------------

MESSAGES = {
    TASK_ADDED: "Task {task_id} added.",
    TASK_UPDATED: "Task {task_id} updated. Changed fields: {fields}.",
    NO_CHANGES: "No changes were made to task {task_id}.",
    TASK_DELETED: "Task {task_id} deleted.",
    DELETION_CANCELLED: "Deletion cancelled.",
    STATUS_CHANGED: "Task {task_id} status changed to {status}.",
    STATUS_UNCHANGED: "Task {task_id} already has status {status}; "
                      "the status is unchanged.",
    TASK_NOT_FOUND: "No task with ID {task_id} exists.",
    SAVE_FAILED: "Warning: the changes could not be saved. They remain in "
                 "memory and are marked as unsaved.",
    UNSAVED_INDICATOR: "Unsaved changes",
    INVALID_STORED_DATA: "The stored data in {path} is invalid, so the "
                         "application cannot start. The file has not been "
                         "changed.",
    EXIT_UNSAVED: "There are unsaved changes.",
    EXIT_RETRY: "Retry saving",
    EXIT_DISCARD: "Exit without saving (changes made since the last "
                  "successful save will be lost)",
    EXIT_CANCEL: "Cancel exit",
    RETRY_FAILED: "Saving failed again. The data remains unsaved.",
    ALL_SAVED: "All changes have been saved.",
    NO_TASKS_YET: "No tasks yet.",
    NO_MATCHING_TASKS: "No tasks match the current search and filters.",
    INTERNAL_ERROR: "An internal application error occurred. "
                    "Please try again.",

    REQUIRED: "{field} must not be empty after trimming.",
    DATE_FORMAT: "{field} must use the YYYY-MM-DD format.",
    INVALID_CALENDAR_DATE: "{field} must be a real calendar date.",
    INVALID_CHOICE: "{field} must exactly match one of the permitted values.",
    INVALID_TASK_ID_FORMAT: (
        "{field} must be a positive ASCII integer without signs, spaces, "
        "separators, or leading zeros."),
    TASK_ID_MUST_BE_POSITIVE: "{field} must be greater than zero.",
}


class MessageError(Exception):
    """A message key or parameter is missing or invalid.

    This is a programming error, not a user-input error: it must
    never be shown as a normal result or replaced by a guessed message.
    """


def render_message(key, **params):
    """Return the exact text for ``key`` from the central message table."""
    try:
        template = MESSAGES[key]
    except KeyError:
        raise MessageError(f"unknown message key: {key!r}") from None
    try:
        return template.format(**params)
    except (KeyError, IndexError) as exc:
        raise MessageError(
            f"missing parameter {exc} for message {key!r}") from None


# --- Results ----------------------------------------------------------------

@dataclass(frozen=True)
class ValidationError:
    """One validation error: the field and the rule it broke."""

    field: str
    rule: str

    @property
    def message(self):
        return render_message(self.rule, field=self.field)


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating one submission.

    ``values`` holds the normalised values when the submission is valid and
    is ``None`` otherwise, so a rejected submission can never be partly
    applied (FR5: no partial change).
    """

    values: object = None
    errors: tuple = field(default_factory=tuple)

    @property
    def ok(self):
        return not self.errors


_ERROR_ORDER = FIELD_ORDER + (TASK_ID,)


def _sorted_errors(errors):
    return tuple(sorted(errors, key=lambda e: _ERROR_ORDER.index(e.field)))


def _result(values, errors):
    if errors:
        return ValidationResult(values=None, errors=_sorted_errors(errors))
    return ValidationResult(values=values)


# --- Field rules ------------------------------------------------------------

DATE_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TASK_ID_SHAPE = re.compile(r"0|[1-9][0-9]*")


def _trim(value):
    """Trim with ``str.strip()``; a missing value counts as empty."""
    return "" if value is None else value.strip()


def _required_text(label, value, errors):
    text = _trim(value)
    if not text:
        errors.append(ValidationError(label, REQUIRED))
    return text


def _due_date(value, errors):
    """Due date: required, then exact shape, then a real date."""
    text = _trim(value)
    if not text:
        errors.append(ValidationError(DUE_DATE, REQUIRED))
    elif not DATE_SHAPE.fullmatch(text):
        errors.append(ValidationError(DUE_DATE, DATE_FORMAT))
    else:
        try:
            date.fromisoformat(text)
        except ValueError:
            errors.append(ValidationError(DUE_DATE, INVALID_CALENDAR_DATE))
    return text


def _choice(label, value, permitted, default, errors):
    """Trim, match case-insensitively, return the canonical form.

    ``default`` is used when the value is empty after trimming; ``None``
    means there is no default in this context, so empty is ``required``.
    """
    text = _trim(value)
    if not text:
        if default is None:
            errors.append(ValidationError(label, REQUIRED))
        return default
    for canonical in permitted:
        if text.casefold() == canonical.casefold():
            return canonical
    errors.append(ValidationError(label, INVALID_CHOICE))
    return None


# --- Validation entry points, one per operation ----------------------------

def validate_new_task(title, subject, due_date, description=None,
                      priority=None, status=None):
    """Validate a task being added (FR1); creation defaults apply.

    On success, ``values`` is a dict with the keys ``title``, ``subject``,
    ``description``, ``due_date``, ``priority`` and ``status``.
    """
    errors = []
    values = {
        "title": _required_text(TITLE, title, errors),
        "subject": _required_text(SUBJECT, subject, errors),
        "description": _trim(description),
        "due_date": _due_date(due_date, errors),
        "priority": _choice(PRIORITY, priority, PRIORITIES,
                            DEFAULT_PRIORITY, errors),
        "status": _choice(STATUS, status, STATUSES, DEFAULT_STATUS, errors),
    }
    return _result(values, errors)


def validate_task_edit(changes):
    """Validate the fields selected for an edit (FR2).

    ``changes`` maps field names from ``EDITABLE_FIELDS`` to new values.
    The create rules apply without defaults. On success, ``values`` holds
    the normalised values of the selected fields only.
    """
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"fields not editable through FR2: {sorted(unknown)}")
    errors = []
    values = {}
    if "title" in changes:
        values["title"] = _required_text(TITLE, changes["title"], errors)
    if "subject" in changes:
        values["subject"] = _required_text(SUBJECT, changes["subject"],
                                           errors)
    if "description" in changes:
        values["description"] = _trim(changes["description"])
    if "due_date" in changes:
        values["due_date"] = _due_date(changes["due_date"], errors)
    if "priority" in changes:
        values["priority"] = _choice(PRIORITY, changes["priority"],
                                     PRIORITIES, None, errors)
    return _result(values, errors)


def validate_status_change(status):
    """Validate a new status (FR4); no default, so empty is ``required``.

    On success, ``values`` is the canonical status string.
    """
    errors = []
    value = _choice(STATUS, status, STATUSES, None, errors)
    return _result(value, errors)


def validate_task_id(text):
    """Validate typed task-ID text (FR5 AC6); it is never trimmed.

    The syntax rule comes first; only a syntactically valid ASCII integer
    reaches the positivity rule. On success, ``values`` is the
    ID as an ``int``. Whether the task exists is checked by FR2-FR4.
    """
    if not isinstance(text, str) or not _TASK_ID_SHAPE.fullmatch(text):
        return _result(None, [ValidationError(TASK_ID,
                                              INVALID_TASK_ID_FORMAT)])
    value = int(text)
    if value <= 0:
        return _result(None, [ValidationError(TASK_ID,
                                              TASK_ID_MUST_BE_POSITIVE)])
    return _result(value, [])


# --- Operation results ------------------------------------------------------

SUCCESS = "success"
NO_CHANGE = "no_change"
INVALID = "invalid"
NOT_FOUND = "not_found"
FOUND = "found"


@dataclass(frozen=True)
class OperationResult:
    """The outcome of one task operation, kept apart from saving.

    ``outcome`` is one of ``SUCCESS``, ``NO_CHANGE``, ``INVALID``,
    ``NOT_FOUND`` or ``FOUND``. ``message`` and ``params`` give the message
    key and its parameters; ``errors`` holds the validation errors of an
    ``INVALID`` outcome. ``saved`` is ``None`` when no save was attempted,
    otherwise whether the save succeeded. ``task`` is a copy of the task
    concerned, where one exists.
    """

    outcome: str
    message: str = None
    params: dict = field(default_factory=dict)
    errors: tuple = ()
    saved: object = None
    task: object = None

    @property
    def ok(self):
        return self.outcome in (SUCCESS, NO_CHANGE, FOUND)

    def lines(self):
        """Return the exact feedback lines, in display order."""
        if self.errors:
            lines = [error.message for error in self.errors]
        else:
            lines = [render_message(self.message, **self.params)]
        if self.saved is False:
            lines.append(render_message(SAVE_FAILED))
        return lines


def _invalid(errors):
    return OperationResult(INVALID, errors=tuple(errors))


def confirms_deletion(answer):
    """Whether a CLI confirmation answer confirms a deletion (FR3).

    Only ``y`` or ``yes``, in any letter case after trimming, confirms;
    any other answer cancels.
    """
    return answer.strip().casefold() in ("y", "yes")


# --- Persistence (FR6) -------------------------------------------------------

LOADED = "loaded"


class Planner:
    """The in-memory task data of one session and its unsaved state (FR6).

    ``tasks`` is the task list in stored order and ``next_id`` the ID that
    the next added task receives. ``unsaved`` is true after a failed save
    and becomes false again after the next successful save.
    """

    def __init__(self, path, tasks, next_id):
        self.path = path
        self.tasks = tasks
        self.next_id = next_id
        self.unsaved = False

    # --- Task operations (FR1-FR4) ------------------------------------------

    def _index_of(self, task_id):
        """Linear search for a task by ID; ``None`` when there is none."""
        for index, task in enumerate(self.tasks):
            if task["id"] == task_id:
                return index
        return None

    def find_task(self, task_id_text):
        """Validate a typed task ID and look the task up (FR2-FR4).

        Called before any further input: the outcome is ``INVALID`` for a
        malformed ID, ``NOT_FOUND`` when no task has the ID, and ``FOUND``
        with a copy of the task otherwise.
        """
        checked = validate_task_id(task_id_text)
        if not checked.ok:
            return _invalid(checked.errors)
        index = self._index_of(checked.values)
        if index is None:
            return OperationResult(NOT_FOUND, TASK_NOT_FOUND,
                                   {"task_id": checked.values})
        return OperationResult(FOUND, task=dict(self.tasks[index]))

    def add_task(self, title, subject, due_date, description=None,
                 priority=None, status=None):
        """Add a task with the next ID at the end of the list (FR1)."""
        checked = validate_new_task(title, subject, due_date, description,
                                    priority, status)
        if not checked.ok:
            return _invalid(checked.errors)
        task = {"id": self.next_id, **checked.values}
        self.tasks.append(task)
        self.next_id += 1
        return OperationResult(SUCCESS, TASK_ADDED, {"task_id": task["id"]},
                               saved=self.save(), task=dict(task))

    def edit_task(self, task_id_text, changes):
        """Edit the selected fields of a task, all or nothing (FR2).

        ``changes`` maps field names from ``EDITABLE_FIELDS`` to new
        values. If no field changes after normalisation, nothing is saved.
        """
        found = self.find_task(task_id_text)
        if found.outcome != FOUND:
            return found
        checked = validate_task_edit(changes)
        if not checked.ok:
            return _invalid(checked.errors)
        task = self.tasks[self._index_of(found.task["id"])]
        changed = [name for name in EDITABLE_FIELDS
                   if name in checked.values
                   and checked.values[name] != task[name]]
        params = {"task_id": task["id"]}
        if not changed:
            return OperationResult(NO_CHANGE, NO_CHANGES, params,
                                   task=dict(task))
        for name in changed:
            task[name] = checked.values[name]
        params["fields"] = ", ".join(FIELD_NAMES[name] for name in changed)
        return OperationResult(SUCCESS, TASK_UPDATED, params,
                               saved=self.save(), task=dict(task))

    def delete_task(self, task_id_text):
        """Delete a task; the others keep their order (FR3).

        Called only after the user has confirmed; ``next_id`` is never
        changed, so a deleted ID is not reused.
        """
        found = self.find_task(task_id_text)
        if found.outcome != FOUND:
            return found
        del self.tasks[self._index_of(found.task["id"])]
        return OperationResult(SUCCESS, TASK_DELETED,
                               {"task_id": found.task["id"]},
                               saved=self.save(), task=found.task)

    def change_status(self, task_id_text, status):
        """Change only the status of a task (FR4)."""
        found = self.find_task(task_id_text)
        if found.outcome != FOUND:
            return found
        checked = validate_status_change(status)
        if not checked.ok:
            return _invalid(checked.errors)
        task = self.tasks[self._index_of(found.task["id"])]
        params = {"task_id": task["id"], "status": checked.values}
        if checked.values == task["status"]:
            return OperationResult(NO_CHANGE, STATUS_UNCHANGED, params,
                                   task=dict(task))
        task["status"] = checked.values
        return OperationResult(SUCCESS, STATUS_CHANGED, params,
                               saved=self.save(), task=dict(task))

    # --- List view (FR11) ---------------------------------------------------

    def list_view(self):
        """Return the tasks to display, as copies, and the empty message.

        The tasks are in stored order. When there are none, ``message`` is
        the key of the message to show instead. Viewing never changes the
        data or the unsaved state.
        """
        tasks = [dict(task) for task in self.tasks]
        return ListView(tasks, None if tasks else NO_TASKS_YET)

    # --- Saving -------------------------------------------------------------

    def save(self):
        """Save the complete current data; return ``True`` on success.

        A failed save keeps every change in memory and marks the data
        unsaved; a later successful save clears the unsaved state.
        """
        try:
            storage.save(self.path, self.tasks, self.next_id)
        except OSError:
            self.unsaved = True
            return False
        self.unsaved = False
        return True

    @property
    def exit_needs_prompt(self):
        """Whether exiting must offer Retry saving, Exit without saving and
        Cancel exit (FR6 Section 5)."""
        return self.unsaved


@dataclass(frozen=True)
class ListView:
    """Tasks to display, and the message key to show when there are none."""

    tasks: list
    message: str = None


@dataclass(frozen=True)
class StartResult:
    """The outcome of loading the data file at start-up (FR6 Section 1).

    ``planner`` is ``None`` when the stored data is invalid, so a session
    can never overwrite a file that failed to load.
    """

    outcome: str
    planner: object = None

    @property
    def ok(self):
        return self.outcome == LOADED


def start(path=None):
    """Load the data file for a new session.

    ``path`` defaults to ``~/.study_planner/tasks.json`` (NFR8). A missing
    file gives an empty task list and ``next_id = 1`` and creates nothing.
    """
    if path is None:
        path = storage.default_data_path()
    try:
        tasks, next_id = storage.load(path)
    except storage.InvalidDataError:
        return StartResult(INVALID_STORED_DATA)
    return StartResult(LOADED, Planner(path, tasks, next_id))
