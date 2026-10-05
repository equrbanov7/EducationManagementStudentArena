"""`live` rejimi — canlı viktorina (apps/live_exam): host HTTP + oyunçular WebSocket.

  * LiveHost (sabit say = `CAP_LIVE_GAMES`): imtahan müəllifi (sessiya hovuzu) öz
    `cap-live-<run>-<k>` imtahanında sessiya yaradır (PIN), lobbi pəncərəsindən sonra
    «Başla» → hər sual: gözləmə → reveal → next … → finish → nəticələr səhifəsi.
  * LivePlayer: anonim oyunçu — join səhifəsi → `enter` (ləqəb) → lobbi WS
    (`/ws/live/<pin>/lobby/`, `game_started`-ə qədər) + oyun WS (`/ws/live/<pin>/play/`):
    `question_published` → düşünmə → `answer` → `answer_saved`; ping hər 15 s.
    Ölçülər (request_type=WS): bağlantı, sualın çatma gecikməsi (host POST-dan
    oyunçuya — eyni prosesdə, eyni saat), cavab→`answer_saved`.
  Oyun koordinasiyası proses daxilindədir — orkestrator bu rejimdə 1 worker işlədir.
  Gözləntilər `expected-live-*.jsonl` (cap_reconcile → LiveAnswer).
"""

from __future__ import annotations

import itertools
import os
import random
import re
import socket
import time
from datetime import datetime

import gevent
from gevent.event import Event
from locust import between, task

from cap_common import (
    CERT,
    COUNTERS,
    GO_AT,
    ORIGIN,
    SEED,
    SESSIONS,
    START_WINDOW,
    THINK_SCALE,
    _Abort,
    _Base,
    append_jsonl,
    csrf,
    fixture_error,
    parks,
)
from cap_ws import WS, WSClosed

GAMES_N = max(1, int(os.environ.get("CAP_LIVE_GAMES", "1") or 1))
Q_SECONDS = float(os.environ.get("CAP_LIVE_Q_SECONDS", "20") or 20)
QUESTIONS = int(os.environ.get("CAP_LIVE_QUESTIONS", "8") or 8)
GAMES = {k: {"pin": None, "ready": Event(), "q_sent": None} for k in range(GAMES_N)}
PIN_RE = re.compile(r"/live/host/([^/?#]+)/presentation/")
_host_cursor = itertools.count()
_player_cursor = itertools.count()

for _key in ("live_games", "live_players_joined", "live_answers_saved", "live_finished"):
    COUNTERS.setdefault(_key, 0)


def _ws_event(user, name, started, error=None, length=0):
    user.environment.events.request.fire(
        request_type="WS",
        name=name,
        response_time=(time.monotonic() - started) * 1000,
        response_length=length,
        exception=RuntimeError(error) if error else None,
    )


def _sleep(seconds):
    gevent.sleep(max(0.0, seconds * THINK_SCALE))


def _ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _answer_window(server_time, question):
    """(cavab pəncərəsinə qədər saniyə, pəncərənin uzunluğu saniyə)."""
    now, starts, ends = _ts(server_time), _ts(question.get("answer_starts_at")), _ts(question.get("ends_at"))
    if not (now and starts):
        return 0.0, float(question.get("time_limit") or 10)
    wait = max(0.0, (starts - now).total_seconds())
    window = (ends - starts).total_seconds() if ends else float(question.get("time_limit") or 10)
    return wait, max(0.5, window)


class _LiveBase(_Base):
    abstract = True

    def _csrf_headers(self, referer_path):
        return {
            "X-CSRFToken": self.client.cookies.get("csrftoken", ""),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": ORIGIN + referer_path,
        }


