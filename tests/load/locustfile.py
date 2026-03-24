"""
EMS Arena — Load Testing Infrastructure (Locust)
=================================================

Reusable load-test scenarios covering the platform's most traffic-intensive
user flows:

  1. **PingUser**         – Liveness probe; sets the performance baseline.
  2. **AnonymousUser**    – Unauthenticated public-facing pages (login, blog).
  3. **StudentUser**      – Login → dashboard → course navigation.
  4. **LiveExamJoiner**   – Join a live exam session by PIN.
  5. **LiveExamPlayer**   – Poll live session state at the rate-limited cadence.
  6. **AnswerSubmitter**  – Submit answers during a live exam (WebSocket flow
                            approximated via HTTP endpoint for baseline).

Usage
-----
Install locust (already in requirements/local.txt) and run:

.. code-block:: bash

    # Quick smoke test (10 users, ramp up 2/s, run for 30 s)
    locust --headless --users 10 --spawn-rate 2 --run-time 30s \\
           --host http://localhost:8000 \\
           -f tests/load/locustfile.py

    # Interactive web UI (open http://localhost:8089)
    locust --host http://localhost:8000 -f tests/load/locustfile.py

    # Target a specific user class
    locust --host http://localhost:8000 -f tests/load/locustfile.py \\
           --headless --users 20 --spawn-rate 5 --run-time 60s \\
           StudentUser

Environment variables
---------------------
``LOAD_USERNAME``   – Username or email for authenticated test users
                      (default: ``testuser``).
``LOAD_PASSWORD``   – Password for authenticated test users
                      (default: ``testpass123``).
``LOAD_LIVE_PIN``   – 10-character PIN of an active live-exam session for
                      ``LiveExamJoiner``/``LiveExamPlayer`` scenarios
                      (default: ``AAAA111111``).
``LOAD_COURSE_ID``  – Numeric course ID to exercise the course dashboard
                      (default: ``1``).
"""

from __future__ import annotations

import os
import re

