"""``grant_temporary_superuser`` — sahibin öz hesabına MÜVƏQQƏTİ tam superadmin girişi (sahib 2026-10-27).

Sahib: «tək Elvin Qurbanov yəni mənə full superadmin access ver ki, yeni dəyişikliklərə əsasən bütün düzəlişləri
sürətli edim, sonra bunu geri alarıq». ``is_superuser`` + ``is_staff`` qoyulur; hesabın rolları / üzvlükləri
dəyişmir. Geri alma: ``--revoke`` (yalnız BU əmrin verdiyi giriş geri alınır — audit izinə görə; əvvəldən
superuser olan hesaba toxunulmur).

Hər iki istiqamət ``AuditLog``-a yazılır (``resource_type = temporary_superuser``; verilmə sətrində ``expires_at``).
Superadmin girişi şəbəkə qaydasına tabedir (``NETWORK_ZONE_SUPERADMIN_INTERNAL_ONLY``). DEFOLT DRY-RUN.
Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.public import log_action
from core.constants import AuditAction
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "temporary_superuser:"
RESOURCE = "temporary_superuser"
MAX_DAYS = 14


class Command(BaseCommand):
    help = "Aktiv hesaba müvəqqəti superadmin girişi verir və ya (--revoke) geri alır."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--days", type=int, default=7, help=f"Müddət (1–{MAX_DAYS} gün; yalnız qeyd üçün)")
        parser.add_argument("--revoke", action="store_true", help="Bu əmrin verdiyi girişi geri al")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        if not 1 <= options["days"] <= MAX_DAYS:
            raise CommandError("temporary_superuser_days_out_of_range")
        AuditLog = django_apps.get_model("audit", "AuditLog")
        with rls_worker_atomic(), bypass_rls(), transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(username=str(options["username"]).strip(), is_active=True)
                .first()
            )
            if user is None:
                raise CommandError("temporary_superuser_user_unknown")
            granted_here = AuditLog.objects.filter(
                resource_type=RESOURCE, resource_id=str(user.pk), changes__operation="grant"
            ).exists()
            revoked_after = (
                AuditLog.objects.filter(resource_type=RESOURCE, resource_id=str(user.pk))
                .order_by("-created_at")
                .values_list("changes__operation", flat=True)
                .first()
            )
            state = "noop"
            if options["revoke"]:
                if user.is_superuser and granted_here and revoked_after == "grant":
                    user.is_superuser = False
                    user.is_staff = False
                    user.save(update_fields=["is_superuser", "is_staff"])
                    self._audit(user, operation="revoke", expires_at=None)
                    state = "revoked"
                elif user.is_superuser:
                    state = "permanent_superuser_untouched"
            elif not user.is_superuser:
                expires_at = timezone.now() + timedelta(days=options["days"])
                user.is_superuser = True
                user.is_staff = True
                user.save(update_fields=["is_superuser", "is_staff"])
                self._audit(user, operation="grant", expires_at=expires_at)
                state = "granted"
            else:
                state = "already_superuser"
            if not options["apply"]:
                transaction.set_rollback(True)
        self.stdout.write(
            f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'} state={state} days={options['days']}"
        )

    @staticmethod
    def _audit(user, *, operation, expires_at):
        log_action(
            action=AuditAction.UPDATE,
            user=user,
            organization=None,
            obj=user,
            old_values={"is_superuser": operation != "grant"},
            new_values={"is_superuser": operation == "grant"},
            changes={
                "operation": operation,
                "expires_at": expires_at.isoformat() if expires_at else "",
            },
            reason=(
                "Müvəqqəti tam superadmin girişi — sahibin 2026-10-27 tapşırığı"
                if operation == "grant"
                else "Müvəqqəti superadmin girişi geri alındı"
            ),
            resource_type=RESOURCE,
            resource_id=str(user.pk),
            resource_repr=user.username,
        )
