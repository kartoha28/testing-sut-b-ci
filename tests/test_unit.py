from dataclasses import replace
import pytest

from courses.models import Student, Course, EnrollmentRequest, EnrollmentStatus
from courses.service import EnrollmentService, EnrollmentRejectedError, ResourceNotFoundError

pytestmark = pytest.mark.unit


class FakeStudentRepo:
    def __init__(self, items=None):
        self.items = dict(items or {})

    def find_by_id(self, student_id):
        return self.items.get(student_id)


class FakeCourseRepo:
    def __init__(self, items=None):
        self.items = dict(items or {})

    def find_by_id(self, course_id):
        return self.items.get(course_id)


class FakeEnrollmentRepo:
    def __init__(self):
        self.items = {}
        self._seq = 1

    def create(self, enrollment):
        saved = replace(enrollment, id=self._seq)
        self.items[self._seq] = saved
        self._seq += 1
        return saved

    def find_by_id(self, enrollment_id):
        return self.items.get(enrollment_id)

    def has_enrollment(self, student_id, course_id):
        return any(
            e.student_id == student_id
            and e.course_id == course_id
            and e.status in (EnrollmentStatus.ENROLLED, EnrollmentStatus.COMPLETED)
            for e in self.items.values()
        )

    def count_occupied(self, course_id):
        return sum(
            1
            for e in self.items.values()
            if e.course_id == course_id and e.status in (EnrollmentStatus.ENROLLED, EnrollmentStatus.COMPLETED)
        )

    def update_status(self, enrollment_id, next_status, refund):
        item = self.items[enrollment_id]
        self.items[enrollment_id] = replace(item, status=next_status, refund=refund)


class StubPolicy:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = 0

    def is_allowed(self, student, course):
        self.calls += 1
        return self.allowed


def make_service(students=None, courses=None, allowed=True):
    s_repo = FakeStudentRepo(students)
    c_repo = FakeCourseRepo(courses)
    e_repo = FakeEnrollmentRepo()
    policy = StubPolicy(allowed=allowed)
    return EnrollmentService(s_repo, c_repo, e_repo, policy), e_repo, policy


@pytest.mark.parametrize(
    "price, regular, coupon_valid, expected",
    [
        (100000, False, False, 100000),  # 0% знижки
        (100000, True, False, 95000),    # 5% постійному слухачу
        (200000, False, False, 180000),  # 10% від 2000 грн (200000 коп.)
        (200000, True, True, 170000),    # 15% комбінована (5% + 10%), coupon_valid не змінює суму
    ],
)
def test_calculate_total_personal_rule(price, regular, coupon_valid, expected):
    service, _, _ = make_service()
    assert service.calculate_total(price, regular=regular, coupon_valid=coupon_valid) == expected


def test_calculate_total_invalid_arguments():
    service, _, _ = make_service()
    with pytest.raises(ValueError):
        service.calculate_total(50, regular=False)
    with pytest.raises(ValueError):
        service.calculate_total(10000, regular="yes")


def test_calculate_refund_returns_full_prepaid():
    service, _, _ = make_service()
    assert service.calculate_refund(170000, 0) == 170000
    assert service.calculate_refund(170000, 30) == 170000


def test_enroll_success_unit_with_fake_repos():
    student = Student(1, "STU-U1", 21, 88, True)
    course = Course(10, "CRS-U1", 200000, 5, 2)
    service, e_repo, policy = make_service({1: student}, {10: course}, allowed=True)

    saved = service.enroll(EnrollmentRequest("REF-U1", 1, 10, coupon_valid=False))

    assert saved.id == 1
    assert saved.status == EnrollmentStatus.ENROLLED
    assert saved.total == 170000
    assert saved.prepaid == 170000
    assert saved.refund == 0
    assert policy.calls == 1
    assert e_repo.count_occupied(10) == 1


def test_enroll_rejects_missing_student_without_calling_policy():
    course = Course(10, "CRS-U1", 100000, 5, 1)
    service, _, policy = make_service({}, {10: course}, allowed=True)

    with pytest.raises(ResourceNotFoundError):
        service.enroll(EnrollmentRequest("REF-MISS", 999, 10))
    assert policy.calls == 0


def test_enroll_rejects_when_policy_denies():
    student = Student(1, "STU-U2", 22, 80, False)
    course = Course(10, "CRS-U2", 100000, 5, 1)
    service, e_repo, policy = make_service({1: student}, {10: course}, allowed=False)

    with pytest.raises(EnrollmentRejectedError):
        service.enroll(EnrollmentRequest("REF-DENY", 1, 10))
    assert policy.calls == 1
    assert e_repo.count_occupied(10) == 0


def test_complete_and_prevent_double_transition():
    student = Student(1, "STU-U3", 25, 90, False)
    course = Course(10, "CRS-U3", 100000, 5, 1)
    service, _, _ = make_service({1: student}, {10: course}, allowed=True)

    created = service.enroll(EnrollmentRequest("REF-LIFE", 1, 10))
    completed = service.complete(created.id)
    assert completed.status == EnrollmentStatus.COMPLETED

    with pytest.raises(EnrollmentRejectedError):
        service.cancel(created.id, days_before_start=5)
