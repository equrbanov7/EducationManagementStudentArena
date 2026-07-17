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

export function stripHtml(value) {
  return htmlDecode(String(value || "").replace(/<[^>]+>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
}

export function parseJsonScript(html, elementId, fallback) {
  const escapedId = String(elementId || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(
    `<script\\b[^>]*id=["']${escapedId}["'][^>]*>([\\s\\S]*?)<\\/script>`,
    "i",
  );
  const match = pattern.exec(String(html || ""));
  if (!match) return fallback;
  try {
    return JSON.parse(htmlDecode(match[1]));
  } catch (_error) {
    return fallback;
  }
}

export function parseJsonBody(response, fallback) {
  try {
    return JSON.parse(String((response && response.body) || ""));
  } catch (_error) {
    return fallback;
  }
}

export function cookieHeaderForUrl(url) {
  const values = http.cookieJar().cookiesForURL(url || BASE_URL) || {};
  return Object.keys(values)
    .filter((name) => values[name] && values[name].length)
    .map((name) => `${name}=${values[name][0]}`)
    .join("; ");
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

// Portal split: /accounts/login/ is a CHOOSER; real forms are role-gated.
// Students authenticate at /accounts/login/telebe/, staff at /accounts/login/muellim/.
export const LOGIN_PATH = __ENV.K6_LOGIN_PATH || "/accounts/login/telebe/";

export function login(user, options) {
  const opts = options || {};
  if (opts.clearCookies !== false) clearAuthCookies();

  const loginUrl = absoluteUrl(opts.loginPath || LOGIN_PATH);
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

  const optionLabelRe = /<label\b[^>]*class\s*=\s*['"][^'"]*option-card[^'"]*['"][^>]*>([\s\S]*?)<\/label>/gi;
  while ((match = optionLabelRe.exec(html || "")) !== null) {
    const fragment = match[1];
    const input = /<input\b[^>]*name\s*=\s*['"]q_(\d+)['"][^>]*>/i.exec(fragment);
    if (!input) continue;
    const qid = input[1];
    const value = attrValue(input[0], "value");
    const labelMatch = /<span\b[^>]*class\s*=\s*['"][^'"]*opt-text[^'"]*['"][^>]*>([\s\S]*?)<\/span>/i.exec(
      fragment,
    );
    byId[qid] = byId[qid] || { id: qid, options: [], kind: "unknown" };
    byId[qid].optionLabels = byId[qid].optionLabels || {};
    if (value && labelMatch) byId[qid].optionLabels[value] = stripHtml(labelMatch[1]);
  }

  return Object.keys(byId)
    .sort((a, b) => parseInt(a, 10) - parseInt(b, 10))
    .map((id) => byId[id]);
}

function regexEscape(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function normalAnswerPersisted(html, question, expectedValue) {
  if (question.options && question.options.length) {
    const tags = String(html || "").match(/<input\b[^>]*>/gi) || [];
    return tags.some((tag) => {
      const name = attrValue(tag, "name");
      const value = attrValue(tag, "value");
      return name === `q_${question.id}` && value === String(expectedValue) && /\bchecked\b/i.test(tag);
    });
  }
  const pattern = new RegExp(
    `<textarea\\b[^>]*name=["']q_${regexEscape(question.id)}["'][^>]*>([\\s\\S]*?)<\\/textarea>`,
    "i",
  );
  const match = pattern.exec(String(html || ""));
  return !!match && htmlDecode(match[1]).includes(String(expectedValue));
}

export function normalAnswerVisibleInResult(html, question, expectedValue) {
  const body = String(html || "");
  if (!(question.options && question.options.length)) {
    return htmlDecode(body).includes(String(expectedValue));
  }
  const selectedLabel = (question.optionLabels || {})[String(expectedValue)] || "";
  const selectedItems = [];
  const itemRe = /<li\b[^>]*class\s*=\s*['"][^'"]*(?:correct-selected|wrong-selected)[^'"]*['"][^>]*>([\s\S]*?)<\/li>/gi;
  let match;
  while ((match = itemRe.exec(body)) !== null) selectedItems.push(stripHtml(match[1]));
  if (!selectedItems.length) return false;
  if (!selectedLabel) return true;
  return selectedItems.some((item) => item.includes(selectedLabel));
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
    resultUrl: jsString("resultUrl"),
    csrfToken: jsString("csrfToken"),
    selectedLanguage: jsString("selectedLanguage") || "python",
    attemptId: jsString("attemptId"),
  };
}

export function parseCodingQuestions(html) {
  const rows = parseJsonScript(html, "coding-questions", []);
  return Array.isArray(rows) ? rows : [];
}

export function codingSourceFor(language, marker) {
  const custom = __ENV.K6_CODING_CONTENT;
  if (custom) return custom.replace(/\{\{MARKER\}\}/g, marker);
  if (language === "javascript") return `// ${marker}\nconsole.log(${JSON.stringify(marker)});\n`;
  if (language === "cpp") {
    return `// ${marker}\n#include <iostream>\nint main(){std::cout << ${JSON.stringify(marker)}; return 0;}\n`;
  }
  if (language === "java") {
    return `// ${marker}\nclass Main { public static void main(String[] args) { System.out.print(${JSON.stringify(
      marker,
    )}); } }\n`;
  }
  if (language === "html") return `<!-- ${marker} -->\n<p>${marker}</p>\n`;
  return `# ${marker}\nprint(${JSON.stringify(marker)})\n`;
}

export function buildCodingQuestionPayload(question, marker) {
  const selectedLanguage = question.selected_language || question.language || "python";
  const originalFiles = question.initial_files || question.starter_files || [];
  const files = originalFiles.length
    ? originalFiles.map((item, index) => ({
        name: item.name,
        content: index === 0 ? codingSourceFor(selectedLanguage, marker) : item.content || "",
      }))
    : [
        {
          name: __ENV.K6_CODING_FILE_NAME || (selectedLanguage === "javascript" ? "main.js" : "main.py"),
          content: codingSourceFor(selectedLanguage, marker),
        },
      ];
  return {
    question_id: question.id,
    selected_language: selectedLanguage,
    active_file_name: files[0].name,
    files,
    stdin: "",
  };
}

export function sleepSeconds(minSeconds, maxSeconds) {
  const min = Number(minSeconds);
  const max = Number(maxSeconds);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return min || 1;
  return min + Math.random() * (max - min);
}
