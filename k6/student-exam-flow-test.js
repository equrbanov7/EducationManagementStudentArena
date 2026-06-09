import http from "k6/http";
import { check, fail, sleep } from "k6";
import exec from "k6/execution";
import {
  absoluteUrl,
  autosaveNormalAnswer,
  boolEnv,
  extractCsrf,
  floatEnv,
  getOrStartAttempt,
  intEnv,
  login,
  parseCodingConfig,
  parseNormalQuestions,
  pickUser,
  pickUserByIndex,
  sleepSeconds,
  submitNormalExam,
} from "./lib/emsarena.js";

export const options = {
  vus: intEnv("STUDENT_FLOW_VUS", 1),
  iterations: intEnv("STUDENT_FLOW_ITERATIONS", 1),
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{class:normal}": ["p(95)<1500"],
    "http_req_duration{class:exam}": ["p(95)<2500"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const slug = __ENV.K6_TEST_EXAM_SLUG;
  if (!slug) fail("Set K6_TEST_EXAM_SLUG to a dedicated load-test exam slug.");

  const user = boolEnv("STUDENT_FLOW_PICK_USER_BY_ITERATION", false)
    ? pickUserByIndex(exec.scenario.iterationInTest)
    : pickUser();

  const loginResult = login(user, { clearCookies: true });
  check(loginResult.response, {
    "student login ok": () => loginResult.success,
  });
  if (!loginResult.success) return;

  check(http.get(absoluteUrl("/accounts/profile/"), { tags: { endpoint: "profile", class: "normal" } }), {
    "profile ok": (r) => r.status === 200,
  });
  check(http.get(absoluteUrl("/exams/assigned/"), { tags: { endpoint: "assigned_exams", class: "exam" } }), {
    "assigned exams ok": (r) => r.status === 200,
  });

  const attemptUrl = getOrStartAttempt(slug);
  const attemptPage = http.get(attemptUrl, {
    tags: { endpoint: "exam_attempt", class: "exam" },
  });
  check(attemptPage, {
    "attempt page ok": (r) => r.status === 200,
  });
  if (attemptPage.status !== 200) return;

  const html = String(attemptPage.body || "");
  const codingConfig = parseCodingConfig(html);
  if (codingConfig.autosaveUrl) {
    const autosaveUrl = absoluteUrl(codingConfig.autosaveUrl);
    const csrfToken = codingConfig.csrfToken || extractCsrf(attemptPage);
    const payload = JSON.stringify({
      selected_language: __ENV.K6_CODING_LANGUAGE || codingConfig.selectedLanguage || "python",
      files: [
        {
          name: __ENV.K6_CODING_FILE_NAME || "main.py",
          content: __ENV.K6_CODING_CONTENT || "print('load test draft')\n",
        },
      ],
      stdin: "",
    });
    const response = http.post(autosaveUrl, payload, {
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
        Referer: attemptUrl,
      },
      tags: { endpoint: "coding_autosave", class: "exam" },
    });
    check(response, {
      "coding autosave ok": (r) => r.status === 200,
    });
    sleep(floatEnv("STUDENT_FLOW_SLEEP_SECONDS", 2));
    return;
  }

  const csrfToken = extractCsrf(attemptPage);
  const questions = parseNormalQuestions(html);
  check(null, {
    "questions discovered": () => questions.length > 0,
  });
  if (!questions.length) return;

  const maxAnswers = Math.min(questions.length, intEnv("STUDENT_FLOW_MAX_ANSWERS", 5));
  for (let i = 0; i < maxAnswers; i += 1) {
    const response = autosaveNormalAnswer(attemptUrl, csrfToken, questions[i], i + __ITER);
    check(response, {
      "autosave ok": (r) => r.status === 200 && /"success"\s*:\s*true/.test(String(r.body || "")),
    });
    sleep(sleepSeconds(floatEnv("ANSWER_SLEEP_MIN_SECONDS", 1), floatEnv("ANSWER_SLEEP_MAX_SECONDS", 4)));
  }

  if (boolEnv("K6_ALLOW_EXAM_SUBMIT", false)) {
    if (!boolEnv("K6_CONFIRM_TEST_EXAM", false)) {
      fail("K6_ALLOW_EXAM_SUBMIT=true also requires K6_CONFIRM_TEST_EXAM=true.");
    }
    const submitResponse = submitNormalExam(attemptUrl, csrfToken);
    check(submitResponse, {
      "exam submit ok": (r) => r.status === 200 && /"finished"\s*:\s*true/.test(String(r.body || "")),
    });
  }
}
