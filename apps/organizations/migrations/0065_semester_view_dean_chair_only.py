"""«Semestr açılışı» akademik UNIT rollarından yalnız dekan + kafedra müdirində (sahib 2026-10-14 axşam).

Sahib (tyutor kimi baxış): «Semestr açılışını yığışdır buradan — ancaq dekan və kafedra müdiri görə bilsin».
Bölmə ``semester.view`` açarı ilə açılır (``rbac_sections``); tyutor və proqram koordinatoru onu ``0041`` /
``0064``-dən almışdı. Şablon tərəfi: ``default_roles_role_audit.ROLE_POST_PARITY_REVOKES`` (paritetdən
SONRA — dəstlər yenə bərabərdir). Org-wide operatorlar (Tədris şöbəsi, prorektor, RİM, RİM əməkdaşı) və
dekan / kafedra müdiri toxunulmur.

* İdempotent: yalnız DƏQİQ ``semester.view`` silinir; ``semester.*`` və ya ``*`` daşıyan rol (tenantın öz
  qərarı) TOXUNULMUR — wildcard-ı açmaq tenantın başqa ``semester.*`` açarlarını da sökərdi.
* Geri dönüş: hər iki rola açarı qaytarır (artıq ``semester.*`` / ``*`` ilə əhatəli deyilsə) — bu, ``0064``-ün
  yekun vəziyyətidir (hər iki rolda ``semester.view`` var idi); təkrar işlədikdə dublikat yazılmır.
"""

from django.db import migrations

_ROLES = ("tutor", "program_coordinator")
_KEY = "semester.view"


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        before = list(role.permissions or [])
        permissions = [key for key in before if key != _KEY]
        if permissions != before:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        permissions = list(role.permissions or [])
        if _covered(permissions, _KEY):
            continue
        role.permissions = [*permissions, _KEY]
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0064_tutor_coordinator_parity")]

    operations = [migrations.RunPython(forward, backward)]
