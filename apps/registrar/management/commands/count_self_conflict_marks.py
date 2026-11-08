"""Yalnız-oxu: tələbə + heyət rolu trigger-ini (registrar 0119) pozan MÖVCUD sətirlərin sayı.

Deploy-dan ƏVVƏL prod-da işlədilir: qiymət sətrinin müəllifi (``entered_by``) həmin açılışa yazılmış tələbədirsə
sətir sayılır. Yalnız SELECT işlədir — heç nə yazmır / düzəltmir. Trigger mövcud sətirləri yoxlamır — bu say
yalnız «köhnə data var mı» sualına cavabdır (sıfır deyilsə sahibə bildir).

    python manage.py count_self_conflict_marks
"""

from __future__ import annotations

import importlib

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

_MIGRATION = "apps.registrar.migrations.0119_self_conflict_author_guard"


class Command(BaseCommand):
    help = "Read-only: count existing score rows authored by a student of the same offering (self-conflict)."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write("PostgreSQL deyil — yoxlama yoxdur.")
            return
        sql = importlib.import_module(_MIGRATION).VIOLATION_COUNT_SQL
        with rls_worker_atomic(), bypass_rls(), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
        total = 0
        for table, count in rows:
            total += count
            self.stdout.write(f"{table}: {count}")
        self.stdout.write(f"TOTAL: {total}")
