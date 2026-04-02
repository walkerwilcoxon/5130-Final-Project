from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

from hypothesis import HealthCheck, assume, given, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from course_management_system import (  # noqa: E402
    VALID_DAYS,
    RegistrationSystem,
    build_demo_system,
    meeting_times_conflict,
    minutes_to_time_string,
    normalize_text,
    parse_meeting_time,
    parse_time_string,
)


def snapshot_system(system: RegistrationSystem) -> str:
    return json.dumps(system.to_dict(), sort_keys=True)


def assert_system_consistency(system: RegistrationSystem) -> None:
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

        enrolled_course_keys: set[tuple[str, str]] = set()
        for section_id in student.current_enrollments:
            assert section_id in system.sections
            section = system.sections[section_id]
            assert student_id in section.enrolled_students
            key = (section.semester, section.course_code)
            assert key not in enrolled_course_keys
            enrolled_course_keys.add(key)

        queued_course_keys: set[tuple[str, str]] = set()
        for section_id in student.waitlisted_sections:
            assert section_id in system.sections
            section = system.sections[section_id]
            assert student_id in section.waitlist
            key = (section.semester, section.course_code)
            assert key not in enrolled_course_keys
            assert key not in queued_course_keys
            queued_course_keys.add(key)


@settings(
    max_examples=600,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(st.text())
def test_normalize_text_is_idempotent(value: str) -> None:
    normalized = normalize_text(value)
    assert normalize_text(normalized) == normalized


@settings(max_examples=800, deadline=None)
@given(hour=st.integers(min_value=0, max_value=23), minute=st.integers(min_value=0, max_value=59))
def test_parse_time_string_round_trip(hour: int, minute: int) -> None:
    text = f"{hour:02d}:{minute:02d}"
    parsed = parse_time_string(text)
    assert parsed == hour * 60 + minute
    assert parse_time_string(minutes_to_time_string(parsed)) == parsed


@settings(max_examples=800, deadline=None)
@given(
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=58),
    duration=st.integers(min_value=1, max_value=120),
    day=st.sampled_from(sorted(VALID_DAYS)),
)
def test_parse_meeting_time_valid_inputs(day: str, hour: int, minute: int, duration: int) -> None:
    start = hour * 60 + minute
    end = start + duration
    assume(end <= 23 * 60 + 59)

    entry = f"{day} {minutes_to_time_string(start)}-{minutes_to_time_string(end)}"
    parsed_day, parsed_start, parsed_end = parse_meeting_time(entry)
    assert parsed_day == day
    assert parsed_start == start
    assert parsed_end == end
    assert parsed_end > parsed_start


@st.composite
def meeting_entry_strategy(draw: st.DrawFn) -> str:
    day = draw(st.sampled_from(sorted(VALID_DAYS)))
    start = draw(st.integers(min_value=0, max_value=(23 * 60) + 58))
    max_duration = min(180, (23 * 60 + 59) - start)
    duration = draw(st.integers(min_value=1, max_value=max_duration))
    end = start + duration
    return f"{day} {minutes_to_time_string(start)}-{minutes_to_time_string(end)}"


meeting_list_strategy = st.lists(meeting_entry_strategy(), min_size=1, max_size=4)


@settings(max_examples=800, deadline=None)
@given(times_a=meeting_list_strategy, times_b=meeting_list_strategy)
def test_meeting_times_conflict_is_symmetric(times_a: list[str], times_b: list[str]) -> None:
    assert meeting_times_conflict(times_a, times_b) == meeting_times_conflict(times_b, times_a)


@settings(max_examples=100, deadline=None)
@given(capacity=st.integers(min_value=1, max_value=4))
def test_waitlist_promotion_preserves_consistency(capacity: int) -> None:
    system = RegistrationSystem()
    assert system.add_instructor("I1", "Instructor", "CS")
    assert system.add_course("CS101", "Intro", 3)
    assert system.create_section(
        "SEC1",
        "CS101",
        "Fall 2026",
        "I1",
        ["Mon 09:00-10:00", "Wed 09:00-10:00"],
        capacity,
    )

    total_students = capacity + 2
    for index in range(total_students):
        assert system.add_student(f"S{index}", f"Student {index}", 18)

    for index in range(total_students):
        ok, _ = system.register_student(f"S{index}", "SEC1")
        assert ok

    section = system.sections["SEC1"]
    assert len(section.enrolled_students) == capacity
    assert len(section.waitlist) == 2

    first_enrolled = section.enrolled_students[0]
    ok, _ = system.drop_student(first_enrolled, "SEC1")
    assert ok

    section = system.sections["SEC1"]
    assert len(section.enrolled_students) == capacity
    assert len(section.waitlist) == 1
    assert first_enrolled not in section.enrolled_students
    assert first_enrolled not in section.waitlist


