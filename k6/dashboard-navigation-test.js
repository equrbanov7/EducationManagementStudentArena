import http from "k6/http";
import { check, fail, sleep } from "k6";
import {
  absoluteUrl,
  floatEnv,
  intEnv,
  login,
  pickUser,
  sleepSeconds,
} from "./lib/emsarena.js";

const dashboardSections = (__ENV.DASHBOARD_SECTIONS || "profile-info,assigned-exams,assigned-courses,my-results")
  .split(",")
  .map((section) => section.trim())
  .filter(Boolean);

export const options = {
  vus: intEnv("DASHBOARD_VUS", 1),
  duration: __ENV.DASHBOARD_DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{class:dashboard}": ["p(95)<2500"],
    checks: ["rate>0.99"],
  },
};

function getOk(path, endpoint, expectedStatuses) {
  const allowed = expectedStatuses || [200];
  const response = http.get(absoluteUrl(path), {
    redirects: 0,
    tags: { endpoint, class: "dashboard" },
  });
  check(response, {
    [`${endpoint} returned expected status`]: (r) => allowed.indexOf(r.status) !== -1,
  });
  return response;
}

export default function () {
  const loginResult = login(pickUser(), { clearCookies: true });
  const loginOk = check(loginResult.response, {
    "dashboard login ok": () => loginResult.success && loginResult.hasSession,
  });
  if (!loginOk || !loginResult.success) {
    fail("Dashboard flow cannot continue without a logged-in session.");
  }

  getOk("/accounts/profile/", "profile_page");
  getOk("/accounts/dashboard/", "dashboard_dispatch", [302, 303]);
  getOk("/accounts/dashboard/student/", "student_dashboard");
  getOk("/accounts/profile/api/badges/", "profile_badges");
  getOk("/accounts/assigned-exams/", "assigned_exams_page");
  getOk("/accounts/assigned-courses/", "assigned_courses_page");
  getOk("/accounts/my-results/", "my_results_page");
  getOk("/exams/assigned/", "exam_assigned_list");
  getOk("/exams/available/", "exam_available_list");

  for (const section of dashboardSections) {
    const response = getOk(`/accounts/profile/api/sections/${section}/`, `profile_section_${section}`);
    check(response, {
      [`profile section ${section} json ok`]: (r) => /"ok"\s*:\s*true/.test(String(r.body || "")),
    });
    sleep(floatEnv("DASHBOARD_SECTION_SLEEP_SECONDS", 0.1));
  }

  sleep(sleepSeconds(floatEnv("DASHBOARD_SLEEP_MIN_SECONDS", 1), floatEnv("DASHBOARD_SLEEP_MAX_SECONDS", 3)));
}
