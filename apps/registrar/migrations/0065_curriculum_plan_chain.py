"""Tədris planının versiya/təsdiq zənciri + plan sətrinin saat sahələri.

Dizayn handoff Mərhələ 2 (ekran 05/07). YENİ CƏDVƏL YOXDUR → əlavə RLS policy
tələb olunmur; yalnız mövcud iki cədvələ sütun əlavə olunur.

BACKFILL — NİYƏ «approved»?
---------------------------
Köçürülmüş (myedu) planlar universitetdə ARTIQ QÜVVƏDƏDİR: onlardan açılış,
jurnal və qiymət törəyib. Yeni ``status`` sahəsinin default-u ``draft``-dır,
yəni backfill olmasa hər ixtisas bir gecədə «Plan yoxdur» olar və semestr
açılışı (ekran 07) BÜTÜN universitet üçün bloklanardı. Ona görə mövcud AKTİV
planlar ``approved`` kimi işarələnir (aktor/protokol BOŞ qalır — uydurulmur).

Sətir kreditləri isə kataloqdakı ``Subject.ects``-dən götürülür (plan sətri
kreditə sahib deyildi), saat isə kredit × 30 — sonradan redaktorda dəqiqləşir.
Geri dönüş sahələri silir, yəni backfill-in geri qaytarılması ayrıca lazım deyil.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _backfill_plan_chain(apps, schema_editor):
    """Mövcud aktiv planları «təsdiqlənib» sayır və sətir kredit/saatını doldurur."""
    Curriculum = apps.get_model("registrar", "Curriculum")
    CurriculumSubject = apps.get_model("registrar", "CurriculumSubject")
    Curriculum.objects.filter(is_active=True).update(status="approved", version=1)
    Curriculum.objects.filter(is_active=False).update(status="draft", version=1)
    for row in CurriculumSubject.objects.select_related("subject").iterator(chunk_size=2000):
        credits = int(getattr(row.subject, "ects", 0) or 0)
        row.credits = credits
        row.total_hours = credits * 30
        # Saat bölgüsü (mühazirə/seminar/lab) köhnə datada YOXDUR — uydurulmur;
        # hamısı sərbəst işə yazılsaydı balans yanlış olardı, ona görə 0 qalır və
        # redaktor sətri «saat bölgüsü yoxdur» kimi işarələyir.
        row.save(update_fields=["credits", "total_hours"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0038_seed_teaching_office_roles"),
        ("registrar", "0064_catalog_archive_and_metadata"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="curriculum",
            name="uniq_curriculum_program_year",
        ),
        migrations.AddField(
            model_name="curriculum",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_curricula",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="last_reason",
            field=models.TextField(blank=True, help_text="Son qaytarma/təsdiq səbəbi (≥20 simvol)."),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="previous_version",
            field=models.ForeignKey(
                blank=True,
                help_text="Bu versiyanın törədiyi əvvəlki plan (silinmir — tarixçədir).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="next_versions",
                to="registrar.curriculum",
            ),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="protocol_number",
            field=models.CharField(
                blank=True, help_text="Elmi Şura protokolunun nömrəsi/tarixi (təsdiqdə yazılır).", max_length=64
            ),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Qaralama"),
                    ("chair_review", "Kafedra baxışı"),
                    ("faculty_council", "Fakültə şurası"),
                    ("teaching_office", "Tədris şöbəsi"),
                    ("approved", "Təsdiqlənib"),
                    ("returned", "Qaytarılıb"),
                ],
                db_index=True,
                default="draft",
                help_text="Təsdiq zəncirindəki mövqe (qaralama → … → təsdiqlənib).",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="submitted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="submitted_curricula",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="version",
            field=models.PositiveSmallIntegerField(
                default=1, help_text="Plan versiyası — təsdiqlənmiş plan dəyişmir, yeni versiya yaranır."
            ),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="assessment_form",
            field=models.CharField(
                choices=[
                    ("exam", "İmtahan"),
                    ("credit", "Hesabat"),
                    ("coursework", "Kurs işi"),
                    ("practice", "Təcrübə"),
                    ("thesis", "Buraxılış işi"),
                ],
                default="exam",
                help_text="Qiymətləndirmə forması (imtahan/hesabat/kurs işi/təcrübə/buraxılış işi).",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="credits",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Sətrin kredit dəyəri — Subject.ects-i ÖVERRIDE edir (kredit ixtisasa görə dəyişir).",
            ),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="lab_hours",
            field=models.PositiveSmallIntegerField(default=0, help_text="Semestrlik laboratoriya saatı."),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="language",
            field=models.CharField(
                blank=True,
                help_text="Tədris dili / sektor kodu (AZ/EN/RU) — tenant-konfiqurasiyalıdır, hardcode edilmir.",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="lecture_hours",
            field=models.PositiveSmallIntegerField(default=0, help_text="Semestrlik mühazirə saatı."),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="row_code",
            field=models.CharField(blank=True, help_text="Plan şifri (məs. MİF-B04.01).", max_length=32),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="selfwork_hours",
            field=models.PositiveSmallIntegerField(default=0, help_text="Sərbəst iş saatı (auditoriyadan kənar)."),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="seminar_hours",
            field=models.PositiveSmallIntegerField(default=0, help_text="Semestrlik seminar/məşğələ saatı."),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="teaching_chair",
            field=models.ForeignKey(
                blank=True,
                help_text="Fənni bu planda tədris edən kafedra (OrgUnit: chair/department).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="taught_plan_rows",
                to="organizations.orgunit",
            ),
        ),
        migrations.AddField(
            model_name="curriculumsubject",
            name="total_hours",
            field=models.PositiveSmallIntegerField(default=0, help_text="Ümumi saat = kredit × 30 (NK 348 b. 3.2.2)."),
        ),
        migrations.AddConstraint(
            model_name="curriculum",
            constraint=models.UniqueConstraint(
                fields=("organization", "program", "admission_year", "version"),
                name="uniq_curriculum_program_year_version",
            ),
        ),
        migrations.RunPython(_backfill_plan_chain, migrations.RunPython.noop),
    ]
