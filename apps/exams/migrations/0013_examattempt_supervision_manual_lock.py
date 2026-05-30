# Generated for EMSArena on 2026-05-30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0012_examattempt_supervision_locked_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='examattempt',
            name='supervision_manual_lock',
            field=models.BooleanField(default=False, verbose_name='supervision_manual_lock'),
        ),
    ]
