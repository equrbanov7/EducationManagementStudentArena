"""«Jurnal təmizliyi» — KEÇİRİLMƏYƏN FƏNN aşkarlaması (yalnız oxu; sahib 2026-10-11).

Sahib: «Qrupun keçmədiyi fənn sistemə səhvən düşüb (qrupa səhvən düşənlər var). Belə edə bilərik: əgər
qrupda HAMI kəsrdirsə və ancaq GİRİŞ BALI varsa, deməli o fənn keçirilməyib.» Əlavə: «keçirilməyən fənndə
heç kimin ÇIXIŞ balı da yoxdur».

Vahid — AÇILIŞ (fənn × qrup × dövr). Açılış «keçirilməyib» sayılır, əgər:

1. **Dövr bitib** — ``period.end_date < bu gün`` və dövr cari DEYİL (gedən/gələcək semestrdə imtahan sadəcə
   hələ olmayıb — heç vaxt namizəd deyil).
2. **≥ 2 tələbə** — açılışda ``dropped`` olmayan ən azı iki qeydiyyat (tək tələbəlik açılış fərdi haldır).
3. **Heç kimin imtahan («çıxış») sübutu yoxdur** — açılışın HEÇ BİR qeydiyyatında (``dropped`` daxil, həm də
   köçürmə sələflərində) :func:`exam_evidence_q`-dakı mənbələrin heç biri yoxdur:
   * yeni sistem: ``FinalGrade.exam_score`` (0 da sübutdur — «gəlib, 0 alıb»), ``ResitRecord.resit_score``,
     hər hansı ``ExamScoreEntry`` (onlayn/kağız imtahan, düzəliş, apellyasiya);
   * köhnə sistem (``LegacyGradeFact``): imtahan xanası («im», boş olmayan bal/mətn — «l» işarəsi də),
     təkrar imtahan xanası («im2»), imtahan giriş/çıxış cəhdi (``imthngrscxsblr``-in ÇIXIŞ balı),
     yekun cədvəli (``yekun``: imtahan / yekun balı və ya ``kesr=0`` — köhnə sistemdə keçib).
   Giriş balı (komponentlər, dərs xanaları, köhnə «giriş», kollokvium/xüsusi kodlar) sübut SAYILMIR.
4. **Hamı kəsr / nəticəsiz** — 3-cü şərtdən çıxır: imtahan balı olmadan kanonik nəticə heç vaxt «keçdi»
   ola bilməz (``finals.compute_final_result``: ``passed`` ⇒ ``graded``). Tələbə ya «Kəsildi / Kəsilir»
   (canlı jurnal, q/b), ya da «Köhnə sistemdə nəticə yazılmayıb» (köçürülmüş, bağlı jurnal) görür —
   ikisi də «keçməyib» deməkdir; ayrıca yoxlama lazım deyil (testlə kilidlənib).

Güc (``strong``) — İKİ şərt birdən:

* **qrup üçün imtahan sessiyası keçirilib**: qrupun EYNİ dövrdəki digər (aktiv sətirli) açılışlarının ən azı
  yarısında (yuxarı yuvarlaq, ən azı biri) imtahan sübutu var — yəni yalnız bu fənn imtahansızdır;
* **dərs izi yoxdur**: açılışda heç bir dərs xanası (``LessonMark``) və kollokvium / midterm / sərbəst iş
  balı yoxdur — yalnız köçürülmüş «giriş» komponenti və ya heç nə (fənn qrupa sadəcə «düşüb»).
Qalan hamısı ``review``: qrupsuz açılış, sessiyası boş dövr (məs. köhnə sistemin imtahan yazmadığı
2021/2022 Yaz) və ya dərs/kollokvium izi olan, amma imtahanı yazılmamış fənn (data boşluğu ola bilər —
etiket ``taught`` ilə göstərilir, RİM ayrıca yoxlayır).

Performans: açılış səviyyəli hesab (:func:`scan`) SABİT sayda sorğudur (imtahan mənbələri başına bir
``DISTINCT offering_id`` + bir aktiv-sətir aqreqatı), qalan qərar Python-da id dəstləri üzərində verilir —
11 000 açılışlı real bazada ``NOT EXISTS`` zənciri statement timeout-a düşürdü.

Qeydiyyat SİLİNMİR: qərar «Boş fənn» ilə eynidir (``dropped``, qərar jurnalı, audit, «Bərpa et»).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from django.db.models import (
    BooleanField,
    Case,
    Count,
    ExpressionWrapper,
    F,
    Func,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    When,
)
from django.utils import timezone

from .models import (
    ComponentKind,
    ComponentScore,
    Enrollment,
    ExamScoreEntry,
    FinalGrade,
    HygieneCategory,
    LegacyGradeEvidenceKind,
    LegacyGradeFact,
    LessonMark,
    ResitRecord,
)

NOT_HELD = HygieneCategory.NOT_HELD.value
REASON_NOT_HELD = "not_held"
TAG_ENTRY_ONLY = "entry_only"
TAG_NO_SCORES = "no_scores"
TAG_LEGACY = "legacy_no_result"
TAG_TAUGHT = "taught"
NOT_HELD_TAGS = (TAG_ENTRY_ONLY, TAG_NO_SCORES, TAG_TAUGHT, TAG_LEGACY)
MIN_STUDENTS = 2

_LEGACY_EXAM_KINDS = (
    LegacyGradeEvidenceKind.EXAM,
    LegacyGradeEvidenceKind.RESIT,
    LegacyGradeEvidenceKind.EXAM_ENTRY_EXIT,
    LegacyGradeEvidenceKind.SUMMARY,
)
#: Mənbədən açılışa iki yol: qeydiyyatın öz açılışı və köçürmə xələfinin açılışı (data sələfdə qalıb).
_PATHS = ("enrollment__offering_id", "enrollment__superseded_by__offering_id")


def legacy_exam_q() -> Q:
    """Köhnə faktda imtahan/çıxış izi: imtahan, təkrar, yekun balı, xanada mətn və ya ``kesr=0`` (keçib).

    «Yalnız giriş balı» = faktda bunların heç biri yoxdur: ``entry_score`` (giriş), kollokvium və xüsusi kodlar
    (``other``: pa/wr/ss/k1…) imtahan sübutu deyil; imtahan giriş/çıxış cəhdində (``exam_entry_exit``) yalnız
    ÇIXIŞ balı (``exam_score``) sayılır.
    """
    scored = (
        Q(exam_score__isnull=False)
        | Q(resit_score__isnull=False)
        | Q(final_score__isnull=False)
        | ~Q(exam_score_text="")
        | ~Q(resit_score_text="")
        | ~Q(final_score_text="")
    )
    in_exam_cell = Q(evidence_kind__in=(LegacyGradeEvidenceKind.EXAM, LegacyGradeEvidenceKind.RESIT)) & ~Q(
        raw_score_text=""
    )
    passed = Q(evidence_kind=LegacyGradeEvidenceKind.SUMMARY, legacy_kesr=0)
    return Q(evidence_kind__in=_LEGACY_EXAM_KINDS) & (scored | in_exam_cell | passed)


def exam_querysets(organization) -> list:
    """İmtahan («çıxış») sübutunun mənbələri — TƏK siyahı (aşkarlama, testlər, CLI izahı)."""
    return [
        FinalGrade.objects.filter(organization=organization, exam_score__isnull=False),
        ResitRecord.objects.filter(organization=organization, resit_score__isnull=False),
        ExamScoreEntry.objects.filter(organization=organization),
        LegacyGradeFact.objects.filter(organization=organization, enrollment__isnull=False).filter(legacy_exam_q()),
    ]


def examined_offering_ids(organization, offering_ids=None) -> set:
    """İmtahan sübutu olan açılışlar — mənbə × yol başına BİR ``DISTINCT`` sorğu (8 sorğu)."""
    found = set()
    for queryset in exam_querysets(organization):
        for path in _PATHS:
            rows = queryset.filter(**{f"{path}__isnull": False})
            if offering_ids is not None:
                rows = rows.filter(**{f"{path}__in": offering_ids})
            found.update(rows.order_by().values_list(path, flat=True).distinct())
    return found


def taught_offering_ids(offering_ids) -> set:
    """Dərs izi olan açılışlar: dərs xanası və ya kollokvium / midterm / sərbəst iş balı (2 sorğu)."""
    ids = list(offering_ids)
    if not ids:
        return set()
    found = set(
        LessonMark.objects.filter(enrollment__offering_id__in=ids)
        .order_by()
        .values_list("enrollment__offering_id", flat=True)
        .distinct()
    )
    found.update(
        ComponentScore.objects.filter(enrollment__offering_id__in=ids)
        .exclude(component__kind=ComponentKind.GENERIC)
        .order_by()
        .values_list("enrollment__offering_id", flat=True)
        .distinct()
    )
    return found


def ended_period_q(prefix: str = "", *, today=None) -> Q:
    """Dövr bitib və cari deyil (``prefix`` — ``offering__`` kimi yol)."""
    today = today or timezone.localdate()
    return Q(**{f"{prefix}period__end_date__lt": today}) & ~Q(**{f"{prefix}period__is_current": True})


def _uuid(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


@dataclass
class Scan:
    """Açılış səviyyəli nəticə: ``offerings`` — ``{offering_id: info}`` (yalnız keçirilməyənlər)."""

    offerings: dict = field(default_factory=dict)

    @property
    def ids(self) -> list:
        return sorted(self.offerings, key=str)

    @property
    def strong_ids(self) -> list:
        return sorted((pk for pk, info in self.offerings.items() if info["strong"]), key=str)

    @property
    def taught_ids(self) -> list:
        return sorted((pk for pk, info in self.offerings.items() if info["taught"]), key=str)


def scan(organization, *, today=None, offering_ids=None) -> Scan:
    """Şərt 1–3 + güc. ``offering_ids`` verilibsə yalnız onlar (və qrup-dövr qonşuları) yoxlanılır."""
    active = (
        Enrollment.objects.filter(organization=organization)
        .exclude(status=Enrollment.Status.DROPPED)
        .filter(ended_period_q("offering__", today=today))
    )
    if offering_ids is not None:
        offering_ids = [_uuid(value) for value in offering_ids if _uuid(value) is not None]
        scope = Enrollment.objects.filter(organization=organization, offering_id__in=offering_ids)
        active = active.filter(
            Q(offering_id__in=offering_ids)
            | Q(
                offering__group_id__in=scope.values("offering__group_id"),
                offering__period_id__in=scope.values("offering__period_id"),
            )
        )
    rows = list(
        active.order_by()
        .values_list("offering_id", "offering__group_id", "offering__period_id")
        .annotate(size=Count("pk"))
    )
    examined = examined_offering_ids(organization, [row[0] for row in rows] if offering_ids is not None else None)
    by_slot = {}
    for offering_id, group_id, period_id, _size in rows:
        if group_id is not None:
            by_slot.setdefault((group_id, period_id), []).append(offering_id)
    result = Scan()
    wanted = set(offering_ids) if offering_ids is not None else None
    for offering_id, group_id, period_id, size in rows:
        if size < MIN_STUDENTS or offering_id in examined or (wanted is not None and offering_id not in wanted):
            continue
        siblings = [pk for pk in by_slot.get((group_id, period_id), ()) if pk != offering_id]
        siblings_exam = sum(1 for pk in siblings if pk in examined)
        result.offerings[offering_id] = {
            "size": size,
            "siblings": len(siblings),
            "siblings_exam": siblings_exam,
            # Ən azı yarısı (yuxarı yuvarlaq) və ən azı biri imtahanlıdır.
            "session": group_id is not None and siblings_exam > 0 and 2 * siblings_exam >= len(siblings),
        }
    taught = taught_offering_ids(result.offerings)
    for offering_id, info in result.offerings.items():
        info["taught"] = offering_id in taught
        info["strong"] = info["session"] and not info["taught"]
    return result


def _count(queryset) -> Subquery:
    return Subquery(
        queryset.order_by().annotate(n=Func(F("pk"), function="COUNT")).values("n")[:1],
        output_field=IntegerField(),
    )


def candidates(organization, *, today=None, result=None):
    """Keçirilməyən açılışların ``dropped`` olmayan qeydiyyatları — annotasiyalar: ``jh_strong``,
    ``jh_has_evidence`` (giriş balı və s.), ``jh_legacy`` (köçürülmüş açılış), ``jh_size`` (yalnız oxunanda
    hesablanır — aqreqat sorğusu istifadə olunmayan annotasiyanı atır)."""
    from . import journal_hygiene as hygiene  # dövri import olmasın: o modul bunu tənbəl çağırır

    result = result if result is not None else scan(organization, today=today)
    active = Enrollment.objects.filter(offering_id=OuterRef("offering_id")).exclude(status=Enrollment.Status.DROPPED)
    return (
        Enrollment.objects.filter(organization=organization, offering_id__in=result.ids)
        .exclude(status=Enrollment.Status.DROPPED)
        .annotate(
            jh_strong=Case(
                When(offering_id__in=result.strong_ids, then=True), default=False, output_field=BooleanField()
            ),
            jh_has_evidence=ExpressionWrapper(
                Q(absence_hours__gt=0) | hygiene.evidence_q(), output_field=BooleanField()
            ),
            jh_legacy=ExpressionWrapper(hygiene.legacy_offering_q(), output_field=BooleanField()),
            jh_taught=Case(
                When(offering_id__in=result.taught_ids, then=True), default=False, output_field=BooleanField()
            ),
            jh_size=_count(active),
        )
    )


#: Etiket → süzgəc şərti (``jh_*`` annotasiyaları üzərində).
TAG_FILTERS = {
    TAG_ENTRY_ONLY: Q(jh_has_evidence=True),
    TAG_NO_SCORES: Q(jh_has_evidence=False),
    TAG_TAUGHT: Q(jh_taught=True),
    TAG_LEGACY: Q(jh_legacy=True),
}


def category_q(code: str):
    return TAG_FILTERS.get(code)


def counts(queryset) -> dict:
    """BİR aqreqat: sətir, açılış (vahid), güclü sətir/açılış, etiket sayları."""
    aggregates = {
        "total": Count("pk"),
        "strong": Count("pk", filter=Q(jh_strong=True)),
        "offerings": Count("offering_id", distinct=True),
        "offerings_strong": Count("offering_id", distinct=True, filter=Q(jh_strong=True)),
    }
    for code, condition in TAG_FILTERS.items():
        aggregates[code] = Count("pk", filter=condition)
    totals = queryset.order_by().aggregate(**aggregates)
    return {key: int(value or 0) for key, value in totals.items()}


def tags_for(row: dict) -> list:
    codes = [TAG_ENTRY_ONLY if row.get("jh_has_evidence") else TAG_NO_SCORES]
    if row.get("jh_taught"):
        codes.append(TAG_TAUGHT)
    if row.get("jh_legacy"):
        codes.append(TAG_LEGACY)
    return codes


def offering_members(organization, offering_ids, *, today=None) -> dict:
    """``{offering_id: {qeydiyyat id-ləri}}`` — HAZIRDA keçirilməyən açılışların bütün aktiv sətirləri."""
    result = scan(organization, today=today, offering_ids=offering_ids)
    members = {}
    rows = (
        Enrollment.objects.filter(organization=organization, offering_id__in=result.ids)
        .exclude(status=Enrollment.Status.DROPPED)
        .values_list("offering_id", "pk")
    )
    for offering_id, pk in rows:
        members.setdefault(str(offering_id), set()).add(str(pk))
    return members


def partial_offerings(organization, rows) -> list:
    """Seçimdə açılışın YALNIZ bir hissəsi varsa həmin açılışlar — vahid açılışdır, yarımçıq qərar olmaz."""
    selected = {}
    for row in rows:
        selected.setdefault(str(row["offering_id"]), set()).add(str(row["id"]))
    members = offering_members(organization, list(selected))
    return sorted(offering for offering, ids in selected.items() if members.get(offering, set()) != ids)


def whole_offering_ids(rows, limit: int) -> list:
    """``(id, offering_id)`` ardıcıllığından ``limit``-ə sığan TAM açılışların id-ləri (sıra saxlanır)."""
    groups = {}
    for pk, offering_id in rows:
        groups.setdefault(offering_id, []).append(str(pk))
    picked = []
    for ids in groups.values():
        if len(picked) + len(ids) > limit:
            break
        picked.extend(ids)
    return picked


__all__ = [
    "MIN_STUDENTS",
    "NOT_HELD",
    "NOT_HELD_TAGS",
    "REASON_NOT_HELD",
    "TAG_ENTRY_ONLY",
    "TAG_LEGACY",
    "TAG_NO_SCORES",
    "TAG_TAUGHT",
    "Scan",
    "candidates",
    "category_q",
    "counts",
    "ended_period_q",
    "exam_querysets",
    "examined_offering_ids",
    "legacy_exam_q",
    "offering_members",
    "partial_offerings",
    "scan",
    "tags_for",
    "taught_offering_ids",
    "whole_offering_ids",
]
