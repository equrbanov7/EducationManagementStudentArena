"""Mövcud rollara RİM hesab-idarəetmə (`user.*`) icazələrini geriyə-doldur.

Yeni təşkilatlar bunu `default_roles.py` → post_save signal-ı ilə alır; bu
migration isə ARTIQ mövcud olan təşkilatların rollarına həmin icazələri əlavə
edir. Əks halda cutover-da köhnə tenantlarda RİM mərkəzi boş görünərdi.

Qayda (bax `apps/organizations/permissions.py` «users» kateqoriyası):

* rektor/direktor/menecer/owner — onsuz da `"*"` daşıyır, toxunulmur;
* prorektor / direktor müavini / İKT Rəhbəri → `user.*` (tam RİM);
* HR → yalnız `user.search` + `user.edit` (parol/blok/silmə QƏSDƏN yox).

İdempotentdir: icazə artıq varsa təkrar əlavə olunmur.
"""

from django.db import migrations

# Rol adı → əlavə olunacaq icazələr.
#: RİM-in GÜNDƏLİK hesab əməliyyatları. `user.grant_privileged` QƏSDƏN
#: DAXİL DEYİL və `user.*` wildcard-ı da işlədilmir — əsasnamənin 5.5 bəndi
#: («yeni administrator səlahiyyəti bir nəfərin nəzarətsiz qərarı ilə
#: verilməməlidir») tələb edir ki, admin yaratmaq hüququ AYRICA verilsin.
_OPERATIONAL_USER_PERMISSIONS = [
    "user.search",
    "user.credentials",
    "user.block",
    "user.soft_delete",
    "user.edit",
]

_ROLE_GRANTS = {
    "vice_rector": list(_OPERATIONAL_USER_PERMISSIONS),
    "deputy_director": list(_OPERATIONAL_USER_PERMISSIONS),
    # RİM rəhbəri: hesab idarəetməsi + rol/səlahiyyət idarəetməsi (əsasnamə 4.2).
    "ikt_rehber": [*_OPERATIONAL_USER_PERMISSIONS, "role.*"],
    "hr": ["user.search", "user.edit"],
}

#: «İKT Rəhbəri» → «Rəqəmsal İnkişaf Mərkəzi (RİM) rəhbəri» adlandırması.
#: Slug (`name`) DƏYİŞMİR — yalnız görünən ad. Yalnız hazırkı dəyəri KÖHNƏ
#: etiketə bərabər olan sətirlər yenilənir: tenant rolu əl ilə adlandırıbsa
#: üzərinə yazmırıq.
_IKT_OLD_DISPLAY_NAMES = ("İKT Rəhbəri", "ICT Manager")
_IKT_NEW_DISPLAY_NAME = "Rəqəmsal İnkişaf Mərkəzi (RİM) rəhbəri"

_ALL_USER_PERMISSIONS = {
    "user.*",
    "user.search",
    "user.credentials",
    "user.block",
    "user.soft_delete",
    "user.edit",
    "user.grant_privileged",
}


def grant_user_permissions(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")

    for role_name, extra_permissions in _ROLE_GRANTS.items():
        for role in Role.objects.filter(name=role_name):
            permissions = list(role.permissions or [])
            # Tam icazəli rol (`*`) onsuz da hər şeyi daşıyır.
            if "*" in permissions:
                continue
            changed = False
            for permission in extra_permissions:
                if permission not in permissions:
                    permissions.append(permission)
                    changed = True
            if changed:
                role.permissions = permissions
                role.save(update_fields=["permissions"])


def rename_ikt_rehber_display(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(
        name="ikt_rehber",
        display_name__in=_IKT_OLD_DISPLAY_NAMES,
    ).update(display_name=_IKT_NEW_DISPLAY_NAME)


def restore_ikt_rehber_display(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(
        name="ikt_rehber",
        display_name=_IKT_NEW_DISPLAY_NAME,
    ).update(display_name="İKT Rəhbəri")


def revoke_user_permissions(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")

    for role_name in _ROLE_GRANTS:
        for role in Role.objects.filter(name=role_name):
            permissions = list(role.permissions or [])
            remaining = [perm for perm in permissions if perm not in _ALL_USER_PERMISSIONS]
            if len(remaining) != len(permissions):
                role.permissions = remaining
                role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    # ⚠️ MERGE QEYDİ (paralel iş dilimi)
    # ------------------------------------------------------------------
    # Bu worktree 0026-da dayanır, amma əsas ağacda paralel olaraq 0027
    # (`seed_grade_approval_permissions`) və 0028 (`seed_group_permissions`)
    # hazırlanır. Fayl adı ONLARLA TOQQUŞMASIN deyə 0029 seçilib, lakin
    # asılılıq hələ 0026-dır — yəni birləşmədən sonra `organizations`-da İKİ
    # yarpaq qalacaq və Django «Conflicting migrations detected» verəcək.
    #
    # DÜZƏLİŞ (bir sətir, birləşmə zamanı):
    #     ("organizations", "0028_seed_group_permissions")
    #   → ("organizations", "0028_seed_group_permissions")
    #
    # Miqrasiya idempotentdir (icazə artıq varsa təkrar əlavə olunmur), ona görə
    # sıranın dəyişməsi nəticəyə təsir etmir.
    dependencies = [
        ("organizations", "0028_seed_group_permissions"),
    ]

    operations = [
        migrations.RunPython(grant_user_permissions, revoke_user_permissions),
        migrations.RunPython(rename_ikt_rehber_display, restore_ikt_rehber_display),
    ]
