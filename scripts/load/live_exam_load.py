#!/usr/bin/env python3
"""
Canlı viktorina (live_exam) yük testi — Audit 2026-09-28 LX-BE.

Real axını HTTP + WebSocket üzərindən sürür (brauzer UI-si nə edirsə):

* host: login → sessiya yarat (POST) → ayarlar (yazılı suallar, multi rejimi) → lobby/play
  WS → start → hər sual: «hamı cavab verdi» (server reveal edir) və ya ``ends_at + 0.18 s``-də
  POST reveal (UI autoMode kimi) → gözləmə → next → … → finished;
* N oyunçu (hamısı EYNİ İP-dən — sinif NAT-ı kimi): join səhifəsi → POST enter (cookie-lər)
  → wait room → lobby WS → ``game_started`` → player_screen + state → play WS → cavablar
  (tək/çox seçimli/yazılı; bəziləri səhv, bəziləri cavabsız) → reveal → … → finished.
  ``--flaky`` ilə hər reveal-dən sonra oyunçuların bir hissəsi TCP-ni qırıb yenidən qoşulur.

Sonda DB yoxlaması (Django ORM, yalnız oxu): bal = cavabların cəmi = server recompute
(eyni qaydalarla), final liderlik sırası = tie qaydası, statistika. İstifadə və nəticələr:
docs/live_exam/LOAD_TEST.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests
from ws_client import WSClient, WSClosed, WSHandshakeError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SEED_EXAM_TITLE = "Canlı viktorina — demo"
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Redmi Note 12) AppleWebKit/537.36 Chrome/127.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
]


# ── Ölçmə ──────────────────────────────────────────────────────────────────────


class Metrics:
    def __init__(self):
        self.samples = defaultdict(list)
        self.counts = Counter()

    def add(self, name: str, value_ms: float) -> None:
        self.samples[name].append(value_ms)

    def count(self, name: str, amount: int = 1) -> None:
        self.counts[name] += amount

    def summary(self) -> dict:
        def pct(values, q):
            ordered = sorted(values)
            return round(ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))], 1)

        return {
            "latency_ms": {
                name: {"n": len(v), "p50": pct(v, 0.5), "p95": pct(v, 0.95), "max": round(max(v), 1)}
                for name, v in sorted(self.samples.items())
                if v
            },
            "counts": dict(sorted(self.counts.items())),
        }


def server_ts(value: str | None) -> float | None:
    return datetime.fromisoformat(value).timestamp() if value else None


# ── Django ORM (yalnız kəşf + yoxlama; oyun özü HTTP/WS üzərindən gedir) ─────────


def django_setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()


def discover_exam(slug: str | None) -> dict:
    from apps.exams.models import Exam, ExamQuestion
    from core.rls import bypass_rls

    with bypass_rls():
        exam = Exam.objects.get(slug=slug) if slug else Exam.objects.filter(title=SEED_EXAM_TITLE).latest("id")
        questions = {}
        for question in ExamQuestion.objects.filter(exam=exam).prefetch_related("options"):
            options = list(question.options.all())
            questions[question.id] = {
                "correct": sorted(o.id for o in options if o.is_correct),
                "wrong": sorted(o.id for o in options if not o.is_correct),
                "texts": {o.id: o.text for o in options},
            }
    return {"slug": exam.slug, "questions": questions}


def verify_game(pin: str, host_final: dict | None, player_finals: dict, *, recompute: bool = True) -> dict:
    """Invariantlar (xam SQL — istənilən kod versiyası ilə işləyir) + ixtiyari server recompute."""
    from django.db import connection

    from core.rls import bypass_rls

    problems: list[str] = []
    with bypass_rls(), connection.cursor() as cursor:
        cursor.execute("SELECT id FROM live_exam_livesession WHERE pin = %s", [pin])
        session_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT p.id, p.score, p.created_at, COALESCE(SUM(a.awarded_points), 0), COUNT(a.id) "
            "FROM live_exam_liveplayer p LEFT JOIN live_exam_liveanswer a ON a.player_id = p.id "
            "WHERE p.session_id = %s GROUP BY p.id",
            [session_id],
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT question_id, COUNT(*), COUNT(DISTINCT player_id) FROM live_exam_liveanswer "
            "WHERE session_id = %s GROUP BY question_id",
            [session_id],
        )
        per_question = {qid: (total, distinct) for qid, total, distinct in cursor.fetchall()}
    for player_id, score, _created, awarded, _count in rows:
        if score != awarded:
            problems.append(f"player {player_id}: score {score} != sum(awarded) {awarded}")
    for qid, (total, distinct) in per_question.items():
        if total != distinct:
            problems.append(f"question {qid}: duplicate answers")
    ordered = [row[0] for row in sorted(rows, key=lambda r: (-r[1], r[2], r[0]))]
    if host_final:
        shown = [row["player_id"] for row in host_final.get("top", [])]
        if shown != ordered[: len(shown)]:
            problems.append("final leaderboard order differs from tie rule")
    ranks = {player_id: index + 1 for index, player_id in enumerate(ordered)}
    wrong_rank = sum(
        1 for pid, final in player_finals.items() if final.get("rank") is not None and final["rank"] != ranks.get(pid)
    )
    if wrong_rank:
        problems.append(f"{wrong_rank} players got a wrong final rank")
    answers = sum(total for total, _ in per_question.values())
    if recompute:
        problems.extend(_recompute_problems(pin))
    return {
        "answers": answers,
        "per_question": {str(k): v[0] for k, v in per_question.items()},
        "players": len(rows),
        "problems": problems,
    }


def _recompute_problems(pin: str) -> list[str]:
    """Saxlanan hər cavabı eyni qaydalarla yenidən hesablayır (yeni kod versiyası)."""
    from apps.exams.models import ExamQuestion
    from apps.live_exam.domain.question_config import resolve_question_config
    from apps.live_exam.domain.session import question_points, question_time_limit
    from apps.live_exam.models import LiveAnswer, LiveSession
    from apps.live_exam.scoring import calculate_answer_score, calculate_typed_score
    from core.rls import bypass_rls

    problems = []
    with bypass_rls():
        session = LiveSession.objects.select_related("exam").get(pin=pin)
        session.host_settings = {k: v for k, v in (session.host_settings or {}).items() if k != "_question_config"}
        questions = {q.id: q for q in ExamQuestion.objects.filter(exam=session.exam).prefetch_related("options")}
        answers = list(LiveAnswer.objects.filter(session=session))
        for answer in answers:
            question = questions[answer.question_id]
            config = resolve_question_config(session, question)
            base, total_ms = question_points(session, question), question_time_limit(session, question) * 1000
            if config.is_text:
                again = calculate_typed_score(
                    text=answer.text_answer,
                    accepted=list(config.accepted),
                    typo_tolerance=config.typo_tolerance,
                    base_points=base,
                    answer_ms=answer.answer_ms,
                    total_ms=total_ms,
                )
            else:
                again = calculate_answer_score(
                    option_ids=answer.choice_ids,
                    correct_ids=list(config.correct_ids),
                    base_points=base,
                    answer_ms=answer.answer_ms,
                    total_ms=total_ms,
                    multi_scoring=config.multi_scoring,
                )
            if again["awarded_points"] != answer.awarded_points or again["is_correct"] != answer.is_correct:
                problems.append(
                    f"recompute mismatch answer={answer.id}: {answer.awarded_points} vs {again['awarded_points']}"
                )
    return problems


# ── HTTP ─────────────────────────────────────────────────────────────────────


class Http:
    def __init__(self, base: str, metrics: Metrics, executor: ThreadPoolExecutor, user_agent: str):
        self.base, self.metrics, self.executor = base.rstrip("/"), metrics, executor
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent

    def _call(self, method, path, label, **kwargs):
        started = time.perf_counter()
        headers = kwargs.pop("headers", {})
        if method == "POST":
            headers.setdefault("X-CSRFToken", self.session.cookies.get("csrftoken", ""))
            headers.setdefault("Referer", self.base + "/")
        for attempt in range(4):
            try:
                response = self.session.request(method, self.base + path, headers=headers, timeout=30, **kwargs)
            except requests.RequestException:
                self.metrics.count(f"http_error:{label}")
                raise
            self.metrics.count(f"http_{response.status_code}:{label}")
            # İstifadəçi kimi: «server məşğuldur» (503) → Retry-After qədər gözlə, yenidən cəhd et.
            if response.status_code != 503 or attempt == 3:
                break
            time.sleep(min(5.0, float(response.headers.get("Retry-After") or 1)))
        self.metrics.add(f"http:{label}", (time.perf_counter() - started) * 1000)
        return response

    async def call(self, method, path, label, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, lambda: self._call(method, path, label, **kwargs))

    def cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self.session.cookies)

    def ws(self, path: str) -> WSClient:
        url = self.base.replace("http", "ws", 1) + path
        return WSClient(url, headers={"Origin": self.base, "Cookie": self.cookie_header()})


# ── Oyunçu ────────────────────────────────────────────────────────────────────


class Player:
    def __init__(self, index, ctx):
        self.index, self.ctx = index, ctx
        agent = USER_AGENTS[0] if ctx.args.same_ua else USER_AGENTS[index % len(USER_AGENTS)]
        self.http = Http(ctx.args.base_url, ctx.metrics, ctx.executor, agent)
        self.rng = random.Random(ctx.args.seed * 1000 + index)
        self.player_id = None
        self.ws = None
        self.pending: dict[int, float] = {}
        self.answered: set[int] = set()
        self.final = None

    async def join(self) -> bool:
        pin = self.ctx.pin
        await self.http.call("GET", f"/live/join/{pin}/", "join_page")
        response = await self.http.call(
            "POST",
            f"/live/join/{pin}/enter/",
            "join_enter",
            data={"nickname": f"Oyunçu {self.index:03d}", "avatar_key": f"avatar_{self.index % 16 + 1}"},
        )
        if response.status_code != 200:
            return False
        await self.http.call("GET", f"/live/wait/{pin}/", "wait_room")
        return True

    async def lobby_until_start(self) -> dict:
        lobby = self.http.ws(f"/ws/live/{self.ctx.pin}/lobby/")
        await lobby.connect()
        self.ctx.metrics.count("ws_lobby_connected")
        self.ctx.lobby_ready.release()
        while True:
            message = await lobby.recv_json()
            if message.get("type") == "lobby_state":
                self.ctx.metrics.count("lobby_state_msgs")
            if message.get("type") == "game_started":
                self.ctx.metrics.add("fanout:game_started", (time.time() - self.ctx.start_posted_at) * 1000)
                await lobby.close()
                return message

    async def connect_play(self, label="play_connect") -> None:
        started = time.perf_counter()
        for attempt in range(6):
            self.ws = self.http.ws(f"/ws/live/{self.ctx.pin}/play/")
            try:
                await self.ws.connect()
                self.ctx.metrics.add(f"ws:{label}", (time.perf_counter() - started) * 1000)
                return
            except (WSHandshakeError, OSError, asyncio.TimeoutError):
                self.ctx.metrics.count(f"ws_connect_retry:{label}")
                await asyncio.sleep(min(4.0, 0.5 * 2**attempt))
        raise RuntimeError("play socket could not connect")

    async def sync_state(self) -> bool:
        """UI kimi snapshot-u tətbiq edir; oyun bitibsə ``True`` (final snapshot-dan)."""
        response = await self.http.call("GET", f"/live/state/{self.ctx.pin}/", "state")
        if response.status_code != 200:
            return False
        data = response.json()
        if data.get("state") == "question" and data.get("question"):
            self.on_question(data["question"])
        if data.get("state") == "finished":
            self.final = {"type": "finished", "my_stats": data.get("my_stats"), "rank": data.get("rank")}
            self.ctx.metrics.count("finished_via_state_snapshot")
            return True
        return False

    def choose(self, question: dict) -> dict:
        meta = self.ctx.exam["questions"][question["id"]]
        roll = self.rng.random()
        if question.get("answer_input") == "text":
            accepted = self.ctx.typed[question["id"]]
            base = accepted[0]
            options = [base, base.lower(), base.upper() + "!", "yanlış cavab", base + "xx"]
            return {
                "text": options[0 if roll < 0.5 else 1 if roll < 0.65 else 2 if roll < 0.75 else 3 if roll < 0.9 else 4]
            }
        if question.get("multi"):
            correct, wrong = list(meta["correct"]), list(meta["wrong"])
            limit = int(question.get("max_select") or len(correct))
            if roll < 0.5:
                picks = correct
            elif roll < 0.8:
                picks = correct[:1]
            else:
                picks = correct[:1] + wrong[:1]
            return {"option_ids": picks[:limit]}
        pool = meta["correct"] if roll < 0.65 else meta["wrong"] or meta["correct"]
        return {"option_id": self.rng.choice(pool)}

    def on_question(self, question: dict) -> None:
        question_id = question["id"]
        if question_id in self.answered or self.rng.random() < self.ctx.args.skip_rate:
            return
        self.answered.add(question_id)
        opens = server_ts(question.get("answer_starts_at")) or time.time()
        window = float(question.get("time_limit") or 15)
        spread = 1.0 if self.ctx.args.burst else min(6.0, window - 2)
        delay = max(0.0, opens - time.time()) + 0.3 + self.rng.random() * spread
        asyncio.get_running_loop().call_later(delay, lambda: asyncio.ensure_future(self.send_answer(question)))

    async def send_answer(self, question: dict) -> None:
        answer = {"type": "answer", "question_id": question["id"], "answer_ms": 0, **self.choose(question)}
        self.pending[question["id"]] = time.perf_counter()
        if self.ws is not None and not self.ws.closed:
            try:
                await self.ws.send_json(answer)
                self.ctx.metrics.count("answers_sent_ws")
                return
            except (WSClosed, ConnectionError):
                pass
        response = await self.http.call(
            "POST",
            f"/live/play/{self.ctx.pin}/answer/",
            "answer_http",
            data=json.dumps(answer),
            headers={"Content-Type": "application/json"},
        )
        self.ctx.metrics.count("answers_sent_http")
        if response.status_code == 200:
            self.on_ack(question["id"])

    def on_ack(self, question_id: int) -> None:
        started = self.pending.pop(question_id, None)
        if started is not None:
            self.ctx.metrics.add("answer_ack", (time.perf_counter() - started) * 1000)

    async def play(self) -> None:
        started = await self.lobby_until_start()
        await asyncio.sleep(self.rng.random() * started.get("redirect_jitter_ms", 0) / 1000)
        await self.http.call("GET", f"/live/play/{self.ctx.pin}/", "player_screen")
        await self.connect_play()
        await self.sync_state()
        while True:
            try:
                message = await self.ws.recv_json()
            except WSClosed as closed:
                self.ctx.metrics.count(f"ws_unexpected_close:{closed.code}")
                await self.connect_play("play_reconnect")
                if await self.sync_state():
                    await self.ws.close()
                    return
                continue
            kind = message.get("type")
            if kind == "question_published":
                self.ctx.metrics.add("fanout:question", (time.time() - server_ts(message["server_time"])) * 1000)
                self.on_question(message["question"])
            elif kind == "answer_saved":
                self.player_id = message.get("player_id") or self.player_id
                self.on_ack(int(message.get("question_id") or 0))
            elif kind == "reveal":
                self.ctx.metrics.add("fanout:reveal", (time.time() - server_ts(message["server_time"])) * 1000)
                if message.get("player_answer"):
                    self.player_id = message["player_answer"]["player_id"]
                    self.ctx.metrics.count("reveal_with_own_answer")
                if "personal" in message or "results" in message:
                    self.ctx.metrics.count("LEAK:reveal_has_private_fields")
                if self.ctx.args.flaky and self.rng.random() < self.ctx.args.flaky:
                    self.ws.abort()  # Wi-Fi qopdu — növbəti recv WSClosed verir → yenidən qoşulma
                    self.ctx.metrics.count("flaky_drops")
                    await asyncio.sleep(0.5 + self.rng.random() * 1.5)
            elif kind == "finished":
                self.final = message
                await self.ws.close()
                return
            elif kind == "error":
                self.ctx.metrics.count(f"ws_error:{message.get('message')}")


# ── Host ─────────────────────────────────────────────────────────────────────


class Host:
    def __init__(self, ctx):
        self.ctx = ctx
        self.http = Http(ctx.args.base_url, ctx.metrics, ctx.executor, "Mozilla/5.0 (Macintosh) Host")
        self.queue: asyncio.Queue = asyncio.Queue()
        self.final = None

    async def prepare(self) -> None:
        args = self.ctx.args
        page = await self.http.call("GET", "/accounts/login/muellim/", "host_login_page")
        response = await self.http.call(
            "POST",
            "/accounts/login/muellim/",
            "host_login",
            data={
                "username": args.teacher,
                "password": args.password,
                "csrfmiddlewaretoken": self.http.session.cookies.get("csrftoken", ""),
            },
        )
        if "sessionid" not in self.http.session.cookies:
            raise SystemExit(f"host login failed ({page.status_code}/{response.status_code})")
        slug = self.ctx.exam["slug"]
        await self.http.call("GET", f"/live/create/{slug}/", "create_confirm")
        created = await self.http.call("POST", f"/live/create/{slug}/", "create_session", data={"force_new": "1"})
        match = re.search(r"/live/host/([A-Z0-9]+)/", created.url)
        if not match:
            raise SystemExit(f"session create failed: {created.status_code} {created.url}")
        self.ctx.pin = match.group(1)

    async def configure(self) -> None:
        body = {
            "typed_questions": {str(qid): {"accepted": []} for qid in self.ctx.typed},
            "multi_scoring": "partial",
            "autoplay": True,
        }
        response = await self.http.call(
            "POST",
            f"/live/host/{self.ctx.pin}/settings/",
            "host_settings",
            data=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            raise SystemExit(f"settings failed: {response.status_code} {response.text[:200]}")

    async def _reader(self, ws) -> None:
        while True:
            try:
                await self.queue.put(await ws.recv_json())
            except WSClosed:
                return

    async def _next_of(self, *kinds, timeout=120.0) -> dict:
        deadline = time.time() + timeout
        while True:
            message = await asyncio.wait_for(self.queue.get(), max(0.1, deadline - time.time()))
            if message.get("type") in kinds:
                return message

    async def run(self, questions: int) -> None:
        lobby = self.http.ws(f"/ws/live/{self.ctx.pin}/lobby/")
        play = self.http.ws(f"/ws/live/{self.ctx.pin}/play/")
        await lobby.connect()
        await play.connect()
        asyncio.ensure_future(self._reader(play))
        await self.ctx.all_joined.wait()
        await asyncio.sleep(1.0)
        self.ctx.start_posted_at = time.time()
        await self.http.call(
            "POST", f"/live/host/{self.ctx.pin}/start/", "host_start", data={"question_count": questions}
        )
        for _number in range(questions):
            published = await self._next_of("question_published")
            ends = server_ts(published["question"]["ends_at"])
            reveal_timer = asyncio.get_running_loop().call_later(
                max(0.0, ends - time.time()) + 0.18,
                lambda: asyncio.ensure_future(
                    self.http.call("POST", f"/live/host/{self.ctx.pin}/reveal/", "host_reveal")
                ),
            )
            reveal = await self._next_of("reveal")
            reveal_timer.cancel()
            self.ctx.metrics.add("fanout:reveal_host", (time.time() - server_ts(reveal["server_time"])) * 1000)
            self.ctx.metrics.count("rounds_revealed")
            hold = self.ctx.args.reveal_hold
            if hold < 0:  # UI kimi: next_question_at-a qədər
                hold = max(0.0, server_ts(reveal["next_question_at"]) - time.time())
            await asyncio.sleep(hold)
            await self.http.call("POST", f"/live/host/{self.ctx.pin}/next/", "host_next")
        self.final = await self._next_of("finished")
        await lobby.close()
        await play.close()


# ── Orkestr ──────────────────────────────────────────────────────────────────


class Context:
    def __init__(self, args):
        self.args = args
        self.metrics = Metrics()
        self.executor = ThreadPoolExecutor(max_workers=min(64, args.players + 4))
        self.pin = None
        self.exam = None
        self.typed: dict[int, list[str]] = {}
        self.start_posted_at = 0.0
        self.all_joined = asyncio.Event()
        self.lobby_ready = asyncio.Semaphore(0)


async def run(args) -> dict:
    ctx = Context(args)
    ctx.exam = await asyncio.to_thread(discover_exam, args.exam_slug)
    host = Host(ctx)
    await host.prepare()
    from apps.live_exam.session_settings import host_question_catalog

    def _catalog():
        from apps.live_exam.models import LiveSession
        from core.rls import bypass_rls

        with bypass_rls():
            return host_question_catalog(LiveSession.objects.get(pin=ctx.pin))

    catalog = await asyncio.to_thread(_catalog) if args.typed_count else []
    eligible = [row for row in catalog if row["typed_eligible"]][: args.typed_count]
    ctx.typed = {row["id"]: row["typed_default_accepted"] for row in eligible}
    await host.configure()
    host_task = asyncio.ensure_future(host.run(args.questions or len(ctx.exam["questions"])))

    players = [Player(index, ctx) for index in range(args.players)]
    join_started = time.perf_counter()
    joined = await asyncio.gather(*(player.join() for player in players), return_exceptions=True)
    ctx.metrics.add("phase:all_joins", (time.perf_counter() - join_started) * 1000)
    active = [player for player, ok in zip(players, joined) if ok is True]
    ctx.metrics.count("joins_ok", len(active))
    ctx.metrics.count("joins_failed", len(players) - len(active))
    tasks = [asyncio.ensure_future(player.play()) for player in active]
    for _ in active:
        await asyncio.wait_for(ctx.lobby_ready.acquire(), 60)
    ctx.all_joined.set()
    results = await asyncio.gather(host_task, *tasks, return_exceptions=True)
    failures = [repr(result) for result in results if isinstance(result, Exception)]
    finals = {p.player_id: p.final for p in active if p.player_id and p.final}
    ctx.metrics.count("players_finished", len(finals))
    verification = await asyncio.to_thread(verify_game, ctx.pin, host.final, finals, recompute=not args.no_recompute)
    return {
        "players": args.players,
        "pin": ctx.pin,
        "typed_questions": list(ctx.typed),
        "task_failures": failures[:10],
        **ctx.metrics.summary(),
        "verification": verification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8019")
    parser.add_argument("--players", type=int, default=90)
    parser.add_argument("--questions", type=int, default=0, help="0 = hamısı")
    parser.add_argument("--exam-slug", default=None)
    parser.add_argument("--teacher", default="live_demo_teacher")
    parser.add_argument("--password", default=os.environ.get("LIVE_DEMO_PASSWORD", "LiveDemo-2026!"))
    parser.add_argument("--typed-count", type=int, default=2, help="neçə uyğun sual yazılı oynansın")
    parser.add_argument("--burst", action="store_true", help="hamı pəncərə açılandan ~1 s ərzində cavab verir")
    parser.add_argument("--skip-rate", type=float, default=0.03, help="cavabsız qalma ehtimalı")
    parser.add_argument("--flaky", type=float, default=0.0, help="reveal-dən sonra qopma ehtimalı (0..1)")
    parser.add_argument("--same-ua", action="store_true", help="bütün oyunçular eyni User-Agent (ən pis hal)")
    parser.add_argument("--reveal-hold", type=float, default=1.5, help="reveal→next gözləmə (s); -1 = UI kimi")
    parser.add_argument(
        "--no-recompute", action="store_true", help="yalnız SQL invariantları (köhnə kod versiyası üçün)"
    )
    parser.add_argument("--seed", type=int, default=2809)
    parser.add_argument("--out", default=None, help="JSON nəticə faylı")
    args = parser.parse_args()

    django_setup()
    report = asyncio.run(run(args))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    ok = not report["verification"]["problems"] and not report["task_failures"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
