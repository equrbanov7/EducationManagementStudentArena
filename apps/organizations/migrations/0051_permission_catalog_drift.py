"""İcazə kataloqu drift-i — audit 2026-09-13 `access` F-06 / hesabat §27 (2026-09-14).

Reyestrdə olub kodda HEÇ YERDƏ yoxlanmayan 13 açar iki yolla həll edildi
(bax ``apps/organizations/permissions.py`` başlığı):

1. **Kataloqdan ÇIXARILANLAR** (funksiya yoxdur): `org.delete`, `role.create`,
   `role.delete`, `grade.override`, `qa.view`, `qa.review`, `qa.flag` və `qa.*`
   wildcard-ı. Saxlanılan ``Role.permissions`` sətirlərindən bu açarlar (legacy
   prefiks yazılışları və `grant:` delegasiya formaları daxil) SİLİNİR — əks halda
   ``validate_permissions`` həmin rolları etibarsız sayar və icazə redaktoru
   mövcud olmayan açarı göstərməyə davam edərdi.
2. **Qapıya BAĞLANANLAR** — davranış dəyişməsin deyə mövcud rollara açar ƏKİLİR:
   * `audit.export` → CSV ixracı indi bu açarla qapılanır. Bu günə qədər ixrac
     «jurnalı görən hər kəs»ə açıq idi (`audit.view`), ona görə `audit.view`
     daşıyan HƏR rola cütü verilir; tenant sonra redaktordan geri ala bilər.
   * `org.settings` + `org.edit` → təşkilat ayarları səhifəsi. Köhnə qapı yalnız
     `level >= 90` idi; həmin səviyyəli (wildcard-sız) rollara hər iki açar əkilir
     ki, heç kim kilidlənməsin (şablonlar: `vice_rector`, `ikt_rehber`,
     `deputy_director`; tenantın öz ≥90 rolları da eyni qaydaya düşür).

`*` (wildcard) daşıyan rol toxunulmur; mövcud açar təkrarlanmır; `level` /
`scope_type` dəyişmir. Geri dönüş yalnız `audit.export` və ≥90 rollardan
`org.settings`-i çıxarır (`org.edit` şablonlarda əvvəldən var idi — toxunulmur);
silinən açarlar geri qaytarılmır (kataloqda artıq yoxdur).
"""

from django.db import migrations

_WILDCARD = "*"
_GRANT = "grant:"

#: Kataloqdan çıxarılan açarlar — kanonik + legacy prefiks yazılışları.
_REMOVED_KEYS = frozenset(
    {
        "org.delete",
        "role.create",
        "role.delete",
        "roles.create",
        "roles.delete",
        "grade.override",
        "grading.override",
        "qa.view",
        "qa.review",
        "qa.flag",
        "qa.*",
    }
)

#: Ayarlar səhifəsinin köhnə səviyyə qapısı (bax `organization_settings`).
_SETTINGS_MIN_LEVEL = 90
_SETTINGS_KEYS = ("org.settings", "org.edit")


def _is_removed(entry: str) -> bool:
    key = entry[len(_GRANT) :].strip() if entry.startswith(_GRANT) else entry
    return key in _REMOVED_KEYS


def _has(permissions, key: str) -> bool:
    prefix_wildcard = "%s.*" % key.split(".", 1)[0]
    return key in permissions or prefix_wildcard in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        current = list(role.permissions or [])
        permissions = [entry for entry in current if not _is_removed(entry)]
        if _WILDCARD not in permissions:
            if "audit.view" in permissions and not _has(permissions, "audit.export"):
                permissions.append("audit.export")
            if (role.level or 0) >= _SETTINGS_MIN_LEVEL:
                for key in _SETTINGS_KEYS:
                    if not _has(permissions, key):
                        permissions.append(key)
        if permissions != current:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        current = list(role.permissions or [])
        if _WILDCARD in current:
            continue
        kept = [entry for entry in current if entry != "audit.export"]
        if (role.level or 0) >= _SETTINGS_MIN_LEVEL:
            kept = [entry for entry in kept if entry != "org.settings"]
        if kept != current:
            role.permissions = kept
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0050_tutor_coordinator_parity")]

    operations = [migrations.RunPython(forward, backward)]
