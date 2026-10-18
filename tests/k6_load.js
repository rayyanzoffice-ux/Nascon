import http from 'k6/http';
import { check, sleep } from 'k6';

const base = __ENV.BASE_URL || 'http://localhost:8080';

export const options = {
  scenarios: {
    guest_viewers: { executor: 'constant-vus', vus: 500, duration: '15s', exec: 'viewStream' },
    chat_posters: { executor: 'constant-vus', vus: 50, duration: '15s', exec: 'postChat' },
  },
  thresholds: {
    http_req_failed: ['rate==0.00'],
    http_req_duration: ['p(95)<800'],
  },
};

export function viewStream() {
  const response = http.get(`${base}/audit/v1/qr/match-m1?inspect=true`);
  check(response, {
    'guest QR status is 200': (result) => result.status === 200,
    'has target_route': (result) => result.json('target_route') !== undefined,
  });
  sleep(0.1);
}

export function postChat() {
  const payload = JSON.stringify({
    chat_room_id: 'chat-cs-session-101',
    incoming_messages: [
      { message_id: `k6-${__VU}-${__ITER}`, sender: `user-${__VU}`, text: 'Live reaction' },
    ],
    check_dlq: false,
  });
  const response = http.post(`${base}/audit/v1/moderation/test`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(response, {
    'chat status is 200 or 201': (result) => result.status === 200 || result.status === 201,
  });
  sleep(0.2);
}
