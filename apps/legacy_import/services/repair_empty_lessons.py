"""Jurnalın MƏZMUNSUZ keçmiş sütunlarının (dərslərin) təmizlənməsi — qayda + hesabat.

Qüsur (sahib, 2026-10-24): «Keçilmiş dərslər»də və jurnalda köhnə sistemdən gələn
çoxlu «Jurnal boşdur» (0/0) sütunu görünür. Mənbəyi: köhnə sistemdə müəllim günü
(``journals_dates_added_by_teacher``) əlavə edib, heç bir xana yazmayıb — cutover
J3 (``journal_lessons``) və ``legacy_delta_apply`` HƏR dərs tarixini ``Lesson``-a
çevirirdi, xanası olsun-olmasın (J3 bunu ``legacy_journal_lesson_kind_absent`` INFO
kodu ilə qeyd edir). Delta artıq belə sütun yaratmır (``delta/lessons.py``); bu
modul ƏVVƏLCƏDƏN yaranmışları silir.

Sahib (2026-10-24, əlavə): «gün yazılıb, içində heç nə yoxdursa silinsin. Bir neçə
tələbəyə “qb” yazılıbsa belə o sütun silinsin, olmamalıdır» — həm köçürülmüş, həm
müəllimin yeni sistemdə açdığı KEÇMİŞ dərs.

Sütunun növü (hamısı keçmiş + məzmunsuz)
-----------------------------------------
* **tam boş** (``empty``) — köçürülmüş, ``LessonMark`` sətri YOXDUR. Həmişə namizəddir.
* **yalnız «qb»** (``absent_only``) — köçürülmüş, xanaları VAR, amma HAMISI ``absent``
  və balsızdır. YALNIZ ``--include-absent-only`` ilə; «qb» xanaları dərslə birlikdə
  silinir və qayıb saatı (``Enrollment.absence_hours``) yenidən hesablanır.
* **müəllimin** (``teacher``) — ``created_by`` doludur (yeni sistemdə ``create_lesson``
  ilə açılıb). YALNIZ ``--include-teacher-lessons`` ilə; tam boş olanı həmin bayraqla,
  yalnız «qb» olanı İKİ bayraqla. Bu gün (``--before`` günü) və sonra YARADILAN dərs
  (keçmiş tarixə olsa da) toxunulmazdır — müəllim onu hələ doldura bilər.

Ortaq şərtlər — HAMISI eyni anda doğru olmalıdır
------------------------------------------------
* **keçmişdədir** — ``date < --before`` (defolt: bu gün; bu günün/gələcəyin dərsi toxunulmaz);
* **real xana yoxdur** — heç bir xanada bal yoxdur və ``absent``-dən başqa status
  (``present``/«iə», ``excused``/«ü/q») yoxdur;
* **müəllim məzmunu yoxdur** — mövzu boşdur, «cədvəldən kənar» səbəbi boşdur, dərsə
  bağlı rəsmi düzəliş (``LessonCorrection``) və ya xana düzəlişi
  (``JournalCorrection.lesson_ref`` — silinmiş xananın izi də) yoxdur. Bu şərt həm də
  DB qoruyucusunu təmin edir: düzəliş cədvəlləri UPDATE/DELETE-ə bağlıdır (0043) və
  xananın silinməsi ``JournalCorrection.lesson_mark``-ı ``SET NULL`` edərdi;
* **jurnal kilidli deyil** — ``AssessmentScheme`` təsdiqlənib/dərc olunubsa sütun
  YALNIZ ``--include-locked`` ilə silinir (``gradebook.delete_lesson`` kilidli
  jurnalda heç vaxt silmir; tarixi jurnal J7 ilə kilidlənib, ona görə bu qərar
  operatorundur — dry-run hər sayı göstərir).

Otaq / saat / növ / müəllim sütunun məzmunu SAYILMIR — onlar köhnə cədvəldən gələn
slot metadatasıdır (J11), boş sütunu dolu etmir.

Silmə, kilid, audit və aqreqatlar: :mod:`.repair_empty_lessons_apply`.

Tələbə SƏTİRLƏRİ (boş qeydiyyatlar) bu əmrdə SİLİNMİR: idxalın yaratdığı yeganə
dəqiq hal (eyni fənnin boş öz-qrup təkrarı) ``delta/dedupe.py``-da rəsmi «alt qrup
birləşməsi» ilə bağlanır; qalan boş sətirlər ``journal_hygiene`` («Boş fənn»)
aşkarlama/qərar axınındadır.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, replace

from django.apps import apps as django_apps
from django.db.models import BooleanField, Count, Exists, ExpressionWrapper, OuterRef, Q, Sum
from django.db.models.functions import Trim
from django.utils import timezone

AUDIT_REASON = "legacy_repair:empty_lessons"
AUDIT_RESOURCE = "legacy_import.empty_lesson"
DEFAULT_BATCH_SIZE = 500

#: ``AttendanceStatus.ABSENT`` («qb») — registrar modellərini birbaşa import etmirik (context_map).
ABSENT = "absent"

#: ``gradebook._CLOSED_STATUSES`` ilə eyni (kilid: təsdiqlənmiş və ya dərc olunmuş sxem).
_LOCKED_APPROVAL_STATUSES = ("approved",)

CATEGORY_EMPTY = "empty"
CATEGORY_ABSENT_ONLY = "absent_only"
CATEGORY_TEACHER = "teacher"

TABLE_HEADERS = ("Açılış", "Fənn", "Qrup", "Silinəcək sütun")


@dataclass(frozen=True)
class Scope:
    """Hansı sütunlar namizəddir — əmrin bayraqları bir yerdə."""

    before: datetime.date
    include_locked: bool = False
    include_absent_only: bool = False
    include_teacher_lessons: bool = False

    @property
    def created_cutoff(self) -> datetime.datetime:
        """Müəllimin dərsi bu andan ƏVVƏL yaradılmalıdır (``before`` gününün başlanğıcı, yerli vaxt)."""

        return timezone.make_aware(datetime.datetime.combine(self.before, datetime.time.min))


def _model(name: str):
    return django_apps.get_model("registrar", name)


def category_of(*, created_by_id, has_marks: bool) -> str:
    if created_by_id is not None:
        return CATEGORY_TEACHER
    return CATEGORY_ABSENT_ONLY if has_marks else CATEGORY_EMPTY


def _locked_journal() -> Exists:
    scheme = _model("AssessmentScheme").objects.filter(offering_id=OuterRef("offering_id"))
    return Exists(scheme.filter(Q(is_published=True) | Q(approval_status__in=_LOCKED_APPROVAL_STATUSES)))


def _has_content() -> Q:
    """Müəllim məzmunu: mövzu, cədvəldən-kənar səbəbi, dərs/xana düzəlişi."""

    lesson_corrections = _model("LessonCorrection").objects.filter(lesson_id=OuterRef("pk"))
    mark_corrections = _model("JournalCorrection").objects.filter(lesson_ref=OuterRef("pk"))
    return (
        ~Q(topic_trimmed="") | ~Q(off_schedule_reason="") | Q(Exists(lesson_corrections)) | Q(Exists(mark_corrections))
    )


def content_mark_q() -> Q:
    """Real xana: bal VAR və ya status «qb» DEYİL (iə, ü/q…)."""

    return Q(score__isnull=False) | ~Q(status=ABSENT)


def markless_past_lessons(organization, *, before: datetime.date):
    """Keçmiş, REAL xanası olmayan dərslər (tam boş + yalnız «qb»), mənşədən/məzmundan/kilidindən ƏVVƏL.

    ``has_marks`` = ən azı bir («qb») xana var.
    """

    marks = _model("LessonMark").objects.filter(lesson_id=OuterRef("pk"))
    return (
        _model("Lesson")
        .objects.filter(organization=organization, date__lt=before)
        .filter(~Exists(marks.filter(content_mark_q())))
        .annotate(topic_trimmed=Trim("topic"), has_marks=Exists(marks))
    )


def empty_imported_lessons(organization, *, before: datetime.date):
    """Köçürülmüş, keçmiş, TAM xanasız dərslər — məzmun/kilid süzgəcindən ƏVVƏL (köhnə səth)."""

    return markless_past_lessons(organization, before=before).filter(created_by__isnull=True, has_marks=False)


def _origin_q(scope: Scope) -> Q:
    allowed = Q(created_by__isnull=True)
    if scope.include_teacher_lessons:
        allowed |= Q(created_by__isnull=False, created_at__lt=scope.created_cutoff)
    return allowed


def candidate_lessons(organization, scope: Scope):
    """Silinəcək dərslər (modul sənədindəki BÜTÜN şərtlər + bayraqlar)."""

    queryset = markless_past_lessons(organization, before=scope.before).filter(_origin_q(scope))
    queryset = queryset.exclude(_has_content())
    if not scope.include_absent_only:
        queryset = queryset.filter(has_marks=False)
    if not scope.include_locked:
        queryset = queryset.filter(~_locked_journal())
    return queryset


def survey(organization, scope: Scope) -> dict:
    """Operator hesabatı — dörd aqreqat + bir say sorğusu, heç nə yazılmır.

    Növ sayları (``empty`` / ``absent_only`` / ``teacher_*``) bayraqdan ASILI DEYİL — dry-run
    bayraq verilməsə nəyin silinəcəyini də göstərir; ``deletable`` isə bayraqlara görədir.
    """

    cutoff = scope.created_cutoff
    imported = Q(created_by__isnull=True)
    teacher = Q(created_by__isnull=False, created_at__lt=cutoff)
    base = markless_past_lessons(organization, before=scope.before).annotate(
        has_content=ExpressionWrapper(_has_content(), output_field=BooleanField())
    )
    free = Q(has_content=False)
    # Aqreqat adları annotasiya adları ilə TOQQUŞMAMALIDIR (Django adı əvəzləyir).
    counts = base.aggregate(
        empty=Count("id", filter=free & imported & Q(has_marks=False)),
        absent_only=Count("id", filter=free & imported & Q(has_marks=True)),
        teacher_empty=Count("id", filter=free & teacher & Q(has_marks=False)),
        teacher_absent_only=Count("id", filter=free & teacher & Q(has_marks=True)),
        teacher_recent=Count("id", filter=free & Q(created_by__isnull=False, created_at__gte=cutoff)),
        with_content=Count("id", filter=Q(has_content=True)),
    )
    # Kilid sayı bayraqdan asılı olmasın: kilidli jurnalda nə qədər namizəd var (silinir / saxlanır).
    wide = candidate_lessons(organization, replace(scope, include_locked=True)).annotate(
        in_locked_journal=_locked_journal()
    )
    chosen = Q(pk__isnull=False) if scope.include_locked else Q(in_locked_journal=False)
    picked = wide.aggregate(
        locked=Count("id", filter=Q(in_locked_journal=True)),
        deletable=Count("id", filter=chosen),
        synthesised=Count("id", filter=chosen & Q(is_legacy_synthesised=True)),
        with_room=Count("id", filter=chosen & Q(room__isnull=False)),
    )
    candidates = candidate_lessons(organization, scope)
    marks = (
        _model("LessonMark")
        .objects.filter(lesson__in=candidates.values("pk"))
        .aggregate(absent_marks=Count("id"), absent_hours=Sum("lesson__hours"))
    )
    future = (
        _model("Lesson")
        .objects.filter(organization=organization, date__gte=scope.before)
        .filter(~Exists(_model("LessonMark").objects.filter(lesson_id=OuterRef("pk")).filter(content_mark_q())))
        .count()
    )
    return {
        **counts,
        **picked,
        "absent_marks": marks["absent_marks"] or 0,
        "absent_hours": marks["absent_hours"] or 0,
        "today_or_later": future,
    }


def per_offering(queryset, *, limit: int = 0) -> list[tuple]:
    """Ən çox silinəcək sütunu olan açılışlar (cədvəl üçün; adsız — fənn/qrup)."""

    rows = (
        queryset.order_by()
        .values("offering_id", "offering__subject__name", "offering__group__name")
        .annotate(n=Count("id"))
        .order_by("-n", "offering__subject__name")
    )
    if limit:
        rows = rows[:limit]
    return [
        (row["offering_id"], row["offering__subject__name"], row["offering__group__name"], row["n"]) for row in rows
    ]


__all__ = [
    "ABSENT",
    "AUDIT_REASON",
    "AUDIT_RESOURCE",
    "CATEGORY_ABSENT_ONLY",
    "CATEGORY_EMPTY",
    "CATEGORY_TEACHER",
    "DEFAULT_BATCH_SIZE",
    "TABLE_HEADERS",
    "Scope",
    "candidate_lessons",
    "category_of",
    "content_mark_q",
    "empty_imported_lessons",
    "markless_past_lessons",
    "per_offering",
    "survey",
]
