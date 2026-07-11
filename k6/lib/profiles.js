import { fail } from "k6";

const HTTP_PROFILES = {
  smoke: {
    targetVus: 1,
    options: {
      scenarios: {
        full_exam: {
          executor: "per-vu-iterations",
          vus: 1,
          iterations: 1,
          maxDuration: "2m",
        },
      },
    },
  },
  "steady-100": {
    targetVus: 100,
    options: {
      scenarios: {
        full_exam: {
          executor: "constant-vus",
          vus: 100,
          duration: "30m",
          gracefulStop: "2m",
        },
      },
    },
  },
  "steady-500": {
    targetVus: 500,
    options: {
      scenarios: {
        full_exam: {
          executor: "constant-vus",
          vus: 500,
          duration: "15m",
          gracefulStop: "2m",
        },
      },
    },
  },
  "spike-1000": {
    targetVus: 1000,
    options: {
      scenarios: {
        full_exam: {
          executor: "ramping-vus",
          startVUs: 0,
          stages: [
            { duration: "30s", target: 1000 },
            { duration: "2m", target: 1000 },
            { duration: "30s", target: 0 },
          ],
          gracefulRampDown: "30s",
        },
      },
    },
  },
  "soak-1h": {
    targetVus: 100,
    options: {
      scenarios: {
        full_exam: {
          executor: "constant-vus",
          vus: 100,
          duration: "1h",
          gracefulStop: "3m",
        },
      },
    },
  },
};

const WS_PROFILES = {
  "ws-smoke": {
    targetVus: 1,
    options: {
      scenarios: {
        websocket: {
          executor: "per-vu-iterations",
          vus: 1,
          iterations: 1,
          maxDuration: "2m",
        },
      },
    },
  },
  "ws-1000": {
    targetVus: 1000,
    options: {
      scenarios: {
        websocket: {
          executor: "per-vu-iterations",
          vus: 1000,
          iterations: 1,
          maxDuration: "10m",
        },
      },
    },
  },
  "ws-reconnect-1000": {
    targetVus: 1000,
    options: {
      scenarios: {
        websocket_reconnect: {
          executor: "per-vu-iterations",
          vus: 1000,
          iterations: 1,
          maxDuration: "10m",
        },
      },
    },
  },
};

function selectedProfile(table, kind) {
  const name = (__ENV.K6_PROFILE || "").trim();
  if (!name) {
    fail(
      `K6_PROFILE is required for ${kind}. ` +
        `Allowed profiles: ${Object.keys(table).join(", ")}.`,
    );
  }
  const profile = table[name];
  if (!profile) {
    fail(`Unknown K6_PROFILE=${name}. Allowed profiles: ${Object.keys(table).join(", ")}.`);
  }
  return { name, targetVus: profile.targetVus, options: profile.options };
}

export function requireHttpProfile() {
  return selectedProfile(HTTP_PROFILES, "full exam HTTP flow");
}

export function requireWebSocketProfile() {
  return selectedProfile(WS_PROFILES, "WebSocket flow");
}

export function assertCredentialCapacity(profile, loadedUsers) {
  if (loadedUsers >= profile.targetVus) return;
  const explicitlyReused = ["1", "true", "yes"].includes(
    String(__ENV.K6_ALLOW_USER_REUSE || "").toLowerCase(),
  );
  if (!explicitlyReused) {
    fail(
      `K6_PROFILE=${profile.name} requires at least ${profile.targetVus} credential rows; ` +
        `only ${loadedUsers} loaded. Seed dedicated users or explicitly set K6_ALLOW_USER_REUSE=true.`,
    );
  }
}

export const commonThresholds = {
  http_req_failed: ["rate<0.01"],
  "http_req_duration{class:normal}": ["p(95)<1500", "p(99)<3000"],
  "http_req_duration{class:exam}": ["p(95)<2500", "p(99)<5000"],
  "http_req_duration{class:reconcile}": ["p(95)<2500", "p(99)<5000"],
  checks: ["rate>0.99"],
  exam_data_loss_rate: ["rate==0"],
};

export const websocketThresholds = {
  checks: ["rate>0.99"],
  ws_connecting: ["p(95)<2000", "p(99)<5000"],
  ws_session_duration: ["p(95)>1000"],
  websocket_connection_failures: ["count==0"],
};