class LiveHost(_LiveBase):
    wait_time = between(1, 2)
    weight = 1
    fixed_count = GAMES_N

    @parks
    def on_start(self):
        self.k = next(_host_cursor)
        exams = SEED.get("live_exams") or []
        keys = sorted(SESSIONS or {}, key=int)
        if self.k >= GAMES_N or not exams or not keys:
            fixture_error(self, "live host setup", f"k={self.k} exams={len(exams)} sessions={len(keys)}")
            raise _Abort()
        self.slug = exams[self.k % len(exams)]
        self._client_setup(65000 + self.k, "/exams/")
        self.client.cookies.set("sessionid", SESSIONS[keys[self.k % len(keys)]], path="/")
        create = f"/live/create/{self.slug}/?force_new=1"
        with self.client.get(create, name="live host create (confirm)", catch_response=True, timeout=30) as r:
            token = csrf(r.text)
            if r.status_code != 200 or not token:
                r.failure(f"create confirm: {r.status_code} {r.error}")
                raise _Abort()
        with self.client.post(
            create,
            data={"csrfmiddlewaretoken": token, "force_new": "1"},
            name="live host create",
            allow_redirects=False,
            catch_response=True,
            timeout=30,
        ) as r:
            found = PIN_RE.search(r.headers.get("Location", ""))
            if r.status_code not in (302, 303) or not found:
                r.failure(f"create: {r.status_code} {r.error} → {r.headers.get('Location', '')[:120]}")
                raise _Abort()
            self.pin = found.group(1)
        self.base = f"/live/host/{self.pin}"
        with self.client.get(f"{self.base}/presentation/?controls=1", name="live host presentation", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"presentation: {r.status_code} {r.error}")
                raise _Abort()
        game = GAMES[self.k]
        game["pin"] = self.pin
        game["ready"].set()
        COUNTERS["live_games"] += 1

    def _post(self, action, name, data=None, ok_conflict=False):
        with self.client.post(
            f"{self.base}/{action}/",
            data=data or {},
            headers=self._csrf_headers(f"{self.base}/presentation/"),
            name=name,
            catch_response=True,
            timeout=30,
        ) as r:
            try:
                payload = r.json()
            except Exception:
                payload = {}
            if r.status_code == 200 and payload.get("ok") is True:
                return payload
            if ok_conflict and r.status_code == 409:
                r.success()
                return payload
            r.failure(f"{action}: {r.status_code} {r.error} {str(payload)[:120]}")
            return None

    def _await_reveal(self):
        """Sual öz vaxtında (server auto-reveal) bitənə qədər state poll; gecikərsə əl ilə reveal."""
        deadline = time.monotonic() + Q_SECONDS * 3
        while time.monotonic() < deadline:
            gevent.sleep(2)
            with self.client.get(f"/live/state/{self.pin}/", name="live host state", catch_response=True, timeout=30) as r:
                try:
                    state = r.json().get("state")
                except Exception:
                    state = None
                if r.status_code != 200 or not state:
                    r.failure(f"state: {r.status_code} {r.error}")
                    continue
            if state in ("reveal", "finished"):
                return
        self._post("reveal", "live host reveal", ok_conflict=True)

    @task
    @parks
    def run_game(self):
        # Lobbi: oyunçular `go` pəncərəsində qoşulur.
        delay = GO_AT + START_WINDOW + 15 - time.time()
        if delay > 0:
            gevent.sleep(delay)
        game = GAMES[self.k]
        game["q_sent"] = time.monotonic()
        if self._post("start", "live host start", {"question_count": str(QUESTIONS)}) is None:
            raise _Abort()
        for _ in range(200):
            self._await_reveal()
            _sleep(4)  # reveal/liderlər ekranı
            game["q_sent"] = time.monotonic()
            result = self._post("next", "live host next", ok_conflict=True)
            if result is None or result.get("finished"):
                break
        self._post("finish", "live host finish", ok_conflict=True)
        with self.client.get(f"/live/results/{self.slug}/{self.pin}/", name="live host results", catch_response=True, timeout=60) as r:
            if r.status_code != 200:
                r.failure(f"results: {r.status_code} {r.error}")
        raise _Abort()


