"""«Parol sıfırlama» açarını (`account.password_reset`) RİM rəhbərinə verir (sahib, 2026-09-30).

Yeni təşkilatlar açarı `ikt_rehber` şablonunun `["*"]` wildcard-ı ilə onsuz da
alır (``default_roles_university``). Bu miqrasiya MÖVCUD tenantları eyni vəziyyətə
gətirir: `ikt_rehber` rolunun açar siyahısı tenantda əl ilə DARALDILIBSA (`*`
yoxdur), açar ayrıca əlavə olunur. 0042/0054 ilə EYNİ naxış:

* `*` və ya `account.*` daşıyan rola TOXUNULMUR (onsuz da əhatəlidir);
* açar artıq varsa heç nə dəyişmir → İDEMPOTENTDİR;
* digər rollara açar VERİLMİR — lazım olsa universitet onu icazə redaktorundan
  («Hesab idarəetməsi (RİM)» kateqoriyası) istənilən aşağı rola verir.

Geri dönüş: açarı yalnız `ikt_rehber` rollarından götürür (kataloqdan da çıxır,
yəni başqa yerdə qalması mənasızdır). Tenant izolyasiyası: hər təşkilatın öz
`Role` sətri ayrıca yenilənir — bir tenantın dəyişikliyi digərinə keçmir.
"""

from django.db import migrations

_ROLE_NAME = "ikt_rehber"
_KEY = "account.password_reset"
_COVERING = ("*", "account.*")


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

    dependencies = [("organizations", "0054_seed_quality_control_roles")]

    operations = [migrations.RunPython(forward, backward)]
