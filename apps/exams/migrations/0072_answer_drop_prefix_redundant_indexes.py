"""Fon işi tutumu 2026-10-07: cavab cədvəllərinin prefiks-təkrar tək-sütun indeksləri.

* ``exams_examanswer_attempt_id_3ba11114`` (attempt_id) — ``unique_together
  (attempt_id, question_id)`` indeksinin prefiksidir;
* ``exams_examanswer_selected_options_examanswer_id_9bd3bf6c`` (examanswer_id) —
  avto M2M cədvəlinin ``UNIQUE (examanswer_id, examquestionoption_id)`` indeksinin
  prefiksidir.

Hər ikisi imtahanın ən isti yazı yolunda (autosave) hər sətirdə yenilənir. Sandbox-da
(2,1 M cavab): 100 000 cavab INSERT 653 → 501 ms, 100 000 seçim 748 → 576 ms (−23 %),
indeks yaddaşı −69 MB; ``attempt_id = …`` / ``examanswer_id IN (…)`` oxuları və CASCADE
silmələri unikal kompozitlə indeks skanı olaraq qalır (EXPLAIN). LockManager fast-path
yükü də hər autosave tranzaksiyasında 2 kilid azalır (bax tutum testi 2026-10-05).

Böyük cədvəllərdir — ``DROP INDEX CONCURRENTLY`` (yazıları bloklamır), ona görə
``atomic = False``. FK məhdudiyyətinə toxunulmur (yalnız indeks); M2M avto-cədvəlinin
indeksi Django state-də izlənmir, ona görə yalnız DB əməliyyatıdır.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("exams", "0071_capacity_drop_unused_indexes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX CONCURRENTLY IF EXISTS "exams_examanswer_attempt_id_3ba11114";',
                    reverse_sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS exams_examanswer_attempt_id_3ba11114 "
                        "ON public.exams_examanswer USING btree (attempt_id);"
                    ),
                ),
                migrations.RunSQL(
                    sql='DROP INDEX CONCURRENTLY IF EXISTS "exams_examanswer_selected_options_examanswer_id_9bd3bf6c";',
                    reverse_sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS exams_examanswer_selected_options_examanswer_id_9bd3bf6c "
                        "ON public.exams_examanswer_selected_options USING btree (examanswer_id);"
                    ),
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="examanswer",
                    name="attempt",
                    field=models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answers",
                        to="exams.examattempt",
                    ),
                ),
            ],
        ),
    ]