class LivePlayer(_LiveBase):
    wait_time = between(1, 2)
    weight = 50

    @parks
    def on_start(self):
        self.seq = next(_player_cursor)
        self.k = self.seq % GAMES_N
        self._client_setup(70000 + self.seq, "/live/")
        if not GAMES[self.k]["ready"].wait(timeout=180):
            fixture_error(self, "live game not ready", f"game {self.k}")
            raise _Abort()
        self.pin = GAMES[self.k]["pin"]
        self.nickname = f"cap{self.seq:05d}"

    def _ws(self, kind):
        scheme = "wss" if self.host.startswith("https") else "ws"
        url = f"{scheme}://{self.host.split('://', 1)[1]}/ws/live/{self.pin}/{kind}/"
        cookies = "; ".join(f"{c.name}={c.value}" for c in self.client.cookies)
        # Origin = Host (AllowedHostsOriginValidator: ALLOWED_HOSTS-da olan host — HTTP sorğuları da «edge»).
        headers = {"Cookie": cookies, "Origin": self.host, "X-Test-Client": self.client.headers.get("X-Test-Client", "")}
        started = time.monotonic()
        try:
            ws = WS(url, headers=headers, timeout=30, cafile=CERT if scheme == "wss" and os.path.exists(CERT) else None)
        except (OSError, WSClosed) as exc:
            _ws_event(self, f"ws {kind} connect", started, error=repr(exc)[:200])
            raise _Abort() from None
        _ws_event(self, f"ws {kind} connect", started)
        return ws

    def _drain_lobby(self, ws):
        try:
            ws.settimeout(300)
            while True:
                if (ws.recv_json() or {}).get("type") == "game_started":
                    break
        except (OSError, WSClosed, ValueError):
            pass
        finally:
            ws.close()

    @task
    @parks
    def play(self):
        self._wait_for_go()
        join = f"/live/join/{self.pin}/"
        with self.client.get(join, name="live join page", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"join page: {r.status_code} {r.error}")
                raise _Abort()
        with self.client.post(
            f"{join}enter/",
            data={"nickname": self.nickname, "csrfmiddlewaretoken": self.client.cookies.get("csrftoken", "")},
            headers=self._csrf_headers(join),
            name="live join enter",
            catch_response=True,
            timeout=30,
        ) as r:
            try:
                ok = r.status_code == 200 and r.json().get("ok") is True
            except Exception:
                ok = False
            if not ok:
                r.failure(f"join enter: {r.status_code} {r.error} {(r.text or '')[:120]!r}")
                raise _Abort()
        COUNTERS["live_players_joined"] += 1
        with self.client.get(f"/live/wait/{self.pin}/", name="live wait room", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"wait room: {r.status_code} {r.error}")
        lobby = self._ws("lobby")
        gevent.spawn(self._drain_lobby, lobby)
        play = self._ws("play")
        try:
            self._play_loop(play)
        finally:
            play.close()
        raise _Abort()

    def _play_loop(self, ws):
        ws.settimeout(15)
        pending = None
        ping_id = 0
        while True:
            try:
                msg = ws.recv_json() or {}
            except socket.timeout:
                ping_id += 1
                ws.send_json({"type": "ping", "id": ping_id})
                continue
            except (OSError, WSClosed, ValueError) as exc:
                _ws_event(self, "ws play closed early", time.monotonic(), error=repr(exc)[:200])
                return
            kind = msg.get("type")
            if kind == "question_published":
                question = msg.get("question") or {}
                sent = GAMES[self.k]["q_sent"]
                if sent is not None:
                    self.environment.events.request.fire(
                        request_type="WS",
                        name="ws question delivery",
                        response_time=(time.monotonic() - sent) * 1000,
                        response_length=0,
                        exception=None,
                    )
                options = [o.get("id") for o in question.get("options") or [] if isinstance(o, dict) and o.get("id")]
                if not options or not question.get("id"):
                    continue
                ws.send_json({"type": "seen", "question_id": question["id"]})
                # Cavab pəncərəsi `answer_starts_at`-dan açılır (əvvəl «hazır ol» fazası);
                # server vaxtına görə hesablanır, düşünmə pəncərənin içində qalır.
                wait, window = _answer_window(msg.get("server_time"), question)
                think = min(window * 0.8, random.uniform(1.5, 8.0) * THINK_SCALE)
                gevent.sleep(wait + think)
                choice = random.choice(options)
                pending = (question["id"], choice, time.monotonic())
                ws.send_json(
                    {"type": "answer", "question_id": question["id"], "option_ids": [choice], "answer_ms": int(think * 1000)}
                )
            elif kind == "answer_saved" and pending is not None:
                _ws_event(self, "ws answer→saved", pending[2])
                append_jsonl(
                    "expected-live",
                    {"pin": self.pin, "nickname": self.nickname, "question_id": pending[0], "option_id": pending[1]},
                )
                COUNTERS["live_answers_saved"] += 1
                pending = None
            elif kind == "error":
                _ws_event(self, "ws play error", time.monotonic(), error=str(msg.get("message"))[:160])
                pending = None
            elif kind == "finished":
                COUNTERS["live_finished"] += 1
                return
            elif kind == "kicked":
                _ws_event(self, "ws kicked", time.monotonic(), error="kicked")
                return


LIVE_CLASSES = [LiveHost, LivePlayer]
