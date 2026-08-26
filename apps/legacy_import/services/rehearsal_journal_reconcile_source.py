"""J8 üçün hesablama qatı: say balansı və ``yekun`` güzgüsü (yazı YOXDUR).

İki müstəqil sübut mənbəyi burada qarşılaşdırılır — ``rehearsal_reconciliation``
modulunun prinsipi ilə eyni: "hər yoxlama hesabatı müqayisə etdiyi mənbədən
MÜSTƏQİL mənbədən yenidən hesablayır".

* **Say balansı**: mənbə sətirləri J4/J5/J6-nın SAF klassifikatorları ilə
  yenidən təsnif olunur (heç bir yazı, heç bir ledger oxunuşu), hədəf sayları
  isə birbaşa registrar cədvəllərindən gəlir.  Fərq (``delta``) dublikat
  uduzanları, həll olunmayan istinadları və hədəf toqquşmalarını əhatə edir və
  hesabata çıxır.
* **``yekun`` güzgüsü**: ``finals.compute_final_result`` düsturunun güzgüsü —
  giriş balı (dərs balları + kollokvium, ``entry_score_max`` ilə clamp) +
  effektiv imtahan balı (təkrar imtahan varsa o) + bonus, 0..100-ə clamp.
  Güzgü import-la yaradılmış jurnal üçün dəqiqdir; tenant-da GENERIC komponent
  və ya sərbəst iş çeklisti varsa kənarlaşma İNFO kimi görünür — reconciliation
  məhz bunun üçündür.
"""

from __future__ import annotations

from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import Sum

from .rehearsal_journal_components_phase import classify_component_cell, is_component_month
from .rehearsal_journal_finals_phase import classify_final_cell, is_final_month
from .rehearsal_journal_marks_phase import classify_mark_cell, is_calendar_month
from .rehearsal_journal_offerings_source import validated_uniqid
from .rehearsal_journal_points_source import (
    ARCHIVE_CUTOFF,
    added_on,
    archive_rows,
    calendar_slot,
    legacy_text,
    point_rows,
)
from .rehearsal_structure_phase import probe_cancellation

BALANCE_DOMAINS = ("marks", "components", "finals")
BALANCE_KEYS = ("source", "empty", "unreadable", "orphan", "overlap")
DEVIATION_TOLERANCE = Decimal("0.5")
DEFAULT_ENTRY_SCORE_MAX = 50
KOLLOKVIUM_KIND = "kollokvium"


def _domain_of(month_id: str) -> str:
    if is_calendar_month(month_id):
        return "marks"
    if is_component_month(month_id):
        return "components"
    return "finals" if is_final_month(month_id) else ""


def _outcome_of(domain: str, month_id: str, day_number: str, point_text: str) -> str:
    """``source``/``empty``/``unreadable`` — yazıla bilən sətir "" qaytarır."""

    if domain == "marks":
        if calendar_slot(month_id, day_number) is None:
            return "unreadable"
        outcome, _status, _score = classify_mark_cell(point_text)
    elif domain == "components":
        outcome, _score = classify_component_cell(point_text)
    else:
        outcome, _score = classify_final_cell(month_id, point_text)
    if outcome == "empty":
        return "empty"
    return "unreadable" if outcome in ("unknown", "range") else ""


def tally_source_rows(context, *, journal_uniqids) -> dict[str, dict[str, int]]:
    """Hər domen üçün mənbə sətirlərinin müstəqil təsnifat sayğacı."""

    tally = {domain: dict.fromkeys(BALANCE_KEYS, 0) for domain in BALANCE_DOMAINS}
    for from_archive in (False, True):
        stream = archive_rows(context) if from_archive else point_rows(context)
        for _legacy_pk, row in stream:
            probe_cancellation(context)
            month_id = legacy_text(row["month_id"])
            domain = _domain_of(month_id)
            if not domain:  # struktur olaraq mümkün deyil — J6 catch-all-dır
                continue
            bucket = tally[domain]
            bucket["source"] += 1
            if from_archive:
                stamped = added_on(row)
                if stamped is None or stamped >= ARCHIVE_CUTOFF:
                    bucket["overlap"] += 1
                    continue
            # 2026-08-28: açılış artıq dilim açarı ilə indekslənir, ona görə
            # orphan qapısı JURNAL dəsti ilə yoxlanılır (dilim açarı ilə yox).
            if validated_uniqid(row["journal_uniqid"]) not in journal_uniqids:
                bucket["orphan"] += 1
                continue
            outcome = _outcome_of(domain, month_id, legacy_text(row["day_number"]), legacy_text(row["point"]))
            if outcome:
                bucket[outcome] += 1
    return tally


