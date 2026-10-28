"""Bölünmüş jurnal — kim hansı SƏTİRLƏRİ (tələbələr) və SÜTUNLARI (dərs növləri) görür/yazır (sahib 2026-10-26).

Sahib: «Fənn 2 müəllim arasında bölünübsə mühazirəçi mühazirəni, seminarçı yalnız öz ballarını görsün.»
Səviyyə jurnalı: «müəllim jurnalını açanda yalnız öz tələbələrini görsün, hamını yox.»

Model :class:`apps.registrar.models.JournalShare`-dədir. Qaydalar (:func:`journal_scope`):

* superuser / İKT (RİM) rəhbəri / təşkilat sahibi — TAM;
* payı OLMAYAN istifadəçi (açılışın sahibi, korrektor, müşahidəçi) — TAM (köhnə davranış dəyişmir);
* açılışın SAHİBİ payla — öz payının tələbələri (boş = hamısı) ∪ başqa heç bir payın örtmədiyi tələbələr;
  dərs növləri: öz növləri (boş = hamısı) ∪ başqa payların iddia etmədiyi növlər — növü yalnız açılışın BÜTÜN
  tələbələrini (birlikdə) əhatə edən paylar iddia edir; qonaq / səviyyə payı sahibin sütunlarını gizlətmir;
* PAY SAHİBİ (sahib deyil) — yalnız öz payı: tələbələr (boş = hamısı), növlər (boş = hamısı).

``Lesson.instructor`` istifadəçinin özüdürsə həmin dərs sütunu HƏMİŞƏ görünür. Bal idarəsi (Midterm, komponent,
yekun, kurs/sərbəst iş) — tam redaktor, sahib və növ məhdudiyyəti OLMAYAN pay sahibi; hər halda yalnız öz
sətirlərində. Yekun bal riyaziyyatı DƏYİŞMİR — yalnız göstərilən/yazıla bilən hissə daralır.

Sorğu büdcəsi: açılış üzrə paylar BİR dəfə oxunur (paylar varsa + ara cədvəl) və offering obyektinə yapışdırılır.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q
from django.utils.translation import pgettext

from .models import Enrollment, JournalShare, LessonKind

#: Bütün dərs növləri — boş ``kinds`` siyahısının mənası.
ALL_KINDS = frozenset(LessonKind.values)
_MEMO_ATTR = "_journal_shares_memo"


@dataclass(frozen=True)
class Scope:
    """İstifadəçinin bu açılışdakı görünüş/yazı əhatəsi. ``None`` = məhdudiyyət yoxdur."""

    kinds: frozenset | None = None
    enrollment_ids: frozenset | None = None
    full: bool = True
    can_manage_scores: bool = True
    is_owner: bool = False
    teacher_id: int | None = None

    def allows_kind(self, kind) -> bool:
        return self.kinds is None or kind in self.kinds

    def owns_lesson(self, lesson) -> bool:
        """Dərs açıq şəkildə bu müəllimin adınadır (``Lesson.instructor``). Adsız (köçürülmüş) dərs heç kimin
        sayılmır — əks halda sahib başqa payın köhnə dərslərini də görərdi."""
        instructor_id = getattr(lesson, "instructor_id", None)
        return instructor_id is not None and instructor_id == self.teacher_id

    def allows_lesson(self, lesson) -> bool:
        return self.allows_kind(getattr(lesson, "kind", None)) or self.owns_lesson(lesson)

    def allows_enrollment(self, enrollment_id) -> bool:
        return self.enrollment_ids is None or str(enrollment_id) in self.enrollment_ids


FULL = Scope()


def active_shares(offering) -> list:
    """Açılışın aktiv payları (hər payda ``enrollment_id_set`` — sətir id-ləri, mətn). Offering-də memo."""
    memo = getattr(offering, _MEMO_ATTR, None)
    if memo is not None:
        return memo
    shares = list(JournalShare.objects.filter(offering_id=offering.pk, is_active=True).order_by("created_at"))
    if shares:
        by_share = defaultdict(set)
        through = JournalShare.enrollments.through.objects.filter(journalshare_id__in=[share.pk for share in shares])
        for share_id, enrollment_id in through.values_list("journalshare_id", "enrollment_id"):
            by_share[share_id].add(str(enrollment_id))
        for share in shares:
            share.enrollment_id_set = frozenset(by_share[share.pk])
    setattr(offering, _MEMO_ATTR, shares)
    return shares


def forget(offering) -> None:
    """Memo-nu at (paylar dəyişəndən sonra eyni obyektlə yenidən hesablamaq üçün)."""
    if hasattr(offering, _MEMO_ATTR):
        delattr(offering, _MEMO_ATTR)


def _has_instructor_authority(user, offering) -> bool:
    """``journal_access._is_live_assigned_instructor`` ilə EYNİ yoxlama (snapshot → canlı sorğu)."""
    from .integrity import is_authorized_instructor
    from .journal_access import _snapshot_grade_input

    verdict = _snapshot_grade_input(user, offering.organization)
    if verdict is not None:
        return verdict
    return is_authorized_instructor(organization=offering.organization, instructor=user)


def share_for(user, offering):
    """İstifadəçinin bu açılışdakı AKTİV payı — müəllimin canlı ``grade.input`` səlahiyyəti varsa; yoxsa None."""
    if not getattr(user, "is_authenticated", False):
        return None
    share = next((item for item in active_shares(offering) if item.teacher_id == user.pk), None)
    if share is None or not _has_instructor_authority(user, offering):
        return None
    return share


def _is_full_actor(user, offering) -> bool:
    if getattr(user, "is_superuser", False) or getattr(user, "is_ikt_rehber", False):
        return True
    return offering.organization.owner_id == user.pk


def _claimed_kinds(offering, others) -> set:
    """Başqa payların sahibdən «aldığı» dərs növləri (RİM MR-000010, 2026-10-27).

    Növ yalnız açılışın BÜTÜN aktiv tələbələrini əhatə edən pay(lar) tərəfindən iddia olunur: bütün sətirli pay
    (``enrollment_id_set`` boş) dərhal; sətir-məhdud paylar (qonaq / səviyyə / yarım qrupun seminarçısı) isə yalnız
    həmin növü daşıyan payların sətirləri BİRLİKDƏ bütün siyahını örtəndə. Bir qonaq tələbəli ``kinds=[]`` payı
    sahibin öz seminar/lab sütunlarını gizlətmir. Sətir-məhdud pay varsa — bir sorğu (aktiv siyahı)."""
    claimed: set = set()
    partial: dict = defaultdict(set)
    for share in others:
        share_kinds = set(share.kinds) & ALL_KINDS if share.kinds else set(ALL_KINDS)
        if not share.enrollment_id_set:
            claimed |= share_kinds
            continue
        for kind in share_kinds:
            partial[kind] |= share.enrollment_id_set
    pending = {kind: rows for kind, rows in partial.items() if kind not in claimed}
    if pending:
        roster = {
            str(pk)
            for pk in Enrollment.objects.filter(offering_id=offering.pk, status=Enrollment.Status.ENROLLED).values_list(
                "pk", flat=True
            )
        }
        claimed |= {kind for kind, rows in pending.items() if roster and roster <= rows}
    return claimed


def journal_scope(user, offering) -> Scope:
    """İstifadəçinin bu açılışdakı əhatəsi (modul şərhindəki qaydalar)."""
    if not getattr(user, "is_authenticated", False) or _is_full_actor(user, offering):
        return FULL
    shares = active_shares(offering)
    own = next((share for share in shares if share.teacher_id == user.pk), None)
    if own is None:
        return FULL
    is_owner = offering.instructor_id == user.pk
    others = [share for share in shares if share is not own]
    kinds = frozenset(own.kinds) & ALL_KINDS if own.kinds else None
    rows = own.enrollment_id_set or None
    if is_owner:
        if kinds is not None:
            kinds = kinds | (ALL_KINDS - _claimed_kinds(offering, others))
        if rows is not None and all(share.enrollment_id_set for share in others):
            claimed_rows = set().union(*(share.enrollment_id_set for share in others))
            offering_rows = {
                str(pk) for pk in Enrollment.objects.filter(offering_id=offering.pk).values_list("pk", flat=True)
            }
            rows = rows | frozenset(offering_rows - claimed_rows)
    if kinds is not None and kinds >= ALL_KINDS:
        kinds = None
    full = kinds is None and rows is None
    return Scope(
        kinds=kinds,
        enrollment_ids=rows,
        full=full,
        can_manage_scores=full or is_owner or kinds is None,
        is_owner=is_owner,
        teacher_id=user.pk,
    )


def visible_lessons(scope: Scope, lessons, mark_map) -> list:
    """Göstərilən dərs sütunları: əhatədəki növlər; sətirlər məhduddursa BAŞQA payın dərsləri də gizlənir.

    Səviyyə jurnalında hər müəllim öz tələbələrinə ayrıca dərs yazır — xanaları yalnız başqa payın
    tələbələrində olan dərs bu müəllimin jurnalında boş sütun kimi görünməməlidir. Öz adına olan dərs və
    hələ heç bir xanası olmayan (yeni) dərs görünür. ``mark_map`` — ``{(qeydiyyat, dərs): işarə}``."""
    lessons = [lesson for lesson in lessons if scope.allows_lesson(lesson)]
    if scope.enrollment_ids is None:
        return lessons
    marked = defaultdict(set)
    for enrollment_id, lesson_id in mark_map:
        marked[lesson_id].add(str(enrollment_id))
    return [
        lesson
        for lesson in lessons
        if scope.owns_lesson(lesson) or not marked.get(lesson.id) or marked[lesson.id] & scope.enrollment_ids
    ]


def has_writable_share(user, offering) -> bool:
    """Pay sahibi (sahib deyil) birbaşa redaktordur — ``journal_access`` qapıları üçün."""
    from .journal_access import offering_accepts_writes

    return offering_accepts_writes(offering) and share_for(user, offering) is not None


def shared_offering_ids(user):
    """İstifadəçinin aktiv payı olan açılışların id subquery-si (siyahılar üçün)."""
    return JournalShare.objects.filter(teacher_id=getattr(user, "pk", user), is_active=True).values("offering_id")


def own_or_shared_q(user, *, prefix: str = "") -> Q:
    """``CourseOffering`` Q — açılışın sahibi VƏ YA aktiv pay sahibi."""
    user_id = getattr(user, "pk", user)
    return Q(**{f"{prefix}instructor_id": user_id}) | Q(**{f"{prefix}pk__in": shared_offering_ids(user_id)})


def scoped_student_counts(user, offerings, counts: dict) -> dict:
    """Siyahının tələbə sayı: pay sahibinin (sahib deyil) sətrində yalnız ÖZ tələbələri.

    Sahibin öz açılışları üçün sorğu yoxdur; başqasının açılışı səhifədə varsa — bir toplu sorğu. Boş pay
    (bütün tələbələr) ara cədvəldə sətir daşımır, sayı ümumi say olaraq qalır."""
    from django.db.models import Count, F

    user_id = getattr(user, "pk", None)
    if getattr(user, "is_superuser", False) or getattr(user, "is_ikt_rehber", False):
        return counts  # tam əhatəli aktor — pay sayı ona aid deyil (sorğu da yoxdur)
    foreign = [offering.pk for offering in offerings if offering.instructor_id != user_id]
    if user_id is None or not foreign:
        return counts
    rows = (
        Enrollment.objects.filter(
            offering_id__in=foreign,
            status=Enrollment.Status.ENROLLED,
            journal_shares__teacher_id=user_id,
            journal_shares__is_active=True,
            journal_shares__offering_id=F("offering_id"),
        )
        .values("offering_id")
        .annotate(n=Count("id", distinct=True))
    )
    return {**counts, **{row["offering_id"]: row["n"] for row in rows}}


def chip(scope: Scope, offering=None) -> dict | None:
    """Jurnal başlığındakı «Bölünmüş jurnal» çipi (məhdud əhatədə); tam əhatədə None."""
    if scope.full:
        return None
    from .practical_label import kind_choices

    labels = dict(kind_choices(offering))  # «praktiki» açılış: seminar → «Praktiki məşğələ»
    kinds = [str(labels[value]) for value in LessonKind.values if scope.kinds is None or value in scope.kinds]
    return {
        "text": pgettext(
            "registrar.journal_share", "Bölünmüş jurnal: yalnız sizin tələbələriniz / dərs növləriniz göstərilir"
        ),
        "kinds": kinds,
        "rows_limited": scope.enrollment_ids is not None,
        "kinds_limited": scope.kinds is not None,
    }


__all__ = [
    "ALL_KINDS",
    "FULL",
    "Scope",
    "active_shares",
    "chip",
    "forget",
    "has_writable_share",
    "journal_scope",
    "own_or_shared_q",
    "scoped_student_counts",
    "share_for",
    "shared_offering_ids",
    "visible_lessons",
]
