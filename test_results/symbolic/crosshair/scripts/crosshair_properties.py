from __future__ import annotations

# crosshair: analysis_kind=PEP316

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import course_management_system as cms  # noqa: E402


def minutes_round_trip(value: int) -> int:
    """
    pre: 0 <= value <= 1439
    post: _ == value
    """
    return cms.parse_time_string(cms.minutes_to_time_string(value))


def meeting_time_round_trip(day_index: int, start_minutes: int, duration: int) -> tuple[str, int, int]:
    """
    pre: 0 <= day_index < 7
    pre: 0 <= start_minutes <= 1438
    pre: 1 <= duration <= 180
    pre: start_minutes + duration <= 1439
    post: _[0] == sorted(cms.VALID_DAYS)[day_index]
    post: _[1] == start_minutes
    post: _[2] == start_minutes + duration
    """
    day = sorted(cms.VALID_DAYS)[day_index]
    end_minutes = start_minutes + duration
    entry = f"{day} {cms.minutes_to_time_string(start_minutes)}-{cms.minutes_to_time_string(end_minutes)}"
    return cms.parse_meeting_time(entry)


def meeting_conflict_is_symmetric(
    day_a: int,
    start_a: int,
    duration_a: int,
    day_b: int,
    start_b: int,
    duration_b: int,
) -> bool:
    """
    pre: 0 <= day_a < 7
    pre: 0 <= day_b < 7
    pre: 0 <= start_a <= 1438
    pre: 0 <= start_b <= 1438
    pre: 1 <= duration_a <= 180
    pre: 1 <= duration_b <= 180
    pre: start_a + duration_a <= 1439
    pre: start_b + duration_b <= 1439
    post: _ == True
    """
    first_day = sorted(cms.VALID_DAYS)[day_a]
    second_day = sorted(cms.VALID_DAYS)[day_b]
    first = [
        f"{first_day} {cms.minutes_to_time_string(start_a)}-{cms.minutes_to_time_string(start_a + duration_a)}"
    ]
    second = [
        f"{second_day} {cms.minutes_to_time_string(start_b)}-{cms.minutes_to_time_string(start_b + duration_b)}"
    ]
    return cms.meeting_times_conflict(first, second) == cms.meeting_times_conflict(second, first)


def waitlist_registration_totals(capacity: int) -> tuple[int, int]:
    """
    pre: 1 <= capacity <= 3
    post: _[0] <= capacity
    post: _[0] + _[1] == 4
    """
    system = cms.RegistrationSystem()
    system.add_instructor("I1", "Instructor", "CS")
    system.add_course("CS101", "Intro", 3)
    system.create_section(
        "SEC1",
        "CS101",
        "Fall 2026",
        "I1",
        ["Mon 09:00-10:00", "Wed 09:00-10:00"],
        capacity,
    )

    for index in range(4):
        system.add_student(f"S{index}", f"Student {index}", 18)
        system.register_student(f"S{index}", "SEC1")

    section = system.sections["SEC1"]
    return len(section.enrolled_students), len(section.waitlist)


def waitlist_promotion_restores_seat_count(capacity: int) -> tuple[int, int]:
    """
    pre: 1 <= capacity <= 3
    post: _[0] == capacity
    post: _[1] == 1
    """
    system = cms.RegistrationSystem()
    system.add_instructor("I1", "Instructor", "CS")
    system.add_course("CS101", "Intro", 3)
    system.create_section(
        "SEC1",
        "CS101",
        "Fall 2026",
        "I1",
        ["Mon 09:00-10:00", "Wed 09:00-10:00"],
        capacity,
    )

    total_students = capacity + 2
    for index in range(total_students):
        system.add_student(f"S{index}", f"Student {index}", 18)
        system.register_student(f"S{index}", "SEC1")

    section = system.sections["SEC1"]
    first_enrolled = section.enrolled_students[0]
    system.drop_student(first_enrolled, "SEC1")
    return len(section.enrolled_students), len(section.waitlist)


def failed_prerequisite_registration_preserves_state() -> bool:
    """
    post: _ == True
    """
    system = cms.build_demo_system()
    before = system.to_dict()
    ok, _ = system.register_student("S001", "SEC1002")
    after = system.to_dict()
    return (not ok) and before == after


def serialization_round_trip_preserves_state() -> bool:
    """
    post: _ == True
    """
    system = cms.build_demo_system()
    restored = cms.RegistrationSystem.from_dict(system.to_dict())
    return restored.to_dict() == system.to_dict()


def remove_student_clears_section_membership(capacity: int) -> bool:
    """
    pre: 1 <= capacity <= 3
    post: _ == True
    """
    system = cms.RegistrationSystem()
    system.add_instructor("I1", "Instructor", "CS")
    system.add_course("CS101", "Intro", 3)
    system.create_section(
        "SEC1",
        "CS101",
        "Fall 2026",
        "I1",
        ["Mon 09:00-10:00", "Wed 09:00-10:00"],
        capacity,
    )
    total_students = capacity + 2
    for index in range(total_students):
        system.add_student(f"S{index}", f"Student {index}", 18)
        system.register_student(f"S{index}", "SEC1")

    target_student = "S0"
    removed = system.remove_student(target_student)
    section = system.sections["SEC1"]
    return (
        removed
        and target_student not in system.students
        and target_student not in section.enrolled_students
        and target_student not in section.waitlist
    )


def remove_section_clears_student_membership(capacity: int) -> bool:
    """
    pre: 1 <= capacity <= 3
    post: _ == True
    """
    system = cms.RegistrationSystem()
    system.add_instructor("I1", "Instructor", "CS")
    system.add_course("CS101", "Intro", 3)
    system.create_section(
        "SEC1",
        "CS101",
        "Fall 2026",
        "I1",
        ["Mon 09:00-10:00", "Wed 09:00-10:00"],
        capacity,
    )
    total_students = capacity + 2
    for index in range(total_students):
        system.add_student(f"S{index}", f"Student {index}", 18)
        system.register_student(f"S{index}", "SEC1")

    removed = system.remove_section("SEC1")
    return removed and all(
        "SEC1" not in student.current_enrollments and "SEC1" not in student.waitlisted_sections
        for student in system.students.values()
    )


def duplicate_course_registration_fails_without_mutation() -> bool:
    """
    post: _ == True
    """
    system = cms.build_demo_system()
    system.create_section("SEC2001", "CS201", "Fall 2026", "I102", ["Fri 13:00-14:15"], 5)
    before = system.to_dict()
    ok, _ = system.register_student("S001", "SEC2001")
    after = system.to_dict()
    return (not ok) and before == after


def credit_limit_rejection_does_not_mutate_state(max_credits: int) -> bool:
    """
    pre: 1 <= max_credits <= 6
    post: _ == True
    """
    system = cms.RegistrationSystem()
    system.add_instructor("I1", "Instructor", "CS")
    system.add_course("C1", "Course 1", 4)
    system.add_course("C2", "Course 2", 4)
    system.add_student("S1", "Student One", max_credits)
    system.create_section("SEC1", "C1", "Fall 2026", "I1", ["Mon 09:00-10:00"], 5)
    system.create_section("SEC2", "C2", "Fall 2026", "I1", ["Tue 09:00-10:00"], 5)
    system.register_student("S1", "SEC1")
    before = system.to_dict()
    ok, _ = system.register_student("S1", "SEC2")
    after = system.to_dict()
    return (not ok) and before == after
