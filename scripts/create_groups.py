"""
Script to create user groups for EMS Arena.
Can be converted to a management command if needed.
"""


def create_groups():
    """
    Create default user groups: Teachers, Students, Admins.
    """
    from django.contrib.auth.models import Group

    groups = ["Teachers", "Students", "Admins"]

    for group_name in groups:
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            print(f"✅ Created group: {group_name}")
        else:
            print(f"ℹ️  Group already exists: {group_name}")


if __name__ == "__main__":
    import os

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    django.setup()
    create_groups()
