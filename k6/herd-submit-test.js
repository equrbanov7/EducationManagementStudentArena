/**
 * Thundering-herd SUBMIT test — deadline auto-submit storm.
 *
 * WHAT IT EXERCISES
 *   Simulates the worst moment of a timed exam: N students who are ALREADY on
 *   an attempt page all press "finish" (or hit the auto-submit deadline) within
 *   the same second. Every VU logs in, opens/resumes its own attempt, autosaves
 *   one draft answer during a warm-up window, then parks on a shared wall-clock
 *   barrier so that all VUs fire their `submit_action=finish` POST at once —
 *   hammering apps/exams/views/student/attempts.py under maximum contention
 *   (mark_finished + optimistic-concurrency + scoring on the same tick).
 *
 * HOW THE HERD SYNCHRONIZES
 *   k6 VUs finish their warm-up at different times, so a wall-clock barrier is
 *   used: exec.instance.currentTestRunDuration is the SAME clock for every VU
 *   (ms since the test started). Each VU sleeps until HERD_PREP_SECONDS have
 *   elapsed since test start, then submits. As long as warm-up (login + start +
 *   autosave) finishes before HERD_PREP_SECONDS, the submits land together. VUs
 *   that miss the barrier submit immediately and are counted in
 *   herd_barrier_missed — raise HERD_PREP_SECONDS if that count is non-trivial.
 *
 * SAFETY — THIS IS DESTRUCTIVE
 *   It creates real attempts and FINISHES them (results are written). Point it
 *   at a throwaway staging exam only, and confirm with
 *   K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true. Each VU must be a distinct student
 *   with its own attempt, so run with K6_ALLOW_EXAM_START=true (each VU starts
 *   its own attempt) — do NOT pin every VU to one K6_ATTEMPT_ID.
 *
 * KEY ENV
 *   HERD_VUS               number of simultaneous submitters (default 50).
 *   HERD_PREP_SECONDS      warm-up window before the synchronized submit (30).
 *   HERD_MAX_DURATION      scenario cap (default "5m").
 *   K6_TEST_EXAM_SLUG      target exam slug (or per-credential "exam_slug").
 *   K6_ALLOW_EXAM_START    "true" so each VU opens its own attempt.
 *   K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW  required "true" guard.
 *
 * METRICS
 *   herd_submit_success (Rate)   share of finishes the server accepted.
 *   herd_submits (Counter)       finish POSTs sent.
 *   herd_barrier_missed (Counter) VUs whose warm-up overran the barrier.
 *   Submit POSTs are tagged {class:"exam", endpoint:"herd_submit"} for the
 *   http_req_duration threshold below.
 *
 * RUN EXAMPLES (LAN target, self-signed TLS)
 *   # 200-student deadline storm on a staging exam
 *   BASE_URL=https://10.0.2.42 K6_INSECURE_SKIP_TLS_VERIFY=true \
 *   K6_USERS_FILE=/abs/path/k6/data/stress-users.json \
 *   K6_TEST_EXAM_SLUG=k6-loadtest K6_ALLOW_EXAM_START=true \
 *   K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true \
 *   HERD_VUS=200 HERD_PREP_SECONDS=40 \
 *     k6 run k6/herd-submit-test.js
 *
 *   # small smoke of the mechanism
 *   BASE_URL=https://10.0.2.42 K6_INSECURE_SKIP_TLS_VERIFY=true \
 *   K6_USERS_FILE=/abs/path/k6/data/stress-users.json \
 *   K6_TEST_EXAM_SLUG=k6-loadtest K6_ALLOW_EXAM_START=true \
 *   K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true HERD_VUS=5 HERD_PREP_SECONDS=15 \
 *     k6 run k6/herd-submit-test.js
 */

import http from "k6/http";
import { check, fail, sleep } from "k6";
import exec from "k6/execution";
import { Counter, Rate } from "k6/metrics";

import {
  autosaveNormalAnswer,
  boolEnv,
  extractCsrf,
  formBody,
  formHeaders,
  getOrStartAttempt,
  intEnv,
  loadedUserCount,
  login,
  parseJsonBody,
  parseNormalQuestions,
  pickAnswer,
  pickUser,
} from "./lib/emsarena.js";

const HERD_VUS = intEnv("HERD_VUS", 50);
const PREP_SECONDS = intEnv("HERD_PREP_SECONDS", 30);
const PREP_MS = PREP_SECONDS * 1000;

