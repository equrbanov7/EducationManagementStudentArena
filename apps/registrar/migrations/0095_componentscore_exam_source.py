"""Midterm test balı jurnala avtomatik (sahib 2026-10-21): ``ComponentScore.exam_source``.

Test formatlı midterm cəhdindən yazılmış Midterm xanasının mənbəyi (cəhd id, imtahan adı/slug, faiz).
NULL = əl ilə yazılıb (mövcud bütün sətirlər). Sütun nullable, defoltsuz — PG-də ani ``ADD COLUMN``,
köhnə kodun INSERT-ləri NULL yazır (rolling deploy təhlükəsizdir). Yeni cədvəl / trigger / RLS yoxdur
(``registrar_componentscore``-un RLS-i və ``trg_journal_mark_guard``-ı olduğu kimi qalır).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0094_retake_refund"),
    ]

    operations = [
        migrations.AddField(
            model_name="componentscore",
            name="exam_source",
            field=models.JSONField(blank=True, editable=False, null=True),
        ),
    ]
