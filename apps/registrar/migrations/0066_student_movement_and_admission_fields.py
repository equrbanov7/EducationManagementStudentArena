"""Tələbə hərəkəti reyestri (`StudentMovement`) + akademik qeydin qəbul sahələri.

Dizayn handoff Mərhələ 3 (ekran 08 «Tələbə qəbulu», 09 «Tələbə reyestri»).

* `StudentMovement` — 6 hərəkət növü üçün APPEND-ONLY əmr jurnalı
  (§8/5 «status dəyişikliyi silinmir — tarixçə yazısıdır»).
  RLS və append-only trigger AYRI migrasiyadadır: `0067_rls_student_movement`.
* `StudentAcademicRecord` — ATİS qəbul atributları (bal, imtahan növü, ATİS id)
  + tələbənin ÖZ təhsil forması və maliyyələşmə mənbəyi (ekran 09 sütunları).
  Sahələr `models/admission_meta.py`-dəki abstrakt bazadadır (modul ölçüsü).

Yeni sahələr NULL/def-dəyərlidir → köçürülmüş 5 213 hesab üçün data itkisi YOX;
`education_form` default «əyani», `funding_type` default «ödənişli» — köhnə
sistemdə struktur sahə olmadığı üçün bunlar SONRADAN reyestrdən dəqiqləşdirilir.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.registrar.models.movement
import core.upload_security


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0041_seed_stage2_permissions"),
        ("registrar", "0065_curriculum_plan_chain"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="studentacademicrecord",
            name="admission_exam_type",
            field=models.CharField(
                blank=True,
                default="",
                help_text="İmtahan növü/qrupu (məs. «I qrup», «Blok», «Magistratura»).",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="studentacademicrecord",
            name="admission_score",
            field=models.DecimalField(
                blank=True, decimal_places=2, help_text="Qəbul balı (ATİS).", max_digits=6, null=True
            ),
        ),
        migrations.AddField(
            model_name="studentacademicrecord",
            name="atis_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="ATİS qəbul siyahısındakı sətir nömrəsi/identifikatoru.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="studentacademicrecord",
            name="education_form",
            field=models.CharField(
                choices=[("full_time", "Əyani"), ("part_time", "Qiyabi"), ("distance", "Distant")],
                db_index=True,
                default="full_time",
                help_text="Tələbənin təhsil forması (ixtisasın default formasından fərqlənə bilər).",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="studentacademicrecord",
            name="funding_type",
            field=models.CharField(
                choices=[("state", "Dövlət sifarişi"), ("paid", "Ödənişli")],
                db_index=True,
                default="paid",
                help_text="Maliyyələşmə mənbəyi (dövlət sifarişi / ödənişli).",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="StudentMovement",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("group_transfer", "Qrupdan qrupa köçürmə"),
                            ("program_transfer", "İxtisasdan ixtisasa köçürmə"),
                            ("form_change", "Əyanidən qiyabiyə (və ya tərsi)"),
                            ("academic_leave", "Akademik məzuniyyət"),
                            ("reinstatement", "Bərpa"),
                            ("expulsion", "Xaric etmə"),
                        ],
                        db_index=True,
                        max_length=24,
                    ),
                ),
                ("order_number", models.CharField(help_text="Rektor/dekanlıq əmrinin nömrəsi.", max_length=64)),
                ("order_date", models.DateField(help_text="Əmrin tarixi.")),
                ("reason", models.TextField(help_text="Əsaslandırma — ən azı 20 simvol (handoff §8/6).")),
                (
                    "document",
                    models.FileField(
                        blank=True,
                        help_text="Ərizə / arayış / protokol — opsional.",
                        upload_to=apps.registrar.models.movement.movement_document_path,
                        validators=[
                            core.upload_security.FileUploadValidator(
                                allowed_extensions={".jpeg", ".jpg", ".pdf", ".png", ".webp"}, max_size_mb=10
                            )
                        ],
                    ),
                ),
                ("from_status", models.CharField(blank=True, default="", max_length=20)),
                ("to_status", models.CharField(blank=True, default="", max_length=20)),
                ("from_label", models.CharField(blank=True, default="", max_length=255)),
                ("to_label", models.CharField(blank=True, default="", max_length=255)),
                ("effective_until", models.DateField(blank=True, null=True)),
                ("actor_name", models.CharField(blank=True, default="", max_length=200)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="student_movements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "from_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="organizations.orgunit",
                    ),
                ),
                (
                    "from_program",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="registrar.program",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="student_movements",
                        to="organizations.organization",
                    ),
                ),
                (
                    "record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movements",
                        to="registrar.studentacademicrecord",
                    ),
                ),
                (
                    "to_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="organizations.orgunit",
                    ),
                ),
                (
                    "to_program",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="registrar.program",
                    ),
                ),
            ],
            options={
                "verbose_name": "student movement",
                "verbose_name_plural": "student movements",
                "ordering": ["-order_date", "-created_at"],
                "indexes": [
                    models.Index(fields=["organization", "-order_date"], name="registrar_s_organiz_8445bb_idx"),
                    models.Index(fields=["organization", "record"], name="registrar_s_organiz_5ec0c8_idx"),
                    models.Index(fields=["organization", "kind"], name="registrar_s_organiz_54b1de_idx"),
                ],
            },
        ),
    ]
