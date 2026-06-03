import http from "k6/http";
import { fail } from "k6";
import { SharedArray } from "k6/data";

export const BASE_URL = (__ENV.BASE_URL || "https://emsarena.com").replace(/\/+$/, "");
export const REFERER_BASE_URL = (__ENV.K6_REFERER_BASE_URL || BASE_URL).replace(/\/+$/, "");

export function intEnv(name, fallback) {
  const raw = __ENV[name];
  if (raw === undefined || raw === "") return fallback;
  const value = parseInt(raw, 10);
  return Number.isFinite(value) ? value : fallback;
}

export function floatEnv(name, fallback) {
  const raw = __ENV[name];
  if (raw === undefined || raw === "") return fallback;
  const value = parseFloat(raw);
  return Number.isFinite(value) ? value : fallback;
}

export function boolEnv(name, fallback) {
  const raw = __ENV[name];
  if (raw === undefined || raw === "") return fallback;
  return ["1", "true", "yes", "y", "on"].indexOf(String(raw).toLowerCase()) !== -1;
}

export function absoluteUrl(pathOrUrl) {
  if (!pathOrUrl) return BASE_URL;
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  return BASE_URL + "/" + String(pathOrUrl).replace(/^\/+/, "");
}

export function formBody(pairs) {
  return pairs
    .filter(([key, value]) => key !== undefined && key !== null && value !== undefined && value !== null)
    .map(([key, value]) => encodeURIComponent(String(key)) + "=" + encodeURIComponent(String(value)))
    .join("&");
}

export function commonHeaders(extra) {
  const headers = {
    "User-Agent": __ENV.K6_USER_AGENT || "EMSArena-k6-loadtest/1.0",
  };
  Object.keys(extra || {}).forEach((key) => {
    headers[key] = extra[key];
  });
  return headers;
}

export function formHeaders(csrfToken, referer, extra) {
  return commonHeaders(
    Object.assign(
      {
        "Content-Type": "application/x-www-form-urlencoded",
        Referer: normalizeReferer(referer || REFERER_BASE_URL + "/"),
        "X-CSRFToken": csrfToken || "",
      },
      extra || {},
    ),
  );
}

export function jsonHeaders(csrfToken, referer, extra) {
  return commonHeaders(
    Object.assign(
      {
        "Content-Type": "application/json",
        Referer: normalizeReferer(referer || REFERER_BASE_URL + "/"),
        "X-CSRFToken": csrfToken || "",
      },
      extra || {},
    ),
  );
}

export function normalizeReferer(referer) {
  const value = String(referer || "");
  if (REFERER_BASE_URL !== BASE_URL && value.startsWith(BASE_URL)) {
    return REFERER_BASE_URL + value.slice(BASE_URL.length);
  }
  return value;
}

function attrValue(tag, attrName) {
  const re = new RegExp(attrName + "\\s*=\\s*['\"]([^'\"]+)['\"]", "i");
  const match = re.exec(tag || "");
  return match ? htmlDecode(match[1]) : "";
}

