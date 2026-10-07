"""Fon işi tutumu 2026-10-07: ``notifications_inappnotification`` prefiks-təkrar indeksləri.

* ``…_recipient_id_d4b9f908`` (recipient_id) — ``(recipient_id, deleted_at, is_read)`` və
  ``(recipient_id, deleted_at, created_at)`` kompozitlərinin prefiksi;
* ``…_organization_id_f508ee82`` (organization_id) — ``notif_org_recipient_idx
  (organization_id, recipient_id)``-in prefiksi (RLS predikatı üçün ``org_txt_idx`` qalır).

Cədvəl hər səhifədə oxunur (oxunmamış sayğac) və fan-out ilə toplu yazılır (bitmiş
imtahan cəhdi, sorğu, final xatırlatması). Sandbox (2 M sətir): 50 000 alıcılı toplu INSERT
3,9 → 2,5 s; sayğac / inbox / CASCADE oxuları kompozit indeks skanı olaraq qalır (EXPLAIN);
hər sorğuda 2 kilid az (LockManager fast-path, tutum testi 2026-10-05). Yalnız indeks silinir
(FK məhdudiyyəti qalır); ``CONCURRENTLY`` → ``atomic = False``.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("notifications", "0004_alter_inappnotification_notification_type"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX CONCURRENTLY IF EXISTS "notifications_inappnotification_recipient_id_d4b9f908";',
                    reverse_sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS notifications_inappnotification_recipient_id_d4b9f908 "
                        "ON public.notifications_inappnotification USING btree (recipient_id);"
                    ),
                ),
                migrations.RunSQL(
                    sql='DROP INDEX CONCURRENTLY IF EXISTS "notifications_inappnotification_organization_id_f508ee82";',
                    reverse_sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS notifications_inappnotification_organization_id_f508ee82 "
                        "ON public.notifications_inappnotification USING btree (organization_id);"
                    ),
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="inappnotification",
                    name="recipient",
                    field=models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="in_app_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="inappnotification",
                    name="organization",
                    field=models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="in_app_notifications",
                        to="organizations.organization",
                    ),
                ),
            ],
        ),
    ]
