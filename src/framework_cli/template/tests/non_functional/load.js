// k6 load test (CD Phase 4). Thresholds map 1:1 to the framework's SLO definitions — a
// threshold breach IS an SLO breach, expressed once. Run via scripts/load.sh (no local
// k6 install; uses the official Docker image). Target + thresholds come from env vars.
import http from 'k6/http';
import { check } from 'k6';

const TARGET = (__ENV.K6_TARGET || 'http://localhost:8000').replace(/\/$/, '');
const P99_MS = Number(__ENV.SLO_P99_MS || 200);
const ERROR_RATE_PCT = Number(__ENV.SLO_ERROR_RATE_PCT || 1);

// Count only 5xx as "failed" so http_req_failed matches the app's error-rate SLO, which is
// 5xx-only (observability/metrics.py). Without this, k6 treats >=400 as failed and a
// legitimate 4xx (e.g. a 404/422 you add later) would falsely trip the error-rate threshold.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 499 }));

export const options = {
  vus: Number(__ENV.K6_VUS || 10),
  duration: __ENV.K6_DURATION || '30s',
  thresholds: {
    // Map 1:1 to the SLO defs: p99 latency (ms) and 5xx error rate (as a fraction).
    http_req_duration: [`p(99)<${P99_MS}`],
    http_req_failed: [`rate<${ERROR_RATE_PCT / 100}`],
  },
};

export default function () {
  const res = http.get(`${TARGET}/items`);
  check(res, { 'status is 200': (r) => r.status === 200 });
}
