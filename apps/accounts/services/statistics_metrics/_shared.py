"""«Statistika» bölməsi — rol-aware metrik modelinin ORTAQ köməkçiləri.

2026-09-12 (sahib tələbi, İKT rəhbərinin ekran görüntüsü): «hər profil özünə aid
mənalı, yaxşı datanı görə biləcək qədər olsun». Köhnə `statistics_selectors`
paketi hər rola eyni 8 «göndəriş sayğacı» kartını verirdi və rəqəmləri
Python-da sətir-sətir hesablayırdı (tələbədə bütün cəhd sətirləri, müəllimdə
qrup başına ayrıca sorğu — N+1). Bu paketdə HƏR rəqəm SQL aqreqatıdır və sorğu
sayı sətir sayından asılı deyil (`test_statistics_section.py` büdcə testləri).

Köhnə paket SİLİNMİR — CSV ixracı (`statistics_export.py`, başqa sahibdədir)
hələ də onun `summary` lüğətini yazır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Avg, Case, Count, ExpressionWrapper, F, FloatField, Q, Value, When
from django.db.models.functions import Cast, Coalesce

#: Yekunlaşmış (bal verən) cəhd statusları — `ExamAttempt.STATUS_CHOICES`.
FINISHED_ATTEMPT_STATUSES = ("submitted", "expired")
#: Keçid həddi (faiz) — köhnə selector-larla eyni (`score >= 50`).
PASS_MARK = 50.0
#: Müəllim yoxlaması tələb edən imtahan növləri (test avtomatik qiymətlənir).
MANUAL_GRADING_EXAM_TYPES = ("written", "coding")
#: Tələbə rolları (`Role.name`) — üzv bölgüsü üçün.
STUDENT_ROLE_NAMES = ("student", "lead_student")
#: Müəllim rolları (`Role.name`) — `core.roles.ProfileRole.MEMBERSHIP_ROLE_ALIASES` güzgüsü.
TEACHER_ROLE_NAMES = (
    "teacher",
    "assistant",
    "assistant_teacher",
    "lab_assistant",
    "instructor",
    "professor",
    "associate_professor",
    "senior_instructor",
)
#: Bloklarda göstərilən maksimum sətir (sıralama SQL-də, kəsmə də SQL-də).
ROW_LIMIT = 8


@dataclass(frozen=True)
class Window:
    """Fəaliyyət metrikaları üçün tarix pəncərəsi.

    `source`: ``"filter"`` — istifadəçi seçib; ``"period"`` — cari akademik
    dövrün tarixləri (defolt); ``"all"`` — məhdudiyyət yoxdur.
    """

    date_from: date | None
    date_to: date | None
    source: str = "all"
    period_name: str = ""

    @property
    def is_bounded(self) -> bool:
        return bool(self.date_from or self.date_to)

    def apply(self, qs, field: str):
        """`field` DateTimeField-inə (`__date`) pəncərəni tətbiq et."""
        if self.date_from:
            qs = qs.filter(**{f"{field}__date__gte": self.date_from})
        if self.date_to:
            qs = qs.filter(**{f"{field}__date__lte": self.date_to})
        return qs

    def apply_date(self, qs, field: str):
        """`field` DateField-inə pəncərəni tətbiq et."""
        if self.date_from:
            qs = qs.filter(**{f"{field}__gte": self.date_from})
        if self.date_to:
            qs = qs.filter(**{f"{field}__lte": self.date_to})
        return qs

    def as_dict(self) -> dict:
        return {
            "date_from": self.date_from.isoformat() if self.date_from else "",
            "date_to": self.date_to.isoformat() if self.date_to else "",
            "source": self.source,
            "period_name": self.period_name,
        }


def parse_date(raw) -> date | None:
    """`YYYY-MM-DD` → date; boş/pozuq dəyər → None."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except (TypeError, ValueError):
        return None


def resolve_period(organization):
    """Təşkilatın CARİ akademik dövrü (yoxdursa ən sonuncusu) — 1 sorğu."""
    if organization is None:
        return None
    from apps.organizations.models import AcademicPeriod

    return (
        AcademicPeriod.objects.filter(organization=organization, is_active=True)
        .order_by("-is_current", "-start_date")
        .only("id", "name", "academic_year", "start_date", "end_date", "is_current")
        .first()
    )


def build_window(*, date_from, date_to, period=None) -> Window:
    """Filtr tarixləri varsa onlar, yoxdursa cari dövrün tarixləri, o da yoxdursa açıq pəncərə."""
    if date_from or date_to:
        return Window(date_from, date_to, source="filter")
    if period is not None:
        return Window(period.start_date, period.end_date, source="period", period_name=period_label(period))
    return Window(None, None, source="all")


def period_label(period) -> str:
    if period is None:
        return ""
    year = getattr(period, "academic_year", "") or ""
    return f"{period.name} {year}".strip()


