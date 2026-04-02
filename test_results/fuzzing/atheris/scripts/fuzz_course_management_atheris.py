from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

import atheris


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

with atheris.instrument_imports():
    import course_management_system as cms  # noqa: E402


VALID_DAYS = sorted(cms.VALID_DAYS)


def consume_small_int(fdp: atheris.FuzzedDataProvider, upper_bound: int) -> int:
    data = fdp.ConsumeBytes(2)
    if not data:
        return 0
    return int.from_bytes(data, "little") % (upper_bound + 1)


def consume_text(fdp: atheris.FuzzedDataProvider, max_bytes: int) -> str:
    return fdp.ConsumeBytes(max_bytes).decode("utf-8", "ignore")


def consume_identifier(fdp: atheris.FuzzedDataProvider, prefix: str, max_bytes: int = 8) -> str:
    text = consume_text(fdp, max_bytes)
    cleaned = "".join(ch for ch in text if ch.isalnum())[:max_bytes]
    return f"{prefix}{cleaned or 'X'}"


def consume_meeting_time(fdp: atheris.FuzzedDataProvider) -> str:
    day = VALID_DAYS[consume_small_int(fdp, len(VALID_DAYS) - 1)]
    start = consume_small_int(fdp, (23 * 60) + 58)
    max_duration = max(1, min(240, (23 * 60 + 59) - start))
    duration = 1 + consume_small_int(fdp, max_duration - 1)
    end = start + duration
    return f"{day} {cms.minutes_to_time_string(start)}-{cms.minutes_to_time_string(end)}"


def choose_existing_or_generated(
    fdp: atheris.FuzzedDataProvider,
    existing_values: list[str],
    prefix: str,
    max_bytes: int = 8,
) -> str:
    if existing_values and consume_small_int(fdp, 1) == 0:
        return existing_values[consume_small_int(fdp, len(existing_values) - 1)]
    return consume_identifier(fdp, prefix, max_bytes=max_bytes)


def seed_minimal_system() -> cms.RegistrationSystem:
    system = cms.RegistrationSystem()
    system.add_instructor("I1", "Instructor One", "CS")
    system.add_instructor("I2", "Instructor Two", "Math")
    system.add_course("CS101", "Intro", 3)
    system.add_course("CS201", "Data Structures", 4, ["CS101"])
    system.add_course("MATH201", "Discrete Math", 3)
    system.add_student("S1", "Student One", 12)
    system.add_student("S2", "Student Two", 15)
    system.add_student("S3", "Student Three", 18)
    system.create_section("SEC1", "CS101", "Fall 2026", "I1", ["Mon 09:00-10:00"], 2)
    system.create_section("SEC2", "CS201", "Fall 2026", "I1", ["Tue 09:00-10:15"], 1)
    system.create_section("SEC3", "MATH201", "Fall 2026", "I2", ["Wed 11:00-12:15"], 2)
    return system


def assert_system_invariants(system: cms.RegistrationSystem) -> None:
    for section_id, section in system.sections.items():
        assert len(section.enrolled_students) <= section.capacity
        assert len(section.enrolled_students) == len(set(section.enrolled_students))
        assert len(section.waitlist) == len(set(section.waitlist))

        for student_id in section.enrolled_students:
            assert student_id in system.students
            student = system.students[student_id]
            assert section_id in student.current_enrollments
            assert section_id not in student.waitlisted_sections

        for student_id in section.waitlist:
            assert student_id in system.students
            student = system.students[student_id]
            assert section_id in student.waitlisted_sections
            assert section_id not in student.current_enrollments
            assert student_id not in section.enrolled_students

    for student_id, student in system.students.items():
        assert len(student.current_enrollments) == len(set(student.current_enrollments))
        assert len(student.waitlisted_sections) == len(set(student.waitlisted_sections))
        assert student.current_credit_load(system.sections) <= student.max_credits

        seen_course_keys: set[tuple[str, str]] = set()
        for section_id in student.current_enrollments:
            assert section_id in system.sections
            section = system.sections[section_id]
            assert student_id in section.enrolled_students
            key = (section.semester, section.course_code)
            assert key not in seen_course_keys
            seen_course_keys.add(key)

        for section_id in student.waitlisted_sections:
            assert section_id in system.sections
            section = system.sections[section_id]
            assert student_id in section.waitlist
            key = (section.semester, section.course_code)
            assert key not in seen_course_keys


