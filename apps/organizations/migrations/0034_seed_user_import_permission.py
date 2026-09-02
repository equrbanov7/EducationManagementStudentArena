"""Tələbə idxalı açarı — `user.import` seed-i (mövcud tenantlar üçün).

AUDİT BOŞLUĞU (2026-09, PHASE 1 §4): «tələbə şöbəsi siyahı yükləyir → hesablar
yaranır → tələbə girə bilir» axınının İŞLƏYƏN yeganə yolu legacy köçürmə idi.
`import_users_from_excel` management komandası mövcuddur, amma
`core/management/command_safety.py` onu prod-da QƏSDƏN bağlayır (bu bağlantı
saxlanılır — zəiflədilmir); RİM mərkəzi isə yalnız MÖVCUD hesabları idarə edir.

Boşluq nəzarətli UI səthi ilə örtülür: profil kabinetindəki «Tələbə idxalı»
(`student-intake`) bölməsi. Onun qapısı bu kanonik açardır.

Niyə AYRI açar (`user.edit` / `user.credentials` deyil): idxal MÖVCUD hesabı
dəyişmir — YENİ kimlik gətirir (hesab + üzvlük + akademik qeyd). Parol
sıfırlamaq səlahiyyəti heç bir rola avtomatik olaraq «minlərlə hesab yarat»
hüququ verməməlidir (əsasnamə 5.5 səlahiyyət ayrılığı).

Mövcud tenantlarda iki rola verilir (`default_roles_university.py` ilə eyni):

    ikt_rehber (RİM)  — cutover operatoru, org-wide
    hr                — qəbul/kadr siyahısının yüklənməsi

`*` daşıyan rollar (rektor/prorektor/sahib) onsuz da əhatə olunur. Digər rola
lazım olsa açar permission-editordan verilir (audit izi ilə).

İdempotentdir. Geri dönüş: açar bütün rollardan çıxarılır.
"""

from django.db import migrations

_PERMISSION = "user.import"

#: Açarın verildiyi default rol adları (kod adı — display_name RİM üçün fərqlidir).
_TARGET_ROLES = ("ikt_rehber", "hr")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_TARGET_ROLES).iterator():
        permissions = list(role.permissions or [])
        if "*" in permissions or _PERMISSION in permissions:
            continue
        permissions.append(_PERMISSION)
        role.permissions = permissions
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = [perm for perm in (role.permissions or []) if perm != _PERMISSION]
        if len(permissions) != len(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0033_schedule_manage_permission")]

    operations = [migrations.RunPython(forward, backward)]
