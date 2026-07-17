/**
 * WebSocket connection-storm load test for the EMSArena real-time exam sockets
 * (Django Channels / daphne / ASGI).
 *
 * WHAT IT EXERCISES
 *   Each VU authenticates over HTTP exactly like a browser (session cookie via
 *   login()), then opens ONE Channels WebSocket and holds it open while
 *   counting handshake latency, failures and inbound frames. This measures how
 *   many concurrent ASGI sockets the server sustains — the dimension the plain
 *   HTTP flow tests cannot see.
 *
 * SOCKETS (config/asgi.py -> apps/exams/routing.py). All authenticate through
 * AuthMiddlewareStack (session cookie in the handshake headers; there is NO
 * query-param token):
 *   /ws/exams/supervision/<attempt_id>/  DEFAULT. What a STUDENT's browser opens
 *       during a supervised "test" attempt (static/exams/js/exam_supervision/
 *       websocket.js). Read-only: the server pushes lock/resume/stop events and
 *       the client sends NOTHING, so no heartbeat is emitted for this channel.
 *       Auth: the user must OWN the attempt (or be its exam author / superadmin),
 *       and EXAM_SUPERVISION_ENABLED must be true (else the consumer closes 4403).
 *   /ws/exams/final/room/<session_id>/   STAFF-only room monitor. Client sends
 *       {"action":"ping"} and the server replies {"event":"pong"}.
 *   /ws/exams/final/wait/<ticket_id>/    Final waiting-room presence socket
 *       (static/.../final_center/waiting_room.js). Client sends
 *       {"action":"heartbeat"}; the consumer silently drops messages arriving
 *       faster than every 3s. Auth also requires a validated final-entry state
 *       in the Django session, so this channel is only reachable after the HTTP
 *       final-entry flow (see final-exam-center-test.js).
 *
 *   Because each path embeds a per-resource id AND the consumer enforces
 *   per-user ownership, a shared id only authorizes its owner. For a realistic
 *   N-VU run either (a) let each VU open its own supervision attempt via the
 *   full-flow gating (K6_TEST_EXAM_SLUG + K6_ALLOW_EXAM_START=true), or (b)
 *   override the path per resource. WS_PATH overrides the whole path verbatim
 *   (e.g. /ws/exams/final/wait/123/); heartbeat is auto-selected from the path.
 *
 * PROFILES (K6_PROFILE -> lib/profiles.js WS_PROFILES: ws-smoke, ws-1000,
 * ws-reconnect-1000). The profile's scenario name binds to the matching export:
 *   websocket           connect, hold WS_HOLD_SECONDS (default 60), clean close.
 *   websocket_reconnect connect / hold WS_RECONNECT_HOLD_SECONDS (default 5) /
 *                       close, looped for WS_HOLD_SECONDS total (connection churn).
 *
 * METRICS / THRESHOLDS (lib/profiles.js websocketThresholds)
 *   ws_connecting            handshake duration (BUILT-IN k6/ws Trend).
 *   ws_session_duration      open-socket lifetime (BUILT-IN k6/ws Trend).
 *   websocket_connection_failures  custom Counter (handshake rejects + consumer
 *       4xxx closes + socket errors). ws_connecting / ws_session_duration are
 *       reserved k6/ws built-ins emitted automatically — redefining them aborts
 *       the run, so only the failure counter is declared here.
 *
 * RUN EXAMPLES (LAN target, self-signed TLS)
 *   # 1-socket smoke on the supervision channel (needs a real attempt id)
 *   BASE_URL=https://10.0.2.42 K6_INSECURE_SKIP_TLS_VERIFY=true \
 *   K6_USERS_FILE=/abs/path/k6/data/stress-users.json \
 *   K6_PROFILE=ws-smoke K6_ATTEMPT_ID=1234 \
 *     k6 run k6/websocket-load-test.js
 *
 *   # 1000 concurrent sockets, each VU opens its own supervision attempt
 *   BASE_URL=https://10.0.2.42 K6_INSECURE_SKIP_TLS_VERIFY=true \
 *   K6_USERS_FILE=/abs/path/k6/data/stress-users.json \
 *   K6_PROFILE=ws-1000 K6_TEST_EXAM_SLUG=k6-loadtest K6_ALLOW_EXAM_START=true \
 *   WS_HOLD_SECONDS=120 \
 *     k6 run k6/websocket-load-test.js
 *
 *   # 1000 sockets against the staff room monitor via explicit path override
 *   BASE_URL=https://10.0.2.42 K6_INSECURE_SKIP_TLS_VERIFY=true \
 *   K6_USERS_FILE=/abs/path/k6/data/staff-users.json \
 *   K6_PROFILE=ws-1000 WS_PATH=/ws/exams/final/room/42/ \
 *     k6 run k6/websocket-load-test.js
 *
 *   # 1000 reconnecting sockets (connection churn)
 *   BASE_URL=https://10.0.2.42 K6_INSECURE_SKIP_TLS_VERIFY=true \
 *   K6_USERS_FILE=/abs/path/k6/data/stress-users.json \
 *   K6_PROFILE=ws-reconnect-1000 K6_TEST_EXAM_SLUG=k6-loadtest \
 *   K6_ALLOW_EXAM_START=true WS_HOLD_SECONDS=60 WS_RECONNECT_HOLD_SECONDS=5 \
 *     k6 run k6/websocket-load-test.js
 */

