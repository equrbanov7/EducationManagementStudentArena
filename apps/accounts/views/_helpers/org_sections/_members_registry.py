"""«Heyət idarəetməsi» — üzv reyestrinin sorğuları və cədvəl sətirləri.

Sahib tapşırığı (2026-09-09): ekran YENİDƏN QURULDU və dəvət/müraciət səthləri
buradan TAM ÇIXARILDI — «təsdiq gözləyən tələbələr», «təşkilata bağlı olmayan
tələbə/müəllim/heyət», «göndərilmiş dəvətlər», «müəllim/heyət müraciətləri».
Səbəb: bu tenantda heç kim dəvətlə gəlmir, şəxsi HƏMİŞƏ təşkilat özü əlavə edir
(«Tələbə əlavəsi» / «Müəllim əlavəsi» intake bölmələri). `StudentOrganizationRequest`
MODELİ və POST əməlləri TOXUNULMAYIB — tələbənin öz «Təşkilata qoşul» axını və
bildiriş zənciri əvvəlki kimi işləyir; sadəcə bu ekranda göstərilmir.

SORĞU BÜDCƏSİ səhifə ölçüsündən ASILI DEYİL (sabit ~6 sorğu):

1. aktiv vahidlər (id · ad · tip · valideyn · rəhbər) — TƏK sorğu;
2. təşkilatın bütün aktiv üzvlükləri (user_id · rol · səviyyə · bölmə) — TƏK
   sorğu; KPI-lər, rol/bölmə filtri və uyğun şəxs dəsti buradan Python-da çıxır;
3. üzvlüyü olmayan, amma profili təşkilata bağlı şəxslər — TƏK sorğu;
4–5. səhifə (`Paginator`: count + slice) — axtarış/sıralama SQL-dədir;
6. YALNIZ səhifədəki şəxslərin üzvlükləri (`select_related`) — TƏK sorğu.

RLS: `Membership` PostgreSQL-də RLS ilə qorunur. Sorğular `bypass_rls()` bloku
İÇİNDƏ TAM İCRA olunur (sətirlər `list()` ilə materiallaşdırılır) — tənbəl
queryset şablonda, blokdan kənarda icra olunsaydı boş nəticə qayıdardı.
"""

import json
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership, OrgUnit
from core.rls import bypass_rls
from core.staff_position import visible_role_label

from ....models import ProfileRole, UserProfile
from ..constants import PROFILE_ROLE_LABELS
from ._members_ui import (
    DEFAULT_SORT,
    KIND_LEADERS,
    KIND_STAFF,
    KIND_STUDENTS,
    KIND_TEACHERS,
    KINDS,
    PREFIX,
    SORTS,
    kind_label,
)

User = get_user_model()

PAGE_SIZE = 25
#: Sətirdə göstərilən rol nişanı sayı (qalanı «+N» çipidir).
ROLE_PREVIEW = 2
#: Bu səviyyədən yuxarı hər rol rəhbər heyət sayılır (org_admin həddi).
LEADERSHIP_MIN_LEVEL = 80

STUDENT_ROLE_NAMES = frozenset({"student", "lead_student"})
TEACHER_ROLE_NAMES = frozenset(
    {"teacher", "assistant_teacher", "assistant", "lab_assistant", "instructor", "professor", "associate_professor"}
)
LEADERSHIP_ROLE_NAMES = frozenset(
    {
        "rector",
        "vice_rector",
        "dean",
        "vice_dean",
        "chair_head",
        "department_head",
        "section_head",
        "program_coordinator",
        "teaching_office_head",
        "exam_center_head",
        "ikt_rehber",
        "director",
        "deputy_director",
        "vice_director",
        "admin_unit_head",
        "org_admin",
        "owner",
        "manager",
        "branch_manager",
    }
)

#: Bu ekrandan uzaqlaşdırıla bilən profil rolları (köhnə davranışla eynidir).
REMOVABLE_PROFILE_ROLES = frozenset(
    {
        ProfileRole.STUDENT,
        ProfileRole.LEAD_STUDENT,
        ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER,
        ProfileRole.MEMBER,
        ProfileRole.HR,
    }
)

