"""Perf/data auditi 2026-09-13 (W2 2026-09-14) — `registrar_lesson (organization_id, date)` örtük indeksi + dublikat FK indeksi.

* **Perf §6 Q3/Q5/Q8/Q10.** `lessons-log` və dövr üzrə seçimlər dərsləri
  `organization_id + date` aralığı ilə süzür; mövcud
  `(organization_id, offering_id, date)` indeksi `offering` olmadan aralığa
  xidmət etmir → klonda (305 k dərs) Parallel Seq Scan, 141 ms.
  `registrar_lesson_org_date_idx (organization_id, date) INCLUDE (offering_id, hours)`
  — siyahı və `SUM(hours)` sorğuları index-only gedə bilir.
* **Data §6.2.** `registrar_resitrecord.enrollment_id` üçün FK-nın avtomatik
  indeksi (`registrar_resitrecord_enrollment_id_ba0fb850`) `uniq_resit_per_enrollment`
  unikal indeksi ilə eyni açardadır → silinir (model: `db_index=False`).

Hər iki əməliyyat `CONCURRENTLY` (istehsalda cədvəl kilidlənmir) → `atomic = False`.
"""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models

_RESIT_FK_INDEX = "registrar_resitrecord_enrollment_id_ba0fb850"


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("registrar", "0075_finalgrade_exam_score_range"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="lesson",
            index=models.Index(
                fields=["organization", "date"],
                include=["offering", "hours"],
                name="registrar_lesson_org_date_idx",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="resitrecord",
                    name="enrollment",
                    field=models.ForeignKey(
                        db_index=False,
                        on_delete=models.deletion.CASCADE,
                        related_name="resit_records",
                        to="registrar.enrollment",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=f"DROP INDEX CONCURRENTLY IF EXISTS {_RESIT_FK_INDEX};",
                    reverse_sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_RESIT_FK_INDEX} "
                        "ON registrar_resitrecord (enrollment_id);"
                    ),
                ),
            ],
        ),
    ]