def score_pct_expression():
    """Cəhdin faiz balı — SQL ifadəsi.

    Köhnə `statistics_selectors._attempt_pct`-in güzgüsü: yazılı imtahanda
    `teacher_score` birbaşa faizdir; test/kodlaşdırma imtahanında
    `correct / (correct + wrong) * 100`. Fərq: Python döngüsü əvəzinə SQL
    aqreqatı — sorğu sayı cəhd sayından asılı deyil.
    """
    correct = Cast(F("correct_count"), FloatField())
    wrong = Cast(F("wrong_count"), FloatField())
    ratio = ExpressionWrapper(Value(100.0) * correct / (correct + wrong), output_field=FloatField())
    return Case(
        When(checked_by_teacher=False, exam__exam_type__in=MANUAL_GRADING_EXAM_TYPES, then=Value(None)),
        When(exam__exam_type="written", then=Cast(Coalesce(F("teacher_score"), Value(0)), FloatField())),
        When(Q(correct_count__gt=0) | Q(wrong_count__gt=0), then=ratio),
        default=Value(0.0),
        output_field=FloatField(),
    )


def attempt_outcome(attempts_qs) -> dict:
    """Yekunlaşmış cəhdlərin nəticəsi — TƏK aqreqat sorğusu.

    Qaytarır: ``finished`` (yekunlaşmış), ``passed`` (≥ PASS_MARK),
    ``avg_score`` (orta faiz), ``checked`` (müəllim yoxlayıb),
    ``grading_queue`` (əl ilə yoxlama tələb edən, hələ yoxlanmamış).
    """
    agg = (
        attempts_qs.filter(status__in=FINISHED_ATTEMPT_STATUSES, is_trial=False)
        .annotate(score_pct=score_pct_expression())
        .aggregate(
            finished=Count("id"),
            graded=Count("score_pct"),
            passed=Count("id", filter=Q(score_pct__gte=PASS_MARK)),
            avg_score=Avg("score_pct"),
            checked=Count("id", filter=Q(checked_by_teacher=True)),
            grading_queue=Count(
                "id",
                filter=Q(checked_by_teacher=False, exam__exam_type__in=MANUAL_GRADING_EXAM_TYPES),
            ),
        )
    )
    return {
        "finished": int(agg["finished"] or 0),
        "passed": int(agg["passed"] or 0),
        "avg_score": round(float(agg["avg_score"]), 1) if agg["avg_score"] is not None else None,
        "checked": int(agg["checked"] or 0),
        "grading_queue": int(agg["grading_queue"] or 0),
        "pass_rate": pct(agg["passed"], agg["graded"]),
    }


def exam_lifecycle_aggregate(exams_qs, *, now) -> dict:
    """İmtahanların həyat dövrü — `Exam.lifecycle_status`-un SQL güzgüsü + bitmiş.

    ``draft``: dərc edilməyib; ``scheduled``: aktiv, başlanğıc gələcəkdə;
    ``running``: aktiv, indi açıqdır; ``finished``: bitmə vaxtı keçib.
    """
    active = Q(is_active=True)
    agg = exams_qs.aggregate(
        total=Count("id"),
        draft=Count("id", filter=Q(is_active=False)),
        scheduled=Count("id", filter=active & Q(start_datetime__gt=now)),
        running=Count(
            "id",
            filter=active
            & (Q(start_datetime__isnull=True) | Q(start_datetime__lte=now))
            & (Q(end_datetime__isnull=True) | Q(end_datetime__gte=now)),
        ),
        finished=Count("id", filter=active & Q(end_datetime__lt=now)),
    )
    return {key: int(value or 0) for key, value in agg.items()}


def pct(numerator, denominator) -> float | None:
    """Faiz (1 onluq); məxrəc sıfırdırsa None — «0%» yalan siqnal verməsin."""
    if not denominator:
        return None
    return round(float(numerator or 0) * 100.0 / float(denominator), 1)


def clamp_pct(value) -> int:
    """Zolaq eni üçün 0–100 tam ədəd."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return int(round(max(0.0, min(100.0, number))))


def distribution(rows, *, label_key, count_key="n", limit=ROW_LIMIT) -> list[dict]:
    """Qruplaşmış sorğu sətirlərini paylanma siyahısına çevir (ən böyük pay 100%)."""
    items = list(rows[:limit])
    top = max((int(row.get(count_key) or 0) for row in items), default=0)
    total = sum(int(row.get(count_key) or 0) for row in items)
    result = []
    for row in items:
        count = int(row.get(count_key) or 0)
        result.append(
            {
                "label": row.get(label_key) or "—",
                "count": count,
                "share": pct(count, total),
                "pct": clamp_pct(pct(count, top)),
            }
        )
    return result