import ws from "k6/ws";
import { check, fail, sleep } from "k6";
import { Counter } from "k6/metrics";

import {
  BASE_URL,
  absoluteUrl,
  cookieHeaderForUrl,
  floatEnv,
  getOrStartAttempt,
  intEnv,
  loadedUserCount,
  login,
  pickUser,
} from "./lib/emsarena.js";
import {
  assertCredentialCapacity,
  requireWebSocketProfile,
  websocketThresholds,
} from "./lib/profiles.js";

const profile = requireWebSocketProfile();
assertCredentialCapacity(profile, loadedUserCount());

// The WS profiles use scenario keys "websocket" and "websocket_reconnect";
// bind each scenario to the exported function of the same name so the reconnect
// profile actually churns connections instead of falling through to default().
const scenarios = {};
Object.keys(profile.options.scenarios).forEach((name) => {
  scenarios[name] = Object.assign({}, profile.options.scenarios[name], { exec: name });
});

export const options = Object.assign({}, profile.options, {
  scenarios,
  thresholds: websocketThresholds,
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max"],
});

// ws_connecting and ws_session_duration are BUILT-IN k6/ws Trends (emitted
// automatically); only the failure counter referenced by websocketThresholds
// and a couple of observability counters are custom.
const connectionFailures = new Counter("websocket_connection_failures");
const sessionsOpened = new Counter("websocket_sessions_opened");
const messagesReceived = new Counter("websocket_messages_received");
const reconnectCycles = new Counter("websocket_reconnect_cycles");

// Task-specified primary env names, with the K6_-prefixed aliases kept for
// back-compat with earlier runs.
const holdSeconds = intEnv("WS_HOLD_SECONDS", intEnv("K6_WS_HOLD_SECONDS", 60));
const reconnectHoldSeconds = floatEnv(
  "WS_RECONNECT_HOLD_SECONDS",
  floatEnv("K6_WS_RECONNECT_HOLD_SECONDS", 5),
);
const reconnectPauseSeconds = floatEnv(
  "WS_RECONNECT_PAUSE_SECONDS",
  floatEnv("K6_WS_RECONNECT_PAUSE_SECONDS", 0.5),
);
// AllowedHostsOriginValidator rejects a missing/foreign Origin unless
// ALLOWED_HOSTS contains "*"; default it to the target host.
const wsOrigin = (__ENV.WS_ORIGIN || BASE_URL).replace(/\/+$/, "");

function ensureSession() {
  const result = login(pickUser(), { clearCookies: true });
  return check(result.response, {
    "ws login succeeded": () => result.success && result.hasSession,
  });
}

function resolveWsPath() {
  // Explicit override wins: any channel (e.g. /ws/exams/final/wait/<ticket_id>/).
  const override = __ENV.WS_PATH || __ENV.K6_WS_PATH;
  if (override) return "/" + String(override).replace(/^\/+/, "");

  // Default: each VU connects to its own attempt's supervision channel.
  const slug = __ENV.K6_TEST_EXAM_SLUG;
  if (!slug) {
    fail("Set WS_PATH or K6_TEST_EXAM_SLUG (plus K6_ATTEMPT_ID / K6_ALLOW_EXAM_START=true).");
  }
  const attemptUrl = getOrStartAttempt(slug);
  const match = /\/attempt\/(\d+)\//.exec(attemptUrl);
  if (!match) fail(`Attempt id could not be parsed from ${attemptUrl}.`);
  return `/ws/exams/supervision/${match[1]}/`;
}

