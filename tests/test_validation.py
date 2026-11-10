"""FR5 input-validation tests (test plan rows V1-V58).

Every case is checked on the shared core, which both versions use. Errors
are compared structurally as (field label, rule identifier) pairs, in the
fixed field order; message texts are checked against the message table.
"""

import unittest

import helpers  # puts src/ on the import path
import core

# AC1's inputs; error tests change one or two fields and keep these.
AC1_INPUT = {
    "title": "  Read Chapter  ",
    "subject": "  Mathematics  ",
    "description": "  Review  chapter notes  ",
    "due_date": "  2026-11-05  ",
    "priority": "  high  ",
    "status": "  in progress  ",
}


def create(**overrides):
    """Validate a new task: AC1's inputs with ``overrides`` applied."""
    values = dict(AC1_INPUT, **overrides)
    return core.validate_new_task(**values)


def pairs(result):
    return [(e.field, e.rule) for e in result.errors]


class ValidationTestCase(unittest.TestCase):

    def assertAccepted(self, result):
        self.assertTrue(result.ok, f"unexpected errors: {pairs(result)}")
        self.assertIsNotNone(result.values)

    def assertRejected(self, result, expected_pairs):
        self.assertFalse(result.ok)
        self.assertIsNone(result.values, "a rejection must store nothing")
        self.assertEqual(pairs(result), expected_pairs)


class TestAC1Normalisation(ValidationTestCase):

    def test_ac1_title_trimmed_case_kept(self):  # V1
        result = create()
        self.assertAccepted(result)
        self.assertEqual(result.values["title"], "Read Chapter")

    def test_ac1_subject_trimmed(self):  # V2
        self.assertEqual(create().values["subject"], "Mathematics")

    def test_ac1_description_outer_trimmed_inner_kept(self):  # V3
        self.assertEqual(create().values["description"],
                         "Review  chapter notes")

    def test_ac1_due_date_trimmed(self):  # V4
        self.assertEqual(create().values["due_date"], "2026-11-05")

    def test_ac1_priority_trimmed_canonical(self):  # V5
        self.assertEqual(create().values["priority"], "High")

    def test_ac1_status_trimmed_canonical(self):  # V6
        self.assertEqual(create().values["status"], "In Progress")

    def test_ac1_all_six_together_no_errors(self):  # V7
        result = create()
        self.assertEqual(result.errors, ())
        self.assertEqual(result.values, {
            "title": "Read Chapter",
            "subject": "Mathematics",
            "description": "Review  chapter notes",
            "due_date": "2026-11-05",
            "priority": "High",
            "status": "In Progress",
        })


class TestAC2RequiredFields(ValidationTestCase):

    def test_ac2_blank_title_and_subject_two_errors(self):  # V8
        result = create(title="", subject="   ")
        self.assertRejected(result, [(core.TITLE, core.REQUIRED),
                                     (core.SUBJECT, core.REQUIRED)])


class TestAC3DateFormat(ValidationTestCase):

    def assertFormatError(self, text):
        self.assertRejected(create(due_date=text),
                            [(core.DUE_DATE, core.DATE_FORMAT)])

    def test_ac3_valid_date_accepted(self):  # V9
        result = create(due_date="2026-11-05")
        self.assertAccepted(result)
        self.assertEqual(result.values["due_date"], "2026-11-05")

    def test_ac3_compact_date_rejected(self):  # V10
        self.assertFormatError("20261105")

    def test_ac3_week_date_rejected(self):  # V11
        self.assertFormatError("2026-W45-4")

    def test_ac3_single_digit_month_day_rejected(self):  # V12
        self.assertFormatError("2026-1-5")

    def test_ac3_slashed_date_rejected(self):  # V13
        self.assertFormatError("10/11/2026")

    def test_ac3_non_ascii_digits_rejected(self):  # V14
        self.assertFormatError(
            "٢٠٢٦-١١-٠٥")


class TestAC4CalendarDate(ValidationTestCase):

    def assertCalendarError(self, text):
        self.assertRejected(create(due_date=text),
                            [(core.DUE_DATE, core.INVALID_CALENDAR_DATE)])

    def test_ac4_feb_30_rejected(self):  # V15
        self.assertCalendarError("2026-02-30")

    def test_ac4_feb_29_non_leap_rejected(self):  # V16
        self.assertCalendarError("2027-02-29")

    def test_ac4_feb_29_leap_accepted(self):  # V17
        self.assertAccepted(create(due_date="2028-02-29"))

    def test_ac4_month_13_rejected(self):  # V18
        self.assertCalendarError("2026-13-01")

    def test_ac4_past_date_accepted(self):  # V19
        result = create(due_date="2025-01-15")
        self.assertAccepted(result)
        self.assertEqual(result.values["due_date"], "2025-01-15")

    def test_ac4_century_non_leap_rejected(self):  # V20
        self.assertCalendarError("2100-02-29")


