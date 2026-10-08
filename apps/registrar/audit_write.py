"""Registrar audit yazısı — SAVEPOINT-li «best-effort» ``AuditLog`` sətri.

Audit 2026-09-28 DB-01: köhnə köməkçilər ``AuditLog.objects.create`` xətasını
savepoint-siz ``except Exception: pass`` ilə udurdu. Xarici ``@transaction.atomic``
içində (jurnal yazısı, yekun bal, status dəyişikliyi) DB xətası
``connection.needs_rollback=True`` qoyur və ``Atomic.__exit__`` bütün
tranzaksiyanı SƏSSİZCƏ geri qaytarırdı — müəllimə «yadda saxlanıldı» deyilir,
qiymətlər isə itirdi. İndi INSERT öz savepoint-ində gedir: audit düşərsə yalnız
ÖZÜ geri qayıdır, domen yazısı qalır və xəta loga düşür (nümunə:
``apps/appeals/services/decisions.py::_audit_score_change``).

``AuditLog`` app registry ilə həll olunur — registrar audit moduluna statik
import saxlamır (modul sərhədi).
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def create_audit_row(*, fail_closed: bool = False, **fields) -> bool:
    """Bir ``AuditLog`` sətri yaz; uğurda ``True``.

    ``fail_closed=True`` — xəta yenidən atılır (rəsmi düzəliş axınları: domen
    dəyişikliyi və audit dəlili birlikdə commit/rollback olunur). Əks halda
    xəta loga yazılır və ``False`` qaytarılır; xarici tranzaksiya sağlam qalır.
    """
    try:
        from django.apps import apps as django_apps

        AuditLog = django_apps.get_model("audit", "AuditLog")
        with transaction.atomic():
            AuditLog.objects.create(**fields)
        return True
    except Exception:  # noqa: BLE001 — savepoint geri qayıdıb; siyasət çağırana aiddir
        if fail_closed:
            raise
        logger.exception(
            "Registrar audit yazısı alınmadı (resource_type=%s, resource_id=%s).",
            fields.get("resource_type"),
            fields.get("resource_id"),
        )
        return False


def create_audit_rows(rows, *, fail_closed: bool = False) -> bool:
    """Bir neçə ``AuditLog`` sətri — ``create_audit_row`` ilə EYNİ siyasət, BİR INSERT.

    2026-10-08 (toplu imtahan balı yazısı): sətir başına savepoint + INSERT əvəzinə
    hamısı bir savepoint-də ``bulk_create`` olunur. Best-effort rejimdə xəta loga düşür
    və yalnız bu audit sətirləri geri qayıdır — domen yazısı qalır.
    """
    rows = list(rows)
    if not rows:
        return True
    try:
        from core.audit import create_audit_logs

        with transaction.atomic():
            create_audit_logs(rows)
        return True
    except Exception:  # noqa: BLE001 — savepoint geri qayıdıb; siyasət çağırana aiddir
        if fail_closed:
            raise
        logger.exception(
            "Registrar audit yazısı alınmadı (resource_type=%s, %d sətir).",
            rows[0].get("resource_type"),
            len(rows),
        )
        return False