def fuzz_registration_system(fdp: atheris.FuzzedDataProvider) -> None:
    system = cms.build_demo_system() if consume_small_int(fdp, 1) else seed_minimal_system()
    operation_count = 1 + consume_small_int(fdp, 39)

    for _ in range(operation_count):
        operation = consume_small_int(fdp, 13)
        student_ids = sorted(system.students)
        course_codes = sorted(system.courses)
        instructor_ids = sorted(system.instructors)
        section_ids = sorted(system.sections)

        if operation == 0:
            system.add_student(
                choose_existing_or_generated(fdp, student_ids, "S"),
                consume_text(fdp, 12) or "Generated Student",
                1 + consume_small_int(fdp, 24),
            )
        elif operation == 1:
            prereq_count = consume_small_int(fdp, min(2, len(course_codes)))
            prerequisites = course_codes[:prereq_count]
            system.add_course(
                choose_existing_or_generated(fdp, course_codes, "C"),
                consume_text(fdp, 16) or "Generated Course",
                1 + consume_small_int(fdp, 6),
                prerequisites,
            )
        elif operation == 2:
            system.add_instructor(
                choose_existing_or_generated(fdp, instructor_ids, "I"),
                consume_text(fdp, 14) or "Generated Instructor",
                consume_text(fdp, 10) or "GEN",
            )
        elif operation == 3 and course_codes and instructor_ids:
            meeting_times = [consume_meeting_time(fdp) for _ in range(1 + consume_small_int(fdp, 2))]
            system.create_section(
                choose_existing_or_generated(fdp, section_ids, "SEC"),
                choose_existing_or_generated(fdp, course_codes, "C"),
                consume_text(fdp, 10) or "Fall 2026",
                choose_existing_or_generated(fdp, instructor_ids, "I"),
                meeting_times,
                1 + consume_small_int(fdp, 5),
            )
        elif operation == 4 and student_ids and section_ids:
            system.register_student(
                choose_existing_or_generated(fdp, student_ids, "S"),
                choose_existing_or_generated(fdp, section_ids, "SEC"),
            )
        elif operation == 5 and student_ids and section_ids:
            system.drop_student(
                choose_existing_or_generated(fdp, student_ids, "S"),
                choose_existing_or_generated(fdp, section_ids, "SEC"),
                reason=consume_text(fdp, 12) or "fuzz drop",
                promote=consume_small_int(fdp, 1) == 1,
            )
        elif operation == 6 and student_ids and course_codes:
            system.record_completed_course(
                choose_existing_or_generated(fdp, student_ids, "S"),
                choose_existing_or_generated(fdp, course_codes, "C"),
            )
        elif operation == 7:
            system.search_courses(consume_text(fdp, 18))
        elif operation == 8 and student_ids:
            system.report_student_schedule(choose_existing_or_generated(fdp, student_ids, "S"))
        elif operation == 9 and section_ids:
            system.report_course_roster(choose_existing_or_generated(fdp, section_ids, "SEC"))
        elif operation == 10 and student_ids:
            system.remove_student(choose_existing_or_generated(fdp, student_ids, "S"))
        elif operation == 11 and section_ids:
            system.remove_section(choose_existing_or_generated(fdp, section_ids, "SEC"))
        elif operation == 12:
            restored = cms.RegistrationSystem.from_dict(system.to_dict())
            assert restored.to_dict() == system.to_dict()
        else:
            system.report_system_summary()

        assert_system_invariants(system)


def fuzz_persistence_payload(fdp: atheris.FuzzedDataProvider) -> None:
    raw_text = consume_text(fdp, 512)
    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, RecursionError, UnicodeDecodeError):
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "fuzz_payload.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        system, message = cms.RegistrationSystem.load_from_file(str(path))
        assert isinstance(message, str)
        if system is not None:
            assert isinstance(system.to_dict(), dict)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    mode = consume_small_int(fdp, 5)

    if mode == 0:
        try:
            cms.parse_time_string(consume_text(fdp, 24))
        except ValueError:
            return
    elif mode == 1:
        try:
            cms.parse_meeting_time(consume_text(fdp, 32))
        except ValueError:
            return
    elif mode == 2:
        times_a = [consume_meeting_time(fdp) for _ in range(1 + consume_small_int(fdp, 2))]
        times_b = [consume_meeting_time(fdp) for _ in range(1 + consume_small_int(fdp, 2))]
        result_ab = cms.meeting_times_conflict(times_a, times_b)
        result_ba = cms.meeting_times_conflict(times_b, times_a)
        assert result_ab == result_ba
    elif mode == 3:
        system = cms.build_demo_system()
        restored = cms.RegistrationSystem.from_dict(system.to_dict())
        assert restored.to_dict() == system.to_dict()
    elif mode == 4:
        fuzz_persistence_payload(fdp)
    else:
        fuzz_registration_system(fdp)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
