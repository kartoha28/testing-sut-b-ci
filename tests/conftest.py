import json
import os
import time
import urllib.request
from pathlib import Path
import psycopg
import pytest
from testcontainers.core.container import DockerContainer

from courses.database import connect
from courses.http_enrollment_policy import HttpEnrollmentPolicy
from courses.repositories import (
    PostgresStudentRepository,
    PostgresCourseRepository,
    PostgresEnrollmentRepository,
)
from courses.service import EnrollmentService
from courses.api import app
from fastapi.testclient import TestClient

class WireMockClient:
    """Клієнт для керування стабами та перевірки запитів WireMock."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def reset(self):
        """Очищає всі мапінги та журнал запитів."""
        req = urllib.request.Request(f"{self.base_url}/__admin/reset", method="POST")
        with urllib.request.urlopen(req) as resp:
            resp.read()

    def stub_allowed(self, allowed: bool = True, status: int = 200):
        """Налаштовує відповідь для POST /enrollment-policy."""
        payload = {
            "request": {
                "method": "POST",
                "url": "/enrollment-policy"
            },
            "response": {
                "status": status,
                "jsonBody": {"allowed": allowed},
                "headers": {"Content-Type": "application/json"}
            }
        }
        req = urllib.request.Request(
            f"{self.base_url}/__admin/mappings",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            resp.read()

    def stub_error(self, status: int = 503, body: str = "Service Unavailable"):
        """Налаштовує повернення помилки сервера (503, 500 тощо)."""
        payload = {
            "request": {
                "method": "POST",
                "url": "/enrollment-policy"
            },
            "response": {
                "status": status,
                "body": body,
                "headers": {"Content-Type": "text/plain"}
            }
        }
        req = urllib.request.Request(
            f"{self.base_url}/__admin/mappings",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            resp.read()

    def get_requests(self) -> list[dict]:
        """Отримує всі зафіксовані HTTP-запити з журналу WireMock."""
        req = urllib.request.Request(f"{self.base_url}/__admin/requests")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("requests", [])

    def get_requests_for(self, url: str = "/enrollment-policy", method: str = "POST") -> list[dict]:
        """Фільтрує зафіксовані запити за URL та HTTP-методом."""
        return [
            r["request"] for r in self.get_requests()
            if r["request"].get("url") == url and r["request"].get("method") == method
        ]


@pytest.fixture(scope="session")
def postgres_container():
    """Автоматичний запуск PostgreSQL через Testcontainers із динамічним портом та застосуванням міграцій."""
    pg = (
        DockerContainer("postgres:16-alpine")
        .with_env("POSTGRES_USER", "courses_student")
        .with_env("POSTGRES_PASSWORD", "tc_secret_password")
        .with_env("POSTGRES_DB", "courses_variant08_test")
        .with_env("POSTGRES_HOST_AUTH_METHOD", "trust")
        .with_bind_ports(5432)
    )

    with pg:
        host = pg.get_container_host_ip()
        port = int(pg.get_exposed_port(5432))

        # Оновлення змінних середовища для динамічного підключення
        os.environ["DB_HOST"] = host
        os.environ["DB_PORT"] = str(port)
        os.environ["DB_NAME"] = "courses_variant08_test"
        os.environ["DB_USER"] = "courses_student"
        os.environ["DB_PASSWORD"] = "tc_secret_password"

        # Очікування готовності PostgreSQL
        ready = False
        for _ in range(40):
            try:
                with psycopg.connect(
                    host=host, port=port, user="courses_student",
                    dbname="courses_variant08_test", password="tc_secret_password"
                ) as conn:
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)

        if not ready:
            raise RuntimeError("PostgreSQL Testcontainer не зміг запуститися вчасно")

        # Автоматичне застосування міграції
        migration_file = Path(__file__).parent.parent / "migrations" / "V1__create_tables.sql"
        migration_sql = migration_file.read_text(encoding="utf-8")
        with psycopg.connect(
            host=host, port=port, user="courses_student",
            dbname="courses_variant08_test", password="tc_secret_password", autocommit=True
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)

        yield pg


@pytest.fixture(scope="session")
def wiremock_container():
    """Автоматичний запуск WireMock через Testcontainers із динамічним портом."""
    wm = DockerContainer("wiremock/wiremock:3.9.1").with_bind_ports(8080)
    with wm:
        host = wm.get_container_host_ip()
        port = int(wm.get_exposed_port(8080))
        url = f"http://{host}:{port}"
        client = WireMockClient(url)

        # Очікування готовності WireMock
        ready = False
        for _ in range(40):
            try:
                req = urllib.request.Request(f"{url}/__admin/mappings")
                with urllib.request.urlopen(req) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.5)

        if not ready:
            raise RuntimeError("WireMock Testcontainer не зміг запуститися вчасно")

        yield client


@pytest.fixture(autouse=True)
def clean_state(request):
    """
    Забезпечує ізоляцію та незалежність інтеграційних і API тестів:
    1. Пропускається для unit-тестів та окремого regression-модуля.
    2. Очищення таблиць PostgreSQL через TRUNCATE CASCADE.
    3. Очищення мапінгів та журналу запитів WireMock.
    4. Встановлення дефолтного стабу (200 OK, allowed: True).
    """
    if request.node.get_closest_marker("unit") or request.path.name == "enrollment_regression.py":
        yield
        return

    request.getfixturevalue("postgres_container")
    wm = request.getfixturevalue("wiremock_container")

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE enrollments, students, courses RESTART IDENTITY CASCADE;")

    wm.reset()
    wm.stub_allowed(True)
    yield


@pytest.fixture
def wiremock(wiremock_container):
    """Надає клієнт WireMock для тесту."""
    return wiremock_container


@pytest.fixture
def policy(wiremock):
    """Справжній HttpEnrollmentPolicy, налаштований на контейнер WireMock."""
    return HttpEnrollmentPolicy(wiremock.base_url, timeout=2)


@pytest.fixture
def db_connection(postgres_container):
    """Надає відкрите з'єднання з БД з autocommit=True та закриває його через with."""
    with connect() as conn:
        yield conn


@pytest.fixture
def student_repo(db_connection):
    return PostgresStudentRepository(db_connection)


@pytest.fixture
def course_repo(db_connection):
    return PostgresCourseRepository(db_connection)


@pytest.fixture
def enrollment_repo(db_connection):
    return PostgresEnrollmentRepository(db_connection)


@pytest.fixture
def service(student_repo, course_repo, enrollment_repo, policy):
    """Екземпляр EnrollmentService з реальними репозиторіями та реальним HttpEnrollmentPolicy."""
    return EnrollmentService(student_repo, course_repo, enrollment_repo, policy)


@pytest.fixture
def client(postgres_container, wiremock_container):
    """TestClient для тестування REST API SUT B через HTTP."""
    os.environ["ENROLLMENT_POLICY_URL"] = wiremock_container.base_url
    with TestClient(app) as test_client:
        yield test_client

