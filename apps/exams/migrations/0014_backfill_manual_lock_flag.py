# One-time backfill: a currently "locked" attempt with zero violations cannot
# be the result of the auto-lock path (which only fires after the violation
# limit is reached, i.e. >= 1 violation). Such an attempt was therefore a
# manual teacher pause created before the supervision_manual_lock flag existed.
# Mark them so the resume flow treats them correctly. Safe & idempotent.

from django.db import migrations


def backfill_manual_lock(apps, schema_editor):
    ExamAttempt = apps.get_model("exams", "ExamAttempt")
    ExamAttempt.objects.filter(
        supervision_status="locked",
        supervision_violation_count=0,
        supervision_manual_lock=False,
    ).update(supervision_manual_lock=True)


def noop_reverse(apps, schema_editor):
    # No reliable way to distinguish backfilled rows on reverse; leave as-is.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0013_examattempt_supervision_manual_lock"),
    ]

    operations = [
        migrations.RunPython(backfill_manual_lock, noop_reverse),
    ]
