import http from "k6/http";
import { check, fail, sleep } from "k6";
import { Trend } from "k6/metrics";
import {
  absoluteUrl,
  autosaveNormalAnswer,
  boolEnv,
  extractCsrf,
  floatEnv,
  formBody,
  formHeaders,
  getOrStartAttempt,
  hasCookie,
  intEnv,
  login,
  loadedUserCount,
  parseCodingConfig,
  parseNormalQuestions,
  pickUserFromSlice,
  sleepSeconds,
} from "./lib/emsarena.js";

const targetVus = intEnv("TARGET_VUS", 50);
const rampDuration = __ENV.RAMP_DURATION || "1m";
const holdDuration = __ENV.HOLD_DURATION || "5m";
const totalUsers = loadedUserCount();
const mainUserStart = intEnv("K6_MAIN_USER_START", 0);
const configuredLoginUserCount = intEnv("K6_LOGIN_USER_COUNT", 0);
const configuredLoginUserStart = intEnv("K6_LOGIN_USER_START", -1);
const loginUserStart =
  configuredLoginUserCount > 0
    ? configuredLoginUserStart >= 0
      ? configuredLoginUserStart
      : totalUsers - configuredLoginUserCount
    : 0;
const defaultMainUserCount =
  configuredLoginUserCount > 0 ? Math.max(0, loginUserStart - mainUserStart) : totalUsers - mainUserStart;
const mainUserCount = intEnv("K6_MAIN_USER_COUNT", defaultMainUserCount);
const allowUserReuse = boolEnv("K6_ALLOW_USER_REUSE", false);
const configuredLoginPercent = Math.max(0, Math.min(1, floatEnv("MIXED_LOGIN_PERCENT", 0.05)));
const loginPercent = configuredLoginUserCount > 0 ? configuredLoginPercent : 0;
const profilePercent = Math.max(0, Math.min(1, floatEnv("MIXED_PROFILE_PERCENT", 0.05)));
const autosavePercent = Math.max(0, Math.min(1, floatEnv("MIXED_AUTOSAVE_PERCENT", 0.20)));
const profileCutoff = Math.min(1, loginPercent + profilePercent);
const readCutoff = Math.max(profileCutoff, Math.min(1, 1 - autosavePercent));
const hostAliases = {};
if (__ENV.K6_HOST_ALIAS_IP) {
  hostAliases[__ENV.K6_HOST_ALIAS_NAME || "emsarena.com"] = __ENV.K6_HOST_ALIAS_IP;
}

if (targetVus > mainUserCount && !allowUserReuse) {
  throw new Error(
    `TARGET_VUS=${targetVus} exceeds main user pool size=${mainUserCount}. ` +
      "Create more dedicated k6 users or set K6_ALLOW_USER_REUSE=true intentionally.",
  );
}

if (configuredLoginPercent > 0 && configuredLoginUserCount <= 0) {
  console.warn("MIXED_LOGIN_PERCENT requested, but K6_LOGIN_USER_COUNT is not set; mixed login branch is disabled.");
}

