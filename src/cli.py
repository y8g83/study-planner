"""Text-based interface (CLI) of the Study Planner.

Run from the repository root with ``python src/cli.py``. This module only
reads input and shows results: validation, task rules, message texts and
saving all come from the shared core.
"""

import logging
import sys
import textwrap
from datetime import date

import core

MENU = (
    ("1", "View tasks"),
    ("2", "Add task"),
    ("3", "Edit task"),
    ("4", "Delete task"),
    ("5", "Change task status"),
    ("6", "Search tasks"),
    ("7", "Filter tasks"),
    ("8", "Sort tasks"),
    ("9", "Summary"),
    ("0", "Exit"),
)

# Filters offered by the filter menu, and sort options by number.
FILTER_CHOICES = (("1", core.FILTER_STATUS), ("2", core.FILTER_PRIORITY),
                  ("3", core.FILTER_SUBJECT))
SORT_CHOICES = (("0", None),) + tuple(
    (str(number), sort)
    for number, sort in enumerate(core.SORT_FIELDS, start=1))

# Fields offered by the edit menu, in the core's field order.
EDIT_FIELDS = tuple(
    (str(number), name)
    for number, name in enumerate(core.EDITABLE_FIELDS, start=1))

INVALID_OPTION = "Please choose one of the listed options."
INVALID_FIELD_SELECTION = (
    "Please enter one or more field numbers from 1 to "
    f"{len(EDIT_FIELDS)}, separated by commas.")

# --- Task table layout ------------------------------------------------------

HEADINGS = ("ID", "Title", "Due Date", "Priority", "Status")
TITLE_WIDTH = 30
DUE_DATE_WIDTH = len("YYYY-MM-DD")
PRIORITY_WIDTH = max(len(text) for text in (HEADINGS[3], *core.PRIORITIES))
STATUS_WIDTH = max(len(text) for text in (HEADINGS[4], *core.STATUSES))
COLUMN_SEPARATOR = " | "


def _wrap(text, width, indent=""):
    return textwrap.wrap(text, width, initial_indent=indent,
                         subsequent_indent=indent, break_on_hyphens=False)


def format_task_table(tasks):
    """Return the lines of the task table for a non-empty task list.

    Long titles wrap inside the Title column; beneath each task, the
    subject and, when not empty, the description are indented to the Title
    column and wrapped to the width of the table.
    """
    id_width = max(2, max(len(str(task["id"])) for task in tasks))
    widths = (id_width, TITLE_WIDTH, DUE_DATE_WIDTH, PRIORITY_WIDTH,
              STATUS_WIDTH)
    table_width = sum(widths) + len(COLUMN_SEPARATOR) * (len(widths) - 1)
    indent = " " * (id_width + len(COLUMN_SEPARATOR))

    def row(cells):
        padded = (cell.ljust(width) for cell, width in zip(cells, widths))
        return COLUMN_SEPARATOR.join(padded).rstrip()

    lines = [row(HEADINGS), "-" * table_width]
    for task in tasks:
        title_lines = _wrap(task["title"], TITLE_WIDTH)
        lines.append(row((str(task["id"]), title_lines[0], task["due_date"],
                          task["priority"], task["status"])))
        lines.extend(row(("", text, "", "", "")) for text in title_lines[1:])
        lines.extend(_wrap(f"Subject: {task['subject']}", table_width,
                           indent))
        if task["description"]:
            lines.extend(_wrap(task["description"], table_width, indent))
    return lines


