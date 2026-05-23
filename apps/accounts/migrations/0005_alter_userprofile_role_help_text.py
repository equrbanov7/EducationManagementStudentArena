"""Update UserProfile.role help_text (FAZA 10).

Clarifies in the model metadata that ``profile.role`` is a denormalized cache,
not the source of truth — the authoritative role is ``Membership.role``.
This is a help_text-only change; no data is touched.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_add_soft_delete_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("superadmin", "Super Admin"),
                    ("org_owner", "Təşkilat Sahibi"),
                    ("org_admin", "Təşkilat Admini"),
                    ("member", "Üzv"),
                    ("hr", "HR"),
                    ("teacher", "Müəllim"),
                    ("assistant_teacher", "Müəllim Köməkçisi"),
                    ("lead_student", "Baş Tələbə"),
                    ("student", "Tələbə"),
                ],
                db_index=True,
                default="member",
                help_text="Denormalizə keş — əsl rol Membership.role-dadır",
                max_length=30,
                verbose_name="Rol",
            ),
        ),
    ]