from locust import HttpUser, between, events, task
from locust.contrib.fasthttp import FastHttpUser

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
_USERNAME: str = os.environ.get("LOAD_USERNAME", "testuser")
_PASSWORD: str = os.environ.get("LOAD_PASSWORD", "testpass123")
_LIVE_PIN: str = os.environ.get("LOAD_LIVE_PIN", "AAAA111111")
_COURSE_ID: str = os.environ.get("LOAD_COURSE_ID", "1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_csrf(html: str) -> str:
    """Extract the CSRF token value from a Django HTML form."""
    match = re.search(r'csrfmiddlewaretoken.*?value="([^"]+)"', html)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# User classes
# ---------------------------------------------------------------------------


class PingUser(FastHttpUser):
    """Hits /ping/ only – pure liveness baseline with minimal overhead.

    Use this class to establish a performance floor before adding
    business-logic scenarios.
    """

    wait_time = between(0.1, 0.5)

    @task
    def ping(self):
        with self.client.get("/ping/", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Expected 200, got {resp.status_code}")


class AnonymousUser(HttpUser):
    """Simulates an unauthenticated visitor browsing public pages."""

    wait_time = between(1, 3)

    @task(5)
    def home(self):
        self.client.get("/", name="[anon] Home")

    @task(3)
    def login_page(self):
        self.client.get("/accounts/login/", name="[anon] Login page")

    @task(1)
    def health(self):
        with self.client.get("/health/", catch_response=True, name="[anon] Health") as resp:
            if resp.status_code not in (200, 207):
                resp.failure(f"Health check failed: {resp.status_code}")


class StudentUser(HttpUser):
    """Simulates an authenticated student: login → dashboard → courses."""

    wait_time = between(1, 4)

    def on_start(self):
        """Log in before running tasks."""
        # Fetch login page to obtain CSRF token
        resp = self.client.get("/accounts/login/")
        csrf = _extract_csrf(resp.text)
        self.client.post(
            "/accounts/login/",
            data={
                "username": _USERNAME,
                "password": _PASSWORD,
                "csrfmiddlewaretoken": csrf,
            },
            headers={"Referer": self.host + "/accounts/login/"},
            name="[student] Login POST",
        )

    @task(5)
    def dashboard(self):
        self.client.get("/", name="[student] Dashboard")

    @task(3)
    def course_list(self):
        self.client.get("/courses/", name="[student] Course list")

    @task(2)
    def course_dashboard(self):
        self.client.get(f"/courses/{_COURSE_ID}/", name="[student] Course detail")

    @task(1)
    def notifications(self):
        self.client.get("/notifications/", name="[student] Notifications")

    def on_stop(self):
        self.client.post(
            "/accounts/logout/",
            data={"csrfmiddlewaretoken": ""},  # CSRF handled by cookie
            name="[student] Logout",
        )


class LiveExamJoiner(HttpUser):
    """Simulates a student joining a live exam session by PIN."""

    wait_time = between(0.5, 2)

    def on_start(self):
        resp = self.client.get("/accounts/login/")
        csrf = _extract_csrf(resp.text)
        self.client.post(
            "/accounts/login/",
            data={
                "username": _USERNAME,
                "password": _PASSWORD,
                "csrfmiddlewaretoken": csrf,
            },
            headers={"Referer": self.host + "/accounts/login/"},
            name="[live] Login",
        )

    @task(10)
    def join_session(self):
        """POST to the live exam join endpoint with a known PIN."""
        resp = self.client.get(f"/join/{_LIVE_PIN}/", name="[live] Join page GET")
        csrf = _extract_csrf(resp.text)
        self.client.post(
            f"/join/{_LIVE_PIN}/",
            data={"pin": _LIVE_PIN, "csrfmiddlewaretoken": csrf},
            headers={"Referer": self.host + f"/join/{_LIVE_PIN}/"},
            name="[live] Join POST",
        )

    @task(1)
    def state_poll(self):
        self.client.get(
            f"/api/v1/live/{_LIVE_PIN}/state/",
            name="[live] State poll",
        )


class LiveExamPlayer(HttpUser):
    """Simulates a player already in a live session polling for state updates.

    Models the JavaScript polling loop that calls /api/v1/live/<pin>/state/
    approximately every 500 ms.  The rate limit is 120 requests/minute so
    this scenario deliberately stays below that threshold.
    """

    wait_time = between(0.5, 1.0)  # ~60–120 req/min per user

    def on_start(self):
        resp = self.client.get("/accounts/login/")
        csrf = _extract_csrf(resp.text)
        self.client.post(
            "/accounts/login/",
            data={
                "username": _USERNAME,
                "password": _PASSWORD,
                "csrfmiddlewaretoken": csrf,
            },
            headers={"Referer": self.host + "/accounts/login/"},
            name="[player] Login",
        )

    @task
    def poll_state(self):
        with self.client.get(
            f"/api/v1/live/{_LIVE_PIN}/state/",
            catch_response=True,
            name="[player] State poll",
        ) as resp:
            if resp.status_code == 429:
                # Rate limited — this is expected under high concurrency;
                # mark as a warning rather than a failure so Locust does not
                # count it as an error in aggregate stats.
                resp.success()
            elif resp.status_code not in (200, 204):
                resp.failure(f"Unexpected status {resp.status_code}")


class AnswerSubmitter(HttpUser):
    """Simulates a player submitting answers during a live exam.

    The live exam answer endpoint is WebSocket-based in production; this
    class approximates the load via the HTTP fallback/API endpoint.  Use
    dedicated WebSocket tooling (e.g. locust-plugins ws) for full WS load
    testing.
    """

    wait_time = between(10, 30)  # Players answer every 10–30 s per question

    def on_start(self):
        resp = self.client.get("/accounts/login/")
        csrf = _extract_csrf(resp.text)
        login_resp = self.client.post(
            "/accounts/login/",
            data={
                "username": _USERNAME,
                "password": _PASSWORD,
                "csrfmiddlewaretoken": csrf,
            },
            headers={"Referer": self.host + "/accounts/login/"},
            name="[answer] Login",
        )
        # Extract CSRF for subsequent mutation requests
        self._csrf = _extract_csrf(login_resp.text) if login_resp else ""

    @task
    def submit_answer(self):
        """Submit an answer to the active live exam question."""
        with self.client.post(
            f"/live/{_LIVE_PIN}/answer/",
            json={"answer_index": 0},
            headers={"X-CSRFToken": self._csrf},
            catch_response=True,
            name="[answer] Submit answer",
        ) as resp:
            if resp.status_code in (200, 201, 204):
                resp.success()
            elif resp.status_code == 400:
                # Already answered / question locked — expected in load tests
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


# ---------------------------------------------------------------------------
# Event hooks — print a benchmark summary at the end of each run
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def _print_summary(environment, **kwargs):
    stats = environment.stats.total
    if stats.num_requests == 0:
        print("\n[load] No requests completed.")
        return
    print(
        f"\n[load] Summary:"
        f"  requests={stats.num_requests}"
        f"  failures={stats.num_failures}"
        f"  median_ms={stats.median_response_time}"
        f"  p95_ms={stats.get_response_time_percentile(0.95)}"
        f"  rps={stats.total_rps:.1f}"
    )
