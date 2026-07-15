"""Arxiv konseptinin ləğvi — data təmizliyi.

"Arxiv" (is_archived) aktiv/deaktiv (is_active) ilə eyni işi görürdü, ona görə
UI + status bölməsi silindi. Sahələr sxemdə qalır (geriyə-uyğunluq, miqrasiya
riski olmasın deyə), amma mövcud arxivlənmiş imtahanlar təmizlənir: gizli
qalmaları üçün deaktiv (is_active=False) edilir və dormant bayraq təmizlənir.
"""

from django.db import migrations


def retire_archive(apps, schema_editor):
    Exam = apps.get_model("exams", "Exam")
    Exam.objects.filter(is_archived=True).update(is_active=False, is_archived=False, archived_at=None)


def noop(apps, schema_editor):
    # Geriyə dönmə arxiv vəziyyətini bərpa etmir (məlumat itkisi yoxdur — sadəcə
    # bayraq təmizlənib); ona görə boş no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0055_drop_active_exam_question_db_trigger"),
    ]

    operations = [
        migrations.RunPython(retire_archive, noop),
    ]
