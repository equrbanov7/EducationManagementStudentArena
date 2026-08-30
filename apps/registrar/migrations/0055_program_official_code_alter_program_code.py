"""Rəsmi dövlət ixtisas şifri üçün AYRICA sütun.

Niyə yeni sütun, niyə ``code``-un unikallığı GÖTÜRÜLMÜR
-------------------------------------------------------
Əvvəlki cəhd ``uniq_program_code_per_org`` məhdudiyyətini götürməyi təklif
etmişdi. Düşmən baxışı bunun köçürmə xəttini ÜÇ yerdə sındırdığını PostgreSQL-də
təkrar istehsal etdi::

    apps/legacy_import/services/rehearsal_sar_phase.py:155
        program_pk_index() ``Program.code``-u primary key kimi işlədir
        («tenant-unique by constraint») → təkrar VƏ YA boş kod
        ``legacy_rehearsal_catalog_index_ambiguous`` atır.
    apps/legacy_import/services/rehearsal_structure_targets.py:169
        get_or_create(organization=…, code=plan.code) → MultipleObjectsReturned.
    apps/legacy_import/services/rehearsal_catalog_phase.py:104-122
        + rehearsal_catalog_targets.py:108
        proqramın ``TargetRef.key``-i ELƏ KODUN ÖZÜDÜR (semantik digest açarı);
        paylaşılan kod eyni açar verir, boş kod açarı boşaldır → _INDEX_AMBIGUOUS.

Ona görə ``code`` toxunulmadan qalır (yalnız ``help_text``) və rəsmi şifr üçün
UNİKAL OLMAYAN, indeksli ``official_code`` sütunu əlavə olunur. ``apps/
legacy_import/`` altında bir sətir də dəyişmir.

RLS: yeni cədvəl/əlaqə yoxdur, yalnız mövcud ``registrar_program`` cədvəlinə
sütun — ayrıca policy miqrasiyası tələb olunmur.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0054_legacy_grade_attempts_and_artifacts"),
    ]

    operations = [
        migrations.AddField(
            model_name="program",
            name="official_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Rəsmi dövlət ixtisas şifri (məs. 050405). UNİKAL DEYİL — bir neçə proqram eyni şifri paylaşa bilər.",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="program",
            name="code",
            field=models.CharField(
                help_text="DAXİLİ identifikator (tenant daxilində unikal). Köçürmə xətti bundan asılıdır — əl ilə dəyişməyin.",
                max_length=32,
            ),
        ),
    ]
