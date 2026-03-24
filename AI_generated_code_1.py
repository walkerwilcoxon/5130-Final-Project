"""
Course Registration and Enrollment Management System
===================================================

Architecture overview:
- Data model classes:
  - Student
  - Course
  - Instructor
  - Section
  - EnrollmentRecord
- RegistrationSystem:
  Central coordinator that stores all entities and implements policy logic:
  prerequisites, schedule conflict checks, capacity/waitlist handling,
  credit limit enforcement, reporting, serialization, and CLI operations.
- Utility functions:
  time parsing, meeting-time conflict detection, ID generation helpers,
  and formatting functions.
- CLI:
  A text-based menu for common university registration operations.

This program is intentionally written as a substantial single-file system with
explicit control flow, helper methods, branching logic, loops, and validation
to support static analysis tasks such as call graph, CFG, and dependency analysis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import deque


# ---------------------------
# Utility functions
# ---------------------------

VALID_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


def normalize_text(value: str) -> str:
    """Normalize a text value for comparison/search."""
    return " ".join(value.strip().split()).lower()


def parse_time_string(time_str: str) -> int:
    """
    Convert 'HH:MM' into minutes since midnight.
    Raises ValueError on invalid input.
    """
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str}")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Time out of range: {time_str}")
    return hour * 60 + minute


def minutes_to_time_string(value: int) -> str:
    """Convert minutes since midnight to HH:MM."""
    hour = value // 60
    minute = value % 60
    return f"{hour:02d}:{minute:02d}"


def parse_meeting_time(entry: str) -> Tuple[str, int, int]:
    """
    Parse a meeting time string like 'Mon 09:00-10:15' into structured form.
    Returns (day, start_minutes, end_minutes).
    """
    raw = entry.strip()
    pieces = raw.split()
    if len(pieces) != 2:
        raise ValueError(f"Meeting time must look like 'Mon 09:00-10:15': {entry}")

    day = pieces[0]
    if day not in VALID_DAYS:
        raise ValueError(f"Invalid day '{day}' in meeting time '{entry}'")

    time_range = pieces[1]
    if "-" not in time_range:
        raise ValueError(f"Time range must contain '-': {entry}")
    start_str, end_str = time_range.split("-", 1)

    start_min = parse_time_string(start_str)
    end_min = parse_time_string(end_str)

    if end_min <= start_min:
        raise ValueError(f"End time must be after start time: {entry}")

    return day, start_min, end_min


def meeting_times_conflict(times_a: List[str], times_b: List[str]) -> bool:
    """
    Return True if any meeting time in two lists conflicts on the same day.
    """
    parsed_a: List[Tuple[str, int, int]] = []
    parsed_b: List[Tuple[str, int, int]] = []

    for entry in times_a:
        parsed_a.append(parse_meeting_time(entry))
    for entry in times_b:
        parsed_b.append(parse_meeting_time(entry))

    for day_a, start_a, end_a in parsed_a:
        for day_b, start_b, end_b in parsed_b:
            if day_a != day_b:
                continue
            if start_a < end_b and start_b < end_a:
                return True
    return False


def safe_int_input(prompt: str) -> Optional[int]:
    """Read an integer from input; return None if invalid."""
    raw = input(prompt).strip()
    try:
        return int(raw)
    except ValueError:
        return None


# ---------------------------
# Data model classes
# ---------------------------

@dataclass
class Student:
    """Represents a student in the registration system."""
    student_id: str
    name: str
    max_credits: int = 18
    completed_courses: List[str] = field(default_factory=list)
    current_enrollments: List[str] = field(default_factory=list)  # section_ids
    waitlisted_sections: List[str] = field(default_factory=list)   # section_ids

    def current_credit_load(self, sections: Dict[str, "Section"]) -> int:
        """Calculate current registered credit load."""
        total = 0
        for section_id in self.current_enrollments:
            section = sections.get(section_id)
            if section is not None:
                total += section.credits
        return total

    def has_completed(self, course_code: str) -> bool:
        """Check if student completed a course."""
        return course_code in self.completed_courses

    def is_registered_in_semester(self, sections: Dict[str, "Section"], semester: str) -> bool:
        """Check if student has any active enrollment in a given semester."""
        for section_id in self.current_enrollments:
            section = sections.get(section_id)
            if section and section.semester == semester:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "name": self.name,
            "max_credits": self.max_credits,
            "completed_courses": list(self.completed_courses),
            "current_enrollments": list(self.current_enrollments),
            "waitlisted_sections": list(self.waitlisted_sections),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Student":
        return Student(
            student_id=data["student_id"],
            name=data["name"],
            max_credits=data.get("max_credits", 18),
            completed_courses=list(data.get("completed_courses", [])),
            current_enrollments=list(data.get("current_enrollments", [])),
            waitlisted_sections=list(data.get("waitlisted_sections", [])),
        )


@dataclass
class Course:
    """Represents a catalog course."""
    course_code: str
    title: str
    credits: int
    prerequisites: List[str] = field(default_factory=list)
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "course_code": self.course_code,
            "title": self.title,
            "credits": self.credits,
            "prerequisites": list(self.prerequisites),
            "active": self.active,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Course":
        return Course(
            course_code=data["course_code"],
            title=data["title"],
            credits=data["credits"],
            prerequisites=list(data.get("prerequisites", [])),
            active=data.get("active", True),
        )


@dataclass
class Instructor:
    """Represents an instructor."""
    instructor_id: str
    name: str
    department: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instructor_id": self.instructor_id,
            "name": self.name,
            "department": self.department,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Instructor":
        return Instructor(
            instructor_id=data["instructor_id"],
            name=data["name"],
            department=data["department"],
        )


@dataclass
class Section:
    """Represents a section/class offering of a course."""
    section_id: str
    course_code: str
    semester: str
    instructor_id: str
    meeting_times: List[str]
    capacity: int
    credits: int
    enrolled_students: List[str] = field(default_factory=list)
    waitlist: List[str] = field(default_factory=list)

    def seats_available(self) -> int:
        """Return number of open seats."""
        return self.capacity - len(self.enrolled_students)

    def is_full(self) -> bool:
        """Return True if section has no open seats."""
        return len(self.enrolled_students) >= self.capacity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "course_code": self.course_code,
            "semester": self.semester,
            "instructor_id": self.instructor_id,
            "meeting_times": list(self.meeting_times),
            "capacity": self.capacity,
            "credits": self.credits,
            "enrolled_students": list(self.enrolled_students),
            "waitlist": list(self.waitlist),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Section":
        return Section(
            section_id=data["section_id"],
            course_code=data["course_code"],
            semester=data["semester"],
            instructor_id=data["instructor_id"],
            meeting_times=list(data.get("meeting_times", [])),
            capacity=data["capacity"],
            credits=data["credits"],
            enrolled_students=list(data.get("enrolled_students", [])),
            waitlist=list(data.get("waitlist", [])),
        )


@dataclass
class EnrollmentRecord:
    """Represents a registration outcome or status relation between student and section."""
    student_id: str
    section_id: str
    status: str  # "enrolled", "waitlisted", "dropped"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "section_id": self.section_id,
            "status": self.status,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "EnrollmentRecord":
        return EnrollmentRecord(
            student_id=data["student_id"],
            section_id=data["section_id"],
            status=data["status"],
        )


# ---------------------------
# Registration system
# ---------------------------

class RegistrationSystem:
    """Main coordination class for the course registration system."""

    def __init__(self) -> None:
        self.students: Dict[str, Student] = {}
        self.courses: Dict[str, Course] = {}
        self.instructors: Dict[str, Instructor] = {}
        self.sections: Dict[str, Section] = {}
        self.enrollment_history: List[EnrollmentRecord] = []

    # ---------------------------
    # Entity creation/removal
    # ---------------------------

    def add_student(self, student_id: str, name: str, max_credits: int = 18) -> bool:
        if not student_id or not name:
            return False
        if student_id in self.students:
            return False
        if max_credits <= 0:
            return False
        self.students[student_id] = Student(student_id=student_id, name=name, max_credits=max_credits)
        return True

    def remove_student(self, student_id: str) -> bool:
        student = self.students.get(student_id)
        if student is None:
            return False

        # Remove from all enrolled sections
        for section_id in list(student.current_enrollments):
            self.drop_student(student_id, section_id, reason="student removed")

        # Remove from all waitlists
        for section_id in list(student.waitlisted_sections):
            section = self.sections.get(section_id)
            if section and student_id in section.waitlist:
                section.waitlist.remove(student_id)

        del self.students[student_id]
        return True

    def add_course(self, course_code: str, title: str, credits: int, prerequisites: Optional[List[str]] = None) -> bool:
        if not course_code or not title:
            return False
        if course_code in self.courses:
            return False
        if credits <= 0 or credits > 10:
            return False
        prereqs = prerequisites or []
        self.courses[course_code] = Course(
            course_code=course_code,
            title=title,
            credits=credits,
            prerequisites=prereqs,
        )
        return True

    def remove_course(self, course_code: str) -> bool:
        if course_code not in self.courses:
            return False

        # Reject removal if sections exist for this course.
        for section in self.sections.values():
            if section.course_code == course_code:
                return False

        del self.courses[course_code]
        return True

    def add_instructor(self, instructor_id: str, name: str, department: str) -> bool:
        if not instructor_id or not name or not department:
            return False
        if instructor_id in self.instructors:
            return False
        self.instructors[instructor_id] = Instructor(
            instructor_id=instructor_id,
            name=name,
            department=department,
        )
        return True

    def remove_instructor(self, instructor_id: str) -> bool:
        if instructor_id not in self.instructors:
            return False

        # Reject removal if still assigned to a section.
        for section in self.sections.values():
            if section.instructor_id == instructor_id:
                return False

        del self.instructors[instructor_id]
        return True

    def create_section(
        self,
        section_id: str,
        course_code: str,
        semester: str,
        instructor_id: str,
        meeting_times: List[str],
        capacity: int,
    ) -> bool:
        if section_id in self.sections:
            return False
        if course_code not in self.courses:
            return False
        if instructor_id not in self.instructors:
            return False
        if capacity <= 0:
            return False
        if not meeting_times:
            return False

        # Validate all meeting times.
        try:
            for entry in meeting_times:
                parse_meeting_time(entry)
        except ValueError:
            return False

        course = self.courses[course_code]
        section = Section(
            section_id=section_id,
            course_code=course_code,
            semester=semester,
            instructor_id=instructor_id,
            meeting_times=meeting_times,
            capacity=capacity,
            credits=course.credits,
        )
        self.sections[section_id] = section
        return True

    def remove_section(self, section_id: str) -> bool:
        section = self.sections.get(section_id)
        if section is None:
            return False

        # Drop all enrolled students and clear waitlist references.
        for student_id in list(section.enrolled_students):
            self.drop_student(student_id, section_id, reason="section removed", promote=False)

        for student_id in list(section.waitlist):
            student = self.students.get(student_id)
            if student and section_id in student.waitlisted_sections:
                student.waitlisted_sections.remove(section_id)

        del self.sections[section_id]
        return True

    # ---------------------------
    # Validation and policy checks
    # ---------------------------

    def student_exists(self, student_id: str) -> bool:
        return student_id in self.students

    def course_exists(self, course_code: str) -> bool:
        return course_code in self.courses

    def section_exists(self, section_id: str) -> bool:
        return section_id in self.sections

    def get_student_semester_sections(self, student_id: str, semester: str) -> List[Section]:
        student = self.students.get(student_id)
        if student is None:
            return []
        result: List[Section] = []
        for section_id in student.current_enrollments:
            section = self.sections.get(section_id)
            if section is not None and section.semester == semester:
                result.append(section)
        return result

    def check_prerequisites(self, student_id: str, course_code: str) -> Tuple[bool, List[str]]:
        student = self.students.get(student_id)
        course = self.courses.get(course_code)
        if student is None or course is None:
            return False, ["student or course not found"]

        missing: List[str] = []
        for prereq in course.prerequisites:
            if not student.has_completed(prereq):
                missing.append(prereq)

        return len(missing) == 0, missing

    def check_schedule_conflict(self, student_id: str, section_id: str) -> Tuple[bool, Optional[str]]:
        student = self.students.get(student_id)
        target = self.sections.get(section_id)
        if student is None or target is None:
            return False, "student or section not found"

        for enrolled_section in self.get_student_semester_sections(student_id, target.semester):
            if enrolled_section.section_id == target.section_id:
                continue
            if meeting_times_conflict(enrolled_section.meeting_times, target.meeting_times):
                return False, enrolled_section.section_id
        return True, None

    def check_credit_limit(self, student_id: str, section_id: str) -> Tuple[bool, int, int]:
        student = self.students.get(student_id)
        section = self.sections.get(section_id)
        if student is None or section is None:
            return False, 0, 0

        current = student.current_credit_load(self.sections)
        projected = current + section.credits
        allowed = projected <= student.max_credits
        return allowed, current, projected

    def check_duplicate_course_in_semester(self, student_id: str, section_id: str) -> Tuple[bool, Optional[str]]:
        student = self.students.get(student_id)
        target = self.sections.get(section_id)
        if student is None or target is None:
            return False, "student or section not found"

        for existing_section_id in student.current_enrollments:
            existing = self.sections.get(existing_section_id)
            if existing and existing.semester == target.semester and existing.course_code == target.course_code:
                return False, existing.section_id

        for waitlisted_section_id in student.waitlisted_sections:
            existing = self.sections.get(waitlisted_section_id)
            if existing and existing.semester == target.semester and existing.course_code == target.course_code:
                return False, existing.section_id

        return True, None

    def can_register(self, student_id: str, section_id: str) -> Tuple[bool, List[str]]:
        """
        Composite registration validation. Returns (allowed, reasons).
        """
        reasons: List[str] = []

        student = self.students.get(student_id)
        section = self.sections.get(section_id)
        if student is None:
            reasons.append("student not found")
        if section is None:
            reasons.append("section not found")
        if reasons:
            return False, reasons

        if student_id in section.enrolled_students:
            reasons.append("student already enrolled in this section")
        if student_id in section.waitlist:
            reasons.append("student already waitlisted for this section")

        ok_prereq, missing = self.check_prerequisites(student_id, section.course_code)
        if not ok_prereq:
            reasons.append(f"missing prerequisites: {', '.join(missing)}")

        ok_dup, conflict_section = self.check_duplicate_course_in_semester(student_id, section_id)
        if not ok_dup:
            reasons.append(f"duplicate course attempt in semester via section {conflict_section}")

        ok_sched, conflicting_section_id = self.check_schedule_conflict(student_id, section_id)
        if not ok_sched:
            reasons.append(f"schedule conflict with section {conflicting_section_id}")

        ok_credit, current, projected = self.check_credit_limit(student_id, section_id)
        if not ok_credit:
            reasons.append(
                f"credit limit exceeded: current {current}, projected {projected}, max {student.max_credits}"
            )

        return len(reasons) == 0, reasons

    # ---------------------------
    # Registration operations
    # ---------------------------

    def register_student(self, student_id: str, section_id: str) -> Tuple[bool, str]:
        allowed, reasons = self.can_register(student_id, section_id)
        if not allowed:
            return False, "; ".join(reasons)

        student = self.students[student_id]
        section = self.sections[section_id]

        if section.is_full():
            section.waitlist.append(student_id)
            if section_id not in student.waitlisted_sections:
                student.waitlisted_sections.append(section_id)
            self.enrollment_history.append(
                EnrollmentRecord(student_id=student_id, section_id=section_id, status="waitlisted")
            )
            return True, f"section full; student {student_id} added to waitlist for {section_id}"

        section.enrolled_students.append(student_id)
        if section_id not in student.current_enrollments:
            student.current_enrollments.append(section_id)

        self.enrollment_history.append(
            EnrollmentRecord(student_id=student_id, section_id=section_id, status="enrolled")
        )
        return True, f"student {student_id} enrolled in {section_id}"

    def drop_student(
        self,
        student_id: str,
        section_id: str,
        reason: str = "user requested drop",
        promote: bool = True,
    ) -> Tuple[bool, str]:
        student = self.students.get(student_id)
        section = self.sections.get(section_id)

        if student is None:
            return False, "student not found"
        if section is None:
            return False, "section not found"

        was_enrolled = student_id in section.enrolled_students
        was_waitlisted = student_id in section.waitlist

        if not was_enrolled and not was_waitlisted:
            return False, "student not enrolled or waitlisted in section"

        if was_enrolled:
            section.enrolled_students.remove(student_id)
            if section_id in student.current_enrollments:
                student.current_enrollments.remove(section_id)

        if was_waitlisted:
            section.waitlist.remove(student_id)
            if section_id in student.waitlisted_sections:
                student.waitlisted_sections.remove(section_id)

        self.enrollment_history.append(
            EnrollmentRecord(student_id=student_id, section_id=section_id, status="dropped")
        )

        message = f"student {student_id} dropped from {section_id} ({reason})"

        if promote and was_enrolled:
            promoted_message = self.promote_waitlist(section_id)
            if promoted_message:
                message += f"; {promoted_message}"

        return True, message

    def promote_waitlist(self, section_id: str) -> str:
        """
        Promote waitlisted students into open seats when possible.
        This function re-checks rules because some state may have changed.
        """
        section = self.sections.get(section_id)
        if section is None:
            return ""

        promotions: List[str] = []

        while not section.is_full() and section.waitlist:
            next_student_id = section.waitlist[0]

            # Guard against missing student data
            student = self.students.get(next_student_id)
            if student is None:
                section.waitlist.pop(0)
                continue

            # Remove stale waitlist reference from student's list if needed later.
            allowed, reasons = self.can_register(next_student_id, section_id)

            # can_register will complain if already waitlisted; for promotion, that specific
            # condition should not block us. Therefore, we manually re-evaluate with custom checks.
            allowed_for_promotion, reasons_for_promotion = self._can_promote_waitlisted_student(next_student_id, section_id)

            if not allowed_for_promotion:
                # Policy choice: keep on waitlist if still possibly eligible later only for capacity?
                # But if reasons are structural (schedule conflict, credits), keeping them may block others.
                # We remove them to avoid indefinite blockage.
                section.waitlist.pop(0)
                if section_id in student.waitlisted_sections:
                    student.waitlisted_sections.remove(section_id)
                promotions.append(
                    f"removed {next_student_id} from waitlist due to ineligibility ({'; '.join(reasons_for_promotion)})"
                )
                continue

            section.waitlist.pop(0)
            if section_id in student.waitlisted_sections:
                student.waitlisted_sections.remove(section_id)
            section.enrolled_students.append(next_student_id)
            if section_id not in student.current_enrollments:
                student.current_enrollments.append(section_id)
            self.enrollment_history.append(
                EnrollmentRecord(student_id=next_student_id, section_id=section_id, status="enrolled")
            )
            promotions.append(f"promoted {next_student_id} from waitlist into {section_id}")

        return "; ".join(promotions)

    def _can_promote_waitlisted_student(self, student_id: str, section_id: str) -> Tuple[bool, List[str]]:
        """
        Specialized eligibility check for waitlist promotion.
        Does not reject because student is already on the waitlist.
        """
        reasons: List[str] = []
        student = self.students.get(student_id)
        section = self.sections.get(section_id)

        if student is None:
            reasons.append("student not found")
            return False, reasons
        if section is None:
            reasons.append("section not found")
            return False, reasons

        if student_id in section.enrolled_students:
            reasons.append("already enrolled")
            return False, reasons

        ok_prereq, missing = self.check_prerequisites(student_id, section.course_code)
        if not ok_prereq:
            reasons.append(f"missing prerequisites: {', '.join(missing)}")

        ok_dup, dup_section = self.check_duplicate_course_in_semester_promotion(student_id, section_id)
        if not ok_dup:
            reasons.append(f"duplicate course attempt in semester via section {dup_section}")

        ok_sched, conflicting = self.check_schedule_conflict(student_id, section_id)
        if not ok_sched:
            reasons.append(f"schedule conflict with section {conflicting}")

        ok_credit, current, projected = self.check_credit_limit(student_id, section_id)
        if not ok_credit:
            reasons.append(
                f"credit limit exceeded: current {current}, projected {projected}, max {student.max_credits}"
            )

        return len(reasons) == 0, reasons

    def check_duplicate_course_in_semester_promotion(self, student_id: str, section_id: str) -> Tuple[bool, Optional[str]]:
        """
        Similar to duplicate course check, but ignore the same waitlisted section because
        the student is being promoted from it.
        """
        student = self.students.get(student_id)
        target = self.sections.get(section_id)
        if student is None or target is None:
            return False, "student or section not found"

        for existing_section_id in student.current_enrollments:
            existing = self.sections.get(existing_section_id)
            if existing and existing.semester == target.semester and existing.course_code == target.course_code:
                return False, existing.section_id

        for waitlisted_section_id in student.waitlisted_sections:
            if waitlisted_section_id == section_id:
                continue
            existing = self.sections.get(waitlisted_section_id)
            if existing and existing.semester == target.semester and existing.course_code == target.course_code:
                return False, existing.section_id

        return True, None

    # ---------------------------
    # Academic record operations
    # ---------------------------

    def record_completed_course(self, student_id: str, course_code: str) -> Tuple[bool, str]:
        student = self.students.get(student_id)
        course = self.courses.get(course_code)

        if student is None:
            return False, "student not found"
        if course is None:
            return False, "course not found"

        if course_code in student.completed_courses:
            return False, "course already recorded as completed"

        student.completed_courses.append(course_code)
        return True, f"recorded completed course {course_code} for {student_id}"

    # ---------------------------
    # Search and list
    # ---------------------------

    def search_courses(self, query: str) -> List[Course]:
        needle = normalize_text(query)
        results: List[Course] = []
        for course in self.courses.values():
            haystack = f"{course.course_code} {course.title}"
            if needle in normalize_text(haystack):
                results.append(course)
        results.sort(key=lambda c: c.course_code)
        return results

    def list_sections_for_course(self, course_code: str) -> List[Section]:
        results: List[Section] = []
        for section in self.sections.values():
            if section.course_code == course_code:
                results.append(section)
        results.sort(key=lambda s: (s.semester, s.section_id))
        return results

    def list_student_schedule(self, student_id: str) -> List[Section]:
        student = self.students.get(student_id)
        if student is None:
            return []
        results: List[Section] = []
        for section_id in student.current_enrollments:
            section = self.sections.get(section_id)
            if section is not None:
                results.append(section)
        results.sort(key=lambda s: (s.semester, s.section_id))
        return results

    # ---------------------------
    # Reporting
    # ---------------------------

    def report_student_schedule(self, student_id: str) -> str:
        student = self.students.get(student_id)
        if student is None:
            return "student not found"

        lines = [f"Schedule for {student.student_id} - {student.name}"]
        sections = self.list_student_schedule(student_id)

        if not sections:
            lines.append("  No current enrollments.")
        else:
            for section in sections:
                course = self.courses.get(section.course_code)
                instructor = self.instructors.get(section.instructor_id)
                lines.append(
                    f"  {section.section_id}: {section.course_code} - {course.title if course else 'Unknown'} "
                    f"({section.semester}), Credits: {section.credits}, "
                    f"Instructor: {instructor.name if instructor else section.instructor_id}, "
                    f"Meetings: {', '.join(section.meeting_times)}"
                )

        if student.waitlisted_sections:
            lines.append("  Waitlisted:")
            for section_id in student.waitlisted_sections:
                section = self.sections.get(section_id)
                if section is not None:
                    lines.append(f"    {section.section_id} ({section.course_code}, {section.semester})")

        total_credits = student.current_credit_load(self.sections)
        lines.append(f"  Current credit load: {total_credits}/{student.max_credits}")

        if student.completed_courses:
            lines.append("  Completed courses: " + ", ".join(sorted(student.completed_courses)))
        else:
            lines.append("  Completed courses: none")

        return "\n".join(lines)

    def report_course_roster(self, section_id: str) -> str:
        section = self.sections.get(section_id)
        if section is None:
            return "section not found"

        course = self.courses.get(section.course_code)
        instructor = self.instructors.get(section.instructor_id)

        lines = [
            f"Roster for {section.section_id}",
            f"  Course: {section.course_code} - {course.title if course else 'Unknown'}",
            f"  Semester: {section.semester}",
            f"  Instructor: {instructor.name if instructor else section.instructor_id}",
            f"  Capacity: {section.capacity}",
            f"  Enrolled: {len(section.enrolled_students)}",
            f"  Open Seats: {section.seats_available()}",
            f"  Meetings: {', '.join(section.meeting_times)}",
            "  Students:",
        ]

        if not section.enrolled_students:
            lines.append("    none")
        else:
            for student_id in section.enrolled_students:
                student = self.students.get(student_id)
                if student:
                    lines.append(f"    {student.student_id} - {student.name}")
                else:
                    lines.append(f"    {student_id} - <missing student record>")

        lines.append("  Waitlist:")
        if not section.waitlist:
            lines.append("    none")
        else:
            for index, student_id in enumerate(section.waitlist, start=1):
                student = self.students.get(student_id)
                if student:
                    lines.append(f"    {index}. {student.student_id} - {student.name}")
                else:
                    lines.append(f"    {index}. {student_id} - <missing student record>")

        return "\n".join(lines)

    def report_open_sections(self) -> str:
        lines = ["Open Sections Report"]
        found = False
        for section in sorted(self.sections.values(), key=lambda s: (s.semester, s.course_code, s.section_id)):
            if section.seats_available() > 0:
                found = True
                course = self.courses.get(section.course_code)
                lines.append(
                    f"  {section.section_id}: {section.course_code} - "
                    f"{course.title if course else 'Unknown'} ({section.semester}) | "
                    f"Open Seats: {section.seats_available()} / {section.capacity}"
                )
        if not found:
            lines.append("  No open sections.")
        return "\n".join(lines)

    def report_overloaded_students(self) -> str:
        lines = ["Overloaded Students Report"]
        found = False
        for student in sorted(self.students.values(), key=lambda s: s.student_id):
            current = student.current_credit_load(self.sections)
            if current > student.max_credits:
                found = True
                lines.append(f"  {student.student_id} - {student.name}: {current}/{student.max_credits}")
        if not found:
            lines.append("  No overloaded students.")
        return "\n".join(lines)

    def report_waitlisted_students(self) -> str:
        lines = ["Waitlisted Students Report"]
        found = False
        for section in sorted(self.sections.values(), key=lambda s: (s.semester, s.section_id)):
            if section.waitlist:
                found = True
                course = self.courses.get(section.course_code)
                lines.append(
                    f"  {section.section_id}: {section.course_code} - "
                    f"{course.title if course else 'Unknown'} ({section.semester})"
                )
                for index, student_id in enumerate(section.waitlist, start=1):
                    student = self.students.get(student_id)
                    name = student.name if student else "<missing>"
                    lines.append(f"    {index}. {student_id} - {name}")
        if not found:
            lines.append("  No waitlisted students.")
        return "\n".join(lines)

    def report_system_summary(self) -> str:
        total_students = len(self.students)
        total_courses = len(self.courses)
        total_instructors = len(self.instructors)
        total_sections = len(self.sections)
        total_enrolled = sum(len(section.enrolled_students) for section in self.sections.values())
        total_waitlisted = sum(len(section.waitlist) for section in self.sections.values())

        lines = [
            "System Summary",
            f"  Students: {total_students}",
            f"  Courses: {total_courses}",
            f"  Instructors: {total_instructors}",
            f"  Sections: {total_sections}",
            f"  Enrollment count: {total_enrolled}",
            f"  Waitlist count: {total_waitlisted}",
        ]
        return "\n".join(lines)

    # ---------------------------
    # Persistence
    # ---------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "students": {k: v.to_dict() for k, v in self.students.items()},
            "courses": {k: v.to_dict() for k, v in self.courses.items()},
            "instructors": {k: v.to_dict() for k, v in self.instructors.items()},
            "sections": {k: v.to_dict() for k, v in self.sections.items()},
            "enrollment_history": [record.to_dict() for record in self.enrollment_history],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "RegistrationSystem":
        system = RegistrationSystem()
        system.students = {k: Student.from_dict(v) for k, v in data.get("students", {}).items()}
        system.courses = {k: Course.from_dict(v) for k, v in data.get("courses", {}).items()}
        system.instructors = {k: Instructor.from_dict(v) for k, v in data.get("instructors", {}).items()}
        system.sections = {k: Section.from_dict(v) for k, v in data.get("sections", {}).items()}
        system.enrollment_history = [
            EnrollmentRecord.from_dict(item) for item in data.get("enrollment_history", [])
        ]
        return system

    def save_to_file(self, filename: str) -> Tuple[bool, str]:
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True, f"saved to {filename}"
        except OSError as exc:
            return False, f"failed to save: {exc}"

    @staticmethod
    def load_from_file(filename: str) -> Tuple[Optional["RegistrationSystem"], str]:
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            system = RegistrationSystem.from_dict(data)
            return system, f"loaded from {filename}"
        except FileNotFoundError:
            return None, "file not found"
        except json.JSONDecodeError as exc:
            return None, f"invalid JSON: {exc}"
        except OSError as exc:
            return None, f"failed to load: {exc}"

    # ---------------------------
    # Display helpers
    # ---------------------------

    def print_all_students(self) -> None:
        print("Students")
        if not self.students:
            print("  none")
            return
        for student in sorted(self.students.values(), key=lambda s: s.student_id):
            print(f"  {student.student_id}: {student.name} (max credits {student.max_credits})")

    def print_all_courses(self) -> None:
        print("Courses")
        if not self.courses:
            print("  none")
            return
        for course in sorted(self.courses.values(), key=lambda c: c.course_code):
            prereq_text = ", ".join(course.prerequisites) if course.prerequisites else "none"
            print(
                f"  {course.course_code}: {course.title} | Credits: {course.credits} | "
                f"Prereqs: {prereq_text}"
            )

    def print_all_sections(self) -> None:
        print("Sections")
        if not self.sections:
            print("  none")
            return
        for section in sorted(self.sections.values(), key=lambda s: (s.semester, s.section_id)):
            print(
                f"  {section.section_id}: {section.course_code} | {section.semester} | "
                f"Seats {len(section.enrolled_students)}/{section.capacity} | "
                f"Waitlist {len(section.waitlist)}"
            )

    def print_all_instructors(self) -> None:
        print("Instructors")
        if not self.instructors:
            print("  none")
            return
        for instructor in sorted(self.instructors.values(), key=lambda i: i.instructor_id):
            print(f"  {instructor.instructor_id}: {instructor.name} ({instructor.department})")


# ---------------------------
# Demo data
# ---------------------------

def build_demo_system() -> RegistrationSystem:
    """Create a hardcoded demo dataset so the program runs immediately."""
    system = RegistrationSystem()

    # Instructors
    system.add_instructor("I100", "Dr. Alice Nguyen", "Computer Science")
    system.add_instructor("I101", "Dr. Ben Carter", "Mathematics")
    system.add_instructor("I102", "Dr. Priya Shah", "Computer Science")
    system.add_instructor("I103", "Dr. Elena Ruiz", "Physics")

    # Courses
    system.add_course("CS101", "Introduction to Programming", 3)
    system.add_course("CS201", "Data Structures", 4, ["CS101"])
    system.add_course("CS301", "Algorithms", 4, ["CS201"])
    system.add_course("MATH201", "Discrete Mathematics", 3)
    system.add_course("PHYS101", "General Physics I", 4)
    system.add_course("CS240", "Computer Organization", 3, ["CS101"])

    # Students
    system.add_student("S001", "John Kim", 18)
    system.add_student("S002", "Maya Patel", 15)
    system.add_student("S003", "Luis Gomez", 12)
    system.add_student("S004", "Nina Brooks", 18)

    # Completed records
    system.record_completed_course("S001", "CS101")
    system.record_completed_course("S001", "MATH201")
    system.record_completed_course("S002", "CS101")
    system.record_completed_course("S002", "CS201")
    system.record_completed_course("S003", "MATH201")
    system.record_completed_course("S004", "CS101")

    # Sections
    system.create_section("SEC1001", "CS201", "Fall 2026", "I100", ["Mon 09:00-10:15", "Wed 09:00-10:15"], 2)
    system.create_section("SEC1002", "CS301", "Fall 2026", "I102", ["Tue 10:30-11:45", "Thu 10:30-11:45"], 2)
    system.create_section("SEC1003", "MATH201", "Fall 2026", "I101", ["Mon 11:00-12:15", "Wed 11:00-12:15"], 3)
    system.create_section("SEC1004", "PHYS101", "Fall 2026", "I103", ["Tue 09:00-10:15", "Thu 09:00-10:15"], 2)
    system.create_section("SEC1005", "CS240", "Fall 2026", "I100", ["Mon 09:30-10:45", "Wed 09:30-10:45"], 2)

    # Some enrollments/waitlist
    system.register_student("S001", "SEC1001")
    system.register_student("S002", "SEC1002")
    system.register_student("S003", "SEC1003")
    system.register_student("S004", "SEC1001")  # fills SEC1001
    system.register_student("S002", "SEC1001")  # should waitlist because full
    system.register_student("S001", "SEC1004")
    # CS240 conflicts with SEC1001 for S004/S001 due to overlapping Monday/Wednesday
    return system


# ---------------------------
# CLI handlers
# ---------------------------

def show_menu() -> None:
    print("\n=== Course Registration and Enrollment Management System ===")
    print("1.  List all students")
    print("2.  List all courses")
    print("3.  List all instructors")
    print("4.  List all sections")
    print("5.  Add student")
    print("6.  Remove student")
    print("7.  Add course")
    print("8.  Remove course")
    print("9.  Add instructor")
    print("10. Remove instructor")
    print("11. Create section")
    print("12. Remove section")
    print("13. Register student in section")
    print("14. Drop student from section")
    print("15. Record completed course for student")
    print("16. Search courses")
    print("17. Student schedule report")
    print("18. Course roster report")
    print("19. Open sections report")
    print("20. Overloaded students report")
    print("21. Waitlisted students report")
    print("22. System summary report")
    print("23. Save to JSON")
    print("24. Load from JSON")
    print("0.  Exit")


def cli_add_student(system: RegistrationSystem) -> None:
    student_id = input("Student ID: ").strip()
    name = input("Student name: ").strip()
    max_credits = safe_int_input("Maximum credits: ")
    if max_credits is None:
        print("Invalid max credits.")
        return
    success = system.add_student(student_id, name, max_credits)
    print("Student added." if success else "Failed to add student.")


def cli_remove_student(system: RegistrationSystem) -> None:
    student_id = input("Student ID to remove: ").strip()
    success = system.remove_student(student_id)
    print("Student removed." if success else "Failed to remove student.")


def cli_add_course(system: RegistrationSystem) -> None:
    course_code = input("Course code: ").strip()
    title = input("Course title: ").strip()
    credits = safe_int_input("Credits: ")
    if credits is None:
        print("Invalid credits.")
        return
    prereq_raw = input("Prerequisites (comma-separated course codes, blank for none): ").strip()
    prereqs = [p.strip() for p in prereq_raw.split(",") if p.strip()] if prereq_raw else []
    success = system.add_course(course_code, title, credits, prereqs)
    print("Course added." if success else "Failed to add course.")


def cli_remove_course(system: RegistrationSystem) -> None:
    course_code = input("Course code to remove: ").strip()
    success = system.remove_course(course_code)
    if success:
        print("Course removed.")
    else:
        print("Failed to remove course. It may not exist, or sections may still reference it.")


def cli_add_instructor(system: RegistrationSystem) -> None:
    instructor_id = input("Instructor ID: ").strip()
    name = input("Instructor name: ").strip()
    department = input("Department: ").strip()
    success = system.add_instructor(instructor_id, name, department)
    print("Instructor added." if success else "Failed to add instructor.")


def cli_remove_instructor(system: RegistrationSystem) -> None:
    instructor_id = input("Instructor ID to remove: ").strip()
    success = system.remove_instructor(instructor_id)
    if success:
        print("Instructor removed.")
    else:
        print("Failed to remove instructor. It may not exist, or sections may still reference it.")


def cli_create_section(system: RegistrationSystem) -> None:
    section_id = input("Section ID: ").strip()
    course_code = input("Course code: ").strip()
    semester = input("Semester: ").strip()
    instructor_id = input("Instructor ID: ").strip()
    capacity = safe_int_input("Capacity: ")
    if capacity is None:
        print("Invalid capacity.")
        return

    print("Enter meeting times one per line like 'Mon 09:00-10:15'. Blank line to finish.")
    meeting_times: List[str] = []
    while True:
        line = input("Meeting time: ").strip()
        if not line:
            break
        meeting_times.append(line)

    success = system.create_section(
        section_id=section_id,
        course_code=course_code,
        semester=semester,
        instructor_id=instructor_id,
        meeting_times=meeting_times,
        capacity=capacity,
    )
    print("Section created." if success else "Failed to create section.")


def cli_remove_section(system: RegistrationSystem) -> None:
    section_id = input("Section ID to remove: ").strip()
    success = system.remove_section(section_id)
    print("Section removed." if success else "Failed to remove section.")


def cli_register_student(system: RegistrationSystem) -> None:
    student_id = input("Student ID: ").strip()
    section_id = input("Section ID: ").strip()
    success, message = system.register_student(student_id, section_id)
    print(message if success else f"Registration failed: {message}")


def cli_drop_student(system: RegistrationSystem) -> None:
    student_id = input("Student ID: ").strip()
    section_id = input("Section ID: ").strip()
    success, message = system.drop_student(student_id, section_id)
    print(message if success else f"Drop failed: {message}")


def cli_record_completed_course(system: RegistrationSystem) -> None:
    student_id = input("Student ID: ").strip()
    course_code = input("Completed course code: ").strip()
    success, message = system.record_completed_course(student_id, course_code)
    print(message if success else f"Failed: {message}")


def cli_search_courses(system: RegistrationSystem) -> None:
    query = input("Search query: ").strip()
    results = system.search_courses(query)
    if not results:
        print("No courses found.")
        return
    print("Search results:")
    for course in results:
        prereqs = ", ".join(course.prerequisites) if course.prerequisites else "none"
        print(f"  {course.course_code}: {course.title} | Credits: {course.credits} | Prereqs: {prereqs}")


def cli_student_schedule_report(system: RegistrationSystem) -> None:
    student_id = input("Student ID: ").strip()
    print(system.report_student_schedule(student_id))


def cli_course_roster_report(system: RegistrationSystem) -> None:
    section_id = input("Section ID: ").strip()
    print(system.report_course_roster(section_id))


def cli_save(system: RegistrationSystem) -> None:
    filename = input("Filename to save JSON: ").strip()
    success, message = system.save_to_file(filename)
    print(message if success else f"Save failed: {message}")


def cli_load() -> Optional[RegistrationSystem]:
    filename = input("Filename to load JSON: ").strip()
    system, message = RegistrationSystem.load_from_file(filename)
    print(message)
    return system


def run_cli(system: RegistrationSystem) -> None:
    while True:
        show_menu()
        choice = input("Select an option: ").strip()

        if choice == "1":
            system.print_all_students()
        elif choice == "2":
            system.print_all_courses()
        elif choice == "3":
            system.print_all_instructors()
        elif choice == "4":
            system.print_all_sections()
        elif choice == "5":
            cli_add_student(system)
        elif choice == "6":
            cli_remove_student(system)
        elif choice == "7":
            cli_add_course(system)
        elif choice == "8":
            cli_remove_course(system)
        elif choice == "9":
            cli_add_instructor(system)
        elif choice == "10":
            cli_remove_instructor(system)
        elif choice == "11":
            cli_create_section(system)
        elif choice == "12":
            cli_remove_section(system)
        elif choice == "13":
            cli_register_student(system)
        elif choice == "14":
            cli_drop_student(system)
        elif choice == "15":
            cli_record_completed_course(system)
        elif choice == "16":
            cli_search_courses(system)
        elif choice == "17":
            cli_student_schedule_report(system)
        elif choice == "18":
            cli_course_roster_report(system)
        elif choice == "19":
            print(system.report_open_sections())
        elif choice == "20":
            print(system.report_overloaded_students())
        elif choice == "21":
            print(system.report_waitlisted_students())
        elif choice == "22":
            print(system.report_system_summary())
        elif choice == "23":
            cli_save(system)
        elif choice == "24":
            loaded = cli_load()
            if loaded is not None:
                system.students = loaded.students
                system.courses = loaded.courses
                system.instructors = loaded.instructors
                system.sections = loaded.sections
                system.enrollment_history = loaded.enrollment_history
        elif choice == "0":
            print("Exiting.")
            break
        else:
            print("Invalid choice. Please select a valid menu option.")


# ---------------------------
# Main block
# ---------------------------

if __name__ == "__main__":
    demo_system = build_demo_system()
    print("Loaded demo Course Registration and Enrollment Management System.")
    print(demo_system.report_system_summary())
    run_cli(demo_system)