export function htmlDecode(value) {
  return String(value || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

export function extractCsrf(response) {
  const body = response && response.body ? String(response.body) : "";
  const hidden = /name\s*=\s*['"]csrfmiddlewaretoken['"][^>]*value\s*=\s*['"]([^'"]+)['"]/i.exec(body);
  if (hidden) return htmlDecode(hidden[1]);

  const jarCookies = http.cookieJar().cookiesForURL(BASE_URL);
  if (jarCookies && jarCookies.csrftoken && jarCookies.csrftoken.length) {
    return jarCookies.csrftoken[0];
  }
  return "";
}

export function clearAuthCookies() {
  const jar = http.cookieJar();
  ["sessionid", "csrftoken"].forEach((name) => {
    if (typeof jar.clear === "function") {
      jar.clear(BASE_URL, name);
    } else if (typeof jar.set === "function") {
      jar.set(BASE_URL, name, "", { max_age: 0 });
    }
  });
}

export function hasCookie(name) {
  const jarCookies = http.cookieJar().cookiesForURL(BASE_URL);
  return !!(jarCookies && jarCookies[name] && jarCookies[name].length && jarCookies[name][0]);
}

export const users = new SharedArray("emsarena-test-users", () => {
  if (__ENV.K6_USERS_FILE) {
    const raw = JSON.parse(open(__ENV.K6_USERS_FILE));
    const loaded = Array.isArray(raw) ? raw : raw.users;
    if (!Array.isArray(loaded) || loaded.length === 0) {
      throw new Error("K6_USERS_FILE must contain a non-empty JSON array or an object with a non-empty users array.");
    }
    return loaded;
  }
  if (__ENV.K6_USERS_JSON) {
    const raw = JSON.parse(__ENV.K6_USERS_JSON);
    const loaded = Array.isArray(raw) ? raw : raw.users;
    if (!Array.isArray(loaded) || loaded.length === 0) {
      throw new Error("K6_USERS_JSON must be a non-empty JSON array or an object with a non-empty users array.");
    }
    return loaded;
  }
  if (__ENV.K6_USERNAME && __ENV.K6_PASSWORD) {
    return [{ username: __ENV.K6_USERNAME, password: __ENV.K6_PASSWORD }];
  }
  return [];
});

export function requireUsers() {
  if (!users.length) {
    fail("Test user missing. Set K6_USERS_JSON, K6_USERS_FILE, or K6_USERNAME/K6_PASSWORD.");
  }
  return users;
}

export function pickUser() {
  const loaded = requireUsers();
  return loaded[(__VU - 1) % loaded.length];
}

export function pickUserByIndex(index) {
  const loaded = requireUsers();
  const normalized = ((index % loaded.length) + loaded.length) % loaded.length;
  return loaded[normalized];
}

export function pickUserFromSlice(start, count, index) {
  const loaded = requireUsers();
  const sliceStart = Math.max(0, start || 0);
  const sliceCount = count && count > 0 ? count : loaded.length - sliceStart;
  if (sliceStart >= loaded.length || sliceCount <= 0 || sliceStart + sliceCount > loaded.length) {
    fail(`Invalid k6 user slice start=${sliceStart} count=${sliceCount} total=${loaded.length}.`);
  }
  const normalized = ((index % sliceCount) + sliceCount) % sliceCount;
  return loaded[sliceStart + normalized];
}

export function loadedUserCount() {
  return requireUsers().length;
}

export function login(user, options) {
  const opts = options || {};
  if (opts.clearCookies !== false) clearAuthCookies();

  const loginUrl = absoluteUrl("/accounts/login/");
  const page = http.get(loginUrl, {
    tags: Object.assign({ endpoint: "login_page", class: "normal" }, opts.tags || {}),
  });
  const csrfToken = extractCsrf(page);

  const payload = formBody([
    ["csrfmiddlewaretoken", csrfToken],
    ["username", user.username],
    ["password", user.password],
    ["next", opts.next || ""],
  ]);

  const response = http.post(loginUrl, payload, {
    redirects: 0,
    headers: formHeaders(csrfToken, loginUrl),
    tags: Object.assign({ endpoint: "login_submit", class: "normal" }, opts.tags || {}),
  });
  const jarCookies = http.cookieJar().cookiesForURL(BASE_URL);
  const hasSession = !!(jarCookies && jarCookies.sessionid && jarCookies.sessionid.length);
  const success = hasSession && (response.status === 302 || response.status === 303 || response.status === 200);

  return {
    page,
    response,
    csrfToken,
    success,
    hasSession,
    user,
  };
}

export function logout() {
  const page = http.get(absoluteUrl("/accounts/profile/"), {
    tags: { endpoint: "profile_for_logout", class: "normal" },
  });
  const csrfToken = extractCsrf(page);
  return http.post(absoluteUrl("/accounts/logout/"), formBody([["csrfmiddlewaretoken", csrfToken]]), {
    redirects: 0,
    headers: formHeaders(csrfToken, absoluteUrl("/accounts/profile/")),
    tags: { endpoint: "logout", class: "normal" },
  });
}

export function getOrStartAttempt(slug, options) {
  const opts = options || {};
  const failOnError = opts.failOnError !== false;
  const attemptId = __ENV.K6_ATTEMPT_ID;
  if (attemptId) {
    return absoluteUrl(`/exams/${slug}/attempt/${attemptId}/`);
  }

  if (!boolEnv("K6_ALLOW_EXAM_START", false)) {
    const message = "Set K6_ATTEMPT_ID or K6_ALLOW_EXAM_START=true before starting/resuming an exam attempt.";
    if (failOnError) fail(message);
    return "";
  }

  const startUrl = absoluteUrl(`/exams/${slug}/start/`);
  const response = http.get(startUrl, {
    redirects: 0,
    tags: { endpoint: "exam_start", class: "exam" },
  });
  const location = response.headers.Location || response.headers.location || "";
  const attemptUrl = attemptUrlFromLocation(location);
  if (!attemptUrl) {
    const message = `Could not resolve attempt URL from start response status=${response.status} location=${location}`;
    if (failOnError) fail(message);
    return "";
  }
  return absoluteUrl(attemptUrl);
}

export function attemptUrlFromLocation(location) {
  if (!location) return "";
  const match = /\/exams\/[^/]+\/attempt\/\d+\/?/i.exec(location);
  return match ? match[0] : "";
}

export function parseNormalQuestions(html) {
  const byId = {};
  let match;
  const dataIdRe = /data-question-id\s*=\s*['"](\d+)['"]/gi;
  while ((match = dataIdRe.exec(html || "")) !== null) {
    byId[match[1]] = byId[match[1]] || { id: match[1], options: [], kind: "unknown" };
  }

  const inputRe = /<input\b[^>]*name\s*=\s*['"]q_(\d+)['"][^>]*>/gi;
  while ((match = inputRe.exec(html || "")) !== null) {
    const qid = match[1];
    const tag = match[0];
    const type = (attrValue(tag, "type") || "").toLowerCase();
    const value = attrValue(tag, "value");
    byId[qid] = byId[qid] || { id: qid, options: [], kind: "unknown" };
    if ((type === "radio" || type === "checkbox") && value) {
      byId[qid].kind = type === "checkbox" ? "multiple" : "single";
      byId[qid].options.push(value);
    }
  }

  const textRe = /<textarea\b[^>]*name\s*=\s*['"]q_(\d+)['"][^>]*>/gi;
  while ((match = textRe.exec(html || "")) !== null) {
    const qid = match[1];
    byId[qid] = byId[qid] || { id: qid, options: [], kind: "written" };
    byId[qid].kind = "written";
  }

  return Object.keys(byId)
    .sort((a, b) => parseInt(a, 10) - parseInt(b, 10))
    .map((id) => byId[id]);
}

export function pickAnswer(question, index) {
  if (question.options && question.options.length) {
    return question.options[index % question.options.length];
  }
  return `Load test draft answer vu=${__VU} iter=${__ITER} q=${question.id}`;
}

export function autosaveNormalAnswer(attemptUrl, csrfToken, question, index) {
  const answerValue = pickAnswer(question, index);
  const pairs = [
    ["csrfmiddlewaretoken", csrfToken],
    ["submit_action", "autosave"],
    ["changed_questions[]", question.id],
    [`q_${question.id}`, answerValue],
  ];
  return http.post(attemptUrl, formBody(pairs), {
    headers: formHeaders(csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
    tags: { endpoint: "exam_autosave", class: "exam" },
  });
}

export function submitNormalExam(attemptUrl, csrfToken) {
  return http.post(
    attemptUrl,
    formBody([
      ["csrfmiddlewaretoken", csrfToken],
      ["submit_action", "finish"],
    ]),
    {
      headers: formHeaders(csrfToken, attemptUrl, { "X-Requested-With": "XMLHttpRequest" }),
      tags: { endpoint: "exam_submit", class: "exam" },
    },
  );
}

export function parseCodingConfig(html) {
  function jsString(key) {
    const re = new RegExp(key + "\\s*:\\s*['\"]([^'\"]+)['\"]", "i");
    const match = re.exec(html || "");
    return match ? htmlDecode(match[1]) : "";
  }
  return {
    autosaveUrl: jsString("autosaveUrl"),
    runUrl: jsString("runUrl"),
    submitUrl: jsString("submitUrl"),
    csrfToken: jsString("csrfToken"),
    selectedLanguage: jsString("selectedLanguage") || "python",
  };
}

export function sleepSeconds(minSeconds, maxSeconds) {
  const min = Number(minSeconds);
  const max = Number(maxSeconds);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return min || 1;
  return min + Math.random() * (max - min);
}
