"""J5b üçün hesablama qatı: tarixi giriş balı və onun ARXİV QALIĞI (yazı YOXDUR).

Niyə bu faza ümumiyyətlə var (spec B, sahibin qaydası)
------------------------------------------------------
Köhnə sistem semestr giriş balını BELƏ hesablayırdı::

    girish = 10 − 0.5×qayıb + k1 + k2 + k3 + si        (0..50-ə clamp)

Yeni sistemin kanonik hesablaması isə (``gradebook_components.entry_score_for``)
GENERIC komponent yoxdursa gündəlik seminar/lab ballarının CƏMİNİ götürür.
İki qayda eyni dataya tətbiq olunanda tələbələrin ~73 %-i fərqli bal görür.
Sahibin qaydası dəyəri yenidən hesablamağı deyil, TARİXİ dəyəri göstərməyi
tələb edir → arxiv komponenti.

Nə üçün "qalıq" (residual), tam giriş balı deyil
------------------------------------------------
``entry_score_for`` GENERIC komponentlərin cəmini dərs-cəminin ƏVƏZİNƏ işlədir,
AMMA kollokvium komponentlərini və sərbəst iş çeklistini HƏMİŞƏ ÜSTƏGƏL edir::

    entry = Σgeneric + Σkollokvium + selfwork_checklist        (cap-a clamp)

J5 (``journal_components``) kollokvium ballarını artıq komponent kimi yazıb —
yəni arxiv komponentinə TAM ``girish`` yazılsaydı kollokvium İKİ DƏFƏ sayılardı.
Ona görə arxiv komponenti ``girish``-in kollokviumla İZAH OLUNMAYAN hissəsini
daşıyır (legacy düsturunda bu məhz ``10 − 0.5×qayıb + si`` hissəsidir)::

    residual = round½↑(clamp(girish − Σkollokvium − selfwork_checklist, 0, 50))
    entry_score_for = residual + Σkollokvium + checklist ≈ girish   ✓

Niyə qalıq TAM ƏDƏDƏ yuvarlaqlaşdırılır (sahibin qaydası, 2026-08-30)
---------------------------------------------------------------------
Qiymətlər tam ədəddir: 72.5 → 73, 72.4 → 72.  Köhnə ``yekun.girish`` sütunu
FLOAT idi (32.5 kimi yuvarlaqlaşdırılMAMIŞ ara dəyər), köhnə sistemin ÇAP
olunmuş bal vərəqləri isə PHP ``round()`` (yarım-yuxarı) işlədirdi — yəni
yarım-yuxarı yuvarlaqlaşdırma köhnə çap həqiqətinə uyğundur.  Kollokvium
balları onsuz da tam ədəddir, deməli kəsiri yalnız qalıq daşıyırdı; onu
yazılmazdan əvvəl :func:`round_half_up` ilə tam ədədə gətiririk.

Beləliklə komponent bölgüsü də dürüst qalır: kollokvium sətirləri öz legacy
dəyərini göstərir, arxiv sətri isə davamiyyət/sərbəst iş payını göstərir.

Bu modul HEÇ NƏ yazmır: yalnız toplu (bulk) oxu indeksləri və saf funksiyalar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping

from django.apps import apps as django_apps
from django.db.models import Count, F

from .rehearsal_journal_offerings_source import legacy_int
from .rehearsal_journal_points_source import yekun_rows
from .rehearsal_structure_phase import probe_cancellation

# Legacy düsturunun sabitləri (araşdırma: 64.4 % dəqiq, 89.8 % ±2 uyğunluq).
ATTENDANCE_BASE = Decimal("10")
ABSENCE_PENALTY = Decimal("0.5")
ENTRY_SCORE_MAX = Decimal("50")
ZERO = Decimal("0")
QUANTUM = Decimal("0.01")  # ``ComponentScore.score`` = DecimalField(…, decimal_places=2)
INTEGER = Decimal("1")  # sahibin qaydası: yazılan qalıq TAM ƏDƏDDİR

ABSENT_STATUS = "absent"  # ``rehearsal_journal_marks_targets.ABSENT_STATUS`` güzgüsü
KOLLOKVIUM_KIND = "kollokvium"
SELF_WORK_KIND = "self_work"

EXACT_TOKEN = "exact"
DERIVED_TOKEN = "derived"

_AGGREGATE_CHUNK = 10_000


def clamp(value: Decimal) -> Decimal:
    """0..50 aralığına sıxışdır və 2 onluğa yuvarlaqlaşdır (sahə forması)."""

    bounded = min(max(value, ZERO), ENTRY_SCORE_MAX)
    return bounded.quantize(QUANTUM)


def round_half_up(value: Decimal) -> Decimal:
    """Tam ədədə YARIM-YUXARI yuvarlaqlaşdır: 72.5 → 73, 72.4 → 72.

    ⚠️ Python ``round()`` İŞLƏTMƏ — o, bankir yuvarlaqlaşdırmasıdır (72.5 → 72).
    Nəticə yenidən sahə formasına (2 onluq) salınır ki, onsuz da tam olan
    dəyərlərin təsviri («15.00») dəyişməsin — derivation barmaq izi yalnız
    həqiqətən kəsirli qalıqlarda dəyişir.
    """

    return value.quantize(INTEGER, rounding=ROUND_HALF_UP).quantize(QUANTUM)


def legacy_girish(row) -> Decimal | None:
    """``yekun.girish`` sütununu Decimal-a çevir; rəqəm deyilsə ``None``.

    ``rehearsal_journal_reconcile_source.legacy_total`` ilə EYNİ ciddilik:
    heç bir coercion, mətn dəyər qəbul edilmir.
    """

    value = row["girish"]
    if type(value) is float:
        return Decimal(str(value))
    if type(value) is int:
        return Decimal(value)
    if type(value) is Decimal:
        return value
    return None


@dataclass(frozen=True)
class EntryScoreValue:
    """Bir tələbənin bir açılışdakı arxiv qərarı — hələ yazılmamış."""

    residual: Decimal  # arxiv komponentinə yazılacaq bal
    entry: Decimal  # bərpa olunan tarixi giriş balı (hesabat üçün)
    token: str  # ``exact`` (yekun cədvəli) və ya ``derived`` (düstur)
    clamped: bool  # dəyər sərhədə dəydi → tam bərpa zəmanəti yoxdur


@dataclass(frozen=True)
class EntryScoreInputs:
    """Hədəfdən oxunmuş toplu indekslər + ``yekun`` dəqiq dəyərləri."""

    absences: Mapping[str, int]
    kollokvium: Mapping[str, Decimal]
    selfwork: Mapping[str, Decimal]
    checklist: Mapping[str, Decimal]
    exact: Mapping[str, Decimal]

    def resolve(self, enrollment_pk: str) -> EntryScoreValue:
        """Tarixi giriş balı → arxiv qalığı; mənbə ``yekun``-dursa düstur işləmir."""

        kollokvium = self.kollokvium.get(enrollment_pk, ZERO)
        checklist = self.checklist.get(enrollment_pk, ZERO)
        raw = self.exact.get(enrollment_pk)
        if raw is None:
            token = DERIVED_TOKEN
            raw = (
                ATTENDANCE_BASE
                - ABSENCE_PENALTY * Decimal(self.absences.get(enrollment_pk, 0))
                + kollokvium
                + self.selfwork.get(enrollment_pk, ZERO)
            )
        else:
            token = EXACT_TOKEN
        entry = clamp(raw)
        wanted = entry - kollokvium - checklist
        bounded = clamp(wanted)
        # Sahibin qaydası (2026-08-30): qalıq TAM ƏDƏDƏ yuvarlaqlaşdırılıb yazılır
        # (köhnə float ``girish``-in kəsiri hədəfə daşınmır).  ``clamped`` bayrağı
        # yuvarlaqlaşdırmadan ƏVVƏLKİ dəyərlərlə hesablanır — yuvarlaqlaşdırma
        # sərhəd hadisəsi deyil, bilinçli normallaşdırmadır.
        residual = round_half_up(bounded)
        return EntryScoreValue(
            residual=residual,
            entry=entry,
            token=token,
            clamped=entry != raw.quantize(QUANTUM) or bounded != wanted.quantize(QUANTUM),
        )


def absence_counts(context) -> dict[str, int]:
    """``Enrollment`` pk → ``absent`` statuslu ``LessonMark`` SAYI.

    ``excused`` (J-V3 üzürlü qaib) qəsdən sayılmır: modelin öz qaydası ilə
    (``recompute_absence_hours``) üzürlü qayıb davamiyyət limitinə daxil deyil.
    """

    model = django_apps.get_model("registrar", "LessonMark")
    rows = (
        model.objects.filter(organization=context.organization, status=ABSENT_STATUS)
        .values("enrollment_id")
        .annotate(total=Count("id"))
    )
    return {str(row["enrollment_id"]): int(row["total"] or 0) for row in rows.iterator(chunk_size=_AGGREGATE_CHUNK)}


def component_totals(context) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """``(kollokvium, sərbəst iş)`` cəmləri — ``entry_score_for`` ilə EYNİ min-qaydası.

    Hər bal öz komponentinin ``max_score``-una sıxışdırılır, çünki kanonik
    hesablama məhz belə toplayır.  ARXİV komponenti ``generic``-dir → bu iki
    süzgəcə düşmür, yəni təkrar icrada öz-özünü qidalandırmır (idempotentlik).
    """

    model = django_apps.get_model("registrar", "ComponentScore")
    rows = model.objects.filter(
        organization=context.organization, component__kind__in=(KOLLOKVIUM_KIND, SELF_WORK_KIND)
    ).values_list("enrollment_id", "component__kind", "score", "component__max_score")
    kollokvium: dict[str, Decimal] = {}
    selfwork: dict[str, Decimal] = {}
    for enrollment_id, kind, score, max_score in rows.iterator(chunk_size=_AGGREGATE_CHUNK):
        bucket = kollokvium if kind == KOLLOKVIUM_KIND else selfwork
        key = str(enrollment_id)
        bucket[key] = bucket.get(key, ZERO) + min(Decimal(score or 0), Decimal(max_score))
    return kollokvium, selfwork


def checklist_counts(context) -> dict[str, Decimal]:
    """``Enrollment`` pk → sərbəst iş çeklistinin təhvil SAYI.

    ``entry_score_for`` sərbəst iş komponentinə BALI deyil, bu sayı əlavə edir
    (J-V12 qeydi).  İmport heç bir ``SelfWorkTopic``/``SelfWorkMark`` yaratmır,
    yəni real köçürmədə bu indeks boşdur — güzgü yenə də tam saxlanılır ki,
    hədəfdə əvvəlcədən çeklist varsa qalıq düzgün hesablansın.
    """

    model = django_apps.get_model("registrar", "SelfWorkMark")
    rows = (
        model.objects.filter(organization=context.organization, done=True, topic__offering=F("enrollment__offering"))
        .values("enrollment_id")
        .annotate(total=Count("id"))
    )
    return {
        str(row["enrollment_id"]): Decimal(int(row["total"] or 0)) for row in rows.iterator(chunk_size=_AGGREGATE_CHUNK)
    }


def exact_entry_scores(context, *, journals, enrollments) -> dict[str, Decimal]:
    """``yekun.girish`` → ``Enrollment`` pk (yalnız 2022/2023 Payız üçün mövcuddur).

    Bu, spec B3-ün icazə verdiyi YEGANƏ əlavə mənbə oxunuşudur; qalan hər dəyər
    artıq köçürülmüş hədəf datasından gəlir.  Həll olunmayan sətir sadəcə
    düşür — J8 onsuz da hər ``yekun`` sətrini ayrıca möhürləyir.
    """

    index: dict[str, Decimal] = {}
    for _legacy_pk, row in yekun_rows(context):
        probe_cancellation(context)
        journal = journals.get(legacy_int(row["journal_id"]))
        if journal is None:
            continue
        enrollment_pk = enrollments.get(f"{journal[0]}:{legacy_int(row['student_id'])}", "")
        girish = legacy_girish(row)
        if not enrollment_pk or girish is None:
            continue
        index[enrollment_pk] = girish
    return index


def build_inputs(context, *, journals, enrollments) -> EntryScoreInputs:
    """Bütün toplu indeksləri bir dəfə qur — sətir-başına sorğu YOXDUR."""

    kollokvium, selfwork = component_totals(context)
    return EntryScoreInputs(
        absences=absence_counts(context),
        kollokvium=kollokvium,
        selfwork=selfwork,
        checklist=checklist_counts(context),
        exact=exact_entry_scores(context, journals=journals, enrollments=enrollments),
    )


__all__ = [
    "ABSENCE_PENALTY",
    "ATTENDANCE_BASE",
    "DERIVED_TOKEN",
    "ENTRY_SCORE_MAX",
    "EXACT_TOKEN",
    "EntryScoreInputs",
    "EntryScoreValue",
    "absence_counts",
    "build_inputs",
    "checklist_counts",
    "clamp",
    "component_totals",
    "exact_entry_scores",
    "legacy_girish",
    "round_half_up",
]
