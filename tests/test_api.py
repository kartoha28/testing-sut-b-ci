import pytest


# ==============================================================================
# 1. POST — Створення ресурсів (Статус 201, Location header, перевірка полів)
# ==============================================================================

def test_post_create_student_and_course_201(client):
    """
    Завдання 1: POST створення студента та курсу.
    Перевірка статусу 201, заголовка Location та отримання id.
    """
    # 1. Створення студента
    student_payload = {
        "code": "STU-API-01",
        "age": 21,
        "entry_score": 88,
        "regular": True,
    }
    resp_student = client.post("/students", json=student_payload)
    assert resp_student.status_code == 201
    assert "Location" in resp_student.headers
    student_data = resp_student.json()
    assert student_data["id"] > 0
    assert resp_student.headers["Location"] == f"/students/{student_data['id']}"
    assert student_data["code"] == "STU-API-01"
    assert student_data["age"] == 21
    assert student_data["entry_score"] == 88
    assert student_data["regular"] is True

    # 2. Створення курсу
    course_payload = {
        "code": "CRS-API-01",
        "price": 250000,
        "capacity": 15,
        "level": 2,
    }
    resp_course = client.post("/courses", json=course_payload)
    assert resp_course.status_code == 201
    assert "Location" in resp_course.headers
    course_data = resp_course.json()
    assert course_data["id"] > 0
    assert resp_course.headers["Location"] == f"/courses/{course_data['id']}"
    assert course_data["code"] == "CRS-API-01"
    assert course_data["price"] == 250000
    assert course_data["capacity"] == 15
    assert course_data["level"] == 2