class StudyPlannerCLI:
    """The menu loop of one session, working on a loaded planner."""

    def __init__(self, planner, read=input, write=print, today=date.today):
        self.planner = planner
        self.read = read
        self.write = write
        self.today = today
        self.actions = {
            "1": self.view_tasks,
            "2": self.add_task,
            "3": self.edit_task,
            "4": self.delete_task,
            "5": self.change_status,
            "6": self.search_tasks,
            "7": self.filter_tasks,
            "8": self.sort_tasks,
            "9": self.show_summary,
        }

    def show(self, *lines):
        for line in lines:
            self.write(line)

    def show_message(self, key, **params):
        self.write(core.render_message(key, **params))

    def show_menu(self):
        self.write()
        self.write("Study Planner")
        if self.planner.unsaved:
            self.show_message(core.UNSAVED_INDICATOR)
        for key, label in MENU:
            self.write(f"{key}. {label}")

    def run(self):
        """Run the menu until the user exits; return the exit status."""
        try:
            while True:
                self.show_menu()
                choice = self.read("Choose an option: ").strip()
                if choice == "0":
                    if self.confirm_exit():
                        return 0
                elif choice in self.actions:
                    self.perform(self.actions[choice])
                else:
                    self.write(INVALID_OPTION)
        except (EOFError, KeyboardInterrupt):
            self.write()
            return 1

    def perform(self, action):
        """Run one menu action; an unexpected error never ends the session."""
        try:
            action()
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception as exc:
            core.log_internal_error(exc)
            self.show_message(core.INTERNAL_ERROR)

    # --- Menu actions ------------------------------------------------------

    def view_tasks(self):
        self.show(*core.view_lines(self.planner.view))
        view = self.planner.list_view()
        if view.message:
            self.show_message(view.message)
        else:
            self.show(*format_task_table(view.tasks))

    def add_task(self):
        title = self.read("Title: ")
        subject = self.read("Subject: ")
        description = self.read("Description (optional): ")
        due_date = self.read("Due date (YYYY-MM-DD): ")
        priority = self.read(
            f"Priority ({', '.join(core.PRIORITIES)}; "
            f"press Enter for {core.DEFAULT_PRIORITY}): ")
        status = self.read(
            f"Status ({', '.join(core.STATUSES)}; "
            f"press Enter for {core.DEFAULT_STATUS}): ")
        result = self.planner.add_task(title, subject, due_date, description,
                                       priority, status)
        self.show(*result.lines())

    def find_task(self):
        """Ask for a task ID; return its text and task, or ``None``.

        The core validates the ID and checks that the task exists before
        any further question is asked.
        """
        task_id_text = self.read("Task ID: ")
        found = self.planner.find_task(task_id_text)
        if found.outcome != core.FOUND:
            self.show(*found.lines())
            return None
        return task_id_text, found.task

    def edit_task(self):
        selected = self.find_task()
        if selected is None:
            return
        task_id_text, task = selected
        self.write("Fields: " + ", ".join(
            f"{number} {core.FIELD_NAMES[name].capitalize()}"
            for number, name in EDIT_FIELDS))
        names = self.parse_field_selection(
            self.read("Fields to edit (numbers separated by commas): "))
        if names is None:
            self.write(INVALID_FIELD_SELECTION)
            return
        changes = {}
        for name in names:
            current = task[name] or "empty"
            changes[name] = self.read(
                f"New {core.FIELD_NAMES[name]} (current: {current}): ")
        self.show(*self.planner.edit_task(task_id_text, changes).lines())

    @staticmethod
    def parse_field_selection(text):
        """Return the selected field names in field order, or ``None``."""
        numbers = {part.strip() for part in text.split(",")}
        names = dict(EDIT_FIELDS)
        if not numbers or not numbers <= set(names):
            return None
        return [name for number, name in EDIT_FIELDS if number in numbers]

    def delete_task(self):
        selected = self.find_task()
        if selected is None:
            return
        task_id_text, task = selected
        answer = self.read(
            f"Delete task {task['id']} \"{task['title']}\"? (y/n): ")
        if core.confirms_deletion(answer):
            self.show(*self.planner.delete_task(task_id_text).lines())
        else:
            self.show_message(core.DELETION_CANCELLED)

    def change_status(self):
        selected = self.find_task()
        if selected is None:
            return
        task_id_text, task = selected
        status = self.read(
            f"New status ({', '.join(core.STATUSES)}; "
            f"current: {task['status']}): ")
        self.show(*self.planner.change_status(task_id_text, status).lines())

    # --- Search, filters, sort and summary (FR7-FR10) -----------------------

    def search_tasks(self):
        self.planner.set_search(
            self.read("Search query (press Enter to clear): "))
        self.view_tasks()

    def filter_tasks(self):
        self.write("Filters: " + ", ".join(
            f"{number} {name.capitalize()}"
            for number, name in FILTER_CHOICES))
        name = dict(FILTER_CHOICES).get(
            self.read("Filter to change: ").strip())
        if name is None:
            self.write(INVALID_OPTION)
            return
        if name == core.FILTER_SUBJECT:
            prompt = "Subject filter (press Enter to clear): "
        else:
            values = (core.STATUSES if name == core.FILTER_STATUS
                      else core.PRIORITIES)
            prompt = (f"{name.capitalize()} filter ({', '.join(values)} "
                      f"or {core.ALL}; press Enter for {core.ALL}): ")
        result = self.planner.set_filter(name, self.read(prompt))
        if not result.ok:
            self.show(*result.lines())
        self.view_tasks()

    def sort_tasks(self):
        self.write("Sort by: " + ", ".join(
            f"{number} {(sort or 'none').capitalize()}"
            for number, sort in SORT_CHOICES))
        choice = self.read("Sort option: ").strip()
        choices = dict(SORT_CHOICES)
        if choice not in choices:
            self.write(INVALID_OPTION)
            return
        self.planner.set_sort(choices[choice])
        self.view_tasks()

    def show_summary(self):
        self.show(*self.planner.summary(self.today()).lines())

    # --- Exit (FR6) ----------------------------------------------------------

    def confirm_exit(self):
        """Return whether to exit, offering the unsaved-changes choices."""
        if not self.planner.exit_needs_prompt:
            return True
        while True:
            self.write()
            self.show_message(core.EXIT_UNSAVED)
            self.write(f"1. {core.render_message(core.EXIT_RETRY)}")
            self.write(f"2. {core.render_message(core.EXIT_DISCARD)}")
            self.write(f"3. {core.render_message(core.EXIT_CANCEL)}")
            choice = self.read("Choose an option: ").strip()
            if choice == "1":
                if self.planner.save():
                    self.show_message(core.ALL_SAVED)
                    return True
                self.show_message(core.RETRY_FAILED)
            elif choice == "2":
                return True
            elif choice == "3":
                return False
            else:
                self.write(INVALID_OPTION)


def main(path=None, read=input, write=print, today=date.today):
    """Start a session on the data file at ``path``; return the exit status.

    ``path`` defaults to ``~/.study_planner/tasks.json``. When the stored
    data is invalid, the error is shown and the session does not start.
    """
    try:
        started = core.start(path)
    except Exception as exc:
        core.log_internal_error(exc)
        write(core.render_message(core.INTERNAL_ERROR))
        return 1
    if not started.ok:
        for line in started.lines():
            write(line)
        return 1
    return StudyPlannerCLI(started.planner, read, write, today).run()


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s: %(message)s")
    sys.exit(main())
