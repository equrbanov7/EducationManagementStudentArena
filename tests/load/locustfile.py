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

import itertools
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

#: Hesab hovuzu. Boş olsa köhnə davranış qalır (hamı `LOAD_USERNAME` ilə girir).
#:
#: NİYƏ HOVUZ: minlərlə VU eyni hesabla girəndə ölçdüyümüz şey tətbiqin tutumu
#: yox, HƏMİN BİR SƏTRİN üzərindəki yarışma olur — `last_login` UPDATE-i,
#: sessiya yazısı və login throttle sayğacı eyni açarı döyür. Nəticə süni
#: darboğazdır: server sağlam olsa belə rəqəmlər pisləşir. Hovuzla hər VU
#: `stress0001…stressNNNN` kimi ayrıca hesab götürür — real imtahan günü
#: mənzərəsi budur.
_USER_PREFIX: str = os.environ.get("LOAD_USER_PREFIX", "")
_USER_COUNT: int = int(os.environ.get("LOAD_USER_COUNT", "0") or 0)
_USER_PAD: int = int(os.environ.get("LOAD_USER_PAD", "4") or 4)

#: Hovuzdan növbəti hesabı verən sayğac. Locust worker-ləri AYRI prosesdir,
#: ona görə hər worker öz hovuz zolağından başlasın deyə `LOAD_USER_OFFSET`
#: worker başına fərqli verilir (workflow bunu avtomatik edir).
_user_cursor = itertools.count(int(os.environ.get("LOAD_USER_OFFSET", "0") or 0))

#: LAN prod-u SAN self-signed sertifikatla işləyir. Sertifikat yoxlaması yalnız
#: `localhost`-a vuranda söndürülür (trafik maşından çıxmır) — kənar hədəfə
#: heç vaxt yoxlamasız vurmuruq.
_INSECURE_TLS: bool = os.environ.get("LOAD_INSECURE_TLS", "") == "1"

if _INSECURE_TLS:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class _TlsAwareHttpUser(HttpUser):
    """Sertifikat yoxlamasını `LOAD_INSECURE_TLS` ilə idarə edən baza sinfi."""

    abstract = True

    def on_start(self):
        if _INSECURE_TLS:
            self.client.verify = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_csrf(html: str) -> str:
    """Extract the CSRF token value from a Django HTML form."""
    match = re.search(r'csrfmiddlewaretoken.*?value="([^"]+)"', html)
    return match.group(1) if match else ""


def _next_credentials() -> tuple[str, str]:
    """Bu VU üçün istifadəçi adı/parol — hovuz varsa növbəti hesab."""
    if not (_USER_PREFIX and _USER_COUNT):
        return _USERNAME, _PASSWORD
    index = next(_user_cursor) % _USER_COUNT
    return f"{_USER_PREFIX}{index + 1:0{_USER_PAD}d}", _PASSWORD


def _login(user, label: str) -> None:
    """Login axını — CSRF al, POST et, nəticəni AÇIQ yoxla.

    `catch_response` olmadan Django login POST-u 200 qaytarır (formu səhv
    etimadnamə ilə yenidən göstərir) və locust bunu UĞUR sayır. Onda yük testi
    «hər şey yaşıl» deyir, halbuki heç kim daxil ola bilməyib. Ona görə
    yönləndirmə olub-olmadığını yoxlayırıq.
    """
    username, password = _next_credentials()
    resp = user.client.get("/accounts/login/", name=f"{label} Login GET")
    csrf = _extract_csrf(resp.text)
    with user.client.post(
        "/accounts/login/",
        data={"username": username, "password": password, "csrfmiddlewaretoken": csrf},
        headers={"Referer": user.host + "/accounts/login/"},
        name=f"{label} Login POST",
        catch_response=True,
        allow_redirects=False,
    ) as post:
        if post.status_code in (301, 302):
            post.success()
        elif post.status_code == 200:
            post.failure("giriş formu geri qayıtdı — etimadnamə qəbul edilmədi")
        else:
            post.failure(f"gözlənilməz status: {post.status_code}")


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


class AnonymousUser(_TlsAwareHttpUser):
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


