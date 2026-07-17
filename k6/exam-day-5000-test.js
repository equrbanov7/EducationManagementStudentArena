/**
 * İmtahan günü simulyasiyası — böyük miqyaslı realistik qarışıq yük.
 *
 * Hər iterasiyada VU davranışı (çəkili, default 60/20/10/10):
 *   60% — imtahandakı tələbə: attempt səhifəsi (GET) + autosave (POST)
 *   20% — panel oxuyanlar: /exams/assigned/ + /accounts/profile/
 *   10% — təzə girişlər (izolyasiya olunmuş cookie jar ilə tam login axını;
 *         yalnız K6_LOGIN_USER_COUNT > 0 olduqda — əks halda boş dayanmaya düşür)
 *   10% — boş dayanma (düşünmə vaxtı)
 *
 * Yük profili (ramping-vus): EXAMDAY_TARGET_VUS (default 1000) hədəfinə
 * EXAMDAY_RAMP_DURATION (default 5m) ərzində qalxır, EXAMDAY_HOLD_DURATION
 * (default 15m) saxlayır, sonra enir. 5000 VU üçün EXAMDAY_TARGET_VUS=5000.
 *
 * İstifadə:
 *   k6 run -e BASE_URL=https://... \
 *          -e K6_USERS_FILE=k6/data/users.json \
 *          -e K6_TEST_EXAM_SLUG=k6-loadtest -e K6_ALLOW_EXAM_START=true \
 *          -e K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true \
 *          -e EXAMDAY_TARGET_VUS=1000 -e EXAMDAY_RAMP_DURATION=5m \
 *          -e EXAMDAY_HOLD_DURATION=15m \
 *          k6/exam-day-5000-test.js
 *
 * QEYDLƏR:
 *  - DESTRUKTİVDİR: attempt-lər və cavablar yaradır. Yalnız ayrılmış staging
 *    imtahanında işlədin; K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true olmadan dayanır.
 *  - Sessiya hər VU üçün bir dəfə qurulur və iterasiyalar arası saxlanılır
 *    (mixed-realistic-load-test.js-dəki sessionReady nümunəsi).
 *  - Attempt gating mixed testlə eynidir: K6_ATTEMPT_ID və ya
 *    K6_ALLOW_EXAM_START=true olmadan imtahan qolu panel oxunuşuna düşür.
 *  - İstifadəçi hovuzları mixed testdəki kimidir: K6_MAIN_USER_START/COUNT əsas
 *    hovuz, K6_LOGIN_USER_START/COUNT təzə-giriş hovuzu (kəsişməməlidir).
 */

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
  LOGIN_PATH,
  loadedUserCount,
  login,
  parseCodingConfig,
  parseNormalQuestions,
  pickUserFromSlice,
  sleepSeconds,
} from "./lib/emsarena.js";

const targetVus = intEnv("EXAMDAY_TARGET_VUS", 1000);
const rampDuration = __ENV.EXAMDAY_RAMP_DURATION || "5m";
const holdDuration = __ENV.EXAMDAY_HOLD_DURATION || "15m";
const rampDownDuration = __ENV.EXAMDAY_RAMP_DOWN_DURATION || rampDuration;

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

// Çəkilər: 60% imtahan, 20% panel, 10% təzə giriş, qalan — boş dayanma.
const examPercent = Math.max(0, Math.min(1, floatEnv("EXAMDAY_EXAM_PERCENT", 0.6)));
const dashboardPercent = Math.max(0, Math.min(1, floatEnv("EXAMDAY_DASHBOARD_PERCENT", 0.2)));
const configuredLoginPercent = Math.max(0, Math.min(1, floatEnv("EXAMDAY_LOGIN_PERCENT", 0.1)));
const loginPercent = configuredLoginUserCount > 0 ? configuredLoginPercent : 0;
const examCutoff = examPercent;
const dashboardCutoff = Math.min(1, examCutoff + dashboardPercent);
const loginCutoff = Math.min(1, dashboardCutoff + loginPercent);

if (targetVus > mainUserCount && !allowUserReuse) {
  throw new Error(
    `EXAMDAY_TARGET_VUS=${targetVus} exceeds main user pool size=${mainUserCount}. ` +
      "Create more dedicated k6 users or set K6_ALLOW_USER_REUSE=true intentionally.",
  );
}

if (configuredLoginPercent > 0 && configuredLoginUserCount <= 0) {
  console.warn(
    "EXAMDAY_LOGIN_PERCENT requested, but K6_LOGIN_USER_COUNT is not set; fresh-login branch is disabled.",
  );
}

