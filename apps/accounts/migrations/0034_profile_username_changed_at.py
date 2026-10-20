from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0033_teaching_pay_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="username_changed_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="İstifadəçinin öz istifadəçi adını sonuncu dəfə dəyişdiyi vaxt.",
                null=True,
                verbose_name="İstifadəçi adı dəyişdirilib",
            ),
        ),
    ]
