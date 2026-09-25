"""Sərbəst iş BALI — TƏK kanonik qayda (bütün sayma yerləri buradan oxuyur).

Sahib 2026-09-25: sərbəst iş yeni sillabusun strukturunu izləyir — 1 × 10,
2 × 5 və ya 10 × 1; cəmi maksimum 10, ikinci dəfə bal verilmir. Köhnə jurnal
«mövzu çeklisti» idi (hər təhvil 1 bal) — o data OLDUĞU KİMİ qalır.

EFFEKTİV BAL (bir işarə)::

    points        varsa → points
    yoxdursa, done      → topic.max_points
    əks halda           → 0

CƏM (bir yazılış) = min(Σ effektiv bal, 10). Köhnə datada (``max_points=1``,
``points=NULL``) bu, ƏVVƏLKİ «təhvil sayı» ilə bayt-bayt eynidir — sübut:
``tests/test_selfwork_points_parity.py`` (keçiddən əvvəlki kod üzərində
ölçülmüş snapshot) və ``tests/test_selfwork_points.py`` (SQL ↔ Python güzgüsü).

SAYMA YERLƏRİ (hamısı BURADAN — güzgü pozulmasın):

* :func:`selfwork_total_for` — ``gradebook_components.entry_score_for`` (tək sətir);
* :func:`selfwork_totals_by_offering` — ``finals_batch`` (roster səthləri);
* :func:`selfwork_totals` — ``analytics._selfwork_map``, ``analytics_fast``
  və ``apps.accounts.academic_summary`` (``key=`` mətn açarı ilə);
* :func:`effective_points` / :func:`cap_total` — lövhə (``selfwork_board``),
  tələbə görünüşü, hook (``selfwork_hook``).

⚠️ Köçürülmüş «arxiv» balı (SELF_WORK ``ComponentScore``) HEÇ BİR cəmə girmir —
o, giriş balının GENERIC qalığının içindədir (bax ``gradebook_components`` və
``selfwork_board`` modullarındakı xəbərdarlıq).

Fənn qovluğu (``apps.subject_folder``) üçün hook müqaviləsi — :func:`record_points`
və :func:`preview` — ``apps.registrar.public_services.selfwork_points`` kimi ixrac
olunur; icra ``selfwork_hook`` modulundadır, struktur ``selfwork_structure``-dadır.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Cast, Coalesce

from apps.registrar.models import SelfWorkMark
from apps.registrar.models.selfwork import SELFWORK_TOTAL_POINTS, SelfWorkSource

#: Sərbəst işin ümumi tavanı (``apps.syllabus`` ``SELFWORK_TOTAL_SCORE`` ilə eyni — testlə kilidlənib).
TOTAL_MAX = Decimal(SELFWORK_TOTAL_POINTS)
#: Bal dəqiqliyi — bir onluq (``SelfWorkMark.points`` = Decimal(4, 1)).
POINTS_STEP = Decimal("0.1")

_ZERO = Decimal("0")
_ONE = Decimal("1")
_POINTS_FIELD = DecimalField(max_digits=6, decimal_places=1)

SOURCE_JOURNAL = SelfWorkSource.JOURNAL.value
SOURCE_SUBJECT_FOLDER = SelfWorkSource.SUBJECT_FOLDER.value


# ── Skalyar qayda ────────────────────────────────────────────────────────────


def normalize(value) -> Decimal:
    """Bal → kanonik Decimal: tam dəyər eksponentsiz (``7.0`` → ``7``), kəsr bir onluqla.

    Köhnə yollar sayğacı ``Decimal(int)`` kimi qaytarırdı; tam balda eyni
    təmsil saxlanılır ki, şablon/test çıxışı dəyişməsin."""
    value = Decimal(value)
    if value == value.to_integral_value():
        return value.quantize(_ONE)
    return value.quantize(POINTS_STEP)


def effective_value(*, points, done, max_points) -> Decimal:
    """Effektiv balın xam sahələr üzərindəki forması (``values_list`` sətirləri üçün)."""
    if points is not None:
        return normalize(points)
    if done:
        return normalize(max_points or 0)
    return _ZERO


def effective_points(mark, topic=None) -> Decimal:
    """Bir işarənin effektiv balı (``mark`` ``None`` → 0). ``topic`` verilməsə ``mark.topic``."""
    if mark is None:
        return _ZERO
    if mark.points is None and not mark.done:
        return _ZERO
    topic = topic if topic is not None else mark.topic
    return effective_value(points=mark.points, done=mark.done, max_points=topic.max_points)


def is_graded(mark) -> bool:
    """İşarə bal daşıyırmı (təhvil və ya real bal) — «ikinci dəfə bal yoxdur» qaydasının əsası."""
    return mark is not None and (mark.done or mark.points is not None)


def cap_total(value) -> Decimal:
    """Cəm → ``min(cəm, 10)`` (kanonik təmsildə)."""
    value = Decimal(value or 0)
    return normalize(value if value < TOTAL_MAX else TOTAL_MAX)


def parse_points(raw):
    """İstifadəçi/hook dəyəri → Decimal və ya ``None`` (boş). Etibarsız → ``ValueError``.

    Bir onluqdan çox dəqiqlik QƏBUL OLUNMUR (yuvarlaqlaşdırma balı gizlicə dəyişərdi)."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        value = Decimal(str(raw).replace(",", ".").strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("points") from exc
    if not value.is_finite() or value != value.quantize(POINTS_STEP):
        raise ValueError("points")
    return normalize(value)