export const options = {
  scenarios: {
    herd_submit: {
      executor: "per-vu-iterations",
      vus: HERD_VUS,
      iterations: 1,
      maxDuration: __ENV.HERD_MAX_DURATION || "5m",
      gracefulStop: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    "http_req_duration{endpoint:herd_submit}": ["p(95)<5000", "p(99)<10000"],
    checks: ["rate>0.95"],
    herd_submit_success: ["rate>0.95"],
  },
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max"],
};

const submitSuccess = new Rate("herd_submit_success");
const submits = new Counter("herd_submits");
const barrierMissed = new Counter("herd_barrier_missed");

function requireSafetyConfirmation() {
  if (!boolEnv("K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW", false)) {
    fail(
      "Herd submit creates attempts and finishes them. " +
        "Use a dedicated staging exam and set K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true.",
    );
  }
}

function configuredValue(user, key, envName, fallback) {
  const value = user && user[key] !== undefined ? user[key] : __ENV[envName];
  return value === undefined || value === null || value === "" ? fallback : value;
}

// Synchronized-finish payload. Mirrors the full-exam-flow "finish" contract:
// submit_action=finish plus the presence marker + value for the one answer the
// VU autosaved, so the attempt is finished with a real committed answer.
function finishExam(attemptUrl, csrfToken, answered) {
  const pairs = [
    ["csrfmiddlewaretoken", csrfToken],
    ["submit_action", "finish"],
  ];
  if (answered) {
    pairs.push([`q_present_${answered.question.id}`, "1"]);
    pairs.push([`q_${answered.question.id}`, answered.value]);
  }
  return http.post(attemptUrl, formBody(pairs), {
    headers: formHeaders(csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
    tags: { endpoint: "herd_submit", class: "exam" },
  });
}

export default function () {
  requireSafetyConfirmation();

  const user = pickUser();
  const slug = configuredValue(user, "exam_slug", "K6_TEST_EXAM_SLUG", "");
  if (!slug) fail("K6_TEST_EXAM_SLUG or credential.exam_slug is required.");

  // --- warm-up: land on the attempt page like a student already taking it ---
  const loginResult = login(user, { clearCookies: true });
  const authed = check(loginResult, {
    "herd login succeeded": (r) => r.success && r.hasSession,
  });
  if (!authed) fail(`Herd login failed for VU ${__VU}.`);

  // getOrStartAttempt honors K6_ATTEMPT_ID / K6_ALLOW_EXAM_START gating; with
  // ALLOW_EXAM_START each distinct VU-user resolves its own attempt.
  const attemptUrl = getOrStartAttempt(slug);

  const attemptPage = http.get(attemptUrl, {
    redirects: 0,
    tags: { endpoint: "exam_attempt", class: "exam" },
  });
  check(attemptPage, { "attempt page loaded": (r) => r.status === 200 });
  if (attemptPage.status !== 200) fail(`Attempt page failed: status=${attemptPage.status}.`);

  const csrfToken = extractCsrf(attemptPage);
  const questions = parseNormalQuestions(String(attemptPage.body || ""));

  // Autosave exactly one draft answer (reuses the lib helper). pickAnswer is
  // deterministic for the same (question, index), so we can replay the same
  // value in the finish payload below.
  let answered = null;
  if (questions.length) {
    const question = questions[0];
    const value = pickAnswer(question, __VU);
    const autosave = autosaveNormalAnswer(attemptUrl, csrfToken, question, __VU);
    const savePayload = parseJsonBody(autosave, {});
    check(autosave, {
      "herd autosave accepted": (r) => r.status === 200 && savePayload.success === true,
    });
    answered = { question, value };
  }

  // --- barrier: wait for the shared deadline, then everyone submits at once ---
  const elapsed = exec.instance.currentTestRunDuration; // ms since test start
  const remaining = (PREP_MS - elapsed) / 1000;
  if (remaining > 0) {
    sleep(remaining);
  } else {
    barrierMissed.add(1);
  }

  // --- thundering herd: synchronized finish ---
  const submit = finishExam(attemptUrl, csrfToken, answered);
  submits.add(1);
  const payload = parseJsonBody(submit, {});
  // 200 + finished, or a benign "already finished" (deadline sweep beat us).
  const ok =
    submit.status === 200 &&
    (payload.finished === true || payload.already_finished === true || payload.success === true);
  submitSuccess.add(ok);
  check(submit, {
    "herd finish accepted": () => ok,
  });
}

// Fail fast if no credentials are loaded before spinning up VUs.
loadedUserCount();
