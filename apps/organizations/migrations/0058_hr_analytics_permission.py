"""«Kadr analitikası» açarını (`people.hr_analytics`) `hr` rolunun mövcud sətirlərinə verir (sahib, 2026-10-11).

Yeni təşkilatlar açarı ``default_roles_university`` şablonundan (``apply_hr_grants``) alır; rektor və
RİM rəhbəri onu `*` ilə onsuz da daşıyır. Bu miqrasiya MÖVCUD tenantları eyni vəziyyətə gətirir —
0056 ilə EYNİ naxış:

* `*` və ya `people.*` daşıyan rola TOXUNULMUR (onsuz da əhatəlidir);
* açar artıq varsa heç nə dəyişmir → İDEMPOTENTDİR;
* digər rollara açar VERİLMİR — lazım olsa universitet onu icazə redaktorundan verir.

Açar YALNIZ OXUDUR (aqreqat analitika + audit olunan Excel ixracı). Geri dönüş: açarı yalnız `hr`
rollarından götürür. Tenant izolyasiyası: hər təşkilatın öz `Role` sətri ayrıca yenilənir.
"""

from django.db import migrations

_ROLE_NAME = "hr"
_KEY = "people.hr_analytics"
_COVERING = ("*", "people.*")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        permissions = list(role.permissions or [])
        if _KEY in permissions or any(entry in permissions for entry in _COVERING):
            continue
        role.permissions = permissions + [_KEY]
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        permissions = list(role.permissions or [])
        if _KEY not in permissions:
            continue
        role.permissions = [entry for entry in permissions if entry != _KEY]
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0057_capacity_drop_unused_indexes")]

    operations = [migrations.RunPython(forward, backward)]
