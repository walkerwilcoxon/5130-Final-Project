from hypothesis import given, strategies as st

@given(st.text())
def test_normalize_text_property_matches_manual_normalization(value):
    expected = " ".join(value.strip().split()).lower()
    assert normalize_text(value) == expected


@given(st.integers(min_value=0, max_value=23), st.integers(min_value=0, max_value=59))
def test_parse_and_format_time_round_trip(hour, minute):
    time_str = f"{hour:02d}:{minute:02d}"
    minutes = parse_time_string(time_str)
    assert minutes == hour * 60 + minute
    assert minutes_to_time_string(minutes) == time_str


@given(
    st.sampled_from(sorted(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])),
    st.integers(min_value=0, max_value=22 * 60 + 58),
    st.integers(min_value=1, max_value=120),
)
def test_parse_meeting_time_property(day, start, duration):
    end = start + duration
    if end > 23 * 60 + 59:
        end = 23 * 60 + 59
    if end <= start:
        end = start + 1

    entry = f"{day} {minutes_to_time_string(start)}-{minutes_to_time_string(end)}"
    parsed_day, parsed_start, parsed_end = parse_meeting_time(entry)

    assert parsed_day == day
    assert parsed_start == start
    assert parsed_end == end


@given(
    st.sampled_from(sorted(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])),
    st.integers(min_value=0, max_value=20 * 60),
    st.integers(min_value=1, max_value=120),
    st.integers(min_value=0, max_value=180),
)
def test_meeting_times_conflict_property_symmetric(day, start1, duration1, offset):
    end1 = start1 + duration1
    if end1 > 23 * 60 + 59:
        end1 = 23 * 60 + 59
    if end1 <= start1:
        end1 = start1 + 1

    start2 = min(start1 + offset, 23 * 60 + 58)
    end2 = min(start2 + duration1, 23 * 60 + 59)
    if end2 <= start2:
        end2 = start2 + 1

    a = [f"{day} {minutes_to_time_string(start1)}-{minutes_to_time_string(end1)}"]
    b = [f"{day} {minutes_to_time_string(start2)}-{minutes_to_time_string(end2)}"]

    assert meeting_times_conflict(a, b) == meeting_times_conflict(b, a)


@given(st.text(min_size=1))
def test_search_courses_property_finds_inserted_unique_title(title):
    system = RegistrationSystem()
    unique_title = f"UniquePrefix_{title}_UniqueSuffix"
    system.add_course("CS777", unique_title, 3)

    results = system.search_courses("uniqueprefix")
    assert any(course.course_code == "CS777" for course in results)


@given(st.text(min_size=1, alphabet=st.characters(blacklist_categories=("Cc", "Cs"))))
def test_save_and_load_property_preserves_student_name(name, tmp_path):
    system = RegistrationSystem()
    system.add_student("S1", name, 18)
    path = tmp_path / "prop_system.json"

    ok, _ = system.save_to_file(str(path))
    loaded, _ = RegistrationSystem.load_from_file(str(path))

    assert ok is True
    assert loaded is not None
    assert loaded.students["S1"].name == name


@given(st.integers(min_value=1, max_value=30))
def test_add_student_property_valid_max_credits(max_credits):
    system = RegistrationSystem()
    ok = system.add_student("S200", "Prop Student", max_credits)
    assert ok is True
    assert system.students["S200"].max_credits == max_credits


@given(st.integers(min_value=-10, max_value=0))
def test_add_student_property_nonpositive_max_credits_fail(max_credits):
    system = RegistrationSystem()
    ok = system.add_student("S201", "Bad Student", max_credits)
    assert ok is False
    assert "S201" not in system.students


@given(st.integers(min_value=1, max_value=10))
def test_add_course_property_valid_credits(credits):
    system = RegistrationSystem()
    ok = system.add_course("CS500", "Property Course", credits)
    assert ok is True
    assert system.courses["CS500"].credits == credits


@given(st.integers().filter(lambda x: x <= 0 or x > 10))
def test_add_course_property_invalid_credits_fail(credits):
    system = RegistrationSystem()
    ok = system.add_course("CS501", "Invalid Credits Course", credits)
    assert ok is False
    assert "CS501" not in system.courses