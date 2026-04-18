// k6 ingestion burst — pushes synthetic Wazuh alerts onto Redis Streams
// at 50 req/s sustained + 500 req/s for 30 s, verifying §7.6 backpressure.
//
// Requires the API to expose a debug ingest endpoint (Phase 8 + only when
// `ENV=dev`). In prod this would be a Filebeat replay; here we hit the
// dev seam so CI can drive it deterministically.
//
// Run:
//   k6 run --env STRIX_API_BASE=http://localhost:8000/api/v1 \
//          --env STRIX_BEARER=$JWT \
//          infra/loadtests/ingest_burst.js

import http from "k6/http";
import { Counter } from "k6/metrics";

const BASE = __ENV.STRIX_API_BASE || "http://localhost:8000/api/v1";
const TOKEN = __ENV.STRIX_BEARER || "";

const dropped = new Counter("ingest_drops");

export const options = {
  scenarios: {
    sustained_50_rps: {
      executor: "constant-arrival-rate",
      rate: 50, timeUnit: "1s", duration: "10m",
      preAllocatedVUs: 20, maxVUs: 100,
    },
    burst_500_rps: {
      executor: "constant-arrival-rate",
      startTime: "9m",
      rate: 500, timeUnit: "1s", duration: "30s",
      preAllocatedVUs: 100, maxVUs: 500,
    },
  },
  thresholds: {
    "http_req_duration{scenario:sustained_50_rps}":
      ["p(99)<400"],   // §7.1 end-to-end p99
    "http_req_failed":   ["rate<0.05"],
    "ingest_drops":      ["count<500"],   // soft cap; backpressure may drop a few
  },
};

function alertPayload() {
  return {
    indicator: "synthetic",
    timestamp: new Date().toISOString(),
    agent_id: `Machine-${1 + (__VU % 5)}-New`,
    rule_id: "80710",
    full_log: "synthetic load-test alert",
    decoder: "auditd",
  };
}

export default function () {
  const params = TOKEN
    ? { headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" } }
    : { headers: { "Content-Type": "application/json" } };
  const r = http.post(`${BASE}/_dev/ingest`, JSON.stringify(alertPayload()), params);
  if (r.status >= 500) dropped.add(1);
}
