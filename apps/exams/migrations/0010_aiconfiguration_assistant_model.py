from django.db import migrations, models

_MODEL_CHOICES = [
    ("gemini-2.5-flash", "Gemini 2.5 Flash (orta keyfiyyət, ucuz)"),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (sürətli, ən ucuz)"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro (yüksək keyfiyyət, bahalı)"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0009_exam_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiconfiguration",
            name="assistant_model",
            field=models.CharField(
                choices=_MODEL_CHOICES,
                default="gemini-2.5-flash",
                help_text="AI Assistant (söhbət) üçün istifadə olunan model.",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="aiconfiguration",
            name="grading_model",
            field=models.CharField(
                choices=_MODEL_CHOICES,
                default="gemini-2.5-flash",
                help_text="Yazılı cavab qiymətləndirmə üçün istifadə olunan model.",
                max_length=50,
            ),
        ),
    ]
