"""Sahibin qərarı (2026-09-14, səhər): RİM rəhbəri (`ikt_rehber`) — HƏR ŞEYİN icazəsi.

«Başqa müəllimin jurnalına baxa bilsin, dərs əlavə edə bilsin, sillabusa baxa
bilsin və s.» → şablon `["*"]` oldu (rektor kimi). Mövcud tenantlarda `ikt_rehber`
adlı rolların açar siyahısı `["*"]` ilə əvəz olunur; geri alma köhnə şablon
siyahısını (2026-09-14 səhər vəziyyəti, `0052` daxil) bərpa edir — tenantın
redaktordan əlavə etdiyi fərdi açarlar geri almada itir (onsuz da `*` içindədir).
"""

from django.db import migrations

_ROLE_NAME = "ikt_rehber"

#: 0052-dən sonrakı şablon siyahısı (geri alma üçün).
_PREVIOUS_TEMPLATE = [
    "org.view",
    "org.edit",
    "unit.*",
    "member.*",
    "course.*",
    "exam.*",
    "final_score.entry",
    "grade.*",
    "group.view",
    "group.manage",
    "journal.correct",
    "journal.close",
    "journal.roster",
    "journal.reassign",
    "schedule.view",
    "schedule.manage",
    "syllabus.*",
    "workload.*",
    "role.*",
    "user.search",
    "user.credentials",
    "user.block",
    "user.soft_delete",
    "user.edit",
    "user.import",
    "people.view_teachers",
    "people.view_students",
    "people.view_contacts",
    "people.view_demographics",
    "people.manage_status",
    "people.manage_teacher_role",
    "people.manage_academic",
    "appeal.respond",
    "appeal.decide",
    "analytics.view_all",
    "audit.view",
    "audit.export",
    "org.settings",
    "application.create",
    "application.handle",
    "application.manage",
    "catalog.view",
    "catalog.manage",
    "student.registry_view",
    "student.movement",
    "student.assign_group",
    "plan.view",
    "plan.edit",
    "plan.submit",
    "plan.approve_chair",
    "plan.approve_council",
    "plan.approve_office",
    "semester.view",
    "semester.open",
    "semester.lock",
    "semester.unlock",
    "appeal.create",
]


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        if list(role.permissions or []) == ["*"]:
            continue
        role.permissions = ["*"]
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        if "*" not in (role.permissions or []):
            continue
        role.permissions = list(_PREVIOUS_TEMPLATE)
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0052_rim_final_score_entry")]

    operations = [migrations.RunPython(forward, backward)]