def test_post_create_enrollment_201(client):
    """
    Завдання 1: POST створення заявки на курс.
    Перевірка статусу 201, Location та початкового стану (Enrolled, total, prepaid, refund=0).
    """
    s_id = client.post("/students", json={"code": "STU-ENR-01", "age": 20, "entry_score": 90, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-ENR-01", "price": 120000, "capacity": 5, "level": 1}).json()["id"]

    enrollment_payload = {
        "reference": "REF-API-001",
        "student_id": s_id,
        "course_id": c_id,
        "coupon_valid": False,
    }
    resp = client.post("/enrollments", json=enrollment_payload)
    assert resp.status_code == 201
    assert "Location" in resp.headers

    data = resp.json()
    assert data["id"] > 0
    assert resp.headers["Location"] == f"/enrollments/{data['id']}"
    assert data["reference"] == "REF-API-001"
    assert data["student_id"] == s_id
    assert data["course_id"] == c_id
    assert data["status"] == "Enrolled"
    assert data["total"] == 120000
    assert data["prepaid"] == 120000
    assert data["refund"] == 0


# ==============================================================================
# 2. GET за id (Статус 200, дані відповідають створеному ресурсу)
# ==============================================================================

def test_get_resource_by_id_200(client):
    """
    Завдання 2: GET за id повертає 200 OK і збережені дані відповідають створеним.
    """
    s_id = client.post("/students", json={"code": "STU-GET-01", "age": 22, "entry_score": 75, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-GET-01", "price": 100000, "capacity": 10, "level": 1}).json()["id"]
    e_id = client.post("/enrollments", json={"reference": "REF-GET-001", "student_id": s_id, "course_id": c_id}).json()["id"]

    # Читання заявки
    resp_enr = client.get(f"/enrollments/{e_id}")
    assert resp_enr.status_code == 200
    enr_data = resp_enr.json()
    assert enr_data["id"] == e_id
    assert enr_data["reference"] == "REF-GET-001"
    assert enr_data["student_id"] == s_id
    assert enr_data["course_id"] == c_id
    assert enr_data["status"] == "Enrolled"

    # Читання студента
    resp_stu = client.get(f"/students/{s_id}")
    assert resp_stu.status_code == 200
    assert resp_stu.json()["code"] == "STU-GET-01"

    # Читання курсу
    resp_crs = client.get(f"/courses/{c_id}")
    assert resp_crs.status_code == 200
    assert resp_crs.json()["code"] == "CRS-GET-01"


# ==============================================================================
# 3. GET неіснуючого ресурсу (Статус 404, перевірка code і message)
# ==============================================================================

def test_get_nonexistent_resource_404(client):
    """
    Завдання 3: GET неіснуючого ресурсу повертає 404 Not Found із контрактом помилки.
    """
    # 1. Неіснуюча заявка
    resp_enr = client.get("/enrollments/999999")
    assert resp_enr.status_code == 404
    err_enr = resp_enr.json()
    assert err_enr["code"] == "NOT_FOUND"
    assert err_enr["message"] == "Заявку не знайдено"

    # 2. Неіснуючий курс
    resp_crs = client.get("/courses/888888")
    assert resp_crs.status_code == 404
    err_crs = resp_crs.json()
    assert err_crs["code"] == "NOT_FOUND"
    assert err_crs["message"] == "Курс не знайдено"

    # 3. Неіснуючий слухач
    resp_stu = client.get("/students/777777")
    assert resp_stu.status_code == 404
    err_stu = resp_stu.json()
    assert err_stu["code"] == "NOT_FOUND"
    assert err_stu["message"] == "Слухача не знайдено"


# ==============================================================================
# 4. Action endpoint: complete та cancel (Статус 200, коректний новий стан)
# ==============================================================================

def test_action_complete_enrollment_200(client):
    """
    Завдання 4: Action endpoint complete переводить заявку в статус Completed.
    """
    s_id = client.post("/students", json={"code": "STU-ACT-01", "age": 25, "entry_score": 80, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-ACT-01", "price": 140000, "capacity": 5, "level": 1}).json()["id"]
    e_id = client.post("/enrollments", json={"reference": "REF-ACT-CMP", "student_id": s_id, "course_id": c_id}).json()["id"]

    # Дія complete
    resp_complete = client.post(f"/enrollments/{e_id}/complete")
    assert resp_complete.status_code == 200
    assert resp_complete.json()["status"] == "Completed"

    # Перевірка нового стану через GET
    resp_get = client.get(f"/enrollments/{e_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["status"] == "Completed"
    assert resp_get.json()["total"] == 140000
    assert resp_get.json()["refund"] == 0


def test_action_cancel_enrollment_200(client):
    """
    Завдання 4: Action endpoint cancel переводить заявку в статус Cancelled та повертає кошти.
    """
    s_id = client.post("/students", json={"code": "STU-ACT-02", "age": 23, "entry_score": 85, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-ACT-02", "price": 180000, "capacity": 5, "level": 1}).json()["id"]
    e_id = client.post("/enrollments", json={"reference": "REF-ACT-CNC", "student_id": s_id, "course_id": c_id}).json()["id"]

    # Дія cancel
    resp_cancel = client.post(f"/enrollments/{e_id}/cancel", json={"days_before_start": 5})
    assert resp_cancel.status_code == 200
    cancel_data = resp_cancel.json()
    assert cancel_data["status"] == "Cancelled"
    assert cancel_data["refund"] == 180000  # 100% повернення для варіанта 08

    # Перевірка нового стану через GET
    resp_get = client.get(f"/enrollments/{e_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["status"] == "Cancelled"
    assert resp_get.json()["refund"] == 180000


# ==============================================================================
# 5. Повторна або заборонена дія (Статус 409, перевірка error response)
# ==============================================================================

def test_forbidden_action_on_completed_enrollment_409(client):
    """
    Завдання 5: Спроба скасувати вже завершену заявку повертає статус 409 Conflict.
    """
    s_id = client.post("/students", json={"code": "STU-FORB-01", "age": 24, "entry_score": 75, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-FORB-01", "price": 100000, "capacity": 5, "level": 1}).json()["id"]
    e_id = client.post("/enrollments", json={"reference": "REF-FORB-01", "student_id": s_id, "course_id": c_id}).json()["id"]

    # Завершення заявки
    assert client.post(f"/enrollments/{e_id}/complete").status_code == 200

    # Заборонена дія: скасування вже завершеної заявки
    resp_bad_cancel = client.post(f"/enrollments/{e_id}/cancel", json={"days_before_start": 3})
    assert resp_bad_cancel.status_code == 409
    err = resp_bad_cancel.json()
    assert err["code"] == "ENROLLMENT_CONFLICT"
    assert err["message"] == "Зміна статусу заборонена"

    # Повторне завершення також заборонене
    resp_bad_complete = client.post(f"/enrollments/{e_id}/complete")
    assert resp_bad_complete.status_code == 409
    assert resp_bad_complete.json()["code"] == "ENROLLMENT_CONFLICT"


def test_enrollment_rejected_capacity_exceeded_409(client):
    """
    Завдання 5: Зарахування на переповнений курс повертає 409 Conflict.
    """
    s1 = client.post("/students", json={"code": "STU-FULL-1", "age": 20, "entry_score": 80, "regular": False}).json()["id"]
    s2 = client.post("/students", json={"code": "STU-FULL-2", "age": 22, "entry_score": 85, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-FULL-1", "price": 100000, "capacity": 1, "level": 1}).json()["id"]

    # Перший студент успішно займає єдине місце
    assert client.post("/enrollments", json={"reference": "REF-F1", "student_id": s1, "course_id": c_id}).status_code == 201

    # Другий студент отримує 409 Conflict
    resp_rejected = client.post("/enrollments", json={"reference": "REF-F2", "student_id": s2, "course_id": c_id})
    assert resp_rejected.status_code == 409
    err = resp_rejected.json()
    assert err["code"] == "ENROLLMENT_CONFLICT"
    assert err["message"] == "Вільних місць немає"


def test_enrollment_rejected_duplicate_enrollment_409(client):
    """
    Завдання 5: Повторне зарахування того самого студента на курс повертає 409 Conflict.
    """
    s_id = client.post("/students", json={"code": "STU-DUP-API", "age": 20, "entry_score": 85, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-DUP-API", "price": 100000, "capacity": 5, "level": 1}).json()["id"]

    # Перше зарахування
    assert client.post("/enrollments", json={"reference": "REF-DUP-1", "student_id": s_id, "course_id": c_id}).status_code == 201

    # Повторне зарахування
    resp_dup = client.post("/enrollments", json={"reference": "REF-DUP-2", "student_id": s_id, "course_id": c_id})
    assert resp_dup.status_code == 409
    err = resp_dup.json()
    assert err["code"] == "ENROLLMENT_CONFLICT"
    assert err["message"] == "Слухача вже зараховано або він завершив курс"


# ==============================================================================
# 6. Незмінність після відхилення (Invariance)
# ==============================================================================

def test_state_invariance_after_rejected_action(client):
    """
    Завдання 6: Після отримання 409 наступний GET підтверджує, що стан ресурсу не змінився.
    """
    s_id = client.post("/students", json={"code": "STU-INV-01", "age": 22, "entry_score": 90, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-INV-01", "price": 150000, "capacity": 5, "level": 1}).json()["id"]
    e_id = client.post("/enrollments", json={"reference": "REF-INV-01", "student_id": s_id, "course_id": c_id}).json()["id"]

    # Переводимо в статус Completed
    client.post(f"/enrollments/{e_id}/complete")
    initial_state = client.get(f"/enrollments/{e_id}").json()
    assert initial_state["status"] == "Completed"
    assert initial_state["refund"] == 0

    # Спроба виконати заборонену дію (скасування завершеного) -> 409
    resp_rejected = client.post(f"/enrollments/{e_id}/cancel", json={"days_before_start": 3})
    assert resp_rejected.status_code == 409

    # ПЕРЕВІРКА НЕЗМІННОСТІ: наступний GET показує, що ресурс залишився в первісному стані
    after_state = client.get(f"/enrollments/{e_id}").json()
    assert after_state["status"] == "Completed"
    assert after_state["refund"] == 0
    assert after_state["total"] == initial_state["total"]
    assert after_state["prepaid"] == initial_state["prepaid"]
    assert after_state == initial_state


# ==============================================================================
# 7. Персональне бізнес-правило (Параметризація знижок 0%, 5%, 10%, 15%)
# ==============================================================================

@pytest.mark.parametrize(
    "regular, price, expected_discount_pct, expected_total",
    [
        (False, 100000, 0, 100000),   # 0%: не regular, ціна < 2000 грн (1000 грн)
        (True,  100000, 5, 95000),    # 5%: regular, ціна < 2000 грн
        (False, 200000, 10, 180000),  # 10%: не regular, ціна >= 2000 грн (2000 грн)
        (True,  200000, 15, 170000),  # 15%: regular, ціна >= 2000 грн
    ],
)
def test_personal_rule_combined_discount_parameterized(client, regular, price, expected_discount_pct, expected_total):
    """
    Завдання 7: Перевірка персонального бізнес-правила варіанта 08 через REST API.
    Комбінована знижка: 5% (regular) + 10% (ціна >= 2000 грн).
    Перевіряється розрахунок total та prepaid у відповіді GET /enrollments/{id}.
    """
    stu_resp = client.post("/students", json={
        "code": f"STU-DISC-{regular}-{price}",
        "age": 20,
        "entry_score": 85,
        "regular": regular,
    })
    assert stu_resp.status_code == 201
    s_id = stu_resp.json()["id"]

    crs_resp = client.post("/courses", json={
        "code": f"CRS-DISC-{regular}-{price}",
        "price": price,
        "capacity": 10,
        "level": 1,
    })
    assert crs_resp.status_code == 201
    c_id = crs_resp.json()["id"]

    # Зарахування через API
    enr_resp = client.post("/enrollments", json={
        "reference": f"REF-DISC-{regular}-{price}",
        "student_id": s_id,
        "course_id": c_id,
        "coupon_valid": False,
    })
    assert enr_resp.status_code == 201
    e_id = enr_resp.json()["id"]

    # Перевірка через GET /enrollments/{id}
    saved = client.get(f"/enrollments/{e_id}").json()
    assert saved["total"] == expected_total
    assert saved["prepaid"] == expected_total
    assert saved["refund"] == 0


# ==============================================================================
# 8. Workflow: POST → GET → action → GET (Динамічна передача id)
# ==============================================================================

def test_full_workflow_enrollment_lifecycle(client):
    """
    Завдання 8: Наскрізний життєвий цикл ресурсу:
    POST (створення) → GET (перевірка) → action cancel → GET (новий стан).
    Id ресурсу передається динамічно з попередньої відповіді.
    """
    # 1. POST створення студента і курсу
    resp_student = client.post("/students", json={"code": "STU-WF-01", "age": 28, "entry_score": 92, "regular": True})
    assert resp_student.status_code == 201
    student_id = resp_student.json()["id"]

    resp_course = client.post("/courses", json={"code": "CRS-WF-01", "price": 200000, "capacity": 5, "level": 2})
    assert resp_course.status_code == 201
    course_id = resp_course.json()["id"]

    # 2. POST створення заявки з динамічними id
    resp_enroll = client.post("/enrollments", json={
        "reference": "REF-WF-001",
        "student_id": student_id,
        "course_id": course_id,
    })
    assert resp_enroll.status_code == 201
    enrollment_id = resp_enroll.json()["id"]
    assert resp_enroll.headers["Location"] == f"/enrollments/{enrollment_id}"

    # 3. GET заявки за динамічним id
    resp_get1 = client.get(f"/enrollments/{enrollment_id}")
    assert resp_get1.status_code == 200
    data_enrolled = resp_get1.json()
    assert data_enrolled["status"] == "Enrolled"
    assert data_enrolled["total"] == 170000  # 15% знижка (regular=True, ціна >= 2000 грн)
    assert data_enrolled["refund"] == 0

    # 4. Action: скасування заявки
    resp_cancel = client.post(f"/enrollments/{enrollment_id}/cancel", json={"days_before_start": 7})
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] == "Cancelled"

    # 5. GET підтвердження оновленого стану заявки
    resp_get2 = client.get(f"/enrollments/{enrollment_id}")
    assert resp_get2.status_code == 200
    data_cancelled = resp_get2.json()
    assert data_cancelled["status"] == "Cancelled"
    assert data_cancelled["refund"] == 170000
    assert data_cancelled["prepaid"] == 170000


# ==============================================================================
# Додаткові перевірки: Недоступність політики (502) та Валідація запиту (400)
# ==============================================================================

def test_post_enrollment_policy_unavailable_502(client, wiremock):
    """
    Перевірка відмови зовнішнього сервісу: WireMock повертає 503 -> API повертає 502 Bad Gateway.
    """
    wiremock.stub_error(status=503, body="Service Unavailable")

    s_id = client.post("/students", json={"code": "STU-502", "age": 20, "entry_score": 80, "regular": False}).json()["id"]
    c_id = client.post("/courses", json={"code": "CRS-502", "price": 100000, "capacity": 5, "level": 1}).json()["id"]

    resp = client.post("/enrollments", json={"reference": "REF-502", "student_id": s_id, "course_id": c_id})
    assert resp.status_code == 502
    err = resp.json()
    assert err["code"] == "POLICY_UNAVAILABLE"
    assert err["message"] == "Зовнішня перевірка недоступна"


def test_invalid_input_validation_400(client):
    """
    Перевірка валідації вхідних даних: неприпустимі значення повертають 400 Bad Request.
    """
    # Вік менше 14 (неприпустимо)
    resp_bad_student = client.post("/students", json={"code": "BAD-AGE", "age": 10, "entry_score": 50, "regular": False})
    assert resp_bad_student.status_code == 400
    assert resp_bad_student.json()["code"] == "INVALID_REQUEST"

    # Некоректне тіло для скасування (відсутнє обов'язкове поле days_before_start)
    resp_bad_cancel = client.post("/enrollments/1/cancel", json={})
    assert resp_bad_cancel.status_code == 400
    assert resp_bad_cancel.json()["code"] == "INVALID_REQUEST"
