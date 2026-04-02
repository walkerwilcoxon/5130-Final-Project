# Atheris Results

- Started at (UTC): `2026-04-02T23:49:14.363434+00:00`
- Duration (seconds): `0.29`
- Exit code: `77`
- Coverage export exit code: `0`
- Fuzzer script: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/scripts/fuzz_course_management_atheris.py`
- Run count: `50000`
- Max input length: `256`
- Raw log: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/raw/atheris.log`
- Corpus directory: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/raw/corpus`
- Crash directory: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/raw/crashes`
- Coverage JSON: `/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/raw/coverage.json`
- Corpus files: `9`
- Crash artifacts: `1`
- `course_management_system.py` coverage: `40.19%`

## Crash Files

- `crash-aa154d6dcd4e4c9d8a47c3e49c77ad36eb8d3cf5`

## Raw Log Tail

```text

 === Uncaught Python exception: ===
KeyError: 'student_id'
Traceback (most recent call last):
  File "/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/scripts/fuzz_course_management_atheris.py", line 235, in TestOneInput
    fuzz_persistence_payload(fdp)
  File "/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/scripts/fuzz_course_management_atheris.py", line 204, in fuzz_persistence_payload
    system, message = cms.RegistrationSystem.load_from_file(str(path))
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/hbtong/5130-Final-Project/course_management_system.py", line 1109, in load_from_file
    system = RegistrationSystem.from_dict(data)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/hbtong/5130-Final-Project/course_management_system.py", line 1087, in from_dict
    system.students = {k: Student.from_dict(v) for k, v in data.get("students", {}).items()}
                          ^^^^^^^^^^^^^^^^^^^^
  File "/Users/hbtong/5130-Final-Project/course_management_system.py", line 270, in from_dict
    student_id=data["student_id"],
               ~~~~^^^^^^^^^^^^^^
KeyError: 'student_id'


[stderr]
INFO: Instrumenting course_management_system
INFO: Using built-in libfuzzer
WARNING: Failed to find function "__sanitizer_acquire_crash_state". Reason dlsym(RTLD_DEFAULT, __sanitizer_acquire_crash_state): symbol not found.
WARNING: Failed to find function "__sanitizer_print_stack_trace". Reason dlsym(RTLD_DEFAULT, __sanitizer_print_stack_trace): symbol not found.
WARNING: Failed to find function "__sanitizer_set_death_callback". Reason dlsym(RTLD_DEFAULT, __sanitizer_set_death_callback): symbol not found.
INFO: Running with entropic power schedule (0xFF, 100).
INFO: Seed: 3641691794
INFO:        9 files found in /Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/raw/corpus
INFO: seed corpus: files: 9 min: 4b max: 3563b total: 3678b rss: 53Mb
==33981== ERROR: libFuzzer: fuzz target exited
SUMMARY: libFuzzer: fuzz target exited
MS: 0 ; base unit: 0000000000000000000000000000000000000000
0x4,0x0,0x7b,0x22,0x73,0x74,0x75,0x64,0x65,0x6e,0x74,0x73,0x22,0x3a,0x20,0x7b,0x22,0x53,0x31,0x22,0x3a,0x20,0x7b,0x7d,0x7d,0x7d,
\004\000{\"students\": {\"S1\": {}}}
artifact_prefix='/Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/raw/crashes/'; Test unit written to /Users/hbtong/5130-Final-Project/test_results/fuzzing/atheris/raw/crashes/crash-aa154d6dcd4e4c9d8a47c3e49c77ad36eb8d3cf5
Base64: BAB7InN0dWRlbnRzIjogeyJTMSI6IHt9fX0=
```