function heartbeatSecondsFor(wsPath) {
  const configured = floatEnv("WS_HEARTBEAT_SECONDS", floatEnv("K6_WS_HEARTBEAT_SECONDS", NaN));
  if (Number.isFinite(configured)) return configured;
  // The supervision channel does not process inbound frames -> disabled.
  if (wsPath.indexOf("/final/wait/") !== -1 || wsPath.indexOf("/final/room/") !== -1) return 15;
  return 0;
}

function heartbeatActionFor(wsPath) {
  const override = __ENV.WS_HEARTBEAT_ACTION || __ENV.K6_WS_HEARTBEAT_ACTION;
  if (override) return override;
  // The staff room monitor answers "ping"; the student waiting room uses "heartbeat".
  return wsPath.indexOf("/final/room/") !== -1 ? "ping" : "heartbeat";
}

function connectOnce(wsPath, holdFor) {
  // https://host -> wss://host, http://host -> ws://host
  const url = absoluteUrl(wsPath).replace(/^http/i, "ws");
  const heartbeatSeconds = heartbeatSecondsFor(wsPath);
  const heartbeatAction = heartbeatActionFor(wsPath);
  let rejectedCode = 0;
  let sawError = false;
  let intentionalClose = false;

  const response = ws.connect(
    url,
    {
      headers: {
        // Session cookie is how AuthMiddlewareStack authenticates the socket.
        Cookie: cookieHeaderForUrl(BASE_URL),
        Origin: wsOrigin,
        "User-Agent": __ENV.K6_USER_AGENT || "EMSArena-k6-loadtest/1.0",
      },
      tags: { endpoint: "exam_ws", class: "ws" },
    },
    (socket) => {
      socket.on("open", () => {
        sessionsOpened.add(1);
        if (heartbeatSeconds > 0) {
          socket.setInterval(() => {
            socket.send(JSON.stringify({ action: heartbeatAction }));
          }, heartbeatSeconds * 1000);
        }
        socket.setTimeout(() => {
          intentionalClose = true;
          socket.close(1000);
        }, holdFor * 1000);
      });
      socket.on("message", () => {
        messagesReceived.add(1);
      });
      socket.on("close", (code) => {
        // 4400/4401/4403 — consumer-level rejection (bad id / auth / feature flag).
        if (Number(code) >= 4000) rejectedCode = Number(code);
      });
      socket.on("error", () => {
        // k6 raises a benign error when we close the socket ourselves; ignore
        // only that case and count everything else.
        if (!intentionalClose) sawError = true;
      });
    },
  );

  // A rejected handshake (AllowedHostsOriginValidator denier, 4xx, TLS, …) never
  // fires "open"; response.status carries the HTTP upgrade status (101 = success).
  const upgraded = !!response && response.status === 101;
  const ok = check(response, {
    "ws handshake upgraded (101)": () => upgraded,
    "ws not rejected by consumer (4xxx)": () => rejectedCode === 0,
  });
  if (!upgraded || rejectedCode || sawError) {
    connectionFailures.add(1);
    // eslint-disable-next-line no-console
    console.warn(
      `ws failure url=${url} status=${response ? response.status : "n/a"} ` +
        `closeCode=${rejectedCode} error=${sawError}`,
    );
  }
  return ok;
}

export function websocket() {
  if (!ensureSession()) {
    connectionFailures.add(1);
    return;
  }
  const wsPath = resolveWsPath();
  connectOnce(wsPath, holdSeconds);
}

export function websocket_reconnect() {
  if (!ensureSession()) {
    connectionFailures.add(1);
    return;
  }
  const wsPath = resolveWsPath();
  const startedAt = Date.now();
  while ((Date.now() - startedAt) / 1000 < holdSeconds) {
    if (!connectOnce(wsPath, reconnectHoldSeconds)) break;
    reconnectCycles.add(1);
    sleep(reconnectPauseSeconds);
  }
}
