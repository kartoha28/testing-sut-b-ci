import json
import pytest

from courses.http_enrollment_policy import EnrollmentPolicyError
from courses.models import (
    Student,
    Course,
    Enrollment,
    EnrollmentRequest,
    EnrollmentStatus,
)
from courses.service import EnrollmentRejectedError


# ==============================================================================
# 1. Repository ↔ Database Integration Tests (_repositoryState)
# ==============================================================================

def test_student_repository_create_and_find_repositoryState(student_repo):
    """Перевірка створення та повторного читання студента з PostgreSQL через репозиторій."""
    student_to_create = Student(id=0, code="STU-001", age=22, entry_score=90, regular=True)
    created = student_repo.create(student_to_create)

    assert created.id > 0
    assert created.code == "STU-001"
    assert created.age == 22
    assert created.entry_score == 90
    assert created.regular is True

    # Читання з БД за згенерованим id
    found = student_repo.find_by_id(created.id)
    assert found is not None
    assert found == created


def test_course_repository_create_and_find_repositoryState(course_repo):
    """Перевірка збереження курсу в PostgreSQL та його отримання."""
    course_to_create = Course(id=0, code="CRS-101", price=250000, capacity=10, level=2)
    created = course_repo.create(course_to_create)

    assert created.id > 0
    assert created.code == "CRS-101"
    assert created.price == 250000
    assert created.capacity == 10
    assert created.level == 2

    found = course_repo.find_by_id(created.id)
    assert found is not None
    assert found == created


def test_student_repository_update_and_delete_repositoryState(student_repo):
    """Перевірка оновлення та видалення запису студента в реальній PostgreSQL."""
    student = student_repo.create(Student(id=0, code="STU-UPD", age=20, entry_score=70, regular=False))

    # Оновлення
    updated_student = Student(id=student.id, code="STU-UPD2", age=21, entry_score=80, regular=True)
    student_repo.update(updated_student)

    found_after_update = student_repo.find_by_id(student.id)
    assert found_after_update is not None
    assert found_after_update.code == "STU-UPD2"
    assert found_after_update.age == 21
    assert found_after_update.entry_score == 80
    assert found_after_update.regular is True

    # Видалення
    student_repo.delete(student.id)
    assert student_repo.find_by_id(student.id) is None


