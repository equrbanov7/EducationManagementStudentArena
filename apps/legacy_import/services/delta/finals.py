"""Yekun/təkrar imtahan balları (``im`` / ``im2``) və komponent xanaları (``k1``–``k3``, ``si``).

``im``  → ``FinalGrade.exam_score``; ``im2`` → ``ResitRecord`` (``reason=total``, ``status=completed``) —
cutover J6-nın ÖZ yazı funksiyaları ilə (``write_exam_score`` / ``write_resit_score``). Fərq: delta
YALNIZ BOŞU doldurur — dəyər varsa və fərqlidirsə «konflikt» sayılır, toxunulmur (yeni sistemin imtahan
körpüsü / «Nəticə» əməli qalibdir). Bal 0–100 deyilsə karantin.

Komponentlər (kollokvium / sərbəst iş) 2026/2027 qiymətləndirmə qaydasında YOXDUR (Midterm 30, sərbəst iş
ləğv) — ona görə yazılmır, yalnız sayılır (sahib qərarı tələb edir).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.apps import apps as django_apps

FINAL_MONTHS = {"im": "exam", "im2": "resit"}
COMPONENT_MONTHS = {"k1", "k2", "k3", "si"}


def _score(point):
    text = str(point or "").strip().replace(",", ".")
    if not text:
        return None, "blank"
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "not_numeric"
    if value < 0 or value > 100:
        return None, "out_of_range"
    return value, "ok"


def apply_finals(run, enrollments: dict) -> None:
    from ..rehearsal_journal_finals_phase import write_exam_score, write_resit_score
    from .lessons import winning_cells

    FinalGrade = django_apps.get_model("registrar", "FinalGrade")
    ResitRecord = django_apps.get_model("registrar", "ResitRecord")
    cells = [
        row
        for row in winning_cells(run.bundle["points"])
        if row["month_id"] in FINAL_MONTHS or row["month_id"] in COMPONENT_MONTHS
    ]
    for row in cells:
        if row["month_id"] in COMPONENT_MONTHS:
            run.count(f"component.{row['month_id']}_not_imported")
    finals = [row for row in cells if row["month_id"] in FINAL_MONTHS]
    old = run.ledger_enrollments({(row["journal_uniqid"], row["student_id"]) for row in finals})
    context = SimpleNamespace(organization=run.organization)
    targets = []
    for row in finals:
        key = (row["journal_uniqid"], row["student_id"])
        enrollment = enrollments.get(key) or old.get(key)
        kind = FINAL_MONTHS[row["month_id"]]
        if enrollment is None:
            run.count(f"final.{kind}.enrollment_unresolved")
            continue
        score, outcome = _score(row["point"])
        if score is None:
            run.count(f"final.{kind}.{outcome}")
            continue
        targets.append((kind, enrollment, score))
    grades = dict(
        FinalGrade.objects.filter(enrollment_id__in=[e.pk for kind, e, _s in targets if kind == "exam"]).values_list(
            "enrollment_id", "exam_score"
        )
    )
    resits = dict(
        ResitRecord.objects.filter(enrollment_id__in=[e.pk for kind, e, _s in targets if kind == "resit"]).values_list(
            "enrollment_id", "resit_score"
        )
    )
    for kind, enrollment, score in targets:
        stored = (grades if kind == "exam" else resits).get(enrollment.pk)
        if stored is not None:
            run.count(f"final.{kind}.same" if Decimal(stored) == score else f"final.{kind}.conflict_kept")
            continue
        writer = write_exam_score if kind == "exam" else write_resit_score
        outcome = writer(context, enrollment_pk=enrollment.pk, score=score, allow_existing=False)
        run.count(f"final.{kind}.{outcome}")
        run.touched("finals", enrollment.pk, [kind])


__all__ = ["apply_finals"]
