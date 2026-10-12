"""Rol auditi 2026-10-13 B14 — «Bildiriş göndər» üçün ``notification.publish`` açarı mövcud tenantlara.

Əvvəl ``publish-notification`` bölməsi rol BAYRAQLARI ilə açılırdı (``accounts/views/_helpers/rbac.py``):
org_admin aliası (səviyyə ≥ 80 və ya rektor/dekan/müdir kimi ekvivalent adlar — imtahan mərkəzi / HR / Tədris
şöbəsi rəhbəri istisna), müəllim aliası, imtahan mərkəzi aliası (RİM əməkdaşı daxil) və HR. İndi bölmə yalnız
açarla açılır, ona görə bu gün bölməni görən HƏR rol açarı alır — görünüş dəyişmir, indi redaktordan idarə olunur.

Seçim QAYDASI bayraq məntiqinin rol-sətri ekvivalentidir (``core.roles.ProfileRole`` alias cədvəli bura KÖÇÜRÜLÜB
— miqrasiya sonradan dəyişən modula söykənməsin):

* ad ``_ROLE_NAMES``-dədir (şablon rolları + alias adları), və ya
* səviyyə ≥ 80 və ad alias-istisna siyahısında deyil (org_admin aliası belə rollara səviyyədən gəlir).

Açar, ``notification.*`` və ya ``*`` artıq varsa TOXUNULMUR → idempotent (0058 / 0061 naxışı). Geri dönüş açarı
eyni qaydaya düşən rollardan götürür (əvvəldən olub-olmadığı bilinmir — 0058 / 0061 ilə eyni qəbul).
"""

from django.db import migrations

_KEY = "notification.publish"

#: Bu gün bölməni rol ADI ilə görən rollar (universitet + məktəb + kurs mərkəzi şablonları və alias adları).
_ROLE_NAMES = frozenset(
    {
        # org_admin aliası (ADMIN_EQUIVALENT_ROLE_NAMES + normallaşdırma: chair_head/section_head → department_head,
        # deputy_director → vice_director).
        "org_admin",
        "org_owner",
        "rector",
        "vice_rector",
        "dean",
        "vice_dean",
        "department_head",
        "chair_head",
        "section_head",
        "director",
        "vice_director",
        "deputy_director",
        "manager",
        "senior_instructor",
        "branch_manager",
        # müəllim aliası (TEACHER / ASSISTANT_TEACHER).
        "teacher",
        "instructor",
        "professor",
        "associate_professor",
        "assistant_teacher",
        "assistant",
        "lab_assistant",
        # imtahan mərkəzi aliası (RİM əməkdaşı → exam_center_staff, İKT rəhbəri → exam_center_head).
        "exam_center",
        "exam_center_head",
        "exam_center_staff",
        "rim_staff",
        "ikt_rehber",
        # HR.
        "hr",
    }
)
#: Yüksək səviyyəyə baxmayaraq org_admin aliası ALMAYAN rollar (``ADMIN_ALIAS_EXEMPT_ROLE_NAMES``).
_ALIAS_EXEMPT = frozenset({"exam_center", "exam_center_head", "exam_center_staff", "hr", "teaching_office_head"})
_ORG_ADMIN_LEVEL = 80


def _eligible(role) -> bool:
    name = (role.name or "").strip().lower()
    if name in _ROLE_NAMES:
        return True
    return (role.level or 0) >= _ORG_ADMIN_LEVEL and name not in _ALIAS_EXEMPT


def _covered(permissions) -> bool:
    return _KEY in permissions or "notification.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        if not _eligible(role) or _covered(permissions):
            continue
        permissions.append(_KEY)
        role.permissions = permissions
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        before = list(role.permissions or [])
        if not _eligible(role) or _KEY not in before:
            continue
        role.permissions = [key for key in before if key != _KEY]
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0061_role_audit_2026_10_13")]

    operations = [migrations.RunPython(forward, backward)]
