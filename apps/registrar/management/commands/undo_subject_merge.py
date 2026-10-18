"""Fənn birləşdirməsini audit izindən GERİ QAYTARIR (2026-10-19). Default: DRY-RUN.

İstifadə::

    python manage.py undo_subject_merge --audit-id <uuid>
    python manage.py undo_subject_merge --audit-id <uuid> --apply --reason "Səhv birləşdirmə — kartlar fərqli fəndir"

Şərtlər və məhdudiyyətlər: :mod:`apps.registrar.subject_merge_undo`. Dry-run eyni yazını
tranzaksiyada edib geri qaytarır — DB qaydaları real yoxlanır, heç nə saxlanmır.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...subject_merge import MergeError
from ...subject_merge_undo import undo


class Command(BaseCommand):
    help = "Fənn birləşdirməsini audit izindən geri qaytarır (default dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--audit-id", required=True, help="birləşmə audit qeydinin id-si")
        parser.add_argument("--apply", action="store_true", help="yaz (yoxdursa yalnız yoxlama)")
        parser.add_argument("--reason", default="", help="səbəb (≥20 simvol; --apply ilə məcburi)")

    def handle(self, *args, **options):
        with rls_worker_atomic(), bypass_rls():
            try:
                report = undo(audit_id=options["audit_id"], apply=options["apply"], reason=options["reason"])
            except MergeError as exc:
                raise CommandError(exc.message) from exc
        self.stdout.write(f"Birləşmə: {', '.join(report['sources'] or [])} → {report['target']}")
        for key, value in sorted((report["counts"] or {}).items()):
            if value:
                self.stdout.write(f"  {key}: {value}")
        if report["issues"]:
            for issue in report["issues"]:
                self.stdout.write(self.style.ERROR(f"BLOK: {issue}"))
            raise CommandError("Geri qaytarma təhlükəsiz deyil — heç nə yazılmadı.")
        if report["applied"]:
            self.stdout.write(self.style.SUCCESS("Geri qaytarıldı."))
        else:
            self.stdout.write('DRY-RUN: geri qaytarma mümkündür; heç nə yazılmadı. Yazmaq üçün --apply --reason "…".')