_STUDENT_PROFILE_ROLES = frozenset({ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})
_TEACHER_PROFILE_ROLES = frozenset({ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER})


# ─── Kiçik köməkçilər ───────────────────────────────────────────────────────


def _display_name(user) -> str:
    return user.get_full_name() or user.username


def _initials(name: str) -> str:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _format_date(value) -> str:
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d.%m.%Y")


def _kind_for_role_name(role_name: str, level: int) -> str:
    if role_name in STUDENT_ROLE_NAMES:
        return KIND_STUDENTS
    if role_name in TEACHER_ROLE_NAMES:
        return KIND_TEACHERS
    return KIND_STAFF


def _kind_for_profile_role(profile_role: str) -> str:
    if profile_role in _STUDENT_PROFILE_ROLES:
        return KIND_STUDENTS
    if profile_role in _TEACHER_PROFILE_ROLES:
        return KIND_TEACHERS
    return KIND_STAFF


def _profile_role_for_role_name(role_name: str, level: int) -> str:
    """`core.roles.map_org_role_to_profile_role` ilə eyni qayda — ad üzərindən."""
    if role_name == "lead_student":
        return ProfileRole.LEAD_STUDENT
    if role_name == "student":
        return ProfileRole.STUDENT
    if role_name == ProfileRole.HR:
        return ProfileRole.HR
    if role_name in {"assistant_teacher", "assistant", "lab_assistant"}:
        return ProfileRole.ASSISTANT_TEACHER
    if role_name in {"teacher", "instructor", "professor", "associate_professor"}:
        return ProfileRole.TEACHER
    if int(level or 0) >= LEADERSHIP_MIN_LEVEL:
        return ProfileRole.ORG_ADMIN
    return ProfileRole.MEMBER


def _is_leader_role(role_name: str, level: int) -> bool:
    return role_name in LEADERSHIP_ROLE_NAMES or int(level or 0) >= LEADERSHIP_MIN_LEVEL


def _role_text(role_name: str, display_name: str = "") -> str:
    """Rol etiketi — «Üzv» doldurucusu YAZILMIR (bax `core.staff_position`)."""
    mapped = _profile_role_for_role_name(role_name, 0)
    return visible_role_label(role_name, display_name or PROFILE_ROLE_LABELS.get(mapped, ""))


# ─── Vahid xəritəsi (TƏK sorğu) ─────────────────────────────────────────────


class _UnitIndex:
    """Aktiv vahidlərin ad/tip/valideyn/rəhbər xəritəsi — bölmə zənciri üçün."""

    def __init__(self, organization):
        self.units = {}
        self.head_user_ids = set()
        self.children = defaultdict(list)
        rows = (
            OrgUnit.objects.filter(organization=organization, is_active=True)
            .order_by()
            .values_list("id", "name", "unit_type", "parent_id", "head_id")
        )
        for unit_id, name, unit_type, parent_id, head_id in rows:
            self.units[unit_id] = (name, unit_type, parent_id)
            self.children[parent_id].append(unit_id)
            if head_id:
                self.head_user_ids.add(head_id)

    def name_of(self, unit_id) -> str:
        row = self.units.get(unit_id)
        return row[0] if row else ""

    def chain(self, unit_id, limit: int = 3) -> str:
        """«Kafedra › Fakültə» zənciri — yaxından uzağa."""
        row = self.units.get(unit_id)
        if row is None:
            return ""
        names, seen, current = [row[0]], set(), row
        while current is not None and current[2] is not None and len(names) <= limit:
            parent_id = current[2]
            if parent_id in seen:
                break
            seen.add(parent_id)
            current = self.units.get(parent_id)
            if current is None:
                break
            names.append(current[0])
        return " › ".join(names)

    def subtree_ids(self, unit_id) -> set:
        """Vahid + bütün alt vahidləri (filtr üçün)."""
        out, stack = set(), [unit_id]
        while stack:
            current = stack.pop()
            if current in out:
                continue
            out.add(current)
            stack.extend(self.children.get(current, ()))
        return out

    def options(self):
        """Fakültə/kafedra seçiciləri — ad sırası ilə (axtarışlı select)."""
        rows = sorted(
            ((unit_id, data[0]) for unit_id, data in self.units.items()),
            key=lambda item: item[1].lower(),
        )
        return [{"value": str(unit_id), "label": name} for unit_id, name in rows]


