"""Backfill appeal.* permissions onto existing roles (FAZA 4).

Eyni qayda default_roles._augment_with_appeal_permissions ilə:
- imtahan idarə edən rollar (exam.create/edit/host/manage və ya exam.*) →
  appeal.create + appeal.respond + appeal.decide
- yalnız imtahana baxan rollar (exam.view) → appeal.create
- "*" rolları toxunulmur (onsuz da hər şeyə icazəlidir).

Təhlükəsiz və idempotent (mövcud icazələr təkrarlanmır). Geri qayıdışda heç nə
silinmir (hansı icazələrin əvvəldən mövcud olduğunu ayırd etmək mümkün deyil).
"""

from django.db import migrations

_EXAM_MANAGEMENT_PERMS = ("exam.*", "exam.create", "exam.edit", "exam.host", "exam.manage")


def backfill_appeal_permissions(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        perms = list(role.permissions or [])
        if "*" in perms:
            continue
        manages_exams = any(perm in perms for perm in _EXAM_MANAGEMENT_PERMS)
        views_exams = "exam.view" in perms or "exam.*" in perms
        if manages_exams:
            to_add = ["appeal.create", "appeal.respond", "appeal.decide"]
        elif views_exams:
            to_add = ["appeal.create"]
        else:
            continue

        added = [perm for perm in to_add if perm not in perms]
        if added:
            role.permissions = perms + added
            role.save(update_fields=["permissions"])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0007_rls_question_bank_appeals"),
    ]

    operations = [
        migrations.RunPython(backfill_appeal_permissions, reverse_noop),
    ]
