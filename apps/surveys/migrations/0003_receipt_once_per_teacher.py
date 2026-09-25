# «1 müəllim üzrə tələbədən 1» (sahib, 2026-09-25): qəbzin unikallığı (kampaniya, tələbə, açılış, müəllim)
# əvəzinə (kampaniya, tələbə, müəllim) — müəllim eyni tələbəyə bir neçə fənn desə də forma bir dəfədir.
# Prod-da hələ sorğu datası yoxdur (modul bu buraxılışla gəlir) — məhdudiyyət təhlükəsiz dəyişir.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("surveys", "0002_rls_surveys"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="surveyreceipt",
            name="surveys_receipt_teacher_once",
        ),
        migrations.AddConstraint(
            model_name="surveyreceipt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scope", "teacher")),
                fields=("campaign", "student", "teacher"),
                name="surveys_receipt_teacher_once",
            ),
        ),
    ]
