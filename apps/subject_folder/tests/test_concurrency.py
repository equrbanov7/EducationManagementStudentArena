"""Həqiqi paralellik (iki DB bağlantısı): cəhd yarışı və «cəmi 10» yarışı.

Mövcud ``assignments`` kodunda cəhd nömrəsi «count + 1» ilə hesablanırdı — iki
paralel göndəriş eyni nömrəni ala bilirdi. Burada zəncir advisory kilidlə
serializasiya olunur; iki paralel göndərişdən biri keçir, digəri təmiz domen
xətası alır. Eyni qeydiyyata iki paralel qəbul cəmi 10-u keçə bilməz.
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal

from django.db import connection

import pytest

from apps.subject_folder import public
from apps.subject_folder.models import FolderTask, Submission
from apps.subject_folder.services import review, submissions

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _slow(module, name, monkeypatch, delay=0.4):
    """Qorunan oxunuşdan SONRA gecikmə — yarış pəncərəsini deterministik genişləndirir.

    Kilid olmasaydı hər iki axın eyni köhnə vəziyyəti oxuyardı; kilidlə ikinci axın
    birincinin commit-ini gözləyir və DƏQİQ domen xətası alır.
    """
    original = getattr(module, name)

    def _wrapped(*args, **kwargs):
        value = original(*args, **kwargs)
        time.sleep(delay)
        return value

    monkeypatch.setattr(module, name, _wrapped)


def _race(*jobs):
    barrier = threading.Barrier(len(jobs))
    results = [None] * len(jobs)

    def _run(index, job):
        try:
            barrier.wait(timeout=10)
            results[index] = ("ok", job())
        except public.FolderError as exc:
            results[index] = ("error", exc.code)
        except Exception as exc:  # pragma: no cover — gözlənilməz xəta testdə görünsün
            results[index] = ("crash", repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=_run, args=(index, job)) for index, job in enumerate(jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_parallel_submissions_produce_one_attempt(ready, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("advisory kilid PostgreSQL tələb edir")
    student = ready.students[0]
    _slow(submissions, "_locked_chain", monkeypatch)

    def job():
        return public.submit(task=ready.slot1, assignment=ready.assignment, student=student, text="paralel").pk

    results = _race(job, job)
    outcomes = sorted(kind for kind, _value in results)
    assert outcomes == ["error", "ok"], results
    # Kilid sayəsində ikinci axın birincinin commit-ini gözləyib «yoxlanılır» vəziyyətini görür
    # (kilidsiz hər ikisi «cəhd yoxdur» oxuyardı və yalnız DB unikallığı tutardı).
    assert [value for kind, value in results if kind == "error"] == ["submission.pending"]
    rows = Submission.objects.filter(task=ready.slot1, enrollment=ready.enrollments[0])
    assert rows.count() == 1 and rows.get().attempt_no == 1


def test_parallel_accepts_cannot_exceed_ten(ready, folder, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("advisory kilid PostgreSQL tələb edir")
    _slow(review, "awarded_total", monkeypatch)
    student, enrollment = ready.students[0], ready.enrollments[0]
    legacy = FolderTask.objects.create(
        organization=ready.org,
        folder=folder,
        kind="selfwork",
        title="Köhnə slot",
        slot_index=9,
        max_points=Decimal("5"),
        is_archived=True,
    )
    Submission.objects.create(
        organization=ready.org,
        task=legacy,
        assignment=ready.assignment,
        enrollment=enrollment,
        student=student,
        kind="selfwork",
        status="accepted",
        points=Decimal("5"),
        points_max=Decimal("5"),
    )
    first = public.submit(task=ready.slots[0], assignment=ready.assignment, student=student, text="bir")
    second = public.submit(task=ready.slots[1], assignment=ready.assignment, student=student, text="iki")

    results = _race(
        lambda: public.accept(first, by_user=ready.teacher, points="5").pk,
        lambda: public.accept(second, by_user=ready.teacher, points="5").pk,
    )
    assert sorted(kind for kind, _value in results) == ["error", "ok"], results
    assert [value for kind, value in results if kind == "error"] == ["review.points_total_exceeded"]
    total = sum(
        Submission.objects.filter(enrollment=enrollment, status="accepted").values_list("points", flat=True),
        Decimal("0"),
    )
    assert total == Decimal("10")
