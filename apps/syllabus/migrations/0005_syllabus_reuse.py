"""Sillabusun TƏKRAR İSTİFADƏSİ (2026-10-08): eyni fənnin eyni semestrdəki başqa
qrupunun sillabusuna bağlanma.

* ``Syllabus.reused_from`` — bağlı dosyenin mənbəyi (SET_NULL: mənbə silinsə hədəf
  öz təsdiqlənmiş məzmunu ilə müstəqil qalır);
* ``ApprovalSource.REUSE`` / ``ChangeKind.REUSED`` — saxta insan təsdiqi
  UYDURULMADAN «eyni məzmun, eyni saatlar» damğası;
* DB invariantları:
  - ``syllabus_not_reused_from_self`` — dosye özünə bağlana bilməz;
  - ``syllabus_reuse_same_org_subject`` — KOMPOZİT FK
    ``(reused_from_id, organization_id, subject_id)`` →
    ``(id, organization_id, subject_id)``: mənbə ilə hədəf HƏMİŞƏ eyni təşkilat
    və eyni fənndir (``uniq_syllabus_reuse_anchor`` onun hədəf açarıdır).
    ``MATCH SIMPLE`` — ``reused_from_id`` NULL olan sətirlər yoxlanmır.
    FK yoxlaması RLS-dən asılı deyil (Postgres RI yoxlamaları sətir təhlükəsizliyini
    keçir), ``DEFERRABLE INITIALLY DEFERRED`` isə Django-nun SET_NULL
    emulyasiyası ilə eyni tranzaksiyada uyğun gəlir.
* ``syllabus_sibling_idx`` — (təşkilat, fənn, semestr) qonşu axtarışı.

Postgres xaricində kompozit FK addımı no-op-dur (0002 RLS nümunəsi).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_FK_NAME = "syllabus_reuse_same_org_subject"

_FORWARD_SQL = f"""
ALTER TABLE syllabus_syllabus
    ADD CONSTRAINT {_FK_NAME}
    FOREIGN KEY (reused_from_id, organization_id, subject_id)
    REFERENCES syllabus_syllabus (id, organization_id, subject_id)
    DEFERRABLE INITIALLY DEFERRED;
"""

_REVERSE_SQL = f"ALTER TABLE syllabus_syllabus DROP CONSTRAINT IF EXISTS {_FK_NAME};"


def _apply_fk(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL)


def _revert_fk(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0057_capacity_drop_unused_indexes"),
        ("registrar", "0085_capacity_drop_unused_indexes"),
        ("syllabus", "0004_standard_assessment_split"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="syllabus",
            name="reused_from",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Bağlı (eyni məzmunlu) sillabusun MƏNBƏ dosyesi — eyni təşkilat, eyni fənn, eyni semestr. "
                    "Bağ ulduz formalıdır: mənbənin özü heç vaxt başqasına bağlı olmur."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reused_by",
                to="syllabus.syllabus",
            ),
        ),
        migrations.AlterField(
            model_name="syllabusversion",
            name="approval_source",
            field=models.CharField(
                choices=[
                    ("human", "İnsan qərarı"),
                    ("migration", "Sistem / köçürmə"),
                    ("reuse", "Bağlı sillabusdan (eyni məzmun)"),
                ],
                default="human",
                help_text="Təsdiqin mənbəyi: insan qərarı və ya köçürmə damğası.",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="syllabusversion",
            name="change_kind",
            field=models.CharField(
                choices=[
                    ("initial", "İlk versiya"),
                    ("minor", "Kiçik dəyişiklik (cari semestr)"),
                    ("major", "Böyük dəyişiklik (növbəti semestr)"),
                    ("copied", "Keçən ildən köçürülüb"),
                    ("imported", "Köhnə sistemdən köçürülüb"),
                    ("reused", "Başqa qrupun sillabusuna bağlanıb"),
                ],
                default="initial",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="syllabus",
            index=models.Index(fields=["organization", "subject", "period"], name="syllabus_sibling_idx"),
        ),
        migrations.AddConstraint(
            model_name="syllabus",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("reused_from__isnull", True),
                    models.Q(("reused_from", models.F("id")), _negated=True),
                    _connector="OR",
                ),
                name="syllabus_not_reused_from_self",
            ),
        ),
        migrations.AddConstraint(
            model_name="syllabus",
            constraint=models.UniqueConstraint(
                fields=("id", "organization", "subject"), name="uniq_syllabus_reuse_anchor"
            ),
        ),
        migrations.RunPython(_apply_fk, _revert_fk),
    ]
