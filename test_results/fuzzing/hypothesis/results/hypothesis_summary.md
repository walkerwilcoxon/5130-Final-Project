# Hypothesis Results

- Started at (UTC): `2026-04-02T23:49:14.354133+00:00`
- Duration (seconds): `3.682`
- Exit code: `1`
- Test file: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py`
- Raw log: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/hypothesis/raw/pytest_hypothesis.log`
- JUnit XML: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/hypothesis/raw/pytest_hypothesis.junit.xml`
- Tests: `11`
- Failures: `1`
- Errors: `0`
- Skipped: `0`

## Hypothesis Statistics

```text
Hypothesis Statistics =============================
test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_normalize_text_is_idempotent:

  - during generate phase (0.13 seconds):
    - Typical runtimes: < 1ms, of which < 1ms in data generation
    - 600 passing examples, 0 failing examples, 0 invalid examples

  - Stopped because settings.max_examples=600


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_parse_time_string_round_trip:

  - during generate phase (0.23 seconds):
    - Typical runtimes: < 1ms, of which < 1ms in data generation
    - 800 passing examples, 0 failing examples, 0 invalid examples

  - Stopped because settings.max_examples=800


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_parse_meeting_time_valid_inputs:

  - during generate phase (0.28 seconds):
    - Typical runtimes: < 1ms, of which < 1ms in data generation
    - 800 passing examples, 0 failing examples, 13 invalid examples
    - Events:
      * 1.60%, invalid because: failed to satisfy assume() in test_parse_meeting_time_valid_inputs (line 106)

  - Stopped because settings.max_examples=800


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_meeting_times_conflict_is_symmetric:

  - during generate phase (0.58 seconds):
    - Typical runtimes: < 1ms, of which < 1ms in data generation
    - 800 passing examples, 0 failing examples, 49 invalid examples

  - Stopped because settings.max_examples=800


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_waitlist_promotion_preserves_consistency:

  - during generate phase (0.00 seconds):
    - Typical runtimes: < 1ms, of which < 1ms in data generation
    - 4 passing examples, 0 failing examples, 0 invalid examples

  - Stopped because nothing left to do


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_failed_prerequisite_registration_does_not_mutate_system:

  - during generate phase (0.00 seconds):
    - Typical runtimes: < 1ms, of which < 1ms in data generation
    - 3 passing examples, 0 failing examples, 0 invalid examples

  - Stopped because nothing left to do


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_serialization_round_trip_preserves_system_state:

  - during generate phase (0.12 seconds):
    - Typical runtimes: < 1ms, of which < 1ms in data generation
    - 160 passing examples, 0 failing examples, 26 invalid examples

  - Stopped because settings.max_examples=160


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_save_load_round_trip_preserves_system_state:

  - during generate phase (0.00 seconds):
    - Typical runtimes: ~ 0-1 ms, of which < 1ms in data generation
    - 4 passing examples, 0 failing examples, 0 invalid examples

  - Stopped because nothing left to do


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_load_from_file_handles_valid_json_without_raising:

  - during reuse phase (0.03 seconds):
    - Typical runtimes: ~ 28ms, of which < 1ms in data generation
    - 0 passing examples, 1 failing examples, 0 invalid examples
    - Found 1 distinct error in this phase

  - Stopped because nothing left to do


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_dynamic_operation_sequences_preserve_core_invariants:

  - during generate phase (0.10 seconds):
    - Typical runtimes: ~ 0-1 ms, of which < 1ms in data generation
    - 120 passing examples, 0 failing examples, 12 invalid examples

  - Stopped because settings.max_examples=120


test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::TestRegistrationSystemStateMachine::runTest:

  - during generate phase (1.83 seconds):
    - Typical runtimes: ~ 2-8 ms, of which ~ 1-3 ms in data generation
    - 250 passing examples, 0 failing examples, 2 invalid examples
    - Events:
      * 90.08%, Retried draw from sampled_from([Rule(function=remove_and_restore_student, arguments={'student_id': sampled_from(['S001', 'S002', 'S003', 'S004'])}, _cached_hash=8745364864325286440, arguments_strategies={'student_id': sampled_from(['S001', 'S002', 'S003', 'S004'])}), Rule(function=roster_report, arguments={'section_id': sampled_from(['SEC1001', 'SEC1002', 'SEC1003', 'SEC1004', 'SEC1005'])}, _cached_hash=2009651837713560349, arguments_strategies={'section_id': sampled_from(['SEC1001', 'SEC1002', 'SEC1003', 'SEC1004', 'SEC1005'])}), Rule(function=search, arguments={'query': text(max_size=20)}, _cached_hash=-6675550890444189082, arguments_strategies={'query': text(max_size=20)}), Rule(function=student_report, arguments={'student_id': sampled_from(['S001', 'S002', 'S003', 'S004'])}, _cached_hash=6816601364090298381, arguments_strategies={'student_id': sampled_from(['S001', 'S002', 'S003', 'S004'])}), Rule(function=drop, arguments={'student_id': sampled_from(['S001', 'S002', 'S003', 'S004']), 'section_id': sampled_from(['SEC1001', 'SEC1002', 'SEC1003', 'SEC1004', 'SEC1005'])}, _cached_hash=-1853070842538145626, arguments_strategies={'section_id': sampled_from(['SEC1001', 'SEC1002', 'SEC1003', 'SEC1004', 'SEC1005']), 'student_id': sampled_from(['S001', 'S002', 'S003', 'S004'])}), Rule(function=record_completion, arguments={'student_id': sampled_from(['S001', 'S002', 'S003', 'S004']), 'course_code': sampled_from(['CS101', 'CS201', 'CS240', 'CS301', 'MATH201', 'PHYS101'])}, _cached_hash=3097810111362807520, arguments_strategies={'course_code': sampled_from(['CS101', 'CS201', 'CS240', 'CS301', 'MATH201', 'PHYS101']), 'student_id': sampled_from(['S001', 'S002', 'S003', 'S004'])}), Rule(function=register, arguments={'student_id': sampled_from(['S001', 'S002', 'S003', 'S004']), 'section_id': sampled_from(['SEC1001', 'SEC1002', 'SEC1003', 'SEC1004', 'SEC1005'])}, _cached_hash=8894705138553013615, arguments_strategies={'section_id': sampled_from(['SEC1001', 'SEC1002', 'SEC1003', 'SEC1004', 'SEC1005']), 'student_id': sampled_from(['S001', 'S002', 'S003', 'S004'])})]).filter(rule_is_enabled) to satisfy filter

  - Stopped because settings.max_examples=250


=========================== short test summary info ============================
FAILED test_results/fuzzing/hypothesis/scripts/test_course_management_hypothesis.py::test_load_from_file_handles_valid_json_without_raising
1 failed, 10 passed in 3.42s
```
