"""Köçürmədən qalan TAM BOŞ jurnal sütunlarının (dərslərin) təmizlənməsi.

Qüsur (sahib, 2026-10-24): «Keçilmiş dərslər»də və jurnalda köhnə sistemdən gələn
çoxlu «Jurnal boşdur» (0/0) sütunu görünür. Mənbəyi: köhnə sistemdə müəllim günü
(``journals_dates_added_by_teacher``) əlavə edib, heç bir xana yazmayıb — cutover
J3 (``journal_lessons``) və ``legacy_delta_apply`` HƏR dərs tarixini ``Lesson``-a
çevirirdi, xanası olsun-olmasın (J3 bunu ``legacy_journal_lesson_kind_absent`` INFO
kodu ilə qeyd edir). Delta artıq belə sütun yaratmır (``delta/lessons.py``); bu
modul ƏVVƏLCƏDƏN yaranmışları silir.

Silinən dərs — HAMISI eyni anda doğru olmalıdır
-----------------------------------------------
* **köçürülüb** — ``created_by`` boşdur (üç idxal yazıçısının ortaq izi; yeni
  sistemdə dərsi yalnız ``create_lesson`` yaradır və aktoru HƏMİŞƏ yazır — bax
  ``apps.registrar.lessons_log_totals`` «KÖÇÜRMƏ»). Müəllimin bu gün açıb hələ
  işarələmədiyi dərs ``created_by`` daşıyır → HEÇ VAXT namizəd deyil;
* **keçmişdədir** — ``date < --before`` (defolt: bu gün, yəni bu günün və
  gələcəyin dərsi toxunulmazdır);
* **heç bir xanası yoxdur** — ``LessonMark`` sətri YOXDUR (status daşıyan hər xana,
  «iə» də daxil, məzmundur);
* **müəllim məzmunu yoxdur** — mövzu boşdur, «cədvəldən kənar» səbəbi boşdur, dərsə
  bağlı rəsmi düzəliş (``LessonCorrection``) və ya xana düzəlişi
  (``JournalCorrection.lesson_ref`` — silinmiş xananın izi) yoxdur;
* **jurnal kilidli deyil** — ``AssessmentScheme`` təsdiqlənib/dərc olunubsa sütun
  YALNIZ ``--include-locked`` ilə silinir (``gradebook.delete_lesson`` kilidli
  jurnalda heç vaxt silmir; tarixi jurnal J7 ilə kilidlənib, ona görə bu qərar
  operatorundur — dry-run hər iki sayı göstərir).

Otaq / saat / növ / müəllim sütunun məzmunu SAYILMIR — onlar köhnə cədvəldən gələn
slot metadatasıdır (J11), boş sütunu dolu etmir.

Təhlükəsizlik: dəstə-dəstə (``batch_size``), hər dəstə öz atomik blokunda (``scoped_atomic``); sətirlər əvvəl
``SELECT … FOR UPDATE`` ilə kilidlənir və şərtlər KİLİD ALTINDA yenidən yoxlanır
(paralel xana yazısı FK kilidində gözləyir və uğursuz olur — sətir itmir). Hər
dəstə açılış başına bir ``AuditLog`` (``resource_type=legacy_import.empty_lesson``)
yazır: silinən dərsin id/tarix/saat/növ/saat/otaq/müəllim izi ``old_values``-dədir.
Ledger (``LegacyEntityMap.target_pk``) silinmir — o, silinməyən sübut qatıdır.
İdempotentdir: ikinci icra 0 namizəd tapır.

Tələbə SƏTİRLƏRİ (boş qeydiyyatlar) bu əmrdə SİLİNMİR: idxalın yaratdığı yeganə
dəqiq hal (eyni fənnin boş öz-qrup təkrarı) ``delta/dedupe.py``-da rəsmi «alt qrup
birləşməsi» ilə bağlanır; qalan boş sətirlər ``journal_hygiene`` («Boş fənn»)
aşkarlama/qərar axınındadır.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db.models import BooleanField, Count, Exists, ExpressionWrapper, OuterRef, Q
from django.db.models.functions import Trim

from core.audit import log_actions
from core.constants import AuditAction

from .repair_support import RepairContext, scoped_atomic

AUDIT_REASON = "legacy_repair:empty_lessons"
AUDIT_RESOURCE = "legacy_import.empty_lesson"
DEFAULT_BATCH_SIZE = 500

#: ``gradebook._CLOSED_STATUSES`` ilə eyni (kilid: təsdiqlənmiş və ya dərc olunmuş sxem).
_LOCKED_APPROVAL_STATUSES = ("approved",)

TABLE_HEADERS = ("Açılış", "Fənn", "Qrup", "Boş sütun")


def _model(name: str):
    return django_apps.get_model("registrar", name)


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


def empty_imported_lessons(organization, *, before: datetime.date):
    """Köçürülmüş, keçmiş, xanasız dərslər — məzmun/kilid süzgəcindən ƏVVƏL."""

    marks = _model("LessonMark").objects.filter(lesson_id=OuterRef("pk"))
    return (
        _model("Lesson")
        .objects.filter(organization=organization, created_by__isnull=True, date__lt=before)
        .filter(~Exists(marks))
        .annotate(topic_trimmed=Trim("topic"))
    )


def candidate_lessons(organization, *, before: datetime.date, include_locked: bool = False):
    """Silinəcək dərslər (modul sənədindəki BÜTÜN şərtlər)."""

    queryset = empty_imported_lessons(organization, before=before).exclude(_has_content())
    if not include_locked:
        queryset = queryset.filter(~_locked_journal())
    return queryset


def survey(organization, *, before: datetime.date, include_locked: bool) -> dict:
    """Operator hesabatı — iki aqreqat sorğu, heç nə yazılmır."""

    lesson_model = _model("Lesson")
    base = empty_imported_lessons(organization, before=before).annotate(
        has_content=ExpressionWrapper(_has_content(), output_field=BooleanField()),
        in_locked_journal=_locked_journal(),
    )
    # Aqreqat adları annotasiya adları ilə TOQQUŞMAMALIDIR (Django adı əvəzləyir).
    counts = base.aggregate(
        empty=Count("id"),
        with_content=Count("id", filter=Q(has_content=True)),
        locked=Count("id", filter=Q(has_content=False, in_locked_journal=True)),
        synthesised=Count("id", filter=Q(has_content=False, is_legacy_synthesised=True)),
        with_room=Count("id", filter=Q(has_content=False, room__isnull=False)),
    )
    marks = _model("LessonMark").objects.filter(lesson_id=OuterRef("pk"))
    untouched = (
        lesson_model.objects.filter(organization=organization)
        .filter(~Exists(marks))
        .aggregate(
            teacher_empty=Count("id", filter=Q(created_by__isnull=False)),
            imported_today_or_later=Count("id", filter=Q(created_by__isnull=True, date__gte=before)),
        )
    )
    deletable = counts["empty"] - counts["with_content"] - (0 if include_locked else counts["locked"])
    return {**counts, **untouched, "deletable": deletable}


def per_offering(queryset, *, limit: int = 0) -> list[tuple]:
    """Ən çox boş sütunu olan açılışlar (cədvəl üçün; adsız — fənn/qrup)."""

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


_SNAPSHOT_FIELDS = (
    "id",
    "offering_id",
    "date",
    "start_time",
    "end_time",
    "kind",
    "hours",
    "room_id",
    "instructor_id",
    "is_legacy_synthesised",
    "created_at",
)


def _snapshot(row: dict) -> dict:
    return {
        key: (value if isinstance(value, (bool, int)) or value is None else str(value)) for key, value in row.items()
    }


@dataclass
class DeleteResult:
    deleted: int = 0
    offerings: int = 0
    batches: int = 0


def delete_empty_lessons(
    context: RepairContext,
    *,
    before: datetime.date,
    include_locked: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> DeleteResult:
    """Namizədləri dəstə-dəstə sil + açılış başına audit (modul sənədi «Təhlükəsizlik»)."""

    lesson_model = _model("Lesson")
    batch_size = max(1, int(batch_size))
    result = DeleteResult()
    touched_offerings: set = set()
    while True:
        remaining = context.limit - result.deleted if context.limit else batch_size
        size = min(batch_size, remaining)
        if size <= 0:
            break
        with scoped_atomic(context):
            candidates = candidate_lessons(context.organization, before=before, include_locked=include_locked)
            ids = list(
                candidates.order_by("offering_id", "date", "start_time", "id").values_list("id", flat=True)[:size]
            )
            if not ids:
                break
            # Kilid altında yenidən yoxla: arada xana/mövzu yazılmış sətir düşür.
            locked = list(
                candidate_lessons(context.organization, before=before, include_locked=include_locked)
                .filter(pk__in=ids)
                .select_for_update(of=("self",))
                .values_list("id", flat=True)
            )
            rows = list(
                lesson_model.objects.filter(pk__in=locked).order_by("date", "start_time").values(*_SNAPSHOT_FIELDS)
            )
            if not rows:
                continue  # dəstənin hamısı arada məzmun alıb — növbəti namizədlər
            by_offering: dict = defaultdict(list)
            for row in rows:
                by_offering[row["offering_id"]].append(_snapshot(row))
            log_actions(
                {
                    "action": AuditAction.DELETE,
                    "user": context.actor,
                    "organization": context.organization,
                    "old_values": {"lessons": lessons, "count": len(lessons)},
                    "reason": AUDIT_REASON,
                    "resource_type": AUDIT_RESOURCE,
                    "resource_id": str(offering_id),
                    "resource_repr": f"{len(lessons)} boş köçürmə sütunu",
                }
                for offering_id, lessons in by_offering.items()
            )
            lesson_model.objects.filter(pk__in=[row["id"] for row in rows]).delete()
        result.deleted += len(rows)
        result.batches += 1
        touched_offerings.update(by_offering)
    result.offerings = len(touched_offerings)
    return result


__all__ = [
    "AUDIT_REASON",
    "AUDIT_RESOURCE",
    "DEFAULT_BATCH_SIZE",
    "TABLE_HEADERS",
    "DeleteResult",
    "candidate_lessons",
    "delete_empty_lessons",
    "empty_imported_lessons",
    "per_offering",
    "survey",
]
