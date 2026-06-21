import apps.exams.models
from django.db import migrations, models


class Migration(migrations.Migration):
    """Variant (ExamQuestionOption / BankQuestionOption) düstur şəkli sahəsi."""

    dependencies = [
        ("exams", "0022_exam_archive_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="examquestionoption",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=apps.exams.models.option_media_path,
                verbose_name="image",
            ),
        ),
        migrations.AddField(
            model_name="bankquestionoption",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=apps.exams.models.bank_option_media_path,
                verbose_name="image",
            ),
        ),
    ]
