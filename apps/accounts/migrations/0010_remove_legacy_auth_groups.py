from django.db import migrations


LEGACY_AUTH_GROUP_NAMES = [
    "student",
    "teacher",
    "assistant_teacher",
    "moderator",
]


def remove_legacy_auth_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=LEGACY_AUTH_GROUP_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_emailotp"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(remove_legacy_auth_groups, migrations.RunPython.noop),
    ]
