"""İmtahan Mərkəzi — yazılı imtahan ballarının köçürmə vərəqi (batch), 2026-09-12.

Sahibin tələbi: «qrup seçilsin, müəllim, tarix və s. lazımlı nə info varsa;
tələbələrin balları sistemə yüklənsin». Kağız imtahanın tarixi / yoxlayan
müəllimi / nəzarətçisi / protokol nömrəsi heç bir mövcud modeldə yoxdur, ona
görə kiçik ``ExamScoreSheet`` (partiya) modeli yaradılır və hər append-only
``ExamScoreEntry`` sətri opsional ``sheet`` FK ilə ona bağlanır.

Təhlükəsizlik: ``sheet`` sütunu NULL-icazəlidir — mövcud sətirlər toxunulmur,
məlumat köçürülməsi yoxdur. RLS siyasəti ayrıca (0072) qoşulur — qardaş
``0049`` + ``0050`` nümunəsi ilə eyni.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.registrar.models.exam_score_entry
import core.upload_security


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0050_tutor_coordinator_parity"),
        ("registrar", "0070_schedule_slot_soft_delete_parking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExamScoreSheet",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "source",
                    models.CharField(
                        choices=[("manual", "Manual roster entry"), ("import", "File import (XLSX/CSV)")],
                        default="manual",
                        max_length=12,
                    ),
                ),
                (
                    "exam_date",
                    models.DateField(blank=True, help_text="Kağız imtahanın keçirildiyi tarix.", null=True),
                ),
                (
                    "examiner_name",
                    models.CharField(blank=True, help_text="Yoxlayan müəllimin adı (snapshot).", max_length=200),
                ),
                (
                    "invigilator_name",
                    models.CharField(blank=True, help_text="Nəzarətçi (sərbəst mətn).", max_length=200),
                ),
                (
                    "protocol_number",
                    models.CharField(blank=True, help_text="Protokol / vərəq nömrəsi.", max_length=64),
                ),
                ("note", models.TextField(blank=True, help_text="Partiya qeydi (opsional).")),
                (
                    "evidence",
                    models.FileField(
                        blank=True,
                        help_text="Skan edilmiş protokol / vərəq (PDF və ya şəkil) — opsional.",
                        upload_to=apps.registrar.models.exam_score_entry.exam_score_sheet_path,
                        validators=[
                            core.upload_security.FileUploadValidator(
                                allowed_extensions={".heic", ".heif", ".jpeg", ".jpg", ".pdf", ".png", ".webp"},
                                max_size_mb=10,
                            )
                        ],
                    ),
                ),
                (
                    "original_filename",
                    models.CharField(blank=True, help_text="İdxal faylının adı (varsa).", max_length=255),
                ),
                ("rows_total", models.PositiveIntegerField(default=0)),
                ("rows_written", models.PositiveIntegerField(default=0)),
                ("rows_skipped", models.PositiveIntegerField(default=0)),
                ("rows_failed", models.PositiveIntegerField(default=0)),
                ("created_by_name", models.CharField(editable=False, max_length=200)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="exam_score_sheets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "examiner",
                    models.ForeignKey(
                        blank=True,
                        help_text="Vərəqi yoxlayan müəllim (default: açılışın müəllimi).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="examined_score_sheets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "offering",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="exam_score_sheets",
                        to="registrar.courseoffering",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="exam_score_sheets",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "exam score sheet",
                "verbose_name_plural": "exam score sheets",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["organization", "offering", "-created_at"], name="reg_ess_org_off_created_idx"
                    ),
                    models.Index(fields=["organization", "-created_at"], name="reg_ess_org_created_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="examscoreentry",
            name="sheet",
            field=models.ForeignKey(
                blank=True,
                help_text="Köçürmə partiyası (vərəq/protokol) — varsa.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entries",
                to="registrar.examscoresheet",
            ),
        ),
    ]