# ─── Üzvlük yığımı ──────────────────────────────────────────────────────────


class _MemberIndex:
    """Təşkilatın bütün üzvlərinin yaddaş xəritəsi (KPI + filtr üçün).

    ``by_user[user_id] = {"roles": [(name, level, unit_id)], "top_level": int,
    "kind": str, "is_leader": bool, "profile_role": str}``
    """

    def __init__(self, *, organization, scoped_unit_ids, superadmin_user_ids, unit_index):
        self.by_user = {}
        membership_rows = Membership.objects.filter(
            organization=organization, is_active=True, user__is_active=True
        ).exclude(user_id__in=superadmin_user_ids)
        if scoped_unit_ids is not None:
            membership_rows = membership_rows.filter(scope_unit_id__in=scoped_unit_ids)
        for user_id, role_name, role_level, unit_id in membership_rows.order_by().values_list(
            "user_id", "role__name", "role__level", "scope_unit_id"
        ):
            role_name = (role_name or "").strip().lower()
            level = int(role_level or 0)
            entry = self.by_user.setdefault(
                user_id,
                {
                    "roles": [],
                    "top_level": -1,
                    "kind": KIND_STAFF,
                    "is_leader": False,
                    "profile_role": ProfileRole.MEMBER,
                },
            )
            entry["roles"].append((role_name, level, unit_id))
            entry["is_leader"] = entry["is_leader"] or _is_leader_role(role_name, level)
            if level > entry["top_level"]:
                entry["top_level"] = level
                entry["kind"] = _kind_for_role_name(role_name, level)
                entry["profile_role"] = _profile_role_for_role_name(role_name, level)

        # Üzvlüyü olmayan, amma profili təşkilata bağlı şəxslər (köhnə axınlardan
        # qalan hesablar) da üzv sayılır — əks halda «tələbə» sayğacı azalırdı.
        if scoped_unit_ids is None:
            profile_rows = (
                UserProfile.objects.filter(organization=organization, user__is_active=True)
                .exclude(user_id__in=superadmin_user_ids)
                .order_by()
                .values_list("user_id", "role")
            )
            for user_id, profile_role in profile_rows:
                if user_id in self.by_user:
                    continue
                self.by_user[user_id] = {
                    "roles": [],
                    "top_level": ProfileRole.LEVELS.get(profile_role, 0),
                    "kind": _kind_for_profile_role(profile_role),
                    "is_leader": False,
                    "profile_role": profile_role,
                }

        for user_id, entry in self.by_user.items():
            entry["is_leader"] = entry["is_leader"] or user_id in unit_index.head_user_ids

    def totals(self) -> dict:
        counts = {"members": len(self.by_user), KIND_STUDENTS: 0, KIND_TEACHERS: 0, KIND_STAFF: 0, KIND_LEADERS: 0}
        for entry in self.by_user.values():
            counts[entry["kind"]] += 1
            if entry["is_leader"]:
                counts[KIND_LEADERS] += 1
        return {
            "members": counts["members"],
            "students": counts[KIND_STUDENTS],
            "teachers": counts[KIND_TEACHERS],
            "staff": counts[KIND_STAFF],
            "leaders": counts[KIND_LEADERS],
        }

    def role_options(self, role_labels) -> list:
        """Reyestrdə RAST GƏLİNƏN rollar + fərqli şəxs sayı."""
        seen = defaultdict(set)
        for user_id, entry in self.by_user.items():
            for role_name, _level, _unit_id in entry["roles"]:
                seen[role_name].add(user_id)
        options = []
        for role_name, users in seen.items():
            label = role_labels.get(role_name) or _role_text(role_name)
            if not label:
                continue
            options.append({"value": role_name, "label": f"{label} ({len(users)})", "_sort": label.lower()})
        options.sort(key=lambda item: item["_sort"])
        return [{"value": item["value"], "label": item["label"]} for item in options]

    def matching_user_ids(self, *, kind, role, unit_ids) -> list:
        out = []
        for user_id, entry in self.by_user.items():
            if kind == KIND_LEADERS:
                if not entry["is_leader"]:
                    continue
            elif kind and entry["kind"] != kind:
                continue
            if role and not any(name == role for name, _level, _unit in entry["roles"]):
                continue
            if unit_ids is not None and not any(unit in unit_ids for _name, _level, unit in entry["roles"]):
                continue
            out.append(user_id)
        return out


