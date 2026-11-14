"""Measure search and merge-sort times on 500 tasks (NFR6).

Run from the repository root:

    python scripts/measure_performance.py

The tasks are generated in memory with a fixed random seed, so nothing is
read from or written to the data file. Each operation goes through the
shared core, exactly as both interfaces use it. The result for each
operation is the fastest of several repeats, divided by the number of
calls per repeat, which reduces the effect of other programs running at
the same time.
"""

import platform
import random
import sys
import timeit
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import core  # noqa: E402

TASK_COUNT = 500
SEED = 44102
REPEATS = 7
CALLS = 50
SUBJECTS = ("Mathematics", "History", "Biology", "Physics", "Chemistry",
            "Geography", "Art", "Économie")
WORDS = ("revise", "essay", "lab", "report", "algebra", "notes", "quiz",
         "reading", "draft", "project", "review", "summary")


def make_tasks(count, seed=SEED):
    """Return ``count`` valid tasks; the same seed gives the same tasks."""
    rng = random.Random(seed)
    start = date(2026, 9, 1)
    tasks = []
    for task_id in range(1, count + 1):
        title = " ".join(rng.choice(WORDS) for _ in range(3)).capitalize()
        tasks.append({
            "id": task_id,
            "title": title,
            "subject": rng.choice(SUBJECTS),
            "description": " ".join(rng.choice(WORDS) for _ in range(6)),
            "due_date": (start + timedelta(days=rng.randrange(120)))
            .isoformat(),
            "priority": rng.choice(core.PRIORITIES),
            "status": rng.choice(core.STATUSES),
        })
    return tasks


def per_call_ms(operation):
    """The fastest time of one call to ``operation``, in milliseconds."""
    best = min(timeit.repeat(operation, number=CALLS, repeat=REPEATS))
    return best / CALLS * 1000


def measure(tasks):
    """Return (operation, milliseconds) pairs for search and each sort."""
    planner = core.Planner(None, tasks, len(tasks) + 1)

    def search(query):
        planner.view = core.ViewState(search=query)
        return planner.list_view()

    results = [
        ("Search, matching query (`algebra`)",
         per_call_ms(lambda: search("algebra"))),
        ("Search, no match (`zzz`)", per_call_ms(lambda: search("zzz"))),
    ]
    for sort in core.SORT_FIELDS:
        results.append((f"Merge sort by {sort}", per_call_ms(
            lambda sort=sort: core.sort_tasks(tasks, sort))))
    return results


def main():
    tasks = make_tasks(TASK_COUNT)
    print(f"Tasks: {len(tasks)} (seed {SEED}); fastest of {REPEATS} "
          f"repeats of {CALLS} calls each")
    print(f"Python {platform.python_version()} on {platform.platform()}")
    print(f"Processor: {platform.processor() or 'not reported'}")
    print()
    print("| Operation | Time per call (ms) |")
    print("|---|---|")
    for name, milliseconds in measure(tasks):
        print(f"| {name} | {milliseconds:.2f} |")


if __name__ == "__main__":
    main()