export const options = {
  noCookiesReset: true,
  stages: [
    { duration: rampDuration, target: targetVus },
    { duration: holdDuration, target: targetVus },
    { duration: rampDownDuration, target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "http_req_duration{class:normal}": ["p(95)<1500"],
    "http_req_duration{class:exam}": ["p(95)<2500"],
    checks: ["rate>0.98"],
  },
};

export function setup() {
  // Təhlükəsizlik qapısı: bu axın attempt/cavab yaradır.
  if (!boolEnv("K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW", false)) {
    fail(
      "Exam-day flow creates attempts and answers. " +
        "Use a dedicated staging exam and set K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true.",
    );
  }
  if (!__ENV.K6_TEST_EXAM_SLUG) {
    fail("Set K6_TEST_EXAM_SLUG to a dedicated load-test exam slug.");
  }
}

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

function resetAttemptState() {
  attemptUrl = "";
  csrfToken = "";
  normalQuestions = [];
  codingAutosaveUrl = "";
  codingLanguage = "python";
}

function ensureLoggedIn() {
  if (sessionReady && hasCookie("sessionid")) return true;
  resetAttemptState();
  const result = login(pickMainUser(), { clearCookies: true });
  recordDuration(loginPageDuration, result.page);
  recordDuration(loginSubmitDuration, result.response);
  const ok = check(result.response, {
    "examday login ok": () => result.success && result.hasSession,
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
    "examday attempt page ok": (r) => r.status === 200,
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

// 60% qolu — imtahandakı tələbə: attempt oxunuşu + autosave.
function examOperation(slug) {
  if (!hasCookie("sessionid") || !hasCookie("csrftoken")) {
    sessionReady = false;
    resetAttemptState();
    if (!ensureLoggedIn()) return;
  }

  // Gating mixed testlə eynidir: icazə yoxdursa attempt yaratmırıq.
  if (!(attemptUrl || boolEnv("K6_ALLOW_EXAM_START", false) || __ENV.K6_ATTEMPT_ID)) {
    dashboardOperation();
    return;
  }
  if (!ensureAttempt(slug)) return;

  const attempt = http.get(attemptUrl, {
    redirects: 0,
    tags: { endpoint: "exam_attempt", class: "exam" },
  });
  recordDuration(attemptPageDuration, attempt);
  const readOk = check(attempt, {
    "examday attempt read ok": (r) => r.status === 200,
  });
  if (!readOk || attempt.status !== 200) {
    sessionReady = false;
    resetAttemptState();
    return;
  }

  if (codingAutosaveUrl) {
    const payload = JSON.stringify({
      selected_language: __ENV.K6_CODING_LANGUAGE || codingLanguage,
      files: [
        {
          name: __ENV.K6_CODING_FILE_NAME || "main.py",
          content: __ENV.K6_CODING_CONTENT || `print('exam day vu ${__VU} iter ${__ITER}')\n`,
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
      "examday coding autosave ok": (r) => r.status === 200,
    });
    return;
  }

  if (!normalQuestions.length) return;
  const question = normalQuestions[(__ITER + __VU) % normalQuestions.length];
  const response = autosaveNormalAnswer(attemptUrl, csrfToken, question, __ITER + __VU);
  recordDuration(autosaveDuration, response);
  const ok = check(response, {
    "examday autosave ok": (r) => r.status === 200 && /"success"\s*:\s*true/.test(String(r.body || "")),
  });
  if (!ok && (response.status === 302 || response.status === 403)) {
    sessionReady = false;
    resetAttemptState();
  }
}

// 20% qolu — panel oxuyanlar: təyin olunmuş imtahanlar + profil.
function dashboardOperation() {
  const assigned = http.get(absoluteUrl("/exams/assigned/"), {
    redirects: 0,
    tags: { endpoint: "assigned_exams", class: "exam" },
  });
  recordDuration(assignedDuration, assigned);
  const assignedOk = check(assigned, {
    "examday assigned read ok": (r) => r.status === 200,
  });
  if (!assignedOk || assigned.status !== 200) {
    sessionReady = false;
    resetAttemptState();
    return;
  }

  const profile = http.get(absoluteUrl("/accounts/profile/"), {
    redirects: 0,
    tags: { endpoint: "profile", class: "normal" },
  });
  recordDuration(profileDuration, profile);
  const profileOk = check(profile, {
    "examday profile read ok": (r) => r.status === 200,
  });
  if (!profileOk || profile.status !== 200) {
    sessionReady = false;
    resetAttemptState();
  }
}

// 10% qolu — təzə giriş: VU-nun əsas sessiyasına toxunmadan izolyasiya olunmuş
// cookie jar ilə tam login axını (login səhifəsi + CSRF + POST).
function freshLoginOperation() {
  const user = pickLoginUser();
  const jar = new http.CookieJar();
  const loginUrl = absoluteUrl(LOGIN_PATH);
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
    "examday fresh login ok": (r) => r.status === 302 || r.status === 303 || r.status === 200,
  });
}

// 10% qolu — boş dayanma: heç bir sorğu, yalnız düşünmə vaxtı.
function idleOperation() {
  sleep(sleepSeconds(floatEnv("EXAMDAY_IDLE_MIN_SECONDS", 3), floatEnv("EXAMDAY_IDLE_MAX_SECONDS", 10)));
}

export default function () {
  const slug = __ENV.K6_TEST_EXAM_SLUG;
  if (!slug) fail("Set K6_TEST_EXAM_SLUG to a dedicated load-test exam slug.");
  if (!ensureLoggedIn()) return;

  const roll = Math.random();
  if (roll < examCutoff) {
    examOperation(slug);
  } else if (roll < dashboardCutoff) {
    dashboardOperation();
  } else if (roll < loginCutoff) {
    freshLoginOperation();
  } else {
    idleOperation();
  }

  sleep(sleepSeconds(floatEnv("EXAMDAY_SLEEP_MIN_SECONDS", 1), floatEnv("EXAMDAY_SLEEP_MAX_SECONDS", 4)));
}
