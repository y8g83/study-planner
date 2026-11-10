"""Shared core of the Study Planner: validation, messages and task rules.

Both the text (CLI) and the Tkinter (GUI) versions call this module; neither
interface validates input or builds messages itself. This module implements
FR5, input validation, and coordinates FR6 loading, saving and the unsaved
state; ``storage`` does the file work.
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

# --- Central message table -------------------------------------------------

MESSAGES = {
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


# --- Persistence (FR6) -------------------------------------------------------

LOADED = "loaded"
INVALID_STORED_DATA = "invalid_stored_data"


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
