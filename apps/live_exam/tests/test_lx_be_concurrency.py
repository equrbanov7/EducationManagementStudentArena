"""LX-BE — paralellik: 60 oyunçu eyni anda cavab verir (real thread-lər, ayrı DB bağlantıları).

İddialar: itirilmiş yeniləmə yoxdur (bal = cavabların cəmi), ikiqat göndəriş bir sətir
yaradır, «hamı cavab verdi» reveal-i TAM BİR dəfə baş verir, vaxt əmsalı server vaxtı
ilə deterministikdir, seriya düzgündür, host reveal ilə yarışan cavablar reveal
paketində ya tam var, ya da rədd olunub (arada qalan yoxdur), final sırası tie qaydasına
uyğundur. Postgres paylaşılan olduğu üçün (max_connections=100) 60 thread istifadə olunur.
"""

from __future__ import annotations

import random
import threading
from datetime import timedelta
from unittest import mock

from django.db import close_old_connections, connection
from django.db.models import Sum
from django.test import TransactionTestCase

from apps.live_exam import services
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.reveal import build_final_bundle, leaderboard_key
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.session_settings import update_session_settings

from .lx_be_support import add_question, make_exam, make_host, make_players, make_session, open_question

THREADS = 60


def _run_parallel(jobs):
    """Hər işi ayrıca thread-də, barrier ilə EYNİ ANDA işə salır; nəticələri qaytarır."""
    barrier = threading.Barrier(len(jobs))
    results: list = [None] * len(jobs)
    errors: list = []

    def worker(index, job):
        try:
            close_old_connections()
            barrier.wait(timeout=30)
            results[index] = job()
        except Exception as exc:  # pragma: no cover - diaqnostika
            errors.append(repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(index, job)) for index, job in enumerate(jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    return results, errors


class SimultaneousAnswersTest(TransactionTestCase):
    def setUp(self):
        self.host, self.org = make_host("lxbeconc")
        self.exam = make_exam(self.host, self.org)
        self.q1, (self.q1_ok, self.q1_bad) = add_question(self.exam, "Q1", [("ok", True), ("no", False)], order=1)
        self.q2, (self.q2_a, self.q2_b, self.q2_c) = add_question(
            self.exam, "Q2", [("a", True), ("b", True), ("c", False)], order=2
        )
        self.q3, _ = add_question(self.exam, "Q3", [("Bakı", True), ("Gəncə", False)], order=3)
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.q1.id, self.q2.id, self.q3.id])
        update_session_settings(self.session, {"typed_questions": {str(self.q3.id): {"accepted": ["Bakı"]}}})
        self.players = make_players(self.session, THREADS)
        self.rng = random.Random(2809)

    def _job(self, player, question, *, at, option_ids=None, text=None):
        return lambda: save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=question.id,
            option_ids=option_ids or [],
            answer_ms=0,  # saxta «0 ms» — server vaxtı işlədilməlidir
            received_at=at,
            text=text,
        )

    def _expected_points(self, fraction, elapsed_ms, total_ms=20000):
        from apps.live_exam.scoring import _kahoot_time_factor, _round_awarded_points

        if fraction <= 0:
            return 0
        return _round_awarded_points(1000 * fraction * _kahoot_time_factor(answer_ms=elapsed_ms, total_ms=total_ms))

    def _assert_scores_consistent(self):
        totals = dict(
            LiveAnswer.objects.filter(session=self.session).values_list("player_id").annotate(Sum("awarded_points"))
        )
        for player in LivePlayer.objects.filter(session=self.session):
            self.assertEqual(player.score, totals.get(player.id, 0), player.nickname)

    def test_sixty_simultaneous_answers_three_rounds(self):
        expected: dict[int, int] = {}

        # ── Raund 1: tək seçim, 60 thread + 10 ikiqat göndəriş (eyni oyunçu, eyni an) ──
        starts = open_question(self.session, self.q1, index=0)
        jobs, plan = [], []
        for player in self.players:
            elapsed = self.rng.randint(300, 15000)
            correct = self.rng.random() < 0.6
            option = self.q1_ok if correct else self.q1_bad
            plan.append((player, elapsed, correct))
            jobs.append(self._job(player, self.q1, at=starts + timedelta(milliseconds=elapsed), option_ids=[option.id]))
        duplicates = [
            self._job(player, self.q1, at=starts + timedelta(milliseconds=elapsed), option_ids=[self.q1_ok.id])
            for player, elapsed, _ in plan[:10]
        ]
        results, errors = _run_parallel(jobs + duplicates)
        self.assertEqual(errors, [])
        self.assertTrue(all(ok for ok, _ in results), [r for r in results if not r[0]][:3])
        self.assertEqual(LiveAnswer.objects.filter(session=self.session, question_id=self.q1.id).count(), THREADS)
        reveals = [result for ok, result in results if result.get("reveal_question_id")]
        self.assertEqual(len(reveals), 1, "«hamı cavab verdi» reveal-i TAM BİR dəfə olmalıdır")
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)

        stored = {answer.player_id: answer for answer in LiveAnswer.objects.filter(session=self.session)}
        for player, elapsed, correct in plan:
            points = self._expected_points(1.0 if correct else 0.0, elapsed)
            # İkiqat göndəriş eyni an → hansı qalib gəlsə də bal eynidir (düz variant ikincidə).
            if player in [p for p, _, _ in plan[:10]] and stored[player.id].is_correct != correct:
                points = self._expected_points(1.0, elapsed)
            self.assertEqual(stored[player.id].awarded_points, points)
            self.assertEqual(stored[player.id].answer_ms, elapsed)
            expected[player.id] = points
        self._assert_scores_consistent()
        streaks = dict(LivePlayer.objects.filter(session=self.session).values_list("id", "streak"))
        for player_id, answer in stored.items():
            self.assertEqual(streaks[player_id], 1 if answer.is_correct else 0)

        # ── Raund 2: çox seçimli (partial), host reveal ilə YARIŞ ──
        self.assertTrue(services.advance_to_next(self.session)["ok"])
        starts = open_question(self.session, self.q2, index=1)
        picks = [[self.q2_a.id], [self.q2_a.id, self.q2_b.id], [self.q2_a.id, self.q2_c.id], [self.q2_b.id]]
        jobs = []
        for index, player in enumerate(self.players):
            elapsed = self.rng.randint(300, 15000)
            jobs.append(
                self._job(player, self.q2, at=starts + timedelta(milliseconds=elapsed), option_ids=picks[index % 4])
            )
        captured = []
        with mock.patch(
            "apps.live_exam.services.broadcast_bundle", side_effect=lambda pin, bundle: captured.append(bundle)
        ):
            results, errors = _run_parallel(
                jobs + [lambda: services.reveal_current(LiveSession.objects.get(pk=self.session.pk))]
            )
        self.assertEqual(errors, [])
        accepted = LiveAnswer.objects.filter(session=self.session, question_id=self.q2.id).count()
        answered_ok = sum(1 for result in results[:-1] if result[0])
        self.assertEqual(accepted, answered_ok)
        host_result = results[-1]
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)
        if host_result["ok"]:
            # Host qalib gəldi: reveal paketi yalnız ondan ƏVVƏL commit olunmuş cavabları görür.
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0].host["distribution"]["total_answers"], accepted)
        self._assert_scores_consistent()

        # ── Raund 3: yazılı cavab, hamı eyni anda ──
        self.assertTrue(services.advance_to_next(self.session)["ok"])
        starts = open_question(self.session, self.q3, index=2)
        texts = ["Bakı", "baki", "BAKI!", "Gəncə", "Bakıı"]
        jobs = [
            self._job(player, self.q3, at=starts + timedelta(milliseconds=1000), text=texts[index % len(texts)])
            for index, player in enumerate(self.players)
        ]
        results, errors = _run_parallel(jobs)
        self.assertEqual(errors, [])
        self.assertTrue(all(ok for ok, _ in results))
        typed = LiveAnswer.objects.filter(session=self.session, question_id=self.q3.id)
        self.assertEqual(typed.count(), THREADS)
        self.assertEqual(typed.filter(is_correct=True).count(), THREADS // 5 * 3)  # «Bakıı» 4 simvol → səhv
        self.assertEqual(sum(1 for ok, result in results if result.get("reveal_question_id")), 1)
        self._assert_scores_consistent()

        # Final: sıra = tie qaydası, bal = cavabların cəmi.
        services.finish_session(self.session)
        final = build_final_bundle(self.session)
        rows = list(LivePlayer.objects.filter(session=self.session).values("id", "score", "created_at"))
        self.assertEqual(
            [row["player_id"] for row in final.host["top"]],
            [row["id"] for row in sorted(rows, key=leaderboard_key)][:50],
        )
        self.assertEqual(final.host["stats"]["answer_count"], LiveAnswer.objects.filter(session=self.session).count())
