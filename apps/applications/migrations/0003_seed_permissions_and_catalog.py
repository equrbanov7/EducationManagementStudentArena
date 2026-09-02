"""Mövcud tenantlar üçün: müraciət icazələri + şöbə/növ kataloqu.

İki iş görülür və hər ikisi İDEMPOTENTDİR:

1. **İcazələr.** Yeni təşkilatlar açarları ``default_roles_university.py``-dan
   alır (signal); MÖVCUD təşkilatların rol sətirlərinə isə burada yazılır.
   Qayda kod ilə eynidir: `alumni` / `member` müraciət göndərə bilmir,
   `*` daşıyan rol (rektor/sahib) onsuz da əhatəlidir, emalçı rolları
   `application.handle`, RİM və prorektor əlavə olaraq `application.manage`.

2. **Kataloq.** Hər AKTİV universitet üçün şöbələr və növlər doldurulur
   (``services.catalog.seed_catalog``). Mövcud sətrə TOXUNULMUR — tenant
   kataloqu redaktə edibsə təkrar icra onu geri qaytarmır.

⚠️ Kataloq seed-i miqrasiya-təhlükəsizdir: ``seed_catalog`` model sinifini
arqumentlə qəbul edir, ona görə burada TARİXİ modellər (``apps.get_model``)
ötürülür — gələcək sahə dəyişikliyi bu miqrasiyanı sındırmır.
"""

from django.db import migrations

from apps.applications.constants import PERM_CREATE, PERM_HANDLE, PERM_MANAGE
from apps.applications.services.catalog import seed_catalog

_ALL = (PERM_CREATE, PERM_HANDLE, PERM_MANAGE)

_CREATE_EXEMPT = {"alumni", "member", "rector"}
_HANDLER_ROLES = {
    "dean",
    "chair_head",
    "program_coordinator",
    "hr",
    "vice_rector",
    "exam_center",
    "exam_center_head",
    "exam_center_staff",
    "ikt_rehber",
}
_MANAGER_ROLES = {"ikt_rehber", "vice_rector"}


def _wanted(role_name):
    wanted = []
    if role_name not in _CREATE_EXEMPT:
        wanted.append(PERM_CREATE)
    if role_name in _HANDLER_ROLES:
        wanted.append(PERM_HANDLE)
    if role_name in _MANAGER_ROLES:
        wanted.append(PERM_MANAGE)
    return wanted


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        if "*" in permissions:
            continue
        changed = False
        for permission in _wanted(role.name):
            if permission not in permissions:
                permissions.append(permission)
                changed = True
        if changed:
            role.permissions = permissions
            role.save(update_fields=["permissions"])

    Organization = apps.get_model("organizations", "Organization")
    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    ApplicationKind = apps.get_model("applications", "ApplicationKind")
    for organization in Organization.objects.filter(is_active=True, org_type="university").iterator():
        seed_catalog(organization, unit_model=ApplicationUnit, kind_model=ApplicationKind)


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        remaining = [permission for permission in permissions if permission not in _ALL]
        if len(remaining) != len(permissions):
            role.permissions = remaining
            role.save(update_fields=["permissions"])
    # Kataloq QƏSDƏN silinmir: tenant onu redaktə etmiş ola bilər və
    # ``Application.kind`` PROTECT-dir — silinmə mövcud müraciətləri uçurardı.


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0002_rls_applications"),
        ("organizations", "0032_seed_alumni_role"),
    ]

    operations = [migrations.RunPython(forward, backward)]
