"""Tkinter interface (GUI) of the Study Planner.

Run from the repository root with ``python src/gui.py``. Like the CLI, this
module only collects input and shows results: validation, task rules,
message texts and saving all come from the shared core.
"""

import logging
import sys
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

import core

APP_TITLE = "Study Planner"
UNSAVED_TITLE = f"{APP_TITLE} (unsaved)"
CONFIRM = "Confirm"
CANCEL = "Cancel"
SELECT_TASK = "Select a task in the list first."

COLUMNS = (("id", "ID", 50), ("title", "Title", 300),
           ("due_date", "Due Date", 100), ("priority", "Priority", 80),
           ("status", "Status", 100))
STATUS_FILTER_OPTIONS = (core.ALL,) + core.STATUSES
PRIORITY_FILTER_OPTIONS = (core.ALL,) + core.PRIORITIES
SORT_NONE = "None"
SORT_OPTIONS = {SORT_NONE: None,
                **{sort.capitalize(): sort for sort in core.SORT_FIELDS}}
FORM_FIELDS = (("title", "Title"), ("subject", "Subject"),
               ("description", "Description"),
               ("due_date", "Due date (YYYY-MM-DD)"))


def make_modal(window, parent):
    """Keep a dialog above its parent and route input to it when shown."""
    window.transient(parent)
    if parent.winfo_viewable():
        window.grab_set()


class ChoiceDialog:
    """A dialog with a message and one button per choice.

    ``result`` is the label of the chosen button, or ``None`` when the
    window is closed without a choice.
    """

    def __init__(self, parent, title, message, choices, stacked=False):
        self.result = None
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.resizable(False, False)
        ttk.Label(self.window, text=message, wraplength=440,
                  justify="left").pack(padx=16, pady=(16, 12), anchor="w")
        buttons = ttk.Frame(self.window)
        buttons.pack(padx=16, pady=(0, 16), fill="x")
        self.buttons = {}
        for choice in choices:
            button = ttk.Button(buttons, text=choice,
                                command=lambda c=choice: self.choose(c))
            if stacked:
                button.pack(fill="x", pady=2)
            else:
                button.pack(side="right", padx=(8, 0))
            self.buttons[choice] = button
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        make_modal(self.window, parent)

    def choose(self, choice):
        self.result = choice
        self.window.destroy()


def ask_choice(parent, title, message, choices, stacked=False):
    """Show a ``ChoiceDialog`` and wait for the answer."""
    dialog = ChoiceDialog(parent, title, message, choices, stacked)
    parent.wait_window(dialog.window)
    return dialog.result


