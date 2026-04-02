import pytest
import inspect
from course_management_system import RegistrationSystem, build_demo_system

# ---------------------------
# CONFIG: Argument Mapping
# ---------------------------

ARG_MAP = {
    "add_student": ("X999", "Benchmark Student", 18),
    "remove_student": ("S003",),
    "add_course": ("CS999", "Benchmark Course", 3, []),
    "remove_course": ("CS999",),
    "add_instructor": ("I999", "Bench Prof", "CS"),
    "remove_instructor": ("I103",),
    "create_section": ("SEC999", "CS101", "Fall 2026", "I100", ["Mon 12:00-13:00"], 2),
    "remove_section": ("SEC1005",),
    "register_student": ("S001", "SEC1003"),
    "drop_student": ("S001", "SEC1003"),
    "record_completed_course": ("S001", "CS101"),
    "search_courses": ("CS",),
    "list_sections_for_course": ("CS101",),
    "list_student_schedule": ("S001",),
    "report_student_schedule": ("S001",),
    "report_course_roster": ("SEC1001",),
    "check_prerequisites": ("S001", "CS201"),
    "check_schedule_conflict": ("S001", "SEC1001"),
    "check_credit_limit": ("S001", "SEC1001"),
    "can_register": ("S001", "SEC1003"),
}

SKIP_METHODS = {
    # Avoid CLI / I/O / heavy print methods
    "save_to_file",
    "load_from_file",
    "print_all_students",
    "print_all_courses",
    "print_all_sections",
    "print_all_instructors",
}


# ---------------------------
# FIXTURE: Demo System
# ---------------------------

@pytest.fixture
def system():
    return build_demo_system()


# ---------------------------
# AUTO-DISCOVERY
# ---------------------------

def get_methods():
    methods = []

    for name, method in inspect.getmembers(RegistrationSystem, inspect.isfunction):
        if name.startswith("_"):
            continue
        if name in SKIP_METHODS:
            continue
        methods.append(name)

    return methods


# ---------------------------
# SAFE CALL WRAPPER
# ---------------------------

def safe_call(system, method_name):
    method = getattr(system, method_name)
    args = ARG_MAP.get(method_name, ())

    try:
        return method(*args)
    except Exception:
        # Ignore failures → we care about performance, not correctness here
        return None


# ---------------------------
# MICRO BENCHMARKS (ALL METHODS)
# ---------------------------

@pytest.mark.parametrize("method_name", get_methods())
def test_all_methods_benchmark(benchmark, system, method_name):
    benchmark(lambda: safe_call(system, method_name))


# ---------------------------
# STRESS TESTS (HIGH LOAD)
# ---------------------------

def test_stress_registration(benchmark):
    def workload():
        system = build_demo_system()
        for _ in range(200):
            system.register_student("S001", "SEC1003")
            system.drop_student("S001", "SEC1003")

    benchmark(workload)


def test_stress_waitlist(benchmark):
    def workload():
        system = build_demo_system()
        for i in range(50):
            sid = f"SX{i}"
            system.add_student(sid, "Load Student")
            system.register_student(sid, "SEC1001")  # force waitlist

    benchmark(workload)


def test_stress_conflict_checks(benchmark, system):
    def workload():
        for _ in range(500):
            system.check_schedule_conflict("S001", "SEC1001")

    benchmark(workload)


# ---------------------------
# SCENARIO BENCHMARK (REALISTIC FLOW)
# ---------------------------

def test_full_registration_flow(benchmark):
    def scenario():
        system = build_demo_system()

        system.add_student("S999", "Scenario Student")
        system.record_completed_course("S999", "CS101")
        system.register_student("S999", "SEC1001")
        system.register_student("S999", "SEC1002")
        system.drop_student("S999", "SEC1001")
        system.promote_waitlist("SEC1001")

    benchmark(scenario)