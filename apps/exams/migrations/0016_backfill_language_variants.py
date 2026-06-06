# Geriyə uyğunluq backfill-i: çoxdilli dəstəkdən əvvəl yaradılmış bütün
# imtahanlar tək-dilli (Azərbaycan dili) sayılır. Hər mövcud imtahan üçün bir
# default "az" dil variantı yaradılır və həmin imtahanın bütün sualları bu
# varianta bağlanır. Beləliklə köhnə imtahan/sual axını pozulmadan yeni
# struktura keçir. Təhlükəsiz və idempotentdir.

from django.db import migrations

DEFAULT_LANGUAGE = "az"


def backfill_language_variants(apps, schema_editor):
    Exam = apps.get_model("exams", "Exam")
    ExamLanguageVariant = apps.get_model("exams", "ExamLanguageVariant")
    ExamQuestion = apps.get_model("exams", "ExamQuestion")

    for exam in Exam.objects.all().iterator():
        variant, _ = ExamLanguageVariant.objects.get_or_create(
            exam_id=exam.id,
            language=DEFAULT_LANGUAGE,
            defaults={"is_active": True},
        )
        ExamQuestion.objects.filter(exam_id=exam.id, language_variant__isnull=True).update(
            language=DEFAULT_LANGUAGE,
            language_variant_id=variant.id,
        )


def reverse_noop(apps, schema_editor):
    # Hansı variantların backfill ilə yaradıldığını etibarlı şəkildə ayırd etmək
    # mümkün olmadığı üçün geri qayıdışda heç nə silinmir.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0015_exam_language_variant"),
    ]

    operations = [
        migrations.RunPython(backfill_language_variants, reverse_noop),
    ]
