"""«Sistem monitorinqi» açarını (`system.monitoring.view`) RİM rəhbərinə verir (sahib, 2026-10-01).

Sahib: «RİM rəhbərinə superadmindəki serveri izləmək özəlliyini ver». Yeni
təşkilatlar açarı `ikt_rehber` şablonunun `["*"]` wildcard-ı ilə onsuz da alır
(``default_roles_university``). Bu miqrasiya MÖVCUD tenantları eyni vəziyyətə
gətirir: `ikt_rehber` rolunun açar siyahısı tenantda əl ilə DARALDILIBSA (`*`
yoxdur), açar ayrıca əlavə olunur. 0055 ilə EYNİ naxış:

* `*` və ya `system.*` daşıyan rola TOXUNULMUR (onsuz da əhatəlidir);
* açar artıq varsa heç nə dəyişmir → İDEMPOTENTDİR;
* digər rollara açar VERİLMİR — lazım olsa universitet onu icazə redaktorundan
  («Sistem monitorinqi» kateqoriyası) istənilən rola verir.

Açar YALNIZ OXUDUR — insident əməlləri superadmin-only qalır
(``apps/monitoring/permissions.superadmin_monitoring_required``).

Geri dönüş: açarı yalnız `ikt_rehber` rollarından götürür. Tenant izolyasiyası:
hər təşkilatın öz `Role` sətri ayrıca yenilənir.
"""

from django.db import migrations

_ROLE_NAME = "ikt_rehber"
_KEY = "system.monitoring.view"
_COVERING = ("*", "system.*")


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

    dependencies = [("organizations", "0055_account_password_reset_permission")]

    operations = [migrations.RunPython(forward, backward)]
