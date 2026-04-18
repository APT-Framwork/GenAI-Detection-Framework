// k6 dashboard load test (P8-1).
//
// Targets §7.1 budget: dashboard endpoints p99 < 500 ms at 200 rps.
// Run locally:
//   k6 run --env STRIX_API_BASE=http://localhost:8000/api/v1 \
//          --env STRIX_BEARER=$JWT \
//          infra/loadtests/api_smoke.js
//
// CI runs nightly via .github/workflows/loadtest.yml (see P8-1).

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const BASE = __ENV.STRIX_API_BASE || "http://localhost:8000/api/v1";
const TOKEN = __ENV.STRIX_BEARER || "";

const dashboard_p99 = new Trend("dashboard_latency_ms", true);
const ok_rate = new Rate("dashboard_ok_rate");

export const options = {
  scenarios: {
    dashboard_steady: {
      executor: "constant-arrival-rate",
      rate: 200, timeUnit: "1s", duration: "60s",
      preAllocatedVUs: 50, maxVUs: 200,
    },
  },
  thresholds: {
    "dashboard_latency_ms":     ["p(99)<500"],     // §7.1
    "dashboard_ok_rate":        ["rate>0.99"],
    "http_req_failed":          ["rate<0.01"],
  },
};

const ENDPOINTS = [
  "/dashboard/attack-vector?window=1h",
  "/dashboard/global-risk?window=1h",
  "/dashboard/victim-graph?window=1h",
  "/analysis/chains?onlyOpen=true&limit=10",
  "/threat-intel/compromised-assets?limit=20",
];

export default function () {
  const url = BASE + ENDPOINTS[Math.floor(Math.random() * ENDPOINTS.length)];
  const params = TOKEN
    ? { headers: { Authorization: `Bearer ${TOKEN}` } }
    : {};
  const t0 = Date.now();
  const res = http.get(url, params);
  dashboard_p99.add(Date.now() - t0);
  ok_rate.add(res.status === 200);
  check(res, { "200": (r) => r.status === 200 });
  sleep(0.05);
}
