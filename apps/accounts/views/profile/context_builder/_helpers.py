"""build_profile_response — kiçik köməkçilər."""

from django.utils.translation import gettext as _

from core.tenancy import restore_request_organization_from_profile

from ....models import ProfileRole
from ..._helpers import PROFILE_ROLE_LABELS
from ..constants import PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK, PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT


def _build_effective_user_roles(user, profile):
    role_names = []

    if getattr(user, "is_superuser", False):
        role_names.append(ProfileRole.SUPERADMIN)

    if hasattr(user, "get_all_roles"):
        for role_name in user.get_all_roles():
            normalized_role_name = ProfileRole.normalize_membership_role_name(role_name)
            if normalized_role_name in PROFILE_ROLE_LABELS and normalized_role_name not in role_names:
                role_names.append(normalized_role_name)

    fallback_role_name = ProfileRole.normalize_membership_role_name(getattr(profile, "role", ""))
    if fallback_role_name in PROFILE_ROLE_LABELS and fallback_role_name not in role_names:
        role_names.append(fallback_role_name)

    role_names.sort(key=lambda role_name: (ProfileRole.LEVELS.get(role_name, 0), role_name), reverse=True)
    return [
        {
            "name": role_name,
            "label": PROFILE_ROLE_LABELS.get(role_name, role_name.replace("_", " ").title()),
        }
        for role_name in role_names
    ]


def _restore_profile_org_context(request, profile, active_section):
    """
    Re-hydrate the active organization for org-bound profile sections when the
    session lost its tenant selection but the profile still points at a valid org.
    """
    if active_section not in PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT:
        return
    restore_request_organization_from_profile(
        request,
        profile=profile,
        allow_multi_org_restore=active_section in PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK,
    )


def _get_publish_notification_targets(user, capabilities):
    """Return list of target options for notification publishing based on role."""
    from apps.exams.models import StudentGroup
    from apps.organizations.models import Membership

    targets = []
    is_superadmin = capabilities["is_superadmin"]
    is_org_admin = capabilities["is_org_admin"]
    is_teacher = capabilities["is_teacher"]

    if is_superadmin:
        # "All users" is exclusive — if selected, ignore specific org selections
        targets.append(
            {
                "value": "all",
                "label": _("target_all_users"),
                "is_exclusive": True,
            }
        )
        from apps.organizations.models import Organization

        # QEYD: tərcümə çağırışları f-string İÇİNDƏ OLMAMALIDIR — xgettext
        # (makemessages) onları görmür və tərcümələri obsolete edir.
        org_prefix_label = _("target_org_prefix")
        for org in Organization.objects.filter(is_active=True, status="active").order_by("name"):
            targets.append(
                {
                    "value": f"org_{org.pk}",
                    "label": f"{org_prefix_label}: {org.name}",
                    "is_exclusive": False,
                }
            )
        return targets

    # Non-superadmin targets are cumulative: a user can be both an organization
    # admin (e.g. an owner) and a teacher, in which case they should be able to
    # target the whole organization as well as their own student groups.
    if is_org_admin:
        # Get user's active org memberships
        org_memberships = (
            Membership.objects.filter(user=user, is_active=True, organization__is_active=True)
            .select_related("organization")
            .order_by("organization__name", "organization_id", "-role__level", "id")
        )
        seen_org_ids = set()
        org_prefix_label = _("target_org_prefix")
        all_members_label = _("target_org_all_members")
        for membership in org_memberships:
            if membership.organization_id in seen_org_ids:
                continue
            seen_org_ids.add(membership.organization_id)
            targets.append(
                {
                    "value": f"org_{membership.organization_id}",
                    "label": f"{org_prefix_label}: {membership.organization.name} ({all_members_label})",
                    "is_exclusive": False,
                }
            )

    if is_teacher:
        teacher_groups = StudentGroup.objects.filter(teacher=user).order_by("name")
        group_prefix_label = _("target_group_prefix")
        for group in teacher_groups:
            targets.append(
                {
                    "value": f"group_{group.pk}",
                    "label": f"{group_prefix_label}: {group.name}",
                    "is_exclusive": False,
                }
            )
    return targets


