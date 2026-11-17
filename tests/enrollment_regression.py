import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from courses.models import Student, Course, EnrollmentRequest, EnrollmentStatus as S
from courses.repositories import PostgresStudentRepository, PostgresCourseRepository, PostgresEnrollmentRepository
from courses.service import EnrollmentService, EnrollmentRejectedError


class Policy:
    def is_allowed(self, student, course):
        return True


@pytest.fixture(scope="module")
def sut():
    with PostgresContainer("postgres:17.6-alpine") as postgres:
        with psycopg.connect(host=postgres.get_container_host_ip(), port=postgres.get_exposed_port(5432),
                             user=postgres.username, password=postgres.password,
                             dbname=postgres.dbname, autocommit=True) as db:
            migration = Path(__file__).resolve().parents[1] / "migrations/V1__create_tables.sql"
            db.execute(migration.read_text(encoding="utf-8"))
            students = PostgresStudentRepository(db)
            courses = PostgresCourseRepository(db)
            enrollments = PostgresEnrollmentRepository(db)
            service = EnrollmentService(students, courses, enrollments, Policy())
            yield db, students, courses, enrollments, service


def student(sut):
    return sut[1].create(Student(0, str(uuid4()), 20, 90, False))


def course(sut):
    return sut[2].create(Course(0, str(uuid4()), 100000, 10, 1))


def request(person, training):
    return EnrollmentRequest(str(uuid4()), person.id, training.id, False)


@pytest.mark.smoke
def test_create_enrollment(sut):
    saved = sut[4].enroll(request(student(sut), course(sut)))
    assert saved.status == S.ENROLLED
    assert sut[3].find_by_id(saved.id) == saved


@pytest.mark.smoke
def test_cancel_enrollment(sut):
    # Виправлення Order Dependency: тест створює власне зарахування, а не залежить від попереднього
    saved = sut[4].enroll(request(student(sut), course(sut)))
    cancelled = sut[4].cancel(saved.id, 7)
    assert cancelled.status == S.CANCELLED
    assert cancelled.refund == 100000
    assert sut[3].find_by_id(saved.id) == cancelled


def test_student_age(sut):
    # Виправлення Shared State: унікальний code <= 40 символів для уникнення порушення UNIQUE(code)
    saved = sut[1].create(Student(0, f"STU-AGE-{uuid4().hex[:12]}", 20, 90, False))
    assert sut[1].find_by_id(saved.id).age == 20


def test_student_score(sut):
    # Виправлення Shared State: унікальний code замість статичного "REGRESSION-STUDENT"
    saved = sut[1].create(Student(0, f"STU-SCORE-{uuid4().hex[:12]}", 25, 85, True))
    assert sut[1].find_by_id(saved.id).entry_score == 85


def test_enrollment_after_policy_check(sut):
    class DelayedPolicy:
        def is_allowed(self, person, training):
            time.sleep(float(os.getenv("REGRESSION_POLICY_DELAY_MS", "200")) / 1000)
            return True

    training = course(sut)
    data = request(student(sut), training)
    service = EnrollmentService(sut[1], sut[2], sut[3], DelayedPolicy())
    with ThreadPoolExecutor(max_workers=1) as executor:
        operation = executor.submit(service.enroll, data)
        # Виправлення Fixed Wait: Condition-based wait (опитування БД до появи запису з таймаутом)
        timeout = 3.0
        interval = 0.02
        deadline = time.time() + timeout
        saved = []
        while time.time() < deadline:
            saved = sut[3].find_enrollments(training.id, S.ENROLLED)
            if len(saved) == 1:
                break
            time.sleep(interval)

        operation.result(timeout=1.0)
        assert len(saved) == 1
        assert saved[0].reference == data.reference
        assert saved[0].total == 100000


def test_enrollment_selection(sut):
    # Виправлення Ordering Flaw: явне сортування ORDER BY reference гарантує детермінований результат
    training = course(sut)
    prefix = str(uuid4())[:8]
    references = [prefix + "-A", prefix + "-B"]
    fixture_order = list(reversed(references)) if os.getenv("REGRESSION_REVERSE_FIXTURE") == "true" else references
    for reference in fixture_order:
        sut[4].enroll(EnrollmentRequest(reference, student(sut).id, training.id, False))
    actual = [row[0] for row in sut[0].execute("SELECT reference FROM enrollments WHERE course_id=%s ORDER BY reference", (training.id,))]
    assert actual == sorted(references)


@pytest.mark.smoke
def test_completion(sut):
    saved = sut[4].enroll(request(student(sut), course(sut)))
    completed = sut[4].complete(saved.id)
    assert completed.status == S.COMPLETED
    assert sut[3].find_by_id(saved.id) == completed


def test_duplicate_enrollment(sut):
    person, training = student(sut), course(sut)
    saved = sut[4].enroll(request(person, training))
    with pytest.raises(EnrollmentRejectedError):
        sut[4].enroll(request(person, training))
    assert sut[3].find_by_id(saved.id) == saved
    assert sut[3].count_occupied(training.id) == 1


def test_policy_rejection(sut):
    class DeniedPolicy:
        def is_allowed(self, person, training):
            return False

    training = course(sut)
    service = EnrollmentService(sut[1], sut[2], sut[3], DeniedPolicy())
    with pytest.raises(EnrollmentRejectedError):
        service.enroll(request(student(sut), training))
    assert sut[3].find_enrollments(training.id, S.ENROLLED) == []


def test_repeated_cancellation(sut):
    saved = sut[4].enroll(request(student(sut), course(sut)))
    cancelled = sut[4].cancel(saved.id, 7)
    with pytest.raises(EnrollmentRejectedError):
        sut[4].cancel(saved.id, 7)
    assert sut[3].find_by_id(saved.id) == cancelled
