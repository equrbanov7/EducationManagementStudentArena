"""Server-side DEFAULT üçün `0066`-dakı qəbul sahələrinə `db_default`.

`0066_student_movement_and_admission_fields` bu 4 sahəni (`atis_id`,
`admission_exam_type`, `education_form`, `funding_type`) NOT NULL + Python-
səviyyəli `default=` ilə əlavə etmişdi. Django-nun `AddField` davranışı NOT
NULL sütun üçün DB defaultunu YALNIZ mövcud sətirləri doldurmaq üçün
MÜVƏQQƏTİ qoyur, sonra SİLİR — nəticədə `Model.save()`-dən keçməyən istənilən
xam `INSERT` (test, legacy-repair əmri, ATİS idxal skripti) bu sütunları
buraxsa `NOT NULL` pozuntusu ilə uğursuz olur (bax
`apps/accounts/tests/test_account_archive_postgres.py` — trigger-DatabaseError
gözlənilən yerdə əvəzinə NOT NULL xətası tuturdu).

`db_default` (Django 5+) əsl server-side DEFAULT yaradır və AlterField-dən
sonra da QALIR — data itkisi yoxdur (mövcud sətirlər artıq dolu idi).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0067_rls_student_movement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentacademicrecord",
            name="admission_exam_type",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text="İmtahan növü/qrupu (məs. «I qrup», «Blok», «Magistratura»).",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="studentacademicrecord",
            name="atis_id",
            field=models.CharField(
                blank=True,
                db_default="",
                db_index=True,
                default="",
                help_text="ATİS qəbul siyahısındakı sətir nömrəsi/identifikatoru.",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="studentacademicrecord",
            name="education_form",
            field=models.CharField(
                choices=[("full_time", "Əyani"), ("part_time", "Qiyabi"), ("distance", "Distant")],
                db_default="full_time",
                db_index=True,
                default="full_time",
                help_text="Tələbənin təhsil forması (ixtisasın default formasından fərqlənə bilər).",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="studentacademicrecord",
            name="funding_type",
            field=models.CharField(
                choices=[("state", "Dövlət sifarişi"), ("paid", "Ödənişli")],
                db_default="paid",
                db_index=True,
                default="paid",
                help_text="Maliyyələşmə mənbəyi (dövlət sifarişi / ödənişli).",
                max_length=16,
            ),
        ),
    ]
