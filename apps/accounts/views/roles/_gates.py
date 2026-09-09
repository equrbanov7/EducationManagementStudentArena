"""«Rolları idarə et» səthinin icazə qapıları — TƏK yerdə.

Köhnə (checkbox / profil enum-u) və yeni (təşkilat rolu ver/geri al) axınlar
EYNİ qapılardan keçməlidir, əks halda birində bağlanan yol digərində açıq
qalır. Qapılar `manage.py`-dən bura köçürüldü; davranış dəyişməyib.
"""

from django.utils.translation import pgettext_lazy

from apps.organizations.models import Membership

from ...models import ProfileRole

#: Təşkilat-səviyyəli heyət rolları — vahid-əhatəli aktor (dekan, kafedra
#: müdiri) verə bilməz.
ORG_WIDE_STAFF_ROLES = frozenset(
    {
        ProfileRole.HR,
        # `EXAM_CENTER` QƏSDƏN yoxdur: rol `exam_center_head`-ə birləşdirildi
        # (miqrasiya 0046) və artıq təyin üçün TƏKLİF OLUNMUR.
        ProfileRole.EXAM_CENTER_HEAD,
        ProfileRole.EXAM_CENTER_STAFF,
        ProfileRole.IKT_REHBER,
        ProfileRole.ORG_ADMIN,
        ProfileRole.ORG_OWNER,
        ProfileRole.SUPERADMIN,
    }
)


def assign_scope(user, organization):
    from apps.organizations.public import get_permission_scope

    scope = get_permission_scope(user, organization, "role.assign")
    if not scope.has_structure_access:
        scope = get_permission_scope(user, organization, "org.manage_members")
    return scope


def actor_is_unit_scoped(user, organization) -> bool:
    return assign_scope(user, organization).is_unit_scoped


def target_in_unit_scope(organization, scope, target_user) -> bool:
    """Hədəf aktorun alt-ağacındadır? — vahidli üzvlük və ya akademik qeydin qrupu ilə."""
    from apps.organizations.models import OrgUnit

    subtree = OrgUnit.objects.filter(scope.unit_subtree_q()).filter(organization=organization).values("pk")
    if Membership.objects.filter(
        user=target_user, organization=organization, is_active=True, scope_unit__in=subtree
    ).exists():
        return True
    from apps.registrar.models import StudentAcademicRecord

    return StudentAcademicRecord.objects.filter(
        organization=organization, student=target_user, group__in=subtree
    ).exists()


def manage_roles_gate_error(request, organization, target_user, *, is_superadmin):
    """`None` = icazə var; əks halda istifadəçiyə göstəriləcək mesaj."""
    if is_superadmin or getattr(organization, "owner_id", None) == request.user.id:
        return None
    from core.permissions import has_permission

    from .._helpers.rbac import _collect_actor_permissions

    actor_permissions, _ = _collect_actor_permissions(request.user, organization)
    permission_list = list(actor_permissions)
    if not (has_permission(permission_list, "role.assign") or has_permission(permission_list, "org.manage_members")):
        return pgettext_lazy("accounts.manage_roles.message", "missing_member_management_permission")
    scope = assign_scope(request.user, organization)
    if scope.is_org_wide:
        return None
    if not scope.is_unit_scoped or not target_in_unit_scope(organization, scope, target_user):
        return pgettext_lazy("accounts.manage_roles.message", "target_outside_structure_scope")
    return None
