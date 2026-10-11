"""Hüseynqulu Bağırov: «Müəllim» üzvlüyü → «Rektor»; əsas rol «Qəyyumlar Şurasının sədri» (sahib 2026-10-11).

Sahib: «Hüseyn müəllimə Rektor olaraq da yaz, müəllim kimi yox». 0059 onun qəyyum üzvlüyünü `board_chair`-ə
keçirmişdi; Forma 7 tutuşdurması isə ona kafedra «Müəllim» üzvlüyü vermişdi və o, «Əsas rol: Müəllim (60)»
görünürdü.

* ``huseynqulu.bagirov``-un həmin təşkilatdakı AKTİV ``teacher`` üzvlükləri ``rector`` olur, ``scope_unit``
  boşalır (rektor təşkilat səviyyəli roldur); ``is_primary`` YALNIZ ``board_chair`` üzvlüyündə qalır;
  ``UserProfile.role`` — ``org_admin`` (``map_org_role_to_profile_role(board_chair/rector)`` ilə eyni).
* İstifadəçi / üzvlük yoxdursa heç nə edilmir (test və klon bazaları). İdempotent.

Geri dönüş: köhnə müəllim üzvlüyünün kafedrası ``Membership.title``-a yazılmır — ona görə geri dönüş həmin
sətirləri `teacher`-ə qaytarır, amma kafedranı bərpa ETMİR (audit jurnalında köhnə dəyər var).
"""

from django.db import migrations

_USERNAME = "huseynqulu.bagirov"


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Membership = apps.get_model("organizations", "Membership")
    UserProfile = apps.get_model("accounts", "UserProfile")

    for chair in Membership.objects.filter(
        user__username=_USERNAME, is_active=True, role__name="board_chair"
    ).select_related("role"):
        organization_id = chair.organization_id
        rector = Role.objects.filter(organization_id=organization_id, name="rector").first()
        if rector is None:
            continue
        Membership.objects.filter(
            user_id=chair.user_id, organization_id=organization_id, is_active=True, role__name="teacher"
        ).update(role=rector, scope_unit=None, is_primary=False)
        Membership.objects.filter(user_id=chair.user_id, organization_id=organization_id, is_active=True).exclude(
            pk=chair.pk
        ).update(is_primary=False)
        if not chair.is_primary:
            Membership.objects.filter(pk=chair.pk).update(is_primary=True)
        UserProfile.objects.filter(user_id=chair.user_id).exclude(role="org_admin").update(role="org_admin")


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Membership = apps.get_model("organizations", "Membership")
    for membership in Membership.objects.filter(user__username=_USERNAME, is_active=True, role__name="rector"):
        teacher = Role.objects.filter(organization_id=membership.organization_id, name="teacher").first()
        if teacher is not None:
            Membership.objects.filter(pk=membership.pk).update(role=teacher)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0059_board_chair_role"),
        ("accounts", "0030_capacity_drop_unused_indexes"),
    ]

    operations = [migrations.RunPython(forward, backward)]