class TaskForm:
    """The add or edit form.

    An add form starts with the creation defaults; an edit form starts
    with the task's current values and has no status field (FR4 changes
    the status). ``on_save`` receives the form and returns the core's
    result; the form closes only when the result is not a rejection, and
    otherwise shows the errors and keeps the entered values.
    """

    def __init__(self, parent, title, on_save, task=None):
        self.task = task
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.resizable(False, False)
        body = ttk.Frame(self.window, padding=16)
        body.pack(fill="both", expand=True)
        self.vars = {}
        row = 0
        for name, label in FORM_FIELDS:
            self.vars[name] = tk.StringVar(
                value=task[name] if task else "")
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w",
                                             pady=3)
            ttk.Entry(body, textvariable=self.vars[name], width=48).grid(
                row=row, column=1, sticky="ew", pady=3)
            row += 1
        choices = [("priority", "Priority", core.PRIORITIES,
                    task["priority"] if task else core.DEFAULT_PRIORITY)]
        if task is None:
            choices.append(("status", "Status", core.STATUSES,
                            core.DEFAULT_STATUS))
        self.boxes = {}
        for name, label, values, initial in choices:
            self.vars[name] = tk.StringVar(value=initial)
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w",
                                             pady=3)
            self.boxes[name] = ttk.Combobox(
                body, textvariable=self.vars[name], values=values,
                state="readonly", width=14)
            self.boxes[name].grid(row=row, column=1, sticky="w", pady=3)
            row += 1
        self.errors = tk.StringVar()
        ttk.Label(body, textvariable=self.errors, foreground="#b00020",
                  justify="left").grid(row=row, column=0, columnspan=2,
                                       sticky="w", pady=(8, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e",
                     pady=(12, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(
            side="right", padx=(8, 0))
        ttk.Button(buttons, text=CANCEL, command=self.window.destroy).pack(
            side="right")
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        make_modal(self.window, parent)

    def values(self):
        return {name: var.get() for name, var in self.vars.items()}

    def changed_values(self):
        """The fields whose text differs from the task's current value."""
        return {name: value for name, value in self.values().items()
                if value != self.task[name]}

    def save(self):
        result = self.on_save(self)
        if result.outcome == core.INVALID:
            self.errors.set("\n".join(result.lines()))
        else:
            self.window.destroy()


class StatusForm:
    """Choose a new status from a drop-down that starts at the current one."""

    def __init__(self, parent, task, on_save):
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title(f"Change status of task {task['id']}")
        self.window.resizable(False, False)
        body = ttk.Frame(self.window, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Task {task['id']}: {task['title']}",
                  wraplength=360).grid(row=0, column=0, columnspan=2,
                                       sticky="w", pady=(0, 8))
        ttk.Label(body, text="Status").grid(row=1, column=0, sticky="w")
        self.status = tk.StringVar(value=task["status"])
        self.box = ttk.Combobox(body, textvariable=self.status,
                                values=core.STATUSES, state="readonly",
                                width=14)
        self.box.grid(row=1, column=1, sticky="w", padx=8)
        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(
            side="right", padx=(8, 0))
        ttk.Button(buttons, text=CANCEL, command=self.window.destroy).pack(
            side="right")
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        make_modal(self.window, parent)

    def save(self):
        self.on_save(self.status.get())
        self.window.destroy()


class StudyPlannerGUI:
    """The main window of one session, working on a loaded planner.

    ``today`` supplies the date for the summary; ``ask_choice`` shows a
    choice dialog and returns the chosen label or ``None``.
    """

    def __init__(self, root, planner, today=date.today,
                 ask_choice=ask_choice):
        self.root = root
        self.planner = planner
        self.today = today
        self.ask_choice = ask_choice
        self.root.title(APP_TITLE)
        self.root.minsize(760, 560)
        self.root.protocol("WM_DELETE_WINDOW", self.exit)
        self.root.report_callback_exception = self.report_error
        self.feedback = tk.StringVar()
        self.message = tk.StringVar()
        self.build_view_controls()
        self.build_task_list()
        self.build_actions()
        self.build_summary()
        self.refresh()

    # --- Layout ------------------------------------------------------------

    def build_view_controls(self):
        frame = ttk.LabelFrame(self.root, text="Search, filters and sort",
                               padding=8)
        frame.pack(fill="x", padx=12, pady=(12, 6))
        self.search = tk.StringVar(value=self.planner.view.search)
        self.status_filter = tk.StringVar(value=core.ALL)
        self.priority_filter = tk.StringVar(value=core.ALL)
        self.subject_filter = tk.StringVar()
        self.sort = tk.StringVar(value=SORT_NONE)

        ttk.Label(frame, text="Search").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.search, width=30).grid(
            row=0, column=1, columnspan=3, sticky="ew", padx=(6, 12))
        ttk.Label(frame, text="Sort by").grid(row=0, column=4, sticky="w")
        self.sort_box = ttk.Combobox(frame, textvariable=self.sort,
                                     values=list(SORT_OPTIONS),
                                     state="readonly", width=12)
        self.sort_box.grid(row=0, column=5, sticky="w", padx=6)
        ttk.Label(frame, text="Status").grid(row=1, column=0, sticky="w",
                                             pady=(6, 0))
        self.status_box = ttk.Combobox(frame, textvariable=self.status_filter,
                                       values=STATUS_FILTER_OPTIONS,
                                       state="readonly", width=12)
        self.status_box.grid(row=1, column=1, sticky="w", padx=6,
                             pady=(6, 0))
        ttk.Label(frame, text="Priority").grid(row=1, column=2, sticky="w",
                                               pady=(6, 0))
        self.priority_box = ttk.Combobox(
            frame, textvariable=self.priority_filter,
            values=PRIORITY_FILTER_OPTIONS, state="readonly", width=10)
        self.priority_box.grid(row=1, column=3, sticky="w", padx=6,
                               pady=(6, 0))
        ttk.Label(frame, text="Subject").grid(row=1, column=4, sticky="w",
                                              pady=(6, 0))
        ttk.Entry(frame, textvariable=self.subject_filter, width=16).grid(
            row=1, column=5, sticky="w", padx=6, pady=(6, 0))
        ttk.Button(frame, text="Clear subject",
                   command=self.clear_subject_filter).grid(
            row=1, column=6, sticky="w", pady=(6, 0))
        frame.columnconfigure(1, weight=1)

        self.search.trace_add("write", self.apply_search)
        self.status_filter.trace_add(
            "write", lambda *_: self.apply_filter(core.FILTER_STATUS,
                                                  self.status_filter))
        self.priority_filter.trace_add(
            "write", lambda *_: self.apply_filter(core.FILTER_PRIORITY,
                                                  self.priority_filter))
        self.subject_filter.trace_add(
            "write", lambda *_: self.apply_filter(core.FILTER_SUBJECT,
                                                  self.subject_filter))
        self.sort.trace_add("write", self.apply_sort)

    def build_task_list(self):
        frame = ttk.LabelFrame(self.root, text="Tasks", padding=8)
        frame.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS],
                                 show="headings", selectmode="browse")
        for name, heading, width in COLUMNS:
            self.tree.heading(name, text=heading, anchor="w")
            self.tree.column(name, width=width, minwidth=width,
                             stretch=name == "status", anchor="w")
        scrollbar = ttk.Scrollbar(frame, orient="vertical",
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        ttk.Label(frame, textvariable=self.message).grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.tag_configure("detail", foreground="#555555")
        self.tree.bind("<Double-1>", lambda _event: self.edit_task())

    def build_actions(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=12, pady=6)
        for text, command in (("Add task", self.add_task),
                              ("Edit task", self.edit_task),
                              ("Delete task", self.delete_task),
                              ("Change status", self.change_status)):
            ttk.Button(frame, text=text, command=command).pack(
                side="left", padx=(0, 8))
        ttk.Button(frame, text="Exit", command=self.exit).pack(side="right")
        ttk.Label(self.root, textvariable=self.feedback, justify="left",
                  wraplength=720).pack(fill="x", padx=12, pady=(0, 6))

    def build_summary(self):
        frame = ttk.LabelFrame(self.root, text="Summary", padding=8)
        frame.pack(fill="x", padx=12, pady=(6, 12))
        self.summary_lines = [tk.StringVar() for _ in range(5)]
        for column, var in enumerate(self.summary_lines):
            ttk.Label(frame, textvariable=var).grid(row=0, column=column,
                                                    sticky="w", padx=(0, 24))
        ttk.Button(frame, text="Refresh", command=self.refresh_summary).grid(
            row=0, column=5, sticky="e")
        frame.columnconfigure(5, weight=1)

    # --- Display -----------------------------------------------------------

    def refresh(self):
        """Redraw the title, the task list and the summary."""
        self.root.title(UNSAVED_TITLE if self.planner.unsaved
                        else APP_TITLE)
        view = self.planner.list_view()
        selection = self.tree.selection()
        selected = selection and (self.tree.parent(selection[0])
                                  or selection[0])
        self.tree.delete(*self.tree.get_children())
        for task in view.tasks:
            item = self.tree.insert("", "end", iid=str(task["id"]), open=True,
                                    values=(task["id"], task["title"],
                                            task["due_date"],
                                            task["priority"],
                                            task["status"]))
            self.tree.insert(item, "end", tags=("detail",),
                             values=("", f"Subject: {task['subject']}"))
            if task["description"]:
                self.tree.insert(item, "end", tags=("detail",),
                                 values=("", task["description"]))
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
        self.message.set(core.render_message(view.message)
                         if view.message else "")
        self.refresh_summary()

    def refresh_summary(self):
        """Recalculate the summary with the current local date."""
        lines = self.planner.summary(self.today()).lines()
        for var, line in zip(self.summary_lines, lines):
            var.set(line)

    def show_result(self, result):
        self.feedback.set("\n".join(result.lines()))
        self.refresh()

    def displayed_ids(self):
        return [int(item) for item in self.tree.get_children()]

    def selected_task(self):
        """The selected task, from its row or one of its secondary rows."""
        selection = self.tree.selection()
        if not selection:
            self.feedback.set(SELECT_TASK)
            return None
        item = self.tree.parent(selection[0]) or selection[0]
        found = self.planner.find_task(item)
        if found.outcome != core.FOUND:
            self.show_result(found)
            return None
        return found.task

    def select(self, task_id):
        """Select the row of a task, as a click on it would."""
        self.tree.selection_set(str(task_id))

    # --- View controls -----------------------------------------------------

    def apply_search(self, *_):
        self.planner.set_search(self.search.get())
        self.refresh()

    def apply_filter(self, name, var):
        result = self.planner.set_filter(name, var.get())
        if not result.ok:
            self.show_result(result)
            return
        self.refresh()

    def clear_subject_filter(self):
        self.subject_filter.set("")

    def apply_sort(self, *_):
        self.planner.set_sort(SORT_OPTIONS[self.sort.get()])
        self.refresh()

    # --- Task operations ---------------------------------------------------

    def add_task(self):
        return TaskForm(self.root, "Add task", self.save_new_task)

    def save_new_task(self, form):
        values = form.values()
        result = self.planner.add_task(
            values["title"], values["subject"], values["due_date"],
            values["description"], values["priority"], values["status"])
        if result.outcome != core.INVALID:
            self.show_result(result)
        return result

    def edit_task(self):
        task = self.selected_task()
        if task is None:
            return None
        return TaskForm(self.root, f"Edit task {task['id']}",
                        self.save_edited_task, task)

    def save_edited_task(self, form):
        result = self.planner.edit_task(str(form.task["id"]),
                                        form.changed_values())
        if result.outcome != core.INVALID:
            self.show_result(result)
        return result

    def delete_task(self):
        task = self.selected_task()
        if task is None:
            return
        choice = self.ask_choice(
            self.root, "Delete task",
            f"Delete task {task['id']} \"{task['title']}\"?",
            (CONFIRM, CANCEL))
        if choice == CONFIRM:
            self.show_result(self.planner.delete_task(str(task["id"])))
        else:
            self.feedback.set(core.render_message(core.DELETION_CANCELLED))

    def change_status(self):
        task = self.selected_task()
        if task is None:
            return None
        return StatusForm(
            self.root, task,
            lambda status: self.show_result(
                self.planner.change_status(str(task["id"]), status)))

    # --- Exit and errors (FR6) ---------------------------------------------

    def exit(self):
        """Close the window, offering the unsaved-changes choices first."""
        if not self.planner.exit_needs_prompt:
            self.root.destroy()
            return
        retry = core.render_message(core.EXIT_RETRY)
        discard = core.render_message(core.EXIT_DISCARD)
        cancel = core.render_message(core.EXIT_CANCEL)
        message = core.render_message(core.EXIT_UNSAVED)
        while True:
            choice = self.ask_choice(self.root, "Unsaved changes", message,
                                     (retry, discard, cancel), stacked=True)
            if choice == retry:
                if self.planner.save():
                    self.root.destroy()
                    return
                message = "\n".join((core.render_message(core.EXIT_UNSAVED),
                                     core.render_message(core.RETRY_FAILED)))
                self.refresh()
            elif choice == discard:
                self.root.destroy()
                return
            else:
                return

    def report_error(self, exc_type, exc, tb):
        """Tk callback errors: log them and show the internal-error text."""
        core.log_internal_error(exc)
        self.feedback.set(core.render_message(core.INTERNAL_ERROR))


def start(root, path=None, show_error=messagebox.showerror, **options):
    """Load the data file and build the main window on ``root``.

    Returns the window, or ``None`` after showing the error when the
    stored data is invalid or loading fails unexpectedly.
    """
    try:
        started = core.start(path)
    except Exception as exc:
        core.log_internal_error(exc)
        show_error(APP_TITLE, core.render_message(core.INTERNAL_ERROR))
        return None
    if not started.ok:
        show_error(APP_TITLE, "\n".join(started.lines()))
        return None
    return StudyPlannerGUI(root, started.planner, **options)


def main(path=None):
    """Run the GUI on the data file at ``path``; return the exit status."""
    root = tk.Tk()
    root.withdraw()
    app = start(root, path, parent_error_handler(root))
    if app is None:
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0


def parent_error_handler(root):
    """``messagebox.showerror`` with the main window as parent."""
    return lambda title, text: messagebox.showerror(title, text, parent=root)


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s: %(message)s")
    sys.exit(main())