# ─── Sətirlər ───────────────────────────────────────────────────────────────


def _page_membership_map(*, organization, user_ids, scoped_unit_ids):
    """Səhifədəki şəxslərin üzvlükləri — TƏK sorğu (`select_related`)."""
    if not user_ids:
        return {}
    queryset = (
        Membership.objects.filter(organization=organization, is_active=True, user_id__in=user_ids)
        .select_related("role", "scope_unit")
        .order_by("user_id", "-is_primary", "-role__level", "role__name")
    )
    if scoped_unit_ids is not None:
        queryset = queryset.filter(scope_unit_id__in=scoped_unit_ids)
    out = defaultdict(list)
    for membership in queryset:
        out[membership.user_id].append(membership)
    return out


def _build_row(*, user, memberships, unit_index, entry, actor_level, is_superadmin, owner_id, can_remove_members):
    name = _display_name(user)
    profile = getattr(user, "profile", None)
    roles, position, joined_at, unit_name, unit_chain = [], "", None, "", ""
    for membership in memberships:
        label = _role_text(membership.role.name, getattr(membership.role, "display_name", ""))
        scope_unit = membership.scope_unit
        roles.append(
            {
                "label": label or kind_label(entry["kind"]),
                "unit": scope_unit.name if scope_unit is not None else "",
                "is_primary": bool(membership.is_primary),
                "title": (membership.title or "").strip(),
            }
        )
        if not position and (membership.title or "").strip():
            position = membership.title.strip()
        if joined_at is None or (membership.created_at and membership.created_at < joined_at):
            joined_at = membership.created_at
        if not unit_name and scope_unit is not None:
            unit_name = scope_unit.name
            unit_chain = unit_index.chain(scope_unit.id)
    if not position:
        position = (getattr(profile, "staff_position", "") or "").strip()

    top_level = entry["top_level"]
    removable = (
        can_remove_members
        and entry["profile_role"] in REMOVABLE_PROFILE_ROLES
        and user.id != owner_id
        and (is_superadmin or top_level < actor_level)
    )
    row = {
        "user_id": user.id,
        "name": name,
        "initials": _initials(name),
        "username": user.username,
        "email": user.email or "",
        "kind": entry["kind"],
        "kind_label": kind_label(entry["kind"]),
        "is_leader": entry["is_leader"],
        "roles": roles,
        "roles_preview": roles[:ROLE_PREVIEW],
        "roles_more": max(0, len(roles) - ROLE_PREVIEW),
        "position": position,
        "unit_name": unit_name,
        "unit_chain": unit_chain,
        "joined": _format_date(joined_at),
        "can_remove": removable,
        "profile_url": reverse("accounts:public_profile", kwargs={"username": user.username}),
    }
    # «Üzv kartı» çekmecəsi ƏLAVƏ SORĞU ATMIR — sətirdəki dəyərlər data-atributla
    # ötürülür (şablon JSON-u avtomatik escape edir, JS `JSON.parse` ilə oxuyur).
    row["detail_json"] = json.dumps(
        {
            key: row[key]
            for key in (
                "name",
                "initials",
                "username",
                "email",
                "kind_label",
                "is_leader",
                "roles",
                "position",
                "unit_name",
                "unit_chain",
                "joined",
                "profile_url",
            )
        },
        ensure_ascii=False,
    )
    return row


