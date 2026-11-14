"""«Passiv» dərs (sahib 2026-11-14) — ``Lesson.is_passive`` + köhnə «Passiv saat» qeydlərinin dərsə çevrilməsi.

``db_default=False``: mövcud dərslər adi qalır, xam SQL INSERT-lər (köçürmə / RLS testləri) sütunu tanımır.

0122 ``PassiveHour`` sətirləri (jurnal başlığındakı yığışdırılan qutu) eyni açılışa PASSİV DƏRS kimi yazılır:
tarix, saat, mövzu = qeyd, yaradan + müəllim = qeydi yazan (yoxdursa açılışın müəllimi), növ = yazanın həmin
jurnaldakı ən çox keçdiyi növ (bölünmüş jurnalda öz payında görünsün), yoxdursa mühazirə. Təkrar qaçış eyni dərsi
ikinci dəfə yaratmır. Dil səviyyə kohortunun açılışı ötürülür (kontakt saatı trigger-i — passiv orada açılmır).
``PassiveHour`` cədvəli SİLİNMİR (arxiv; kod onu oxumur). Geri: çevrilmiş (qeydsiz) passiv dərslər silinir.
RLS: yazı ``app.bypass_rls`` tranzaksiya daxilində (``set_config(..., true)``).
"""

from collections import Counter

from django.db import migrations, models


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)", params=None)


def _kind_for(Lesson, offering_id, author_id):
    kinds = Counter(
        Lesson.objects.filter(offering_id=offering_id, instructor_id=author_id, is_passive=False).values_list(
            "kind", flat=True
        )
    )
    return kinds.most_common(1)[0][0] if kinds else "lecture"


def convert_passive_hours(apps, schema_editor):
    _bypass(schema_editor)
    PassiveHour = apps.get_model("registrar", "PassiveHour")
    Lesson = apps.get_model("registrar", "Lesson")
    Cohort = apps.get_model("registrar", "LanguageLevelCohort")
    cohort_offerings = set(Cohort.objects.values_list("offering_id", flat=True))
    for row in PassiveHour.objects.select_related("offering").order_by("offering_id", "date", "created_at"):
        if row.offering_id in cohort_offerings:
            continue
        author_id = row.created_by_id or row.offering.instructor_id
        exists = Lesson.objects.filter(
            offering_id=row.offering_id, is_passive=True, date=row.date, hours=row.hours, topic=row.note
        ).exists()
        if exists:
            continue
        Lesson.objects.create(
            organization_id=row.organization_id,
            offering_id=row.offering_id,
            date=row.date,
            kind=_kind_for(Lesson, row.offering_id, author_id),
            topic=row.note,
            hours=row.hours,
            created_by_id=row.created_by_id,
            instructor_id=author_id,
            is_passive=True,
        )


def revert_passive_hours(apps, schema_editor):
    _bypass(schema_editor)
    PassiveHour = apps.get_model("registrar", "PassiveHour")
    Lesson = apps.get_model("registrar", "Lesson")
    for row in PassiveHour.objects.all():
        Lesson.objects.filter(
            offering_id=row.offering_id,
            is_passive=True,
            date=row.date,
            hours=row.hours,
            topic=row.note,
            marks__isnull=True,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0123_guest_document_docx"),
    ]

    operations = [
        migrations.AddField(
            model_name="lesson",
            name="is_passive",
            field=models.BooleanField(db_default=False, default=False, help_text="Passiv dərs — saat hesabına düşmür."),
        ),
        migrations.RunPython(convert_passive_hours, revert_passive_hours),
    ]
