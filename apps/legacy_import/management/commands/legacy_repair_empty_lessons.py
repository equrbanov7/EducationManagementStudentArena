"""``legacy_repair_empty_lessons`` — köçürmədən qalan TAM BOŞ jurnal sütunlarını silir.

Dry-run DEFAULT-dur (yalnız saylar + açılış cədvəli). Qayda, təhlükəsizlik və audit:
``apps.legacy_import.services.repair_empty_lessons``.

    manage.py legacy_repair_empty_lessons --organization qku
    manage.py legacy_repair_empty_lessons --organization qku --apply --i-know-this-is-production
    manage.py legacy_repair_empty_lessons --organization qku --include-locked --apply --i-know-this-is-production
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.legacy_import.services import repair_empty_lessons as service
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


class Command(BaseCommand):
    help = (
        "Köhnə sistemdən köçürülmüş, heç bir xanası və mövzusu olmayan keçmiş dərsləri (tam boş jurnal "
        "sütunlarını) silir. Müəllimin yeni sistemdə açdığı dərsə toxunulmur. Dry-run default."
    )

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument(
            "--before",
            default="",
            help="Yalnız bu tarixdən ƏVVƏLKİ dərslər (YYYY-MM-DD, default: bu gün — bu gün/gələcək toxunulmaz)",
        )
        parser.add_argument(
            "--include-locked",
            action="store_true",
            help="Kilidli (təsdiqlənmiş/dərc olunmuş) jurnalların boş sütunlarını da sil (default: toxunma)",
        )
        parser.add_argument("--batch-size", type=int, default=service.DEFAULT_BATCH_SIZE, help="Dəstə ölçüsü")
        parser.add_argument("--show", type=int, default=20, help="Cədvəldə göstəriləcək açılış sayı")

    def handle(self, *args, **options):
        before = _before(options["before"])
        include_locked = bool(options["include_locked"])
        if int(options["batch_size"]) < 1:
            raise CommandError("legacy_repair_empty_lessons_batch_invalid")
        with rls_worker_atomic():
            context = build_context(options)
            with scoped_atomic(context):
                stats = service.survey(context.organization, before=before, include_locked=include_locked)
                candidates = service.candidate_lessons(
                    context.organization, before=before, include_locked=include_locked
                )
                table = service.per_offering(candidates, limit=int(options["show"]))
            self.stdout.write(render_table(service.TABLE_HEADERS, table, max_rows=int(options["show"])))

            result = service.DeleteResult()
            if context.apply:
                result = service.delete_empty_lessons(
                    context,
                    before=before,
                    include_locked=include_locked,
                    batch_size=int(options["batch_size"]),
                )

        summary = {
            "tarix həddi (bu tarixdən əvvəl)": before.isoformat(),
            "köçürülmüş, xanasız keçmiş dərs": stats["empty"],
            "  ↳ məzmunlu (mövzu/düzəliş) — saxlanır": stats["with_content"],
            "  ↳ kilidli jurnalda": f"{stats['locked']} ({'silinir' if include_locked else 'saxlanır; --include-locked'})",
            "  ↳ bərpa olunmuş (is_legacy_synthesised)": stats["synthesised"],
            "  ↳ otağı olan (slot metadatası)": stats["with_room"],
            "SİLİNƏCƏK namizəd": stats["deletable"],
            "toxunulmaz: müəllimin boş dərsi": stats["teacher_empty"],
            "toxunulmaz: köçürülmüş, bu gün/gələcək": stats["imported_today_or_later"],
            "FAKTİKİ silinən": result.deleted,
            "açılış / dəstə": f"{result.offerings} / {result.batches}",
        }
        self.stdout.write(render_summary("legacy_repair_empty_lessons", context, summary))
