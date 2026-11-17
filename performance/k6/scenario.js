import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const PROFILE = __ENV.PROFILE || 'baseline';

const profiles = {
  baseline: {
    vus: 1,
    duration: '20s',
  },
  load: {
    stages: [
      { duration: '10s', target: 10 },
      { duration: '30s', target: 10 },
      { duration: '10s', target: 0 },
    ],
  },
  stress: {
    stages: [
      { duration: '10s', target: 30 },
      { duration: '20s', target: 30 },
      { duration: '10s', target: 0 },
    ],
  },
};

export const options = {
  ...profiles[PROFILE],
  thresholds: {
    http_req_duration: ['p(95)<500', 'avg<200'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  // Унікальний код слухача (до 40 символів): префікс + VU + ітерація + таймстемп
  const uniqueCode = `S_${__VU}_${__ITER}_${Date.now() % 10000000}`;

  const payload = JSON.stringify({
    code: uniqueCode,
    age: 20,
    entry_score: 85,
    regular: false,
  });

  const headers = { 'Content-Type': 'application/json' };

  // Крок 1: POST /students — створення слухача
  const postRes = http.post(`${BASE_URL}/students`, payload, {
    headers: headers,
    tags: { name: 'POST /students' },
  });

  const postOk = check(postRes, {
    'POST /students status is 201': (r) => r.status === 201,
    'POST /students has valid id': (r) => r.json('id') > 0,
  });

  if (!postOk) {
    sleep(0.5);
    return;
  }

  // Динамічна кореляція: витягуємо id створеного слухача
  const studentId = postRes.json('id');

  // Крок 2: GET /students/{id} — отримання створеного слухача за id
  const getRes = http.get(`${BASE_URL}/students/${studentId}`, {
    tags: { name: 'GET /students/{id}' },
  });

  check(getRes, {
    'GET /students/{id} status is 200': (r) => r.status === 200,
    'GET /students/{id} matches created id': (r) => r.json('id') === studentId,
  });

  sleep(0.5);
}
