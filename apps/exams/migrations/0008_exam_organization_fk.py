import django.db.models.deletion
from django.db import migrations, models


def populate_exam_organization(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    Exam = apps.get_model("exams", "Exam")
    UserProfile = apps.get_model("accounts", "UserProfile")

    profile_org_map = dict(
        UserProfile.objects.exclude(organization__isnull=True).values_list("user_id", "organization_id")
    )
    course_org_map = dict(Course.objects.exclude(organization__isnull=True).values_list("id", "organization_id"))

    updates = []
    for exam in Exam.objects.all().only("id", "author_id", "course_id"):
        organization_id = course_org_map.get(exam.course_id) or profile_org_map.get(exam.author_id)
        if organization_id:
            exam.organization_id = organization_id
            updates.append(exam)

    if updates:
        Exam.objects.bulk_update(updates, ["organization"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_userprofile_requested_organization_message"),
        ("organizations", "0001_initial"),
        ("courses", "0003_course_organization_fk"),
        ("exams", "0007_examquestion_created_at"),
    ]

    operations = [
        migrations.RenameField(
            model_name="exam",
            old_name="organization_id",
            new_name="legacy_organization_id",
        ),
        migrations.AddField(
            model_name="exam",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text="organization",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="exams",
                to="organizations.organization",
                verbose_name="organization",
            ),
        ),
        migrations.RunPython(populate_exam_organization, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="exam",
            name="legacy_organization_id",
        ),
    ]