export const options = {
  noCookiesReset: true,
  hosts: hostAliases,
  stages: [
    { duration: rampDuration, target: targetVus },
    { duration: holdDuration, target: targetVus },
    { duration: rampDuration, target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{class:normal}": ["p(95)<1500"],
    "http_req_duration{class:exam}": ["p(95)<2500"],
    checks: ["rate>0.99"],
  },
};

let sessionReady = false;
let attemptUrl = "";
let csrfToken = "";
let normalQuestions = [];
let codingAutosaveUrl = "";
let codingLanguage = "python";

const loginPageDuration = new Trend("endpoint_login_page_duration", true);
const loginSubmitDuration = new Trend("endpoint_login_submit_duration", true);
const assignedDuration = new Trend("endpoint_assigned_duration", true);
const attemptPageDuration = new Trend("endpoint_attempt_page_duration", true);
const attemptReadDuration = new Trend("endpoint_attempt_read_duration", true);
const autosaveDuration = new Trend("endpoint_autosave_duration", true);
const profileDuration = new Trend("endpoint_profile_duration", true);

function recordDuration(trend, response) {
  if (response && response.timings) {
    trend.add(response.timings.duration);
  }
}

function pickMainUser() {
  return pickUserFromSlice(mainUserStart, mainUserCount, __VU - 1);
}

function pickLoginUser() {
  return pickUserFromSlice(loginUserStart, configuredLoginUserCount, __VU + __ITER);
}

function logReadFailure(name, response) {
  if (__ENV.DEBUG_READ_FAILURES !== "true") return;
  const location = response.headers.Location || response.headers.location || "";
  console.log(
    `${name} failed status=${response.status} location=${location} hasSession=${hasCookie("sessionid")} vu=${__VU} iter=${__ITER}`,
  );
}

function resetAttemptState() {
  attemptUrl = "";
  csrfToken = "";
  normalQuestions = [];
  codingAutosaveUrl = "";
  codingLanguage = "python";
}

function isolatedLoginOperation() {
  const user = pickLoginUser();
  const jar = new http.CookieJar();
  const loginUrl = absoluteUrl("/accounts/login/");
  const page = http.get(loginUrl, {
    jar,
    tags: { endpoint: "login_page_isolated", class: "normal" },
  });
  const isolatedCsrf = extractCsrf(page);
  const response = http.post(
    loginUrl,
    formBody([
      ["csrfmiddlewaretoken", isolatedCsrf],
      ["username", user.username],
      ["password", user.password],
      ["next", ""],
    ]),
    {
      jar,
      redirects: 0,
      headers: formHeaders(isolatedCsrf, loginUrl),
      tags: { endpoint: "login_submit_isolated", class: "normal" },
    },
  );
  check(response, {
    "mixed isolated login ok": (r) => r.status === 302 || r.status === 303 || r.status === 200,
  });
}

function ensureLoggedIn() {
  if (sessionReady && hasCookie("sessionid")) return true;
  resetAttemptState();
  const result = login(pickMainUser(), { clearCookies: true });
  recordDuration(loginPageDuration, result.page);
  recordDuration(loginSubmitDuration, result.response);
  const ok = check(result.response, {
    "mixed login ok": () => result.success && result.hasSession,
  });
  sessionReady = ok && result.success;
  return sessionReady;
}

function ensureAttempt(slug) {
  if (attemptUrl) return true;
  attemptUrl = getOrStartAttempt(slug, { failOnError: false });
  if (!attemptUrl) {
    sessionReady = false;
    return false;
  }
  const page = http.get(attemptUrl, {
    redirects: 0,
    tags: { endpoint: "exam_attempt", class: "exam" },
  });
  recordDuration(attemptPageDuration, page);
  const ok = check(page, {
    "mixed attempt page ok": (r) => r.status === 200,
  });
  if (!ok || page.status !== 200) {
    sessionReady = false;
    resetAttemptState();
    return false;
  }

  const html = String(page.body || "");
  const codingConfig = parseCodingConfig(html);
  csrfToken = codingConfig.csrfToken || extractCsrf(page);
  if (codingConfig.autosaveUrl) {
    codingAutosaveUrl = absoluteUrl(codingConfig.autosaveUrl);
    codingLanguage = codingConfig.selectedLanguage || "python";
    return true;
  }
  normalQuestions = parseNormalQuestions(html);
  return normalQuestions.length > 0;
}

function readOperation(slug) {
  const assigned = http.get(absoluteUrl("/exams/assigned/"), {
    redirects: 0,
    tags: { endpoint: "assigned_exams", class: "exam" },
  });
  recordDuration(assignedDuration, assigned);
  const assignedOk = check(assigned, {
    "assigned read ok": (r) => r.status === 200,
  });
  if (!assignedOk || assigned.status !== 200) {
    logReadFailure("assigned", assigned);
    sessionReady = false;
    resetAttemptState();
    return;
  }

  if (__ENV.MIXED_READ_AVAILABLE === "true") {
    const available = http.get(absoluteUrl("/exams/available/"), {
      redirects: 0,
      tags: { endpoint: "available_exams", class: "exam" },
    });
    check(available, {
      "available read ok": (r) => r.status === 200,
    });
  }

  if ((attemptUrl || boolEnv("K6_ALLOW_EXAM_START", false) || __ENV.K6_ATTEMPT_ID) && ensureAttempt(slug)) {
    const attempt = http.get(attemptUrl, {
      redirects: 0,
      tags: { endpoint: "exam_attempt", class: "exam" },
    });
    recordDuration(attemptReadDuration, attempt);
    const ok = check(attempt, {
      "attempt read ok": (r) => r.status === 200,
    });
    if (!ok || attempt.status !== 200) {
      logReadFailure("attempt", attempt);
      sessionReady = false;
      resetAttemptState();
    }
  }
}

function autosaveOperation(slug) {
  if (!hasCookie("sessionid") || !hasCookie("csrftoken")) {
    sessionReady = false;
    resetAttemptState();
    if (!ensureLoggedIn()) return;
  }
  if (!ensureAttempt(slug)) return;

  if (codingAutosaveUrl) {
    const payload = JSON.stringify({
      selected_language: __ENV.K6_CODING_LANGUAGE || codingLanguage,
      files: [
        {
          name: __ENV.K6_CODING_FILE_NAME || "main.py",
          content: __ENV.K6_CODING_CONTENT || `print('load test vu ${__VU} iter ${__ITER}')\n`,
        },
      ],
      stdin: "",
    });
    const response = http.post(codingAutosaveUrl, payload, {
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
        Referer: attemptUrl,
      },
      tags: { endpoint: "coding_autosave", class: "exam" },
    });
    recordDuration(autosaveDuration, response);
    check(response, {
      "coding autosave ok": (r) => r.status === 200,
    });
    return;
  }

  if (!normalQuestions.length) return;
  const question = normalQuestions[(__ITER + __VU) % normalQuestions.length];
  const response = autosaveNormalAnswer(attemptUrl, csrfToken, question, __ITER + __VU);
  recordDuration(autosaveDuration, response);
  const ok = check(response, {
    "mixed autosave ok": (r) => r.status === 200 && /"success"\s*:\s*true/.test(String(r.body || "")),
  });
  if (!ok && (response.status === 302 || response.status === 403)) {
    sessionReady = false;
    resetAttemptState();
  }
  if (!ok && __ENV.DEBUG_AUTOSAVE_FAILURES === "true") {
    const snippet = String(response.body || "").replace(/\s+/g, " ").slice(0, 900);
    console.log(`autosave failed status=${response.status} body=${snippet}`);
  }
}

export default function () {
  const slug = __ENV.K6_TEST_EXAM_SLUG;
  if (!slug) fail("Set K6_TEST_EXAM_SLUG to a dedicated load-test exam slug.");
  if (!ensureLoggedIn()) return;

  const roll = Math.random();
  if (roll < loginPercent) {
    isolatedLoginOperation();
  } else if (roll < profileCutoff) {
    const profile = http.get(absoluteUrl("/accounts/profile/"), {
      redirects: 0,
      tags: { endpoint: "profile", class: "normal" },
    });
    recordDuration(profileDuration, profile);
    const profileOk = check(profile, {
      "profile read ok": (r) => r.status === 200,
    });
    if (!profileOk || profile.status !== 200) {
      logReadFailure("profile", profile);
      sessionReady = false;
      resetAttemptState();
    }
  } else if (roll < readCutoff) {
    readOperation(slug);
  } else {
    autosaveOperation(slug);
  }

  sleep(sleepSeconds(floatEnv("MIXED_SLEEP_MIN_SECONDS", 1), floatEnv("MIXED_SLEEP_MAX_SECONDS", 5)));
}