@settings(max_examples=120, deadline=None)
@given(student_id=st.sampled_from(["S001", "S003", "S004"]))
def test_failed_prerequisite_registration_does_not_mutate_system(student_id: str) -> None:
    system = build_demo_system()
    before = snapshot_system(system)
    ok, _ = system.register_student(student_id, "SEC1002")
    after = snapshot_system(system)
    assert not ok
    assert before == after


operation_strategy = st.lists(
    st.tuples(
        st.sampled_from(["register", "drop", "record"]),
        st.sampled_from(["S001", "S002", "S003", "S004"]),
        st.sampled_from(
            [
                "SEC1001",
                "SEC1002",
                "SEC1003",
                "SEC1004",
                "SEC1005",
                "CS101",
                "CS201",
                "CS240",
                "CS301",
                "MATH201",
                "PHYS101",
            ]
        ),
    ),
    min_size=1,
    max_size=12,
)


@settings(max_examples=160, deadline=None)
@given(operations=operation_strategy)
def test_serialization_round_trip_preserves_system_state(
    operations: list[tuple[str, str, str]],
) -> None:
    system = build_demo_system()

    for action, student_id, target in operations:
        if action == "register" and target.startswith("SEC"):
            system.register_student(student_id, target)
        elif action == "drop" and target.startswith("SEC"):
            system.drop_student(student_id, target)
        elif action == "record" and not target.startswith("SEC"):
            system.record_completed_course(student_id, target)

    restored = RegistrationSystem.from_dict(system.to_dict())
    assert restored.to_dict() == system.to_dict()


@settings(max_examples=80, deadline=None)
@given(student_id=st.sampled_from(["S001", "S002", "S003", "S004"]))
def test_save_load_round_trip_preserves_system_state(student_id: str) -> None:
    system = build_demo_system()
    system.report_student_schedule(student_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "system.json"
        ok, _ = system.save_to_file(str(output_path))
        assert ok
        loaded, message = RegistrationSystem.load_from_file(str(output_path))
        assert loaded is not None, message
        assert loaded.to_dict() == system.to_dict()


json_scalar_strategy = st.none() | st.booleans() | st.integers() | st.text(max_size=12)
json_value_strategy = st.recursive(
    json_scalar_strategy,
    lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=10,
)


@settings(max_examples=160, deadline=None)
@given(payload=json_value_strategy)
def test_load_from_file_handles_valid_json_without_raising(payload: object) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "arbitrary.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            system, message = RegistrationSystem.load_from_file(str(path))
        except Exception as exc:  # pragma: no cover - this is the bug signal
            raise AssertionError(
                f"load_from_file raised {type(exc).__name__}: {exc} for payload {payload!r}"
            ) from exc

        assert isinstance(message, str)
        assert system is None or isinstance(system, RegistrationSystem)


small_text = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "Zs")),
    min_size=1,
    max_size=10,
).map(lambda value: " ".join(value.split()) or "X")

student_id_strategy = st.sampled_from([f"S{i}" for i in range(5)])
course_code_strategy = st.sampled_from([f"C{i}" for i in range(4)])
instructor_id_strategy = st.sampled_from([f"I{i}" for i in range(3)])
section_id_strategy = st.sampled_from([f"SEC{i}" for i in range(6)])
semester_strategy = st.sampled_from(["Fall 2026", "Spring 2027"])
meeting_times_strategy = st.lists(meeting_entry_strategy(), min_size=1, max_size=2)

operation_strategy = st.one_of(
    st.tuples(st.just("add_student"), student_id_strategy, small_text, st.integers(min_value=-2, max_value=24)),
    st.tuples(st.just("remove_student"), student_id_strategy),
    st.tuples(st.just("add_course"), course_code_strategy, small_text, st.integers(min_value=-1, max_value=12)),
    st.tuples(st.just("remove_course"), course_code_strategy),
    st.tuples(st.just("add_instructor"), instructor_id_strategy, small_text, small_text),
    st.tuples(
        st.just("create_section"),
        section_id_strategy,
        course_code_strategy,
        semester_strategy,
        instructor_id_strategy,
        meeting_times_strategy,
        st.integers(min_value=-1, max_value=6),
    ),
    st.tuples(st.just("remove_section"), section_id_strategy),
    st.tuples(st.just("register"), student_id_strategy, section_id_strategy),
    st.tuples(st.just("drop"), student_id_strategy, section_id_strategy),
    st.tuples(st.just("record"), student_id_strategy, course_code_strategy),
    st.tuples(st.just("save_load")),
)