class StudentUser(_TlsAwareHttpUser):
    """Simulates an authenticated student: login → dashboard → courses."""

    wait_time = between(1, 4)

    def on_start(self):
        super().on_start()
        _login(self, "[student]")

    @task(5)
    def dashboard(self):
        self.client.get("/", name="[student] Dashboard")

    @task(3)
    def course_list(self):
        # `/courses/` marşrutu YOXDUR (kök URL təyin olunmayıb) — siyahı
        # `/courses/my-courses/`-dadır. Köhnə yazılış hər sorğuda 404 alırdı və
        # yük testi «%88 uğursuz» göstərirdi: rəqəm tətbiqin deyil, ssenarinin
        # qüsuru idi.
        self.client.get("/courses/my-courses/", name="[student] Course list")

    @task(2)
    def course_dashboard(self):
        if not _COURSE_ID or _COURSE_ID == "0":
            return  # kurs ID verilməyibsə bu addımı buraxırıq (saxta 404 yaratmasın)
        self.client.get(f"/courses/{_COURSE_ID}/dashboard/", name="[student] Course detail")

    @task(1)
    def notifications(self):
        self.client.get("/notifications/", name="[student] Notifications")

    def on_stop(self):
        # CSRF cookie-dən oxunur. Boş token göndərmək 403 verirdi — Django
        # cookie ilə YANAŞI formada da token tələb edir.
        self.client.post(
            "/accounts/logout/",
            data={"csrfmiddlewaretoken": self.client.cookies.get("csrftoken", "")},
            headers={"Referer": self.host + "/"},
            name="[student] Logout",
        )


class LiveExamJoiner(_TlsAwareHttpUser):
    """Simulates a student joining a live exam session by PIN."""

    wait_time = between(0.5, 2)

    def on_start(self):
        super().on_start()
        _login(self, "[live]")

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


class LiveExamPlayer(_TlsAwareHttpUser):
    """Simulates a player already in a live session polling for state updates.

    Models the JavaScript polling loop that calls /api/v1/live/<pin>/state/
    approximately every 500 ms.  The rate limit is 120 requests/minute so
    this scenario deliberately stays below that threshold.
    """

    wait_time = between(0.5, 1.0)  # ~60–120 req/min per user

    def on_start(self):
        super().on_start()
        _login(self, "[player]")

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


class AnswerSubmitter(_TlsAwareHttpUser):
    """Simulates a player submitting answers during a live exam.

    The live exam answer endpoint is WebSocket-based in production; this
    class approximates the load via the HTTP fallback/API endpoint.  Use
    dedicated WebSocket tooling (e.g. locust-plugins ws) for full WS load
    testing.
    """

    wait_time = between(10, 30)  # Players answer every 10–30 s per question

    def on_start(self):
        super().on_start()
        # Bu sinif `_login()`-dən istifadə ETMİR: sonrakı mutasiya sorğuları
        # üçün login CAVABININ gövdəsindən CSRF çıxarır, `_login()` isə
        # `allow_redirects=False` ilə işləyir və gövdə boş qalır.
        username, password = _next_credentials()
        resp = self.client.get("/accounts/login/")
        csrf = _extract_csrf(resp.text)
        login_resp = self.client.post(
            "/accounts/login/",
            data={
                "username": username,
                "password": password,
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


class ProfileSpaUser(_TlsAwareHttpUser):
    """Profil SPA — müəllim/imtahan mərkəzi işçisinin əsl gündəlik axını.

    Bu sinif audit zamanı əlavə olundu: «İmtahanlarım» bölməsi səhifələndi və
    KPI kartları ayrıca aqreqat sorğulara keçirildi. Həmin dəyişikliyin yük
    altında da qazanc verdiyini görmək üçün fraqment endpoint-i birbaşa vurulur
    — istifadəçi bölmələr arasında keçəndə brauzer məhz bunu çağırır.
    """

    wait_time = between(1, 3)

    def on_start(self):
        super().on_start()
        _login(self, "[profile]")

    @task(4)
    def my_exams(self):
        self.client.get("/accounts/profile/api/sections/my-exams/", name="[profile] my-exams fraqment")

    @task(2)
    def my_exams_page_two(self):
        self.client.get(
            "/accounts/profile/api/sections/my-exams/?exam_page=2",
            name="[profile] my-exams səhifə 2",
        )

    @task(2)
    def my_courses(self):
        self.client.get("/accounts/profile/api/sections/my-courses/", name="[profile] my-courses fraqment")

    @task(1)
    def full_page(self):
        self.client.get("/accounts/profile/", name="[profile] tam səhifə")