def display(value) -> str:
    """Bal mətni: ``4`` / ``4.5`` / ``—`` (şablon və mesajlar üçün)."""
    if value is None:
        return "—"
    return format(normalize(value), "f")


# ── SQL qaydası (aqreqatlar) ─────────────────────────────────────────────────


def points_expression():
    """``COALESCE(points, CASE WHEN done THEN topic.max_points ELSE 0 END)`` — SQL güzgüsü."""
    return Coalesce(
        F("points"),
        Case(
            When(done=True, then=Cast("topic__max_points", _POINTS_FIELD)),
            default=Value(_ZERO),
            output_field=_POINTS_FIELD,
        ),
        output_field=_POINTS_FIELD,
    )


def _graded_marks():
    # ``done`` süzgəci: bal = təhvil (DB CHECK ``selfwork_mark_points_imply_done``),
    # yəni ``done=False`` sətri cəmə HEÇ NƏ vermir; süzgəc ``(enrollment, done)``
    # indeksini işlədir və «işarəsi olmayan yazılış açarsızdır» davranışını saxlayır.
    return SelfWorkMark.objects.filter(done=True)


def selfwork_totals(enrollment_ids, *, key=None) -> dict:
    """``{açar: cəm}`` — yazılışlar üzrə TƏK aqreqat sorğu (analitika güzgüləri).

    ``enrollment_ids`` siyahı və ya ``qs.values("id")`` alt-sorğusu ola bilər.
    ``key`` — qruplaşdırma ifadəsi (məs. ``Cast("enrollment_id", TextField())``
    — ``analytics_fast`` mətn açarları); verilməsə ``enrollment_id``.
    Təhvili olmayan yazılış lüğətə DÜŞMÜR (çağıran 0 götürür)."""
    qs = _graded_marks().filter(enrollment_id__in=enrollment_ids)
    rows = qs.values_list("enrollment_id") if key is None else qs.annotate(swp_key=key).values_list("swp_key")
    return {row_key: cap_total(total) for row_key, total in rows.annotate(total=Sum(points_expression()))}


def selfwork_totals_by_offering(enrollment_ids, offering_ids) -> dict:
    """``{(enrollment_id, offering_id): cəm}`` — ``finals_batch`` üçün TƏK aqreqat sorğu."""
    rows = (
        _graded_marks()
        .filter(enrollment_id__in=enrollment_ids, topic__offering_id__in=offering_ids)
        .values_list("enrollment_id", "topic__offering_id")
        .annotate(total=Sum(points_expression()))
    )
    return {(enrollment_id, offering_id): cap_total(total) for enrollment_id, offering_id, total in rows}


def selfwork_total_for(enrollment) -> Decimal:
    """Bir yazılışın öz açılışındakı sərbəst iş cəmi (``entry_score_for`` tək-sətir yolu)."""
    total = (
        _graded_marks()
        .filter(enrollment_id=enrollment.pk, topic__offering_id=enrollment.offering_id)
        .aggregate(total=Sum(points_expression()))["total"]
    )
    return cap_total(total)


