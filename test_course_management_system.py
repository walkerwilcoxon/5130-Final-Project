import json

from course_management_system import (
    RegistrationSystem,
    build_demo_system,
    normalize_text,
    parse_time_string,
    minutes_to_time_string,
    parse_meeting_time,
    meeting_times_conflict,
)


def test_normalize_text_lowercases_and_collapses_spaces():
    assert normalize_text("  Hello   WORLD  ") == "hello world"


def test_parse_time_string_valid():
    assert parse_time_string("09:30") == 570


def test_parse_time_string_invalid_format_raises():
    try:
        parse_time_string("0930")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Invalid time format" in str(exc)


def test_minutes_to_time_string_formats_correctly():
    assert minutes_to_time_string(570) == "09:30"


def test_parse_meeting_time_valid():
    day, start, end = parse_meeting_time("Mon 09:00-10:15")
    assert day == "Mon"
    assert start == 540
    assert end == 615


def test_meeting_times_conflict_true_on_overlap_same_day():
    a = ["Mon 09:00-10:15"]
    b = ["Mon 10:00-11:00"]
    assert meeting_times_conflict(a, b) is True


def test_meeting_times_conflict_false_on_different_days():
    a = ["Mon 09:00-10:15"]
    b = ["Tue 09:00-10:15"]
    assert meeting_times_conflict(a, b) is False


def test_add_student_success():
    system = RegistrationSystem()
    assert system.add_student("S100", "Alice", 15) is True
    assert "S100" in system.students
    assert system.students["S100"].name == "Alice"


def test_add_student_duplicate_fails():
    system = RegistrationSystem()
    assert system.add_student("S100", "Alice", 15) is True
    assert system.add_student("S100", "Alice Again", 15) is False


def test_add_course_invalid_credits_fails():
    system = RegistrationSystem()
    assert system.add_course("CS999", "Impossible Course", 0) is False
    assert "CS999" not in system.courses


def test_create_section_invalid_meeting_time_fails():
    system = RegistrationSystem()
    system.add_instructor("I1", "Dr. X", "CS")
    system.add_course("CS101", "Intro", 3)
    ok = system.create_section(
        "SEC1",
        "CS101",
        "Fall 2026",
        "I1",
        ["BadDay 09:00-10:15"],
        10,
    )
    assert ok is False
    assert "SEC1" not in system.sections


def test_register_student_successful_enrollment():
    system = build_demo_system()
    success, message = system.register_student("S004", "SEC1004")
    assert success is True
    assert "enrolled" in message
    assert "S004" in system.sections["SEC1004"].enrolled_students
    assert "SEC1004" in system.students["S004"].current_enrollments


def test_register_student_missing_prerequisite_fails():
    system = build_demo_system()
    success, message = system.register_student("S003", "SEC1001")
    assert success is False
    assert "missing prerequisites" in message


def test_register_student_schedule_conflict_fails():
    system = build_demo_system()
    success, message = system.register_student("S001", "SEC1005")
    assert success is False
    assert "schedule conflict" in message


def test_register_student_duplicate_course_same_semester_fails():
    system = build_demo_system()
    system.create_section(
        "SEC2001",
        "CS201",
        "Fall 2026",
        "I102",
        ["Fri 13:00-14:15"],
        5,
    )
    success, message = system.register_student("S001", "SEC2001")
    assert success is False
    assert "duplicate course attempt in semester" in message


def test_register_student_credit_limit_exceeded_fails():
    system = RegistrationSystem()
    system.add_instructor("I1", "Dr. A", "CS")
    system.add_course("C1", "Course 1", 4)
    system.add_course("C2", "Course 2", 4)
    system.add_student("S1", "Student One", 6)
    system.create_section("SEC1", "C1", "Fall 2026", "I1", ["Mon 09:00-10:00"], 5)
    system.create_section("SEC2", "C2", "Fall 2026", "I1", ["Tue 09:00-10:00"], 5)

    ok1, _ = system.register_student("S1", "SEC1")
    ok2, msg2 = system.register_student("S1", "SEC2")

    assert ok1 is True
    assert ok2 is False
    assert "credit limit exceeded" in msg2


def test_waitlist_added_when_section_full():
    system = build_demo_system()
    section = system.sections["SEC1001"]
    student = system.students["S002"]

    assert "S002" in section.waitlist
    assert "SEC1001" in student.waitlisted_sections


def test_drop_enrolled_student_promotes_waitlisted_student():
    system = build_demo_system()
    success, message = system.drop_student("S004", "SEC1001")
    assert success is True
    assert "promoted S002" in message
    assert "S002" in system.sections["SEC1001"].enrolled_students
    assert "SEC1001" not in system.students["S002"].waitlisted_sections


def test_remove_student_cleans_up_enrollments_and_waitlists():
    system = build_demo_system()
    assert system.remove_student("S002") is True
    assert "S002" not in system.students
    assert "S002" not in system.sections["SEC1001"].waitlist
    assert "S002" not in system.sections["SEC1002"].enrolled_students


def test_record_completed_course_duplicate_fails():
    system = build_demo_system()
    success, message = system.record_completed_course("S001", "CS101")
    assert success is False
    assert "already recorded" in message


def test_search_courses_finds_by_code_or_title_case_insensitive():
    system = build_demo_system()
    results = system.search_courses("data structures")
    assert len(results) == 1
    assert results[0].course_code == "CS201"


def test_report_student_schedule_contains_expected_content():
    system = build_demo_system()
    report = system.report_student_schedule("S001")
    assert "Schedule for S001 - John Kim" in report
    assert "SEC1001" in report
    assert "Current credit load" in report


def test_save_and_load_round_trip(tmp_path):
    system = build_demo_system()
    path = tmp_path / "cms.json"

    ok, _ = system.save_to_file(str(path))
    loaded, msg = RegistrationSystem.load_from_file(str(path))

    assert ok is True
    assert loaded is not None
    assert "loaded from" in msg
    assert loaded.students["S001"].name == system.students["S001"].name
    assert loaded.sections["SEC1001"].course_code == system.sections["SEC1001"].course_code
    assert loaded.sections["SEC1001"].waitlist == system.sections["SEC1001"].waitlist