#: Çipin `title` tooltip-ində göstərilən qrup adlarının tavanı — bir fənn 40+
#: qrupa oxuna bilər, tooltip-i sonsuz uzatmağın mənası yoxdur.
TEACHER_SUBJECT_TOOLTIP_GROUPS = 12


def build_teacher_subject_rows(user, organization):
    """«Tədris etdiyi fənlər» — FƏNN üzrə TƏKRARSIZ siyahı.

    PROBLEM (2026-08 sahib bildirişi: «eyni fənlər təkrarda düşüb»): siyahı
    ``CourseOffering`` sətirlərindən qurulurdu və dedup açarı
    ``(subject_id, group_id)`` idi. Bir fənn neçə qrupa/semestrə oxunursa, o
    qədər çip çıxırdı — istifadəçi üçün bu, eyni fənnin təkrar düşməsidir.

    ÖLÇÜ (rehearsal bazası; 8 515 instruktorlu offering, 543 müəllim×org):
      * köhnə açarla render olunan çip:  8 341
      * fənn (subject_id) üzrə təkrarsız: 4 082  → 4 259 ARTIQ çip (51%)
      * müəllimlərin 383/543-ü (70%) təsirlənirdi
      * ən pis hal: 152 çip → cəmi 5 fənn

    HƏLL: qruplaşdırma açarı ``subject_id``-dir. AD üzrə birləşdirmək qəsdən
    SEÇİLMƏYİB — ölçü göstərdi ki, eyni adı fərqli ``subject_id`` ilə daşıyan
    yalnız 2 müəllim×org var (4 082 → 4 080): qazanc yox dərəcədə azdır, risk
    isə real (fərqli kataloq fənlərini birləşdirmək).

    MƏLUMAT İTMİR: qrup/semestr sayı çipin özündə, qrup adları isə ``title``
    tooltip-ində qalır; tək qrup halında ad olduğu kimi göstərilir.

    Əlavə fayda: ``values_list`` ilə yalnız lazım olan sütunlar çəkilir —
    əvvəlki ``select_related`` ilə tam ORM obyektləri (ən pis halda 160 ədəd)
    yüklənirdi.
    """
    rows = {}
    offerings = user.taught_offerings.filter(organization=organization).values_list(
        "subject_id", "subject__name", "subject__code", "group_id", "group__name", "period_id"
    )
    for subject_id, subject_name, subject_code, group_id, group_name, period_id in offerings:
        row = rows.get(subject_id)
        if row is None:
            row = rows[subject_id] = {
                "name": (subject_name or subject_code or "").strip(),
                "code": (subject_code or "").strip(),
                "groups": {},
                "periods": set(),
            }
        if group_id is not None and group_id not in row["groups"]:
            row["groups"][group_id] = (group_name or "").strip()
        if period_id is not None:
            row["periods"].add(period_id)

    result = []
    for row in sorted(rows.values(), key=lambda r: (r["name"].casefold(), r["code"])):
        group_names = sorted(name for name in row["groups"].values() if name)
        tooltip = ", ".join(group_names[:TEACHER_SUBJECT_TOOLTIP_GROUPS])
        if len(group_names) > TEACHER_SUBJECT_TOOLTIP_GROUPS:
            tooltip = f"{tooltip}…"
        result.append(
            {
                "name": row["name"],
                "code": row["code"],
                "group_count": len(row["groups"]),
                "period_count": len(row["periods"]),
                # Tək qrupda köhnə görünüş qorunur: «Fənn · QRUP-101».
                "single_group_name": group_names[0] if len(group_names) == 1 else "",
                "groups_tooltip": tooltip,
            }
        )
    return result
