/**
 * Final imtahan mərkəzi — yük testi.
 *
 * Ssenari (hər VU = imtahan zalındakı bir tələbə kompüteri):
 *   1. PIN giriş səhifəsi (GET)  → CSRF
 *   2. PIN ilə giriş (POST)      → gate-ə redirect
 *   3. Gate (GET) + qaydalar/dil təsdiqi (POST) → gözləmə otağı
 *   4. Gözləmə otağı (GET) + aşağı tezlikli state poll (WS fallback yolu)
 *   5. Oturum aktivləşəndə begin (POST) → take_exam redirect URL
 *
 * İstifadə:
 *   k6 run -e BASE_URL=... -e FINAL_USERS="user1:PIN1,user2:PIN2" \
 *          -e FINAL_VUS=50 -e FINAL_DURATION=2m k6/final-exam-center-test.js
 *
 * QEYD: FINAL_USERS üçün oturum "entry_open"/"active" vəziyyətində olmalı,
 * PIN-lər əvvəlcədən yaradılmalıdır (exam center panelindən). Bu test yalnız
 * HTTP yolunu ölçür; WS bağlantı həcmi ayrıca alətlə ölçülməlidir.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { absoluteUrl, clearAuthCookies, extractCsrf, formHeaders, intEnv } from "./lib/emsarena.js";

export const options = {
  vus: intEnv("FINAL_VUS", 1),
  duration: __ENV.FINAL_DURATION || "1m",
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "http_req_duration{class:final_entry}": ["p(95)<1500"],
    "http_req_duration{class:final_state}": ["p(95)<800"],
    checks: ["rate>0.98"],
  },
};

const credentials = (__ENV.FINAL_USERS || "")
  .split(",")
  .map((pair) => pair.trim())
  .filter(Boolean)
  .map((pair) => {
    const [username, pin] = pair.split(":");
    return { username, pin };
  });

function pickCredential() {
  if (!credentials.length) return null;
  return credentials[(__VU - 1) % credentials.length];
}

export default function () {
  const cred = pickCredential();
  if (!cred) {
    check(null, { "FINAL_USERS təyin olunub": () => false });
    return;
  }

  clearAuthCookies();

  // 1. Giriş səhifəsi + CSRF
  const entryPage = http.get(absoluteUrl("/exams/final/entry/"), {
    tags: { endpoint: "final_entry_page", class: "final_entry" },
  });
  check(entryPage, { "entry page 200": (r) => r.status === 200 });
  const csrf = extractCsrf(entryPage);

  // 2. PIN girişi
  const entryPost = http.post(
    absoluteUrl("/exams/final/entry/"),
    { username: cred.username, pin: cred.pin, csrfmiddlewaretoken: csrf },
    {
      redirects: 0,
      headers: formHeaders(csrf, absoluteUrl("/exams/final/entry/")),
      tags: { endpoint: "final_entry_post", class: "final_entry" },
    }
  );
  const gateLocation = entryPost.headers.Location || "";
  const entered = check(entryPost, {
    "PIN girişi gate-ə yönləndirir": (r) => r.status === 302 && gateLocation.indexOf("/gate/") !== -1,
  });
  if (!entered) return;

  // 3. Gate + təsdiq
  const gatePage = http.get(absoluteUrl(gateLocation), {
    tags: { endpoint: "final_gate", class: "final_entry" },
  });
  check(gatePage, { "gate 200": (r) => r.status === 200 });
  const gateCsrf = extractCsrf(gatePage);
  const gatePost = http.post(
    absoluteUrl(gateLocation),
    { accept_rules: "1", language: __ENV.FINAL_LANGUAGE || "", csrfmiddlewaretoken: gateCsrf },
    {
      redirects: 0,
      headers: formHeaders(gateCsrf, absoluteUrl(gateLocation)),
      tags: { endpoint: "final_gate_post", class: "final_entry" },
    }
  );
  const waitingLocation = gatePost.headers.Location || "";
  check(gatePost, {
    "gate gözləmə otağına yönləndirir": (r) => r.status === 302 && waitingLocation.indexOf("/waiting/") !== -1,
  });
  if (!waitingLocation) return;

  // 4. Gözləmə otağı + state poll (WS fallback tezliyi ilə)
  const waitingPage = http.get(absoluteUrl(waitingLocation), {
    tags: { endpoint: "final_waiting", class: "final_entry" },
  });
  check(waitingPage, { "waiting 200": (r) => r.status === 200 });

  const ticketId = (waitingLocation.match(/waiting\/(\d+)\//) || [])[1];
  const pollCount = intEnv("FINAL_STATE_POLLS", 3);
  let sessionActive = false;
  for (let i = 0; i < pollCount; i += 1) {
    const state = http.get(absoluteUrl(`/exams/final/waiting/${ticketId}/state/`), {
      tags: { endpoint: "final_state", class: "final_state" },
    });
    check(state, { "state 200": (r) => r.status === 200 });
    if (state.status === 200 && state.json("session_state") === "active") {
      sessionActive = true;
      break;
    }
    sleep(intEnv("FINAL_POLL_SLEEP", 5));
  }

  // 5. Otaq aktivdirsə — sinxron start yolu (begin → take_exam URL)
  if (sessionActive) {
    const beginCsrf = extractCsrf(waitingPage);
    const begin = http.post(absoluteUrl(`/exams/final/waiting/${ticketId}/begin/`), null, {
      headers: formHeaders(beginCsrf, absoluteUrl(waitingLocation)),
      tags: { endpoint: "final_begin", class: "final_entry" },
    });
    check(begin, {
      "begin uğurlu və ya gözləmə (409)": (r) => r.status === 200 || r.status === 409,
    });
  }

  sleep(1);
}
