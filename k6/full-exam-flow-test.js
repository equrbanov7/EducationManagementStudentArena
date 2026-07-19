import http from "k6/http";
import { check, fail, sleep } from "k6";
import exec from "k6/execution";
import { Counter, Rate, Trend } from "k6/metrics";

import {
  absoluteUrl,
  boolEnv,
  buildCodingQuestionPayload,
  clearAuthCookies,
  extractCsrf,
  floatEnv,
  formBody,
  formHeaders,
  jsonHeaders,
  loadedUserCount,
  login,
  normalAnswerPersisted,
  normalAnswerVisibleInResult,
  parseCodingConfig,
  parseCodingQuestions,
  parseJsonBody,
  parseNormalQuestions,
  pickAnswer,
  pickUser,
} from "./lib/emsarena.js";
import {
  assertCredentialCapacity,
  commonThresholds,
  requireHttpProfile,
} from "./lib/profiles.js";

// Ladder override: EXAM_FLOW_VUS set → simple constant-vus stage (for the
// on-server max-capacity ladder); otherwise fall back to the named K6_PROFILE.
const _ladderVus = Number(__ENV.EXAM_FLOW_VUS || 0);
let options;
if (_ladderVus > 0) {
  options = {
    scenarios: {
      full_exam: {
        executor: "constant-vus",
        vus: _ladderVus,
        duration: __ENV.EXAM_FLOW_DURATION || "60s",
        gracefulStop: "20s",
      },
    },
    thresholds: commonThresholds,
    summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max"],
  };
} else {
  const profile = requireHttpProfile();
  const credentialCount = loadedUserCount();
  assertCredentialCapacity(profile, credentialCount);
  options = Object.assign({}, profile.options, {
    thresholds: commonThresholds,
    summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max"],
  });
}
export { options };

const attemptsStarted = new Counter("exam_flow_attempts_started");
const answersAutosaved = new Counter("exam_flow_answers_autosaved");
const attemptsSubmitted = new Counter("exam_flow_attempts_submitted");
const reconciliations = new Counter("exam_flow_reconciliations");
const dataLossRate = new Rate("exam_data_loss_rate");
const reconciliationDuration = new Trend("exam_reconciliation_duration", true);

function requireSafetyConfirmation() {
  if (!boolEnv("K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW", false)) {
    fail(
      "Full flow creates attempts and submits answers. " +
        "Use a dedicated staging exam and set K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true.",
    );
  }
}

function configuredValue(user, key, envName, fallback) {
  const value = user && user[key] !== undefined ? user[key] : __ENV[envName];
  return value === undefined || value === null || value === "" ? fallback : value;
}

function locationOf(response) {
  return (response && (response.headers.Location || response.headers.location)) || "";
}

function absoluteLocation(response) {
  const location = locationOf(response);
  return location ? absoluteUrl(location) : "";
}

function attemptUrlFrom(value) {
  const match = /\/exams\/([^/]+)\/attempt\/(\d+)\/?/i.exec(String(value || ""));
  return match ? absoluteUrl(match[0]) : "";
}

function attemptResultUrl(attemptUrl) {
  return String(attemptUrl || "").replace(/\/?(?:\?.*)?$/, "/result/");
}

function taggedGet(url, endpoint, metricClass) {
  return http.get(url, {
    redirects: 0,
    tags: { endpoint, class: metricClass || "exam" },
  });
}

function startWithPassword(user, slug) {
  const loginResult = login(user, { clearCookies: true });
  const ok = check(loginResult.response, {
    "full flow password login succeeded": () => loginResult.success && loginResult.hasSession,
  });
  if (!ok) fail(`Password login failed for VU ${__VU}.`);

  const response = taggedGet(absoluteUrl(`/exams/${slug}/start/`), "exam_start", "exam");
  const attemptUrl = attemptUrlFrom(locationOf(response));
  check(response, {
    "direct start redirects to an attempt": (r) => [301, 302, 303].includes(r.status) && !!attemptUrl,
  });
  if (!attemptUrl) fail(`Could not resolve attempt URL from direct start: status=${response.status}.`);
  return attemptUrl;
}

