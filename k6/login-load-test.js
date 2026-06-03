import { check, sleep } from "k6";
import { BASE_URL, boolEnv, floatEnv, intEnv, login, logout, pickUser } from "./lib/emsarena.js";

export const options = {
  vus: intEnv("LOGIN_VUS", 1),
  duration: __ENV.LOGIN_DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:login_submit}": ["p(95)<1500"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const user = pickUser();
  const result = login(user, { clearCookies: true });

  check(result.response, {
    "login returned expected status": (r) => [200, 302, 303].indexOf(r.status) !== -1,
    "login created session": () => result.success && result.hasSession,
  });

  if (boolEnv("LOGIN_POST_LOGOUT", false) && result.success) {
    const logoutResponse = logout();
    check(logoutResponse, {
      "logout accepted": (r) => [200, 302, 303].indexOf(r.status) !== -1,
    });
  }

  sleep(floatEnv("LOGIN_SLEEP_SECONDS", 2));
  if (__ENV.DEBUG_LOGIN === "true") {
    console.log(`base=${BASE_URL} user=${user.username} status=${result.response.status}`);
  }
}