class TestAC5PriorityAndStatus(ValidationTestCase):

    def test_ac5_priority_upper_canonical(self):  # V21
        self.assertEqual(create(priority="LOW").values["priority"], "Low")

    def test_ac5_priority_unknown_rejected(self):  # V22
        self.assertRejected(create(priority="Urgent"),
                            [(core.PRIORITY, core.INVALID_CHOICE)])

    def test_ac5_priority_partial_rejected(self):  # V23
        self.assertRejected(create(priority="Hi"),
                            [(core.PRIORITY, core.INVALID_CHOICE)])

    def test_ac5_priority_empty_when_creating_default(self):  # V24
        self.assertEqual(create(priority="").values["priority"], "Medium")

    def test_ac5_status_upper_canonical(self):  # V25
        self.assertEqual(create(status="COMPLETED").values["status"],
                         "Completed")

    def test_ac5_status_missing_space_rejected(self):  # V26
        self.assertRejected(create(status="inprogress"),
                            [(core.STATUS, core.INVALID_CHOICE)])

    def test_ac5_status_double_space_rejected(self):  # V27
        self.assertRejected(create(status="In  Progress"),
                            [(core.STATUS, core.INVALID_CHOICE)])

    def test_ac5_status_unknown_rejected(self):  # V28
        self.assertRejected(create(status="Done"),
                            [(core.STATUS, core.INVALID_CHOICE)])

    def test_ac5_status_empty_when_creating_default(self):  # V29
        self.assertEqual(create(status="").values["status"], "Pending")

    def test_ac5_status_empty_in_status_change_rejected(self):  # V30
        self.assertRejected(core.validate_status_change(""),
                            [(core.STATUS, core.REQUIRED)])


class TestAC6TaskId(ValidationTestCase):

    def assertIdError(self, text, rule):
        self.assertRejected(core.validate_task_id(text), [(core.TASK_ID,
                                                           rule)])

    def test_ac6_id_valid_accepted(self):  # V31
        result = core.validate_task_id("3")
        self.assertAccepted(result)
        self.assertEqual(result.values, 3)

    def test_ac6_id_surrounding_spaces_rejected(self):  # V32
        self.assertIdError(" 3 ", core.INVALID_TASK_ID_FORMAT)

    def test_ac6_id_plus_sign_rejected(self):  # V33
        self.assertIdError("+3", core.INVALID_TASK_ID_FORMAT)

    def test_ac6_id_leading_zeros_rejected(self):  # V34
        self.assertIdError("007", core.INVALID_TASK_ID_FORMAT)

    def test_ac6_id_underscore_rejected(self):  # V35
        self.assertIdError("1_0", core.INVALID_TASK_ID_FORMAT)

    def test_ac6_id_non_ascii_digit_rejected(self):  # V36
        self.assertIdError("٣", core.INVALID_TASK_ID_FORMAT)

    def test_ac6_id_zero_rejected(self):  # V37
        self.assertIdError("0", core.TASK_ID_MUST_BE_POSITIVE)

    def test_ac6_id_negative_rejected(self):  # V38
        self.assertIdError("-1", core.INVALID_TASK_ID_FORMAT)

    def test_ac6_id_letters_rejected(self):  # V39
        self.assertIdError("abc", core.INVALID_TASK_ID_FORMAT)

    def test_ac6_id_empty_rejected(self):  # V40
        self.assertIdError("", core.INVALID_TASK_ID_FORMAT)


class TestWhitespaceDefaults(ValidationTestCase):

    def test_rule_priority_whitespace_when_creating_default(self):  # V41
        self.assertEqual(create(priority="   ").values["priority"], "Medium")

    def test_rule_status_whitespace_when_creating_default(self):  # V42
        self.assertEqual(create(status="   ").values["status"], "Pending")

    def test_rule_status_whitespace_in_status_change_rejected(self):  # V43
        self.assertRejected(core.validate_status_change("   "),
                            [(core.STATUS, core.REQUIRED)])


class TestFieldRules(ValidationTestCase):

    def test_rule_description_omitted_stored_empty(self):  # V44
        values = dict(AC1_INPUT)
        del values["description"]
        result = core.validate_new_task(**values)
        self.assertAccepted(result)
        self.assertEqual(result.values["description"], "")

    def test_rule_description_empty_stored_empty(self):  # V45
        self.assertEqual(create(description="").values["description"], "")

    def test_rule_title_internal_spacing_kept(self):  # V46
        self.assertEqual(create(title="Read  Chapter").values["title"],
                         "Read  Chapter")

    def test_rule_subject_internal_spacing_kept(self):  # V47
        self.assertEqual(
            create(subject="Computer  Science").values["subject"],
            "Computer  Science")


class TestDueDateRequired(ValidationTestCase):

    def test_rule_due_date_empty_required(self):  # V48
        self.assertRejected(create(due_date=""),
                            [(core.DUE_DATE, core.REQUIRED)])

    def test_rule_due_date_whitespace_required(self):  # V49
        self.assertRejected(create(due_date="   "),
                            [(core.DUE_DATE, core.REQUIRED)])


