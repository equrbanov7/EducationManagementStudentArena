# Migration: Replace Lab.allowed_students TextField with ManyToManyField
#
# Strategy:
#  1. Rename the old TextField to `allowed_students_legacy` so its data is
#     preserved during the transition.
#  2. Add the new ManyToManyField `allowed_students`.
#  3. Populate the M2M relation from the comma-separated IDs stored in the
#     legacy field (RunPython, forward migration only; reverse simply clears
#     the M2M since the text data is restored by the field rename reversal).
#  4. Drop the legacy field.

from django.conf import settings
from django.db import migrations, models


def _migrate_allowed_students_forward(apps, schema_editor):
    """Copy comma-separated user IDs from the legacy text field into the M2M table."""
    Lab = apps.get_model("labs", "Lab")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    for lab in Lab.objects.exclude(allowed_students_legacy=""):
        raw = lab.allowed_students_legacy or ""
        user_ids = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                user_ids.append(int(part))

        if not user_ids:
            continue

        users = list(User.objects.filter(pk__in=user_ids))
        lab.allowed_students.set(users)


def _migrate_allowed_students_reverse(apps, schema_editor):
    """
    Reverse: write M2M user IDs back into the legacy text field and clear the M2M.

    This keeps the reverse migration safe and data-preserving.
    """
    Lab = apps.get_model("labs", "Lab")

    for lab in Lab.objects.all():
        ids = list(lab.allowed_students.values_list("pk", flat=True))
        if ids:
            lab.allowed_students_legacy = ",".join(str(pk) for pk in ids)
            lab.save(update_fields=["allowed_students_legacy"])
        lab.allowed_students.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("labs", "0003_alter_lab_teacher_files_alter_labanswer_answer_file_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: preserve old text data under a temporary name
        migrations.RenameField(
            model_name="lab",
            old_name="allowed_students",
            new_name="allowed_students_legacy",
        ),
        # Step 2: create the new M2M relation
        migrations.AddField(
            model_name="lab",
            name="allowed_students",
            field=models.ManyToManyField(
                blank=True,
                related_name="allowed_labs",
                to=settings.AUTH_USER_MODEL,
                verbose_name="İcazəli tələbələr",
            ),
        ),
        # Step 3: populate the M2M from the legacy text column
        migrations.RunPython(
            _migrate_allowed_students_forward,
            _migrate_allowed_students_reverse,
        ),
        # Step 4: remove the now-redundant legacy text column
        migrations.RemoveField(
            model_name="lab",
            name="allowed_students_legacy",
        ),
    ]