@settings(max_examples=120, deadline=None)
@given(operations=st.lists(operation_strategy, min_size=1, max_size=20))
def test_dynamic_operation_sequences_preserve_core_invariants(operations: list[tuple[object, ...]]) -> None:
    system = RegistrationSystem()

    for operation in operations:
        name = operation[0]
        if name == "add_student":
            _, student_id, student_name, max_credits = operation
            system.add_student(student_id, student_name, max_credits)
        elif name == "remove_student":
            _, student_id = operation
            system.remove_student(student_id)
        elif name == "add_course":
            _, course_code, title, credits = operation
            system.add_course(course_code, title, credits)
        elif name == "remove_course":
            _, course_code = operation
            system.remove_course(course_code)
        elif name == "add_instructor":
            _, instructor_id, instructor_name, department = operation
            system.add_instructor(instructor_id, instructor_name, department)
        elif name == "create_section":
            _, section_id, course_code, semester, instructor_id, meeting_times, capacity = operation
            system.create_section(section_id, course_code, semester, instructor_id, meeting_times, capacity)
        elif name == "remove_section":
            _, section_id = operation
            system.remove_section(section_id)
        elif name == "register":
            _, student_id, section_id = operation
            system.register_student(student_id, section_id)
        elif name == "drop":
            _, student_id, section_id = operation
            system.drop_student(student_id, section_id)
        elif name == "record":
            _, student_id, course_code = operation
            system.record_completed_course(student_id, course_code)
        elif name == "save_load":
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "sequence.json"
                ok, _ = system.save_to_file(str(path))
                if ok:
                    loaded, _ = RegistrationSystem.load_from_file(str(path))
                    if loaded is not None:
                        system = loaded

        assert_system_consistency(system)
        assert RegistrationSystem.from_dict(system.to_dict()).to_dict() == system.to_dict()


@settings(
    max_examples=250,
    stateful_step_count=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
class RegistrationSystemStateMachine(RuleBasedStateMachine):
    def _assert_consistency(self) -> None:
        assert_system_consistency(self.system)

    @initialize()
    def init_system(self) -> None:
        self.system = build_demo_system()

    @rule(
        student_id=st.sampled_from(["S001", "S002", "S003", "S004"]),
        section_id=st.sampled_from(["SEC1001", "SEC1002", "SEC1003", "SEC1004", "SEC1005"]),
    )
    def register(self, student_id: str, section_id: str) -> None:
        self.system.register_student(student_id, section_id)

    @rule(
        student_id=st.sampled_from(["S001", "S002", "S003", "S004"]),
        section_id=st.sampled_from(["SEC1001", "SEC1002", "SEC1003", "SEC1004", "SEC1005"]),
    )
    def drop(self, student_id: str, section_id: str) -> None:
        self.system.drop_student(student_id, section_id)

    @rule(
        student_id=st.sampled_from(["S001", "S002", "S003", "S004"]),
        course_code=st.sampled_from(["CS101", "CS201", "CS240", "CS301", "MATH201", "PHYS101"]),
    )
    def record_completion(self, student_id: str, course_code: str) -> None:
        self.system.record_completed_course(student_id, course_code)

    @rule(query=st.text(min_size=0, max_size=20))
    def search(self, query: str) -> None:
        self.system.search_courses(query)

    @rule(student_id=st.sampled_from(["S001", "S002", "S003", "S004"]))
    def student_report(self, student_id: str) -> None:
        self.system.report_student_schedule(student_id)

    @rule(section_id=st.sampled_from(["SEC1001", "SEC1002", "SEC1003", "SEC1004", "SEC1005"]))
    def roster_report(self, section_id: str) -> None:
        self.system.report_course_roster(section_id)

    @rule(student_id=st.sampled_from(["S001", "S002", "S003", "S004"]))
    def remove_and_restore_student(self, student_id: str) -> None:
        prior = snapshot_system(self.system)
        if self.system.remove_student(student_id):
            self.system = RegistrationSystem.from_dict(json.loads(prior))

    @invariant()
    def serialization_round_trip_invariant(self) -> None:
        assert RegistrationSystem.from_dict(self.system.to_dict()).to_dict() == self.system.to_dict()

    @invariant()
    def consistency_invariant(self) -> None:
        self._assert_consistency()


TestRegistrationSystemStateMachine = RegistrationSystemStateMachine.TestCase
