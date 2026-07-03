"""Retention / cleanup for in-app notifications (audit finding DATABASE-001).

``InAppNotification`` rows are soft-deleted (``deleted_at`` set) when a user
removes them and are excluded from the user's default view thereafter. The app
never removes them automatically, so the table grows without bound. This command
hard-deletes rows that users have *already soft-deleted* longer than a grace
window (completely user-invisible → safe to reclaim) and can optionally purge
very old *read* notifications when an operator explicitly opts in.

Audit logs are deliberately NOT handled here: ``AuditLog`` is compliance data
that must be partitioned / archived (a DB-level operation), never bulk-deleted
by a maintenance command.

Dry-run by default; pass ``--commit`` to actually delete.

Examples
--------
    # Report only (safe default):
    python manage.py purge_notifications

    # Reclaim rows users soft-deleted more than 30 days ago:
    python manage.py purge_notifications --commit

    # Also purge READ notifications older than a year (opt-in):
    python manage.py purge_notifications --read-days 365 --commit

Schedule via Celery beat / cron once validated in staging.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import InAppNotification
from core.rls import bypass_rls


class Command(BaseCommand):
    help = (
        "Hard-delete in-app notifications that were soft-deleted past a grace window "
        "(and, optionally, old read notifications). Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--soft-deleted-days",
            type=int,
            default=30,
            help="Hard-delete rows soft-deleted (deleted_at) more than N days ago. Default: 30.",
        )
        parser.add_argument(
            "--read-days",
            type=int,
            default=0,
            help=(
                "Also hard-delete READ notifications older than N days (opt-in; 0 = disabled). "
                "Unread notifications are never touched."
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Delete in batches of this size. Default: 1000.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually delete. Without this flag the command only reports (dry-run).",
        )

    def handle(self, *args, **options):
        soft_days = max(0, int(options["soft_deleted_days"]))
        read_days = max(0, int(options["read_days"]))
        batch_size = max(1, int(options["batch_size"]))
        commit = bool(options["commit"])
        now = timezone.now()

        # Maintenance runs outside any request, so no RLS tenant context is set;
        # bypass RLS so the sweep can see and delete rows across every tenant.
        with bypass_rls():
            soft_qs = InAppNotification.objects.filter(
                deleted_at__isnull=False,
                deleted_at__lt=now - timedelta(days=soft_days),
            )
            soft_total = soft_qs.count()

            read_qs = None
            read_total = 0
            if read_days > 0:
                # Disjoint from soft_qs (deleted_at IS NULL) so no double count.
                read_qs = InAppNotification.objects.filter(
                    is_read=True,
                    deleted_at__isnull=True,
                    created_at__lt=now - timedelta(days=read_days),
                )
                read_total = read_qs.count()

            self.stdout.write(f"Soft-deleted > {soft_days}d: {soft_total} row(s) eligible.")
            if read_days > 0:
                self.stdout.write(f"Read > {read_days}d (opt-in): {read_total} row(s) eligible.")

            if not commit:
                self.stdout.write(
                    self.style.WARNING(
                        f"DRY-RUN: would delete {soft_total + read_total} row(s). " "Re-run with --commit to apply."
                    )
                )
                return

            deleted = self._purge(soft_qs, batch_size)
            if read_qs is not None:
                deleted += self._purge(read_qs, batch_size)

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} notification row(s)."))

    @staticmethod
    def _purge(queryset, batch_size: int) -> int:
        """Delete matching rows in bounded batches to avoid a single huge lock."""
        deleted = 0
        while True:
            batch_ids = list(queryset.values_list("pk", flat=True)[:batch_size])
            if not batch_ids:
                break
            with transaction.atomic():
                InAppNotification.objects.filter(pk__in=batch_ids).delete()
            deleted += len(batch_ids)
        return deleted