def test_enrollment_repository_crud_repositoryState(student_repo, course_repo, enrollment_repo):
    """Перевірка збереження, пошуку, оновлення статусу та підрахунку заявок у PostgreSQL."""
    student = student_repo.create(Student(id=0, code="STU-ENR", age=25, entry_score=85, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-ENR", price=150000, capacity=5, level=1))

    # Створення заявки напряму через репозиторій
    enrollment = Enrollment(
        id=0,
        reference="REF-REPO-1",
        student_id=student.id,
        course_id=course.id,
        total=150000,
        prepaid=150000,
        refund=0,
        status=EnrollmentStatus.ENROLLED,
    )
    saved = enrollment_repo.create(enrollment)
    assert saved.id > 0

    # Перевірка наявності та підрахунку зайнятих місць
    assert enrollment_repo.has_enrollment(student.id, course.id) is True
    assert enrollment_repo.count_occupied(course.id) == 1

    # Пошук за статусом
    enrolled_list = enrollment_repo.find_enrollments(course.id, EnrollmentStatus.ENROLLED)
    assert len(enrolled_list) == 1
    assert enrolled_list[0].reference == "REF-REPO-1"

    # Оновлення статусу на Completed
    enrollment_repo.update_status(saved.id, EnrollmentStatus.COMPLETED, 0)
    updated = enrollment_repo.find_by_id(saved.id)
    assert updated is not None
    assert updated.status == EnrollmentStatus.COMPLETED

    # Видалення
    enrollment_repo.delete(saved.id)
    assert enrollment_repo.find_by_id(saved.id) is None
    assert enrollment_repo.count_occupied(course.id) == 0


# ==============================================================================
# 2. Service → Repository → Database Business Scenarios (_serviceState)
# ==============================================================================

def test_service_enroll_success_serviceState(student_repo, course_repo, service, wiremock):
    """
    Позитивний сценарій: успішне зарахування слухача через Service з HTTP-запитом до WireMock.
    Перевіряється відповідь сервісу та параметри виконаного HTTP-запиту.
    """
    student = student_repo.create(Student(id=0, code="STU-SRV-POS", age=19, entry_score=95, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-SRV-POS", price=120000, capacity=2, level=1))

    request = EnrollmentRequest(reference="REF-SRV-POS", student_id=student.id, course_id=course.id)
    result = service.enroll(request)

    assert result.id > 0
    assert result.status == EnrollmentStatus.ENROLLED
    assert result.total == 120000
    assert result.prepaid == 120000
    assert result.refund == 0

    # Перевірка HTTP-взаємодії з WireMock
    requests = wiremock.get_requests_for("/enrollment-policy", "POST")
    assert len(requests) == 1
    body = json.loads(requests[0]["body"])
    assert body == {"studentId": student.id, "courseId": course.id}


def test_service_enroll_capacity_exceeded_serviceState(student_repo, course_repo, enrollment_repo, service, wiremock):
    """
    Локальна бізнес-відмова (3.8): відмова при вичерпаній місткості курсу.
    Демонструє різницю:
    - для успішного зарахування student1: HTTP request = 1
    - для локально відхиленого student2: новий HTTP request НЕ надсилається (HTTP request = 0).
    """
    student1 = student_repo.create(Student(id=0, code="STU-CAP-1", age=20, entry_score=80, regular=False))
    student2 = student_repo.create(Student(id=0, code="STU-CAP-2", age=22, entry_score=85, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-CAP-1", price=100000, capacity=1, level=1))

    # Перший студент успішно зараховується (надсилає 1 HTTP-запит)
    req1 = EnrollmentRequest(reference="REF-CAP-1", student_id=student1.id, course_id=course.id)
    service.enroll(req1)
    assert enrollment_repo.count_occupied(course.id) == 1
    assert len(wiremock.get_requests_for("/enrollment-policy")) == 1

    # Другий студент намагається записатися на переповнений курс -> локальна відмова
    req2 = EnrollmentRequest(reference="REF-CAP-2", student_id=student2.id, course_id=course.id)
    with pytest.raises(EnrollmentRejectedError, match="Вільних місць немає"):
        service.enroll(req2)

    # ГЛИБОКА ПЕРЕВІРКА БД: небажаний запис НЕ створено
    assert enrollment_repo.has_enrollment(student2.id, course.id) is False
    assert enrollment_repo.count_occupied(course.id) == 1
    enrollments_in_db = enrollment_repo.find_enrollments(course.id, EnrollmentStatus.ENROLLED)
    assert len(enrollments_in_db) == 1
    assert enrollments_in_db[0].student_id == student1.id

    # ПЕРЕВІРКА HTTP: для student2 HTTP-запит НЕ виконувався (загальна кількість залишилася 1)
    assert len(wiremock.get_requests_for("/enrollment-policy")) == 1


def test_service_enroll_policy_disallowed_serviceState(student_repo, course_repo, enrollment_repo, service, wiremock):
    """
    Зовнішня бізнес-відмова (3.6): WireMock повернув allowed=false.
    Демонструє:
    - HTTP request виконано (HTTP request = 1) з правильним тілом;
    - SUT правильно обробляє відповідь (EnrollmentRejectedError);
    - Небажаний запис у PostgreSQL НЕ створено.
    """
    student = student_repo.create(Student(id=0, code="STU-POL-DENY", age=23, entry_score=88, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-POL-DENY", price=150000, capacity=5, level=1))

    # Налаштування WireMock: 200 OK з {"allowed": false}
    wiremock.stub_allowed(False)

    req = EnrollmentRequest(reference="REF-POL-DENY", student_id=student.id, course_id=course.id)
    with pytest.raises(EnrollmentRejectedError, match="Зарахування не дозволено"):
        service.enroll(req)

    # ГЛИБОКА ПЕРЕВІРКА БД: заявка не з'явилась у PostgreSQL
    assert enrollment_repo.has_enrollment(student.id, course.id) is False
    assert enrollment_repo.count_occupied(course.id) == 0
    assert len(enrollment_repo.find_enrollments(course.id, EnrollmentStatus.ENROLLED)) == 0

    # ПЕРЕВІРКА HTTP: запит був виконаний
    requests = wiremock.get_requests_for("/enrollment-policy", "POST")
    assert len(requests) == 1
    body = json.loads(requests[0]["body"])
    assert body == {"studentId": student.id, "courseId": course.id}


def test_service_enroll_policy_service_unavailable_serviceState(student_repo, course_repo, enrollment_repo, service, wiremock):
    """
    Недоступність зовнішнього сервісу (3.7): WireMock повертає HTTP 503 Service Unavailable.
    Перевіряється:
    - SUT перериває операцію винятком EnrollmentPolicyError;
    - Небажаний запис у PostgreSQL НЕ створено;
    - HTTP-запит до WireMock був виконаний.
    """
    student = student_repo.create(Student(id=0, code="STU-503", age=25, entry_score=80, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-503", price=100000, capacity=5, level=1))

    # Налаштування WireMock: 503 Service Unavailable
    wiremock.stub_error(status=503, body="Service Unavailable")

    req = EnrollmentRequest(reference="REF-503", student_id=student.id, course_id=course.id)
    with pytest.raises(EnrollmentPolicyError, match="Помилка HTTP-політики: 503"):
        service.enroll(req)

    # ГЛИБОКА ПЕРЕВІРКА БД: стан БД не змінено
    assert enrollment_repo.has_enrollment(student.id, course.id) is False
    assert enrollment_repo.count_occupied(course.id) == 0

    # ПЕРЕВІРКА HTTP: запит дійсно надсилався до WireMock
    assert len(wiremock.get_requests_for("/enrollment-policy", "POST")) == 1


def test_service_enroll_duplicate_rejected_serviceState(student_repo, course_repo, enrollment_repo, service, wiremock):
    """
    Локальна бізнес-відмова (3.8): спроба повторного зарахування того самого слухача на курс.
    Перевіряється відхилення на рівні SUT без надсилання повторного HTTP-запиту.
    """
    student = student_repo.create(Student(id=0, code="STU-DUP", age=21, entry_score=90, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-DUP", price=180000, capacity=5, level=1))

    # Перше зарахування успішне (1 HTTP-запит)
    service.enroll(EnrollmentRequest(reference="REF-DUP-1", student_id=student.id, course_id=course.id))
    assert len(wiremock.get_requests_for("/enrollment-policy")) == 1

    # Повторне зарахування відхиляється локально
    with pytest.raises(EnrollmentRejectedError, match="Слухача вже зараховано"):
        service.enroll(EnrollmentRequest(reference="REF-DUP-2", student_id=student.id, course_id=course.id))

    # ГЛИБОКА ПЕРЕВІРКА БД: у БД залишається лише один запис
    all_enrollments = enrollment_repo.find_enrollments(course.id, EnrollmentStatus.ENROLLED)
    assert len(all_enrollments) == 1
    assert all_enrollments[0].reference == "REF-DUP-1"

    # ПЕРЕВІРКА HTTP: повторний HTTP-запит НЕ виконувався
    assert len(wiremock.get_requests_for("/enrollment-policy")) == 1


def test_service_transition_invalid_serviceState(student_repo, course_repo, enrollment_repo, service):
    """Негативний сценарій: заборона повторної зміни статусу завершеної заявки."""
    student = student_repo.create(Student(id=0, code="STU-TRN", age=24, entry_score=75, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-TRN", price=100000, capacity=5, level=1))

    enrollment = service.enroll(EnrollmentRequest(reference="REF-TRN", student_id=student.id, course_id=course.id))
    service.complete(enrollment.id)

    # Повторний перехід (скасування вже завершеного) заборонений
    with pytest.raises(EnrollmentRejectedError, match="Зміна статусу заборонена"):
        service.cancel(enrollment.id)

    # ГЛИБОКА ПЕРЕВІРКА БД: стан заявки не пошкоджено, залишається Completed
    persisted = enrollment_repo.find_by_id(enrollment.id)
    assert persisted is not None
    assert persisted.status == EnrollmentStatus.COMPLETED


# ==============================================================================
# 3. Persisted State Verification (_persistedState)
# ==============================================================================

def test_service_enroll_persistedState(student_repo, course_repo, enrollment_repo, service, wiremock):
    """Перевірка фактичного стану БД через повторне звернення до Repository після enroll."""
    student = student_repo.create(Student(id=0, code="STU-PERS", age=20, entry_score=90, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-PERS", price=140000, capacity=3, level=1))

    service_result = service.enroll(EnrollmentRequest(reference="REF-PERS-1", student_id=student.id, course_id=course.id))

    # Повторне читання з реальної PostgreSQL
    db_record = enrollment_repo.find_by_id(service_result.id)
    assert db_record is not None
    assert db_record.id == service_result.id
    assert db_record.reference == "REF-PERS-1"
    assert db_record.student_id == student.id
    assert db_record.course_id == course.id
    assert db_record.status == EnrollmentStatus.ENROLLED
    assert db_record.total == 140000
    assert db_record.prepaid == 140000
    assert db_record.refund == 0

    # Перевірка HTTP
    requests = wiremock.get_requests_for("/enrollment-policy")
    assert len(requests) == 1
    assert json.loads(requests[0]["body"]) == {"studentId": student.id, "courseId": course.id}


@pytest.mark.parametrize(
    "regular, price, expected_discount_pct, expected_total",
    [
        (False, 100000, 0, 100000),   # 0%: не regular, ціна < 2000 грн (1000 грн)
        (True,  100000, 5, 95000),    # 5%: regular, ціна < 2000 грн
        (False, 200000, 10, 180000),  # 10%: не regular, ціна >= 2000 грн (2000 грн)
        (True,  200000, 15, 170000),  # 15%: regular, ціна >= 2000 грн
    ],
)
def test_service_personal_rule_combined_discount_persistedState(
    student_repo, course_repo, enrollment_repo, service, regular, price, expected_discount_pct, expected_total
):
    """
    Персональне бізнес-правило (Варіант 08):
    5% постійному слухачу + 10% при ціні від 2000 грн (200 000 коп.).
    Відсотки додаються: 0%, 5%, 10%, 15%.
    Перевіряється збережений фактичний стан `total` та `prepaid` у PostgreSQL.
    """
    student = student_repo.create(Student(id=0, code=f"STU-DISC-{regular}-{price}", age=22, entry_score=85, regular=regular))
    course = course_repo.create(Course(id=0, code=f"CRS-DISC-{regular}-{price}", price=price, capacity=10, level=1))

    ref = f"REF-DISC-{regular}-{price}"
    created = service.enroll(EnrollmentRequest(reference=ref, student_id=student.id, course_id=course.id))

    # Перевірка фактичного стану в PostgreSQL
    saved_enrollment = enrollment_repo.find_by_id(created.id)
    assert saved_enrollment is not None
    assert saved_enrollment.total == expected_total
    assert saved_enrollment.prepaid == expected_total
    assert saved_enrollment.refund == 0


def test_service_complete_lifecycle_persistedState(student_repo, course_repo, enrollment_repo, service, wiremock):
    """
    Перевірка фактичного стану PostgreSQL при завершенні курсу (Enrolled -> Completed).
    Завершення заявки НЕ викликає зовнішній HTTP-сервіс.
    """
    student = student_repo.create(Student(id=0, code="STU-CMP", age=30, entry_score=92, regular=False))
    course = course_repo.create(Course(id=0, code="CRS-CMP", price=160000, capacity=5, level=1))

    enrollment = service.enroll(EnrollmentRequest(reference="REF-CMP", student_id=student.id, course_id=course.id))
    wiremock.reset()  # Скидаємо журнал після зарахування

    # Виконання complete
    completed = service.complete(enrollment.id)
    assert completed.status == EnrollmentStatus.COMPLETED

    # Перевірка фактичного стану в PostgreSQL
    persisted = enrollment_repo.find_by_id(enrollment.id)
    assert persisted is not None
    assert persisted.status == EnrollmentStatus.COMPLETED
    assert persisted.total == 160000
    assert persisted.prepaid == 160000
    assert persisted.refund == 0
    assert enrollment_repo.count_occupied(course.id) == 1

    # Завершення не робить HTTP-запитів до WireMock
    assert len(wiremock.get_requests()) == 0


def test_service_cancel_lifecycle_persistedState(student_repo, course_repo, enrollment_repo, service, wiremock):
    """
    Перевірка фактичного стану PostgreSQL при скасуванні заявки (Enrolled -> Cancelled).
    За правилом варіанта 08 повертається 100% передоплати (refund = prepaid).
    Скасування заявки НЕ викликає зовнішній HTTP-сервіс.
    """
    student = student_repo.create(Student(id=0, code="STU-CNC", age=28, entry_score=80, regular=True))
    course = course_repo.create(Course(id=0, code="CRS-CNC", price=250000, capacity=5, level=1))

    # 15% знижка: 250000 - 37500 = 212500
    enrollment = service.enroll(EnrollmentRequest(reference="REF-CNC", student_id=student.id, course_id=course.id))
    assert enrollment.prepaid == 212500
    wiremock.reset()  # Скидаємо журнал після зарахування

    # Скасування заявки за 5 днів до початку
    cancelled = service.cancel(enrollment.id, days_before_start=5)
    assert cancelled.status == EnrollmentStatus.CANCELLED
    assert cancelled.refund == 212500

    # Перевірка фактичного стану в PostgreSQL
    persisted = enrollment_repo.find_by_id(enrollment.id)
    assert persisted is not None
    assert persisted.status == EnrollmentStatus.CANCELLED
    assert persisted.total == 212500
    assert persisted.prepaid == 212500
    assert persisted.refund == 212500
    # Скасована заявка звільняє місце!
    assert enrollment_repo.count_occupied(course.id) == 0

    # Скасування не робить HTTP-запитів до WireMock
    assert len(wiremock.get_requests()) == 0
