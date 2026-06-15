from django.db import migrations, models
from django.utils.translation import pgettext_lazy


class Migration(migrations.Migration):
    """
    Müəllim imtahanı arxivləyə bilsin — soft state.

    `is_archived` + `archived_at` əlavə olunur. Hər ikisi geriyə uyğun
    defaultlarla gəlir (mövcud imtahanlar arxivlənmir), ona görə migration
    təhlükəsizdir və data backfill tələb etmir.
    """

    dependencies = [
        ("exams", "0021_examattempt_unique_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="is_archived",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=pgettext_lazy("exams.model.exam.help", "is_archived"),
                verbose_name=pgettext_lazy("exams.model.exam.field", "is_archived"),
            ),
        ),
        migrations.AddField(
            model_name="exam",
            name="archived_at",
            field=models.DateTimeField(
                blank=True,
                help_text=pgettext_lazy("exams.model.exam.help", "archived_at"),
                null=True,
                verbose_name=pgettext_lazy("exams.model.exam.field", "archived_at"),
            ),
        ),
        migrations.AddIndex(
            model_name="exam",
            index=models.Index(
                fields=["author", "is_archived", "-created_at"],
                name="exam_author_archived_idx",
            ),
        ),
    ]
