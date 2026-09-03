"""`grade.approve_chair` / `grade.approve_final` → `journal.close` (təsdiq zənciri ləğvi).

SAHİBİN QƏRARI (2026-08): müəllim → kafedra → dekan qiymət təsdiq zənciri ləğv
edildi. Onun icazə açarları da kataloqdan çıxarıldı (bax
``apps/organizations/permissions.py``). Yerinə semestr sonu TOPLU jurnal
bağlama/açma açarı gəlir: ``journal.close``.

Bu miqrasiya mövcud tenantların rol sətirlərini uyğunlaşdırır:

1. hər rolda köhnə iki açar SİLİNİR (kataloqda olmadıqları üçün
   ``validate_permissions`` onları rədd edərdi);
2. ``journal.close`` YALNIZ RİM roluna (``ikt_rehber``) verilir — sahibin
   qərarına görə jurnalı semestr sonunda RİM bağlayır. Digər rollara (dekan,
   kafedra müdiri…) lazım olsa permission-editordan verilir. ``*`` daşıyan
   rollar (rektor/sahib) onsuz da hər şeyi əhatə edir.

İdempotentdir. Geri dönüş: ``journal.close`` çıxarılır və köhnə açarlar
əvvəlki sahiblərinə (chair_head → approve_chair, dean/rektorat → approve_final)
qaytarılır.
"""

from django.db import migrations

_OLD_PERMISSIONS = ("grade.approve_chair", "grade.approve_final")
_NEW_PERMISSION = "journal.close"

#: Geri dönüşdə köhnə açarın qaytarılacağı rollar (irəli gedişdə silinənlərin
#: mənbəyi: ``default_roles_university.py``-ın 0030-dan ƏVVƏLKİ vəziyyəti).
_REVERSE_GRANTS = {
    "chair_head": ["grade.approve_chair"],
}


def _save(role, permissions):
    role.permissions = permissions
    role.save(update_fields=["permissions"])


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        remaining = [perm for perm in permissions if perm not in _OLD_PERMISSIONS]
        changed = len(remaining) != len(permissions)
        if role.name == "ikt_rehber" and "*" not in remaining and _NEW_PERMISSION not in remaining:
            remaining.append(_NEW_PERMISSION)
            changed = True
        if changed:
            _save(role, remaining)


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = [perm for perm in (role.permissions or []) if perm != _NEW_PERMISSION]
        changed = len(permissions) != len(role.permissions or [])
        for perm in _REVERSE_GRANTS.get(role.name, []):
            if perm not in permissions:
                permissions.append(perm)
                changed = True
        if changed:
            _save(role, permissions)


class Migration(migrations.Migration):

    dependencies = [("organizations", "0029_seed_rim_user_permissions")]

    operations = [migrations.RunPython(forward, backward)]