function startWithAccessCode(user, slug) {
  const loginResult = login(user, { clearCookies: true });
  if (!loginResult.success) fail(`Password login failed before access-code entry for VU ${__VU}.`);

  const code = configuredValue(user, "access_code", "K6_EXAM_ACCESS_CODE", "");
  if (!code) fail("access_code entry mode requires access_code per credential or K6_EXAM_ACCESS_CODE.");
  const endpoint = absoluteUrl("/exams/code-check/");
  const response = http.post(
    endpoint,
    formBody([
      ["csrfmiddlewaretoken", loginResult.csrfToken],
      ["exam_slug", slug],
      ["access_code", code],
    ]),
    {
      redirects: 0,
      headers: formHeaders(loginResult.csrfToken, endpoint, { "X-Requested-With": "XMLHttpRequest" }),
      tags: { endpoint: "exam_access_code", class: "exam" },
    },
  );
  const payload = parseJsonBody(response, {});
  const attemptUrl = attemptUrlFrom(payload.redirect_url || locationOf(response));
  check(response, {
    "access code starts an attempt": (r) => r.status === 200 && payload.success === true && !!attemptUrl,
  });
  if (!attemptUrl) fail(`Access-code start failed: status=${response.status}.`);
  return attemptUrl;
}

function beginFinalWaiting(waitingUrl, csrfToken) {
  const ticketMatch = /\/waiting\/(\d+)\//.exec(waitingUrl);
  if (!ticketMatch) fail(`Final waiting ticket id missing from ${waitingUrl}.`);
  const ticketId = ticketMatch[1];
  const stateUrl = absoluteUrl(`/exams/final/waiting/${ticketId}/state/`);
  const maxPolls = Number(__ENV.FINAL_STATE_POLLS || 60);
  let active = false;
  for (let poll = 0; poll < maxPolls; poll += 1) {
    const stateResponse = taggedGet(stateUrl, "final_state", "exam");
    const state = parseJsonBody(stateResponse, {});
    if (stateResponse.status === 200 && state.session_state === "active") {
      active = true;
      break;
    }
    sleep(floatEnv("FINAL_STATE_POLL_SECONDS", 1));
  }
  if (!active) fail(`Final room did not become active after ${maxPolls} polls.`);

  const beginUrl = absoluteUrl(`/exams/final/waiting/${ticketId}/begin/`);
  const begin = http.post(beginUrl, null, {
    redirects: 0,
    headers: formHeaders(csrfToken, waitingUrl),
    tags: { endpoint: "final_begin", class: "exam" },
  });
  const payload = parseJsonBody(begin, {});
  const attemptUrl = attemptUrlFrom(payload.redirect_url || locationOf(begin));
  check(begin, {
    "final begin returns attempt URL": (r) => r.status === 200 && payload.success === true && !!attemptUrl,
  });
  if (!attemptUrl) fail(`Final begin failed: status=${begin.status}.`);
  return attemptUrl;
}

function startWithFinalPin(user) {
  clearAuthCookies();
  const endpoint = absoluteUrl("/exams/final/");
  const page = taggedGet(endpoint, "final_entry_page", "exam");
  const csrfToken = extractCsrf(page);
  const username = configuredValue(user, "username", "K6_USERNAME", "");
  const pin = configuredValue(user, "pin", "K6_FINAL_PIN", "");
  if (!username || !pin) fail("final_pin entry mode requires username and pin in every credential row.");

  const entry = http.post(
    endpoint,
    formBody([
      ["csrfmiddlewaretoken", csrfToken],
      ["username", username],
      ["pin", pin],
    ]),
    {
      redirects: 0,
      headers: formHeaders(csrfToken, endpoint),
      tags: { endpoint: "final_pin_entry", class: "exam" },
    },
  );
  const directAttempt = attemptUrlFrom(locationOf(entry));
  if (directAttempt) return directAttempt;
  const modalUrl = absoluteLocation(entry) || endpoint;
  const modalPage = taggedGet(modalUrl, "final_gate", "exam");
  const modalAttempt = attemptUrlFrom(locationOf(modalPage));
  if (modalAttempt) return modalAttempt;

  const modalCsrf = extractCsrf(modalPage) || csrfToken;
  const confirm = http.post(
    endpoint,
    formBody([
      ["csrfmiddlewaretoken", modalCsrf],
      ["action", "confirm"],
      ["accept_rules", "1"],
      ["language", configuredValue(user, "language", "FINAL_LANGUAGE", "")],
    ]),
    {
      redirects: 0,
      headers: formHeaders(modalCsrf, endpoint),
      tags: { endpoint: "final_gate_confirm", class: "exam" },
    },
  );
  const confirmedAttempt = attemptUrlFrom(locationOf(confirm));
  if (confirmedAttempt) return confirmedAttempt;
  const waitingUrl = absoluteLocation(confirm);
  check(confirm, {
    "final gate redirects to waiting room": (r) => [301, 302, 303].includes(r.status) && /\/waiting\//.test(waitingUrl),
  });
  if (!waitingUrl) fail(`Final PIN gate failed: status=${confirm.status}.`);
  const waitingPage = taggedGet(waitingUrl, "final_waiting", "exam");
  return beginFinalWaiting(waitingUrl, extractCsrf(waitingPage) || modalCsrf);
}

