import http from 'k6/http';
import { check, sleep } from 'k6';

const base = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export const options = {
  vus: Number(__ENV.K6_VUS || 5),
  duration: __ENV.K6_DURATION || '10s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
  },
};

export default function () {
  const health = http.get(`${base}/health`);
  check(health, {
    'health responds 200': (response) => response.status === 200,
    'health reports ready': (response) => response.json('status') === 'ok',
  });

  const ping = http.get(`${base}/api/v1/ping`);
  check(ping, {
    'ping responds 200': (response) => response.status === 200,
    'ping payload is valid': (response) => response.json('pong') === true,
  });
  sleep(0.1);
}
