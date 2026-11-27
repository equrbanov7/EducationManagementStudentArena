import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("labs", "0002_labsubmission_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="labanswer",
            name="question",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT, related_name="answers", to="labs.labquestion"
            ),
        ),
    ]