function resolveAttempt(user, slug, entryMode) {
  if (entryMode === "access_code") return startWithAccessCode(user, slug);
  if (entryMode === "final_pin") return startWithFinalPin(user);
  if (entryMode !== "password") fail(`Unsupported entry_mode=${entryMode}.`);
  return startWithPassword(user, slug);
}

function markerFor(kind, questionId) {
  const runId = String(__ENV.K6_RUN_ID || "manual").replace(/[^a-zA-Z0-9_.-]/g, "-");
  return `k6-${kind}-${runId}-vu${__VU}-i${exec.scenario.iterationInTest}-q${questionId}`;
}

function reconcile(ok, label) {
  dataLossRate.add(!ok);
  check(null, { [label]: () => ok });
  return ok;
}

function normalAnswerValue(question, index) {
  return question.options && question.options.length ? pickAnswer(question, index) : markerFor("answer", question.id);
}

function normalAnswerPairs(csrfToken, answers, action) {
  const pairs = [
    ["csrfmiddlewaretoken", csrfToken],
    ["submit_action", action],
  ];
  answers.forEach((item) => {
    pairs.push([`q_present_${item.question.id}`, "1"]);
    pairs.push([`q_${item.question.id}`, item.value]);
    if (action === "autosave") pairs.push(["changed_questions[]", item.question.id]);
  });
  return pairs;
}

