import http from "k6/http";
import { check, fail, sleep } from "k6";
import {
  absoluteUrl,
  boolEnv,
  extractCsrf,
  floatEnv,
  formBody,
  formHeaders,
  intEnv,
} from "./lib/emsarena.js";

export const options = {
  scenarios: {
    signup_smoke: {
      executor: "shared-iterations",
      vus: intEnv("SIGNUP_VUS", 1),
      iterations: intEnv("SIGNUP_ITERATIONS", 1),
      maxDuration: __ENV.SIGNUP_MAX_DURATION || "2m",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:signup_submit}": ["p(95)<2500"],
    checks: ["rate>0.99"],
  },
};

function randomSuffix() {
  return `${Date.now()}_${__VU}_${__ITER}_${Math.floor(Math.random() * 1000000)}`;
}

export default function () {
  if (!boolEnv("ALLOW_SIGNUP_SMOKE", false)) {
    fail("Signup sends OTP/email. Set ALLOW_SIGNUP_SMOKE=true only for a very small production smoke test.");
  }

  const registerUrl = absoluteUrl("/accounts/register/");
  const page = http.get(registerUrl, {
    tags: { endpoint: "signup_page", class: "normal" },
  });
  const csrfToken = extractCsrf(page);
  const suffix = randomSuffix();
  const username = `loadtest_${suffix}`;
  const emailDomain = __ENV.SIGNUP_EMAIL_DOMAIN || "emsarena.test";
  const email = `loadtest+${suffix}@${emailDomain}`;
  const password = __ENV.SIGNUP_PASSWORD || `LoadTest!${suffix}Aa1`;

  const payload = formBody([
    ["csrfmiddlewaretoken", csrfToken],
    ["username", username],
    ["email", email],
    ["first_name", "Load"],
    ["last_name", "Test"],
    ["password", password],
    ["password2", password],
    ["country", __ENV.SIGNUP_COUNTRY || "AZ"],
    ["organization_type", __ENV.SIGNUP_ORGANIZATION_TYPE || "course_student"],
    ["join_organization", __ENV.SIGNUP_JOIN_ORGANIZATION_ID || ""],
    ["specialization", __ENV.SIGNUP_SPECIALIZATION || "Load Test"],
    ["group_number", __ENV.SIGNUP_GROUP_NUMBER || "LT-1"],
    ["phone", ""],
    ["department", ""],
    ["staff_position", ""],
    ["initial_role", "member"],
    ["accept_privacy_policy", "on"],
  ]);

  const response = http.post(registerUrl, payload, {
    redirects: 0,
    headers: formHeaders(csrfToken, registerUrl),
    tags: { endpoint: "signup_submit", class: "normal" },
  });

  check(response, {
    "signup reached expected safe point": (r) => [200, 302, 303, 429].indexOf(r.status) !== -1,
    "signup did not finish account": (r) => r.status !== 201,
  });

  if (__ENV.DEBUG_SIGNUP === "true") {
    console.log(`signup username=${username} email=${email} status=${response.status}`);
  }
  sleep(floatEnv("SIGNUP_SLEEP_SECONDS", 1));
}

