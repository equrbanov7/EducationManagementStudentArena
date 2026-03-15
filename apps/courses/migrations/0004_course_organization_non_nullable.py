import django.db.models.deletion
from django.db import migrations, models


def handle_courses_without_organization(apps, schema_editor):
    """
    Data migration: assign organization for any remaining null records.
    Courses that still have no organization after previous migrations are
    deleted to enforce tenant isolation (orphaned records have no tenant
    boundary and cannot be safely assigned).
    """
    Course = apps.get_model("courses", "Course")
    UserProfile = apps.get_model("accounts", "UserProfile")

    profile_org_map = dict(
        UserProfile.objects.exclude(organization__isnull=True).values_list("user_id", "organization_id")
    )

    null_courses = Course.objects.filter(organization__isnull=True)
    updates = []
    orphan_ids = []

    for course in null_courses.only("id", "owner_id"):
        organization_id = profile_org_map.get(course.owner_id)
        if organization_id:
            course.organization_id = organization_id
            updates.append(course)
        else:
            orphan_ids.append(course.id)

    if updates:
        Course.objects.bulk_update(updates, ["organization"])

    if orphan_ids:
        Course.objects.filter(id__in=orphan_ids).delete()


class Migration(migrations.Migration):

    # atomic=False is required because PostgreSQL cannot ALTER TABLE while
    # deferred trigger events (e.g. FK cascades) from the preceding RunPython
    # step are still pending within the same transaction.
    atomic = False

    dependencies = [
        ("courses", "0003_course_organization_fk"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(handle_courses_without_organization, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="course",
            name="organization",
            field=models.ForeignKey(
                help_text="Kursun aid olduğu təşkilat",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="courses",
                to="organizations.organization",
                verbose_name="Təşkilat",
            ),
        ),
    ]
