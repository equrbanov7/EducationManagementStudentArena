import django.db.models.deletion
from django.db import migrations, models


def handle_exams_without_organization(apps, schema_editor):
    """
    Data migration: assign organization for any remaining null records.
    Exams that still have no organization after previous migrations are
    deleted to enforce tenant isolation (orphaned records have no tenant
    boundary and cannot be safely assigned).
    """
    Exam = apps.get_model("exams", "Exam")
    Course = apps.get_model("courses", "Course")
    UserProfile = apps.get_model("accounts", "UserProfile")

    profile_org_map = dict(
        UserProfile.objects.exclude(organization__isnull=True).values_list("user_id", "organization_id")
    )
    course_org_map = dict(Course.objects.exclude(organization__isnull=True).values_list("id", "organization_id"))

    null_exams = Exam.objects.filter(organization__isnull=True)
    updates = []
    orphan_ids = []

    for exam in null_exams.only("id", "author_id", "course_id"):
        organization_id = course_org_map.get(exam.course_id) or profile_org_map.get(exam.author_id)
        if organization_id:
            exam.organization_id = organization_id
            updates.append(exam)
        else:
            orphan_ids.append(exam.id)

    if updates:
        Exam.objects.bulk_update(updates, ["organization"])

    if orphan_ids:
        Exam.objects.filter(id__in=orphan_ids).delete()


class Migration(migrations.Migration):

    # atomic=False is required because PostgreSQL cannot ALTER TABLE while
    # deferred trigger events (e.g. FK cascades) from the preceding RunPython
    # step are still pending within the same transaction.
    atomic = False

    dependencies = [
        ("courses", "0004_course_organization_non_nullable"),
        ("exams", "0009_alter_examquestion_created_at"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(handle_exams_without_organization, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="exam",
            name="organization",
            field=models.ForeignKey(
                help_text="organization",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="exams",
                to="organizations.organization",
                verbose_name="organization",
            ),
        ),
    ]