class TestEditContext(ValidationTestCase):

    def test_rule_edit_title_empty_required(self):  # V50
        self.assertRejected(core.validate_task_edit({"title": ""}),
                            [(core.TITLE, core.REQUIRED)])

    def test_rule_edit_priority_empty_required_no_default(self):  # V51
        self.assertRejected(core.validate_task_edit({"priority": ""}),
                            [(core.PRIORITY, core.REQUIRED)])

    def test_rule_edit_priority_whitespace_required(self):  # V52
        self.assertRejected(core.validate_task_edit({"priority": "   "}),
                            [(core.PRIORITY, core.REQUIRED)])

    def test_rule_edit_due_date_empty_required(self):  # V53
        self.assertRejected(core.validate_task_edit({"due_date": ""}),
                            [(core.DUE_DATE, core.REQUIRED)])

    def test_rule_edit_description_empty_stored_empty(self):  # V54
        result = core.validate_task_edit({"description": ""})
        self.assertAccepted(result)
        self.assertEqual(result.values, {"description": ""})

    def test_rule_edit_priority_trimmed_canonical(self):  # V55
        result = core.validate_task_edit({"priority": " low "})
        self.assertAccepted(result)
        self.assertEqual(result.values, {"priority": "Low"})


class TestErrorsTogether(ValidationTestCase):

    def test_rule_three_different_errors_together(self):  # V56
        result = create(title="", due_date="2026-02-30", priority="Urgent")
        self.assertRejected(result, [
            (core.TITLE, core.REQUIRED),
            (core.DUE_DATE, core.INVALID_CALENDAR_DATE),
            (core.PRIORITY, core.INVALID_CHOICE),
        ])


class TestTrimming(ValidationTestCase):

    def test_rule_description_whitespace_only_stored_empty(self):  # V57
        self.assertEqual(create(description="   ").values["description"],
                         "")

    def test_rule_title_unicode_whitespace_trimmed(self):  # V58
        title = "\t Read Chapter \n"
        self.assertEqual(create(title=title).values["title"],
                         "Read Chapter")


class TestMessageTexts(unittest.TestCase):
    """Exact texts from the central message table."""

    def message(self, result):
        self.assertEqual(len(result.errors), 1)
        return result.errors[0].message

    def test_date_format_message(self):  # V10
        self.assertEqual(self.message(create(due_date="20261105")),
                         "Due date must use the YYYY-MM-DD format.")

    def test_calendar_date_message(self):  # V15
        self.assertEqual(self.message(create(due_date="2026-02-30")),
                         "Due date must be a real calendar date.")

    def test_status_required_message(self):  # V30, V43
        for text in ("", "   "):
            self.assertEqual(
                self.message(core.validate_status_change(text)),
                "Status must not be empty after trimming.")

    def test_task_id_format_message(self):  # V34, V40
        for text in ("007", ""):
            self.assertEqual(
                self.message(core.validate_task_id(text)),
                "Task ID must be a positive ASCII integer without signs, "
                "spaces, separators, or leading zeros.")

    def test_task_id_positive_message(self):  # V37
        self.assertEqual(self.message(core.validate_task_id("0")),
                         "Task ID must be greater than zero.")

    def test_due_date_required_message(self):  # V48, V49, V53
        for result in (create(due_date=""), create(due_date="   "),
                       core.validate_task_edit({"due_date": ""})):
            self.assertEqual(self.message(result),
                             "Due date must not be empty after trimming.")

    def test_priority_required_message(self):  # V51, V52
        for text in ("", "   "):
            self.assertEqual(
                self.message(core.validate_task_edit({"priority": text})),
                "Priority must not be empty after trimming.")

    def test_invalid_choice_message(self):  # V22
        self.assertEqual(
            self.message(create(priority="Urgent")),
            "Priority must exactly match one of the permitted values.")


class TestDesignChecks(unittest.TestCase):
    """Message errors, editable fields and trimming."""

    def test_rule_missing_message_parameter_raises(self):
        with self.assertRaises(core.MessageError):
            core.render_message(core.REQUIRED)

    def test_rule_unknown_message_key_raises(self):
        with self.assertRaises(core.MessageError):
            core.render_message("no_such_key", field="Title")

    def test_rule_status_not_editable_through_edit(self):
        with self.assertRaises(ValueError):
            core.validate_task_edit({"status": "Completed"})

    def test_rule_due_date_extra_characters_rejected(self):
        # FR5 field rule: the value must match YYYY-MM-DD *exactly*, so a
        # valid date followed by more characters is a format error, not a
        # calendar error (V59).
        for text in ("2026-11-055", "2026-11-05x", "12026-11-05"):
            with self.subTest(text=text):
                result = create(due_date=text)
                self.assertEqual(pairs(result),
                                 [(core.DUE_DATE, core.DATE_FORMAT)])

    def test_rule_zero_width_space_is_not_trimmed(self):
        result = create(title="​Read")
        self.assertEqual(result.values["title"], "​Read")


if __name__ == "__main__":
    unittest.main()