def tally_target_rows(context) -> dict[str, int]:
    """Hədəf tərəfin sayları — registrar cədvəllərindən birbaşa."""

    organization = context.organization
    mark_model = django_apps.get_model("registrar", "LessonMark")
    score_model = django_apps.get_model("registrar", "ComponentScore")
    final_model = django_apps.get_model("registrar", "FinalGrade")
    resit_model = django_apps.get_model("registrar", "ResitRecord")
    return {
        "marks": mark_model.objects.filter(organization=organization).count(),
        "components": score_model.objects.filter(organization=organization).count(),
        "finals": (
            final_model.objects.filter(organization=organization, exam_score__isnull=False).count()
            + resit_model.objects.filter(organization=organization, resit_score__isnull=False).count()
        ),
    }


def balance_delta(bucket: dict[str, int], target: int) -> int:
    """``mənbə − (boş + oxunmayan + orphan + overlap) − hədəf``."""

    writable = bucket["source"] - bucket["empty"] - bucket["unreadable"] - bucket["orphan"] - bucket["overlap"]
    return writable - target


class FinalMirror:
    """``finals.compute_final_result`` düsturunun toplu (bulk) güzgüsü."""

    __slots__ = ("bonus", "caps", "exam", "kollokvium", "lessons", "offering_of", "resit")

    def __init__(self, context) -> None:
        organization = context.organization
        self.lessons = _sum_by_enrollment(
            django_apps.get_model("registrar", "LessonMark").objects.filter(
                organization=organization, score__isnull=False
            ),
            "score",
        )
        self.kollokvium = _sum_by_enrollment(
            django_apps.get_model("registrar", "ComponentScore").objects.filter(
                organization=organization, component__kind=KOLLOKVIUM_KIND
            ),
            "score",
        )
        self.exam, self.bonus = {}, {}
        for enrollment_id, exam_score, bonus in (
            django_apps.get_model("registrar", "FinalGrade")
            .objects.filter(organization=organization)
            .values_list("enrollment_id", "exam_score", "bonus")
        ):
            key = str(enrollment_id)
            if exam_score is not None:
                self.exam[key] = Decimal(exam_score)
            self.bonus[key] = Decimal(bonus or 0)
        self.resit = {
            str(enrollment_id): Decimal(score)
            for enrollment_id, score in django_apps.get_model("registrar", "ResitRecord")
            .objects.filter(organization=organization, resit_score__isnull=False)
            .values_list("enrollment_id", "resit_score")
        }
        self.caps = {
            str(offering_id): int(cap)
            for offering_id, cap in django_apps.get_model("registrar", "AssessmentScheme")
            .objects.filter(organization=organization)
            .values_list("offering_id", "entry_score_max")
        }
        self.offering_of = {
            str(pk): str(offering_id)
            for pk, offering_id in django_apps.get_model("registrar", "Enrollment")
            .objects.filter(organization=organization)
            .values_list("pk", "offering_id")
        }

    def entry_score(self, enrollment_pk: str) -> Decimal:
        offering_pk = self.offering_of.get(enrollment_pk, "")
        cap = Decimal(self.caps.get(offering_pk, DEFAULT_ENTRY_SCORE_MAX))
        total = self.lessons.get(enrollment_pk, Decimal("0")) + self.kollokvium.get(enrollment_pk, Decimal("0"))
        return min(total, cap)

    def total_score(self, enrollment_pk: str) -> Decimal:
        effective_exam = self.resit.get(enrollment_pk, self.exam.get(enrollment_pk, Decimal("0")))
        total = self.entry_score(enrollment_pk) + effective_exam + self.bonus.get(enrollment_pk, Decimal("0"))
        return max(Decimal("0"), min(Decimal("100"), total))


def _sum_by_enrollment(queryset, field: str) -> dict[str, Decimal]:
    return {
        str(row["enrollment_id"]): Decimal(row["total"] or 0)
        for row in queryset.values("enrollment_id").annotate(total=Sum(field))
    }


def legacy_total(row) -> Decimal | None:
    """``yekun`` sütununu Decimal-a çevir; rəqəm deyilsə ``None``."""

    value = row["yekun"]
    if type(value) is float:
        return Decimal(str(value))
    if type(value) is int:
        return Decimal(value)
    if type(value) is Decimal:
        return value
    return None
