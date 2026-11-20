"""Sahib 2026-11-20: «Kənardan jurnal girişi» — RİM rəhbərinin kabinetdən verdiyi şəbəkə istisnası.

Yalnız sxem (PII yoxdur): hesablar kabinetdən əlavə olunur. Tenant-sız cədvəl — RLS siyasəti yoxdur
(``remote_journal_access_models`` şərhi). Bir hesabın eyni anda bir aktiv icazəsi (qismən unikal indeks).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0037_exam_score_edit_one_hour_2026_11_17"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RemoteJournalAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("note", models.CharField(blank=True, default="", max_length=255, verbose_name="Qeyd")),
                ("granted_at", models.DateTimeField(auto_now_add=True, verbose_name="Verilmə vaxtı")),
                ("revoked_at", models.DateTimeField(blank=True, null=True, verbose_name="Geri alınma vaxtı")),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Verən",
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Geri alan",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="remote_journal_access_grants",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Hesab",
                    ),
                ),
            ],
            options={
                "verbose_name": "Kənardan jurnal girişi",
                "verbose_name_plural": "Kənardan jurnal girişləri",
                "ordering": ("-granted_at",),
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("revoked_at__isnull", True)),
                        fields=("user",),
                        name="accounts_remote_journal_access_one_active",
                    )
                ],
            },
        ),
    ]