def selfwork_slots(enrollments, offering_ids) -> tuple[dict, dict]:
    """Slot-slot görünüş + cəm — TƏK sorğu (mövzular LEFT JOIN yazılışların işarələri).

    Qaytarır ``({enrollment_id: [slot…]}, {(enrollment_id, offering_id): cəm})``.
    Cəm :func:`selfwork_totals_by_offering` ilə EYNİ qaydadır (Python güzgüsü —
    ``test_selfwork_points`` kilidləyir); ``finals_batch.build(selfwork_loader=…)``
    üçün yazılıb ki, «Fənlərim» slot göstərişi ƏLAVƏ sorğu etməsin. Slot:
    ``{"index", "title", "points" (effektiv və ya None), "max_points", "from_folder"}``
    — strukturlu açılışda ``slot_index`` üzrə, köhnə çeklistdə sıra ilə ilk 10 mövzu."""
    from django.db.models import FilteredRelation, Q

    from apps.registrar.models import SelfWorkTopic

    wanted = set(offering_ids)
    owners: dict = {}
    for enrollment in enrollments:
        if enrollment.offering_id in wanted:
            owners.setdefault(enrollment.offering_id, []).append(enrollment.id)
    enrollment_ids = [pk for pks in owners.values() for pk in pks]
    rows = (
        SelfWorkTopic.objects.filter(offering_id__in=list(owners))
        .annotate(swp_mark=FilteredRelation("marks", condition=Q(marks__enrollment_id__in=enrollment_ids)))
        .values_list(
            "offering_id",
            "id",
            "slot_index",
            "order",
            "created_at",
            "title",
            "max_points",
            "swp_mark__enrollment_id",
            "swp_mark__done",
            "swp_mark__points",
            "swp_mark__source",
        )
    )
    topics: dict = {}
    marks: dict = {}
    for offering_id, topic_id, slot_index, order, created_at, title, max_points, owner, done, points, source in rows:
        topics.setdefault(offering_id, {})[topic_id] = (slot_index, order, created_at, title, max_points)
        if owner is not None and done:
            marks[(owner, topic_id)] = (effective_value(points=points, done=True, max_points=max_points), source)
    slots: dict = {}
    totals: dict = {}
    for offering_id, by_topic in topics.items():
        items = sorted(by_topic.items(), key=lambda pair: (pair[1][0] or 0, pair[1][1], pair[1][2]))
        structured = all(meta[0] is not None for _topic_id, meta in items)
        visible = items if structured else items[:10]
        for enrollment_id in owners.get(offering_id, ()):
            graded = [
                marks[(enrollment_id, topic_id)][0] for topic_id, _meta in items if (enrollment_id, topic_id) in marks
            ]
            if graded:
                totals[(enrollment_id, offering_id)] = cap_total(sum(graded, _ZERO))
            slots[enrollment_id] = [
                {
                    "index": meta[0] if structured else position,
                    "title": meta[3],
                    "points": marks.get((enrollment_id, topic_id), (None, None))[0],
                    "max_points": meta[4],
                    "from_folder": marks.get((enrollment_id, topic_id), (None, None))[1] == SOURCE_SUBJECT_FOLDER,
                }
                for position, (topic_id, meta) in enumerate(visible, start=1)
            ]
    return slots, totals


# ── Fənn qovluğu hook-u (müqavilə — icra ``selfwork_hook``-dadır) ────────────


def record_points(*, offering, enrollment, slot_index, slot_title, max_points, points, source_ref, by_user):
    """Fənn qovluğunda qəbul edilmiş sərbəst iş balını jurnala yazır → ``(ok, mesaj)``.

    Müqavilə (``apps/subject_folder/public.py`` §9): ``True`` — yazıldı (və ya eyni
    ``source_ref`` + eyni bal ilə ARTIQ yazılıb, idempotent); ``False`` — jurnal
    qəbul etmir (kilidli, qeydiyyat aktiv deyil, şkala uyğunsuz, slotda artıq bal
    var — ikinci bal yoxdur, cəm 10-u keçir, struktur yoxdur/uyğunsuz)."""
    from apps.registrar import selfwork_hook

    return selfwork_hook.record_points(
        offering=offering,
        enrollment=enrollment,
        slot_index=slot_index,
        slot_title=slot_title,
        max_points=max_points,
        points=points,
        source_ref=source_ref,
        by_user=by_user,
    )


def preview(*, offering, enrollment, slot_index, points) -> dict:
    """Fənn qovluğunun baxış zolağı üçün jurnal tərəfi — YAZI YOXDUR, ≤ 3 sorğu.

    ``{"topic_title", "max_points", "current_points", "total_after", "total_max",
    "blocked", "reason"}``."""
    from apps.registrar import selfwork_hook

    return selfwork_hook.preview(offering=offering, enrollment=enrollment, slot_index=slot_index, points=points)


def ensure_structure(offering):
    """Təsdiqlənmiş sillabusun strukturunu jurnala tətbiq edir (idempotent) → struktur planı.

    Bax :func:`apps.registrar.selfwork_structure.ensure_structure`."""
    from apps.registrar import selfwork_structure

    return selfwork_structure.ensure_structure(offering)


__all__ = [
    "POINTS_STEP",
    "SOURCE_JOURNAL",
    "SOURCE_SUBJECT_FOLDER",
    "TOTAL_MAX",
    "cap_total",
    "display",
    "effective_points",
    "effective_value",
    "ensure_structure",
    "is_graded",
    "normalize",
    "parse_points",
    "points_expression",
    "preview",
    "record_points",
    "selfwork_slots",
    "selfwork_total_for",
    "selfwork_totals",
    "selfwork_totals_by_offering",
]