function runNormalFlow(attemptUrl, attemptPage, csrfToken) {
  const questions = parseNormalQuestions(String(attemptPage.body || ""));
  if (!questions.length) fail("No normal exam questions were discovered.");
  const configuredMax = Number(__ENV.FULL_FLOW_MAX_ANSWERS || 0);
  const selected = configuredMax > 0 ? questions.slice(0, configuredMax) : questions;
  const answers = selected.map((question, index) => ({ question, value: normalAnswerValue(question, index + __VU) }));

  answers.forEach((item) => {
    const response = http.post(attemptUrl, formBody(normalAnswerPairs(csrfToken, [item], "autosave")), {
      headers: formHeaders(csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
      tags: { endpoint: "exam_autosave", class: "exam" },
    });
    const payload = parseJsonBody(response, {});
    const ok = response.status === 200 && payload.success === true;
    check(response, { "normal autosave succeeded": () => ok });
    if (!ok) fail(`Autosave failed for question ${item.question.id}: status=${response.status}.`);
    answersAutosaved.add(1);
    sleep(floatEnv("FULL_FLOW_ANSWER_THINK_SECONDS", 0.2));
  });

  const before = Date.now();
  const readback = taggedGet(attemptUrl, "exam_autosave_readback", "reconcile");
  const readbackHtml = String(readback.body || "");
  answers.forEach((item) => {
    reconcile(
      readback.status === 200 && normalAnswerPersisted(readbackHtml, item.question, item.value),
      "autosaved answer is present on authoritative attempt readback",
    );
  });
  reconciliationDuration.add(Date.now() - before);

  const submit = http.post(attemptUrl, formBody(normalAnswerPairs(csrfToken, answers, "finish")), {
    headers: formHeaders(csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
    tags: { endpoint: "exam_submit", class: "exam" },
  });
  const payload = parseJsonBody(submit, {});
  const resultUrl = absoluteUrl(payload.redirect_url || attemptResultUrl(attemptUrl));
  const submitted = submit.status === 200 && payload.success === true && payload.finished === true;
  check(submit, { "normal exam submitted": () => submitted });
  if (!submitted) fail(`Normal submit failed: status=${submit.status}.`);
  attemptsSubmitted.add(1);

  const result = taggedGet(resultUrl, "exam_result", "reconcile");
  const resultHtml = String(result.body || "");
  answers.forEach((item) => {
    reconcile(
      result.status === 200 && normalAnswerVisibleInResult(resultHtml, item.question, item.value),
      "submitted answer is visible in result reconciliation",
    );
  });
  reconciliations.add(1);
}

function codingQuestionHasMarker(question, marker) {
  return (question.initial_files || []).some((item) => String(item.content || "").includes(marker));
}

function runCodingFlow(attemptUrl, attemptPage, config) {
  const questions = parseCodingQuestions(String(attemptPage.body || ""));
  if (!questions.length || !config.autosaveUrl || !config.submitUrl) {
    fail("Coding page is missing questions/autosave/submit configuration.");
  }
  const payloads = questions.map((question) => {
    const marker = markerFor("code", question.id);
    return { marker, payload: buildCodingQuestionPayload(question, marker) };
  });

  payloads.forEach((item) => {
    const response = http.post(absoluteUrl(config.autosaveUrl), JSON.stringify(item.payload), {
      headers: jsonHeaders(config.csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
      tags: { endpoint: "coding_autosave", class: "exam" },
    });
    const responsePayload = parseJsonBody(response, {});
    const ok = response.status === 200 && responsePayload.success === true;
    check(response, { "coding autosave succeeded": () => ok });
    if (!ok) fail(`Coding autosave failed: status=${response.status}.`);
    answersAutosaved.add(1);

    if (boolEnv("K6_CODING_EXECUTE", false)) {
      const run = http.post(absoluteUrl(config.runUrl), JSON.stringify(item.payload), {
        headers: jsonHeaders(config.csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
        tags: { endpoint: "coding_run", class: "exam" },
      });
      check(run, { "coding sandbox run accepted": (r) => r.status === 200 && parseJsonBody(r, {}).success === true });
    }
  });

  const readback = taggedGet(attemptUrl, "coding_autosave_readback", "reconcile");
  const readbackQuestions = parseCodingQuestions(String(readback.body || ""));
  payloads.forEach((item) => {
    const current = readbackQuestions.find((question) => String(question.id) === String(item.payload.question_id));
    reconcile(
      readback.status === 200 && !!current && codingQuestionHasMarker(current, item.marker),
      "coding autosave marker is present on authoritative attempt readback",
    );
  });

  const submitPayload = { questions: payloads.map((item) => item.payload) };
  const submit = http.post(absoluteUrl(config.submitUrl), JSON.stringify(submitPayload), {
    headers: jsonHeaders(config.csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
    tags: { endpoint: "coding_submit", class: "exam" },
  });
  const responsePayload = parseJsonBody(submit, {});
  const submitted = submit.status === 200 && responsePayload.success === true && responsePayload.finished === true;
  check(submit, { "coding exam submitted": () => submitted });
  if (!submitted) fail(`Coding submit failed: status=${submit.status}.`);
  attemptsSubmitted.add(1);

  const resultUrl = absoluteUrl(responsePayload.redirect_url || config.resultUrl || attemptResultUrl(attemptUrl));
  const result = taggedGet(resultUrl, "coding_result", "reconcile");
  const resultHtml = String(result.body || "");
  payloads.forEach((item) => {
    reconcile(
      result.status === 200 && resultHtml.includes(item.marker),
      "submitted coding marker is visible in result reconciliation",
    );
  });
  reconciliations.add(1);
}

export default function () {
  requireSafetyConfirmation();
  const user = pickUser();
  const slug = configuredValue(user, "exam_slug", "K6_TEST_EXAM_SLUG", "");
  const entryMode = configuredValue(user, "entry_mode", "K6_ENTRY_MODE", "password");
  if (entryMode !== "final_pin" && !slug) fail("K6_TEST_EXAM_SLUG or credential.exam_slug is required.");

  const attemptUrl = resolveAttempt(user, slug, entryMode);
  attemptsStarted.add(1);
  const attemptPage = taggedGet(attemptUrl, "exam_attempt", "exam");
  check(attemptPage, { "attempt page loaded": (r) => r.status === 200 });
  if (attemptPage.status !== 200) fail(`Attempt page failed: status=${attemptPage.status}.`);

  const html = String(attemptPage.body || "");
  const codingConfig = parseCodingConfig(html);
  if (codingConfig.autosaveUrl) {
    runCodingFlow(attemptUrl, attemptPage, codingConfig);
  } else {
    runNormalFlow(attemptUrl, attemptPage, extractCsrf(attemptPage));
  }
  sleep(floatEnv("FULL_FLOW_ITERATION_PAUSE_SECONDS", 1));
}
