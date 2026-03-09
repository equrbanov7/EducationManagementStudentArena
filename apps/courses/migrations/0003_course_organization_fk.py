import django.db.models.deletion
from django.db import migrations, models


def populate_course_organization(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    UserProfile = apps.get_model("accounts", "UserProfile")

    profile_org_map = dict(
        UserProfile.objects.exclude(organization__isnull=True).values_list("user_id", "organization_id")
    )

    updates = []
    for course in Course.objects.all().only("id", "owner_id"):
        organization_id = profile_org_map.get(course.owner_id)
        if organization_id:
            course.organization_id = organization_id
            updates.append(course)

    if updates:
        Course.objects.bulk_update(updates, ["organization"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_userprofile_requested_organization_message"),
        ("organizations", "0001_initial"),
        ("courses", "0002_course_grading_type_course_organization_id_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="course",
            old_name="organization_id",
            new_name="legacy_organization_id",
        ),
        migrations.AddField(
            model_name="course",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text="Kursun aid olduğu təşkilat",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="courses",
                to="organizations.organization",
                verbose_name="Təşkilat",
            ),
        ),
        migrations.RunPython(populate_course_organization, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="course",
            name="legacy_organization_id",
        ),
    ]
