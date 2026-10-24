"""``legacy_repair_empty_lessons`` — jurnalın MƏZMUNSUZ keçmiş sütunlarını silir.

Dry-run DEFAULT-dur (yalnız saylar + açılış cədvəli). Qayda: ``apps.legacy_import.services.repair_empty_lessons``;
silmə, aqreqatlar və audit: ``apps.legacy_import.services.repair_empty_lessons_apply``.

Defolt yalnız köçürülmüş TAM BOŞ sütun; genişləndirmə AÇIQ bayraqladır (review olunsun):

* ``--include-absent-only``     — xanaları yalnız balsız «qb» olan sütun da (xanalar da silinir, qayıb saatı
  yenidən hesablanır);
* ``--include-teacher-lessons`` — müəllimin yeni sistemdə açdığı keçmiş sütun da (son ``TEACHER_GRACE_DAYS``
  gündə yaradılan və ya tarixli istisna);
* ``--include-locked``          — kilidli (təsdiqlənmiş/dərc olunmuş) jurnallar da.

    manage.py legacy_repair_empty_lessons --organization qku
    manage.py legacy_repair_empty_lessons --organization qku --apply --i-know-this-is-production
    manage.py legacy_repair_empty_lessons --organization qku --include-locked --include-absent-only \
        --include-teacher-lessons --apply --i-know-this-is-production
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.legacy_import.services import repair_empty_lessons as service
from apps.legacy_import.services import repair_empty_lessons_apply as deletion
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
    scoped_atomic,
)
from core.rls_pooling import rls_worker_atomic


def _before(raw: str) -> datetime.date:
    today = timezone.localdate()
    if not raw:
        return today
    try:
        value = datetime.date.fromisoformat(str(raw).strip())
    except ValueError:
        raise CommandError("legacy_repair_empty_lessons_before_invalid: --before YYYY-MM-DD olmalıdır") from None
    if value > today:
        # Bu günün/gələcəyin dərsi heç vaxt silinmir (müəllim hələ yaza bilər).
        raise CommandError("legacy_repair_empty_lessons_before_future: --before bu gündən sonra ola bilməz")
    return value


def _since(raw: str):
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(str(raw).strip())
    except ValueError:
        raise CommandError("legacy_repair_empty_lessons_since_invalid: --since YYYY-MM-DD olmalıdır") from None


class Command(BaseCommand):
    help = (
        "Heç bir real xanası (bal / iə / ü/q), mövzusu və düzəlişi olmayan keçmiş dərsləri (boş jurnal "
        "sütunlarını) silir. Defolt: yalnız köçürülmüş tam boş sütun; «qb»-li və müəllimin sütunu açıq "
        "bayraqla. Bu gün/gələcək toxunulmaz. Dry-run default."
    )

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument(
            "--before",
            default="",
            help="Yalnız bu tarixdən ƏVVƏLKİ dərslər (YYYY-MM-DD, default: bu gün — bu gün/gələcək toxunulmaz)",
        )
        parser.add_argument(
            "--since",
            default="",
            help="Yalnız bu tarixdən (YYYY-MM-DD, daxil) SONRAKI dərslər (default: hamısı)",
        )
        parser.add_argument(
            "--include-locked",
            action="store_true",
            help="Kilidli (təsdiqlənmiş/dərc olunmuş) jurnalların boş sütunlarını da sil (default: toxunma)",
        )
        parser.add_argument(
            "--include-absent-only",
            action="store_true",
            help="Xanaları YALNIZ balsız «qb» olan sütunları da sil (xanalarla; qayıb saatı yenidən hesablanır)",
        )
        parser.add_argument(
            "--include-teacher-lessons",
            action="store_true",
            help="Müəllimin yeni sistemdə açdığı keçmiş sütunları da sil (son 3 gündə yaradılan/tarixli istisna)",
        )
        parser.add_argument("--batch-size", type=int, default=service.DEFAULT_BATCH_SIZE, help="Dəstə ölçüsü")
        parser.add_argument("--show", type=int, default=20, help="Cədvəldə göstəriləcək açılış sayı")

    def handle(self, *args, **options):
        scope = service.Scope(
            before=_before(options["before"]),
            since=_since(options["since"]),
            include_locked=bool(options["include_locked"]),
            include_absent_only=bool(options["include_absent_only"]),
            include_teacher_lessons=bool(options["include_teacher_lessons"]),
        )
        if int(options["batch_size"]) < 1:
            raise CommandError("legacy_repair_empty_lessons_batch_invalid")
        with rls_worker_atomic():
            context = build_context(options)
            with scoped_atomic(context):
                stats = service.survey(context.organization, scope)
                candidates = service.candidate_lessons(context.organization, scope)
                table = service.per_offering(candidates, limit=int(options["show"]))
            self.stdout.write(render_table(service.TABLE_HEADERS, table, max_rows=int(options["show"])))

            result = deletion.DeleteResult()
            if context.apply:
                result = deletion.delete_empty_lessons(context, scope, batch_size=int(options["batch_size"]))

        self.stdout.write(render_summary("legacy_repair_empty_lessons", context, _summary(scope, stats, result)))


def _flag(enabled: bool, name: str) -> str:
    return "silinir" if enabled else f"saxlanır; {name}"


def _summary(scope, stats: dict, result) -> dict:
    """Operator xülasəsi. Açarlarda «:» OLMAMALIDIR — prod-data-ops loq süzgəci ``  açar : dəyər`` formasını tutur."""

    teacher_on = scope.include_teacher_lessons
    teacher_absent_on = teacher_on and scope.include_absent_only
    by_category = result.by_category
    return {
        "tarix həddi (bu tarixdən əvvəl)": scope.before.isoformat(),
        "başlanğıc (bu tarixdən etibarən)": scope.since.isoformat() if scope.since else "hamısı",
        "köçürülmüş, tam boş (xanasız) keçmiş dərs": stats["empty"],
        "köçürülmüş, yalnız «qb» xanalı keçmiş dərs": (
            f"{stats['absent_only']} ({_flag(scope.include_absent_only, '--include-absent-only')})"
        ),
        "müəllimin tam boş keçmiş dərsi": f"{stats['teacher_empty']} ({_flag(teacher_on, '--include-teacher-lessons')})",
        "müəllimin yalnız «qb» xanalı keçmiş dərsi": (
            f"{stats['teacher_absent_only']} "
            f"({_flag(teacher_absent_on, '--include-teacher-lessons + --include-absent-only')})"
        ),
        "  ↳ kilidli jurnalda": f"{stats['locked']} ({_flag(scope.include_locked, '--include-locked')})",
        "  ↳ bərpa olunmuş (is_legacy_synthesised)": stats["synthesised"],
        "  ↳ otağı olan (slot metadatası)": stats["with_room"],
        "SİLİNƏCƏK namizəd": stats["deletable"],
        "  ↳ silinəcək «qb» xanası / qayıb saatı": f"{stats['absent_marks']} / {stats['absent_hours']}",
        "toxunulmaz — məzmunlu (mövzu/düzəliş)": stats["with_content"],
        "müəllim dərsi buferi (gün)": (
            f"{service.TEACHER_GRACE_DAYS} ({scope.teacher_grace_start.isoformat()} və sonra yaradılan "
            "və ya tarixli müəllim dərsi saxlanır)"
        ),
        "toxunulmaz — müəllimin buferdəki dərsi": stats["teacher_recent"],
        "toxunulmaz — bu gün/gələcək (real xanasız)": stats["today_or_later"],
        "FAKTİKİ silinən": result.deleted,
        "  ↳ tam boş / yalnız «qb» / müəllimin": (
            f"{by_category[service.CATEGORY_EMPTY]} / {by_category[service.CATEGORY_ABSENT_ONLY]} / "
            f"{by_category[service.CATEGORY_TEACHER]}"
        ),
        "  ↳ silinən «qb» xanası / qayıb saatı": f"{result.marks} / {result.absence_hours}",
        "qayıb saatı yenidən hesablanan qeydiyyat": result.enrollments_recomputed,
        "açılış / dəstə": f"{result.offerings} / {result.batches}",
    }