# ─── Public builder ─────────────────────────────────────────────────────────


def build_members_registry(
    *,
    request,
    organization,
    is_superadmin,
    actor_level,
    superadmin_user_ids,
    can_remove_members,
):
    """Üzv reyestrinin bütün context-i (KPI · filtr · cədvəl · səhifə)."""
    from apps.organizations.public import get_unit_scope

    unit_scope = get_unit_scope(request.user, organization, request=request)
    scoped_unit_ids = None
    if not is_superadmin and unit_scope.is_unit_scoped:
        scoped_unit_ids = list(
            OrgUnit.objects.filter(organization=organization)
            .filter(unit_scope.unit_subtree_q())
            .values_list("pk", flat=True)
        )

    search = (request.GET.get(f"{PREFIX}q") or "").strip()[:120]
    kind = (request.GET.get(f"{PREFIX}kind") or "").strip().lower()
    kind = kind if kind in KINDS else ""
    role = (request.GET.get(f"{PREFIX}role") or "").strip().lower()[:100]
    raw_unit = (request.GET.get(f"{PREFIX}unit") or "").strip()
    sort = (request.GET.get(f"{PREFIX}sort") or "").strip()
    sort = sort if sort in SORTS else DEFAULT_SORT

    with bypass_rls():
        unit_index = _UnitIndex(organization)
        member_index = _MemberIndex(
            organization=organization,
            scoped_unit_ids=scoped_unit_ids,
            superadmin_user_ids=superadmin_user_ids,
            unit_index=unit_index,
        )
        unit_options = unit_index.options()
        role_labels = {
            (name or "").strip().lower(): _role_text(name, display or "")
            for name, display in organization.roles.filter(is_active=True).values_list("name", "display_name")
        }
        role_options = member_index.role_options(role_labels)
        if role and not any(option["value"] == role for option in role_options):
            role = ""
        unit_ids = None
        unit_id = ""
        for option in unit_options:
            if option["value"] == raw_unit:
                unit_id = raw_unit
                break
        if unit_id:
            for candidate in unit_index.units:
                if str(candidate) == unit_id:
                    unit_ids = unit_index.subtree_ids(candidate)
                    break

        matching_ids = member_index.matching_user_ids(kind=kind, role=role, unit_ids=unit_ids)
        users = User.objects.filter(id__in=matching_ids).select_related("profile")
        if search:
            users = users.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(profile__staff_position__icontains=search)
            )
        users = users.annotate(
            joined_at=Max(
                "memberships__created_at",
                filter=Q(memberships__organization=organization, memberships__is_active=True),
            )
        ).order_by(*SORTS[sort], "pk")
        page_obj = Paginator(users, PAGE_SIZE).get_page(request.GET.get(f"{PREFIX}page"))
        page_users = list(page_obj.object_list)
        membership_map = _page_membership_map(
            organization=organization,
            user_ids=[user.id for user in page_users],
            scoped_unit_ids=scoped_unit_ids,
        )

    owner_id = getattr(organization, "owner_id", None)
    rows = [
        _build_row(
            user=user,
            memberships=membership_map.get(user.id, []),
            unit_index=unit_index,
            entry=member_index.by_user.get(
                user.id,
                {"kind": KIND_STAFF, "is_leader": False, "top_level": 0, "profile_role": ProfileRole.MEMBER},
            ),
            actor_level=actor_level,
            is_superadmin=is_superadmin,
            owner_id=owner_id,
            can_remove_members=can_remove_members,
        )
        for user in page_users
    ]
    totals = member_index.totals()
    return {
        "rows": rows,
        "page_obj": page_obj,
        "totals": totals,
        "filters": {
            "search": search,
            "kind": kind,
            "role": role,
            "unit_id": unit_id,
            "sort": sort,
            "role_options": role_options,
            "unit_options": unit_options,
            "is_filtered": bool(search or kind or role or unit_id),
        },
        "scope_active": scoped_unit_ids is not None,
    }
