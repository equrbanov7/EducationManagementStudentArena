"""
Fakültə və kafedra idarəetmə view-ları.

Köhnə "org-structure" (birləşik) səhifəsi views.organization_structure-da
qalır (geri uyğunluq). Bu modul yeni AYRI səhifələri verir:

- organization_faculties  → fakültələr (CRUD + dekan təyini + axtarış/sıralama/pagination)
- organization_kafedras   → kafedralar (CRUD + fakültə filtri + müdir/müəllim təyini)

Tenant izolyasiyası: bütün OrgUnit/Membership sorğuları aktiv təşkilat +
unit scope (apps.organizations.scoping) ilə məhdudlaşdırılır. Yazma əməliyyatları
mərkəzi RBAC icazələri (`unit.create/edit/delete`, `member.edit`) ilə qorunur.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import pgettext

from core.constants import OrgUnitType

from .models import Membership, Organization, OrgUnit
from .views import (
    _can_manage_organization,
    _can_view_structure,
    _get_structure_scope,
    _has_org_permission,
    _is_ajax_request,
    _unique_unit_slug,
    _visible_units_queryset,
)

# Kafedra kimi qəbul edilən unit tipləri (köhnə datada hər ikisi işlənib).
KAFEDRA_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)

# Kafedraya təyin edilə bilən "müəllim" rolları (org tipindən asılı adlar).
TEACHER_ROLE_NAMES = ("teacher", "assistant", "assistant_teacher", "instructor", "collaborator")

# Rəhbər (dekan / kafedra müdiri) namizədi sayıla bilən minimal rol levli.
HEAD_CANDIDATE_MIN_LEVEL = 40

FACULTY_PAGE_SIZE = 9
KAFEDRA_PAGE_SIZE = 9

_SORT_OPTIONS = {
    "name": ("name",),
    "-name": ("-name",),
    "newest": ("-created_at", "name"),
    "oldest": ("created_at", "name"),
}


# --------------------------------------------------------------------------- #
# Ortaq köməkçilər
# --------------------------------------------------------------------------- #


def _unit_permission_flags(request, organization):
    """Cari istifadəçinin struktur üzərində yazma icazələri (mərkəzi RBAC)."""
    can_manage = _can_manage_organization(request.user, organization)
    return {
        "can_create": can_manage or _has_org_permission(request, "unit.create"),
        "can_edit": can_manage or _has_org_permission(request, "unit.edit"),
        "can_delete": can_manage or _has_org_permission(request, "unit.delete"),
        # Müəllim/rəhbər təyinatı üzv redaktəsidir (HR-ın `member.edit` icazəsi var).
        "can_assign_members": can_manage or _has_org_permission(request, "member.edit"),
    }


def _visible_faculties_qs(organization, scope):
    return _visible_units_queryset(organization, scope).filter(unit_type=OrgUnitType.FACULTY)


def _visible_kafedras_qs(organization, scope):
    return _visible_units_queryset(organization, scope).filter(unit_type__in=KAFEDRA_UNIT_TYPES)


def _teacher_memberships_qs(organization):
    """Təşkilatın aktiv müəllim üzvlükləri (kafedra təyinatı üçün)."""
    return (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
            role__name__in=TEACHER_ROLE_NAMES,
        )
        .select_related("user", "role", "scope_unit")
        .order_by("user__first_name", "user__last_name", "user__username")
    )


def _head_candidates(organization):
    """Rəhbər (dekan/müdir) namizədləri — idarəetmə/müəllim səviyyəli aktiv üzvlər."""
    seen_user_ids = set()
    candidates = []
    memberships = (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
            role__level__gte=HEAD_CANDIDATE_MIN_LEVEL,
        )
        .select_related("user", "role")
        .order_by("-role__level", "user__first_name", "user__username")
    )
    for membership in memberships:
        if membership.user_id in seen_user_ids:
            continue
        seen_user_ids.add(membership.user_id)
        candidates.append(
            {
                "user_id": membership.user_id,
                "full_name": membership.user.get_full_name() or membership.user.username,
                "role_label": membership.role.display_name,
            }
        )
    return candidates


def _clean_sort(raw_sort):
    sort = (raw_sort or "").strip()
    return sort if sort in _SORT_OPTIONS else "name"


def _section_ajax_response(request, section_name, partial_template, context_key, context, *, status=200):
    """POST sonrası profil bölməsinin yenilənmiş HTML fraqmentini qaytarır."""
    context = dict(context)
    context.update(
        {
            "active_section": section_name,
            "profile_base_url": reverse("accounts:profile"),
            "embedded_in_profile": True,
        }
    )
    context[context_key] = context
    html = render_to_string(partial_template, context, request=request)
    return JsonResponse({"ok": status < 400, "section": section_name, "html": html}, status=status)


def _get_org_or_redirect(request, slug):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = _get_structure_scope(request, organization)
    if not _can_view_structure(request, organization, scope):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return organization, scope, redirect("organizations:select")
    return organization, scope, None


# --------------------------------------------------------------------------- #
# Kontekst qurucuları (profil AJAX bölməsi + tam səhifə eyni konteksti paylaşır)
# --------------------------------------------------------------------------- #


def build_organization_faculties_context(request, organization, *, form_errors=None, form_values=None, notice=""):
    scope = _get_structure_scope(request, organization)
    can_view = _can_view_structure(request, organization, scope)
    flags = _unit_permission_flags(request, organization)

    search = (request.GET.get("faculty_search") or "").strip()[:120]
    sort = _clean_sort(request.GET.get("faculty_sort"))

    faculties = (
        _visible_faculties_qs(organization, scope)
        .select_related("head")
        .annotate(
            kafedra_count=Count(
                "children",
                filter=Q(children__is_active=True, children__unit_type__in=KAFEDRA_UNIT_TYPES),
                distinct=True,
            )
        )
    )
    total_count = faculties.count()
    if search:
        faculties = faculties.filter(Q(name__icontains=search) | Q(code__icontains=search))
    faculties = faculties.order_by(*_SORT_OPTIONS[sort])

    page_obj = Paginator(faculties, FACULTY_PAGE_SIZE).get_page(request.GET.get("faculty_page"))
    kafedra_total = _visible_kafedras_qs(organization, scope).count()

    pagination_query = urlencode(
        {
            key: value
            for key, value in {"section": "org-faculties", "faculty_search": search, "faculty_sort": sort}.items()
            if value
        }
    )

    return {
        "organization": organization,
        "can_view": can_view,
        "faculties": page_obj,
        "faculties_page_obj": page_obj,
        "faculty_total_count": total_count,
        "filtered_count": page_obj.paginator.count,
        "kafedra_total_count": kafedra_total,
        "search_query": search,
        "sort_value": sort,
        "head_candidates": _head_candidates(organization) if flags["can_assign_members"] else [],
        "can_create": flags["can_create"] and scope.is_org_wide,
        "can_edit": flags["can_edit"],
        "can_delete": flags["can_delete"],
        "can_assign_head": flags["can_assign_members"],
        "pagination_query": pagination_query,
        "form_errors": form_errors or {},
        "form_values": form_values or {},
        "notice": notice,
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }


def build_organization_kafedras_context(request, organization, *, form_errors=None, form_values=None, notice=""):
    scope = _get_structure_scope(request, organization)
    can_view = _can_view_structure(request, organization, scope)
    flags = _unit_permission_flags(request, organization)

    search = (request.GET.get("kafedra_search") or "").strip()[:120]
    sort = _clean_sort(request.GET.get("kafedra_sort"))
    faculty_filter = (request.GET.get("kafedra_faculty") or "").strip()

    faculty_options = list(_visible_faculties_qs(organization, scope).only("id", "name").order_by("name"))
    valid_faculty_ids = {str(faculty.id) for faculty in faculty_options}
    if faculty_filter not in valid_faculty_ids:
        faculty_filter = ""

    kafedras = (
        _visible_kafedras_qs(organization, scope)
        .select_related("parent", "head")
        .annotate(
            teacher_count=Count(
                "memberships",
                filter=Q(memberships__is_active=True, memberships__role__name__in=TEACHER_ROLE_NAMES),
                distinct=True,
            )
        )
    )
    total_count = kafedras.count()
    if search:
        kafedras = kafedras.filter(Q(name__icontains=search) | Q(code__icontains=search))
    if faculty_filter:
        kafedras = kafedras.filter(parent_id=faculty_filter)
    kafedras = kafedras.order_by(*_SORT_OPTIONS[sort])

    page_obj = Paginator(kafedras, KAFEDRA_PAGE_SIZE).get_page(request.GET.get("kafedra_page"))

    # Səhifədəki kafedraların müəllimləri — tək sorğu, N+1 yoxdur.
    page_unit_ids = [unit.id for unit in page_obj.object_list]
    teachers_by_unit = {}
    if page_unit_ids:
        for membership in _teacher_memberships_qs(organization).filter(scope_unit_id__in=page_unit_ids):
            teachers_by_unit.setdefault(membership.scope_unit_id, []).append(membership)
    for unit in page_obj.object_list:
        unit.teacher_members = teachers_by_unit.get(unit.id, [])

    # Təyinat modalı üçün bütün müəllim üzvlükləri (cari kafedrası etiketdə).
    teacher_options = list(_teacher_memberships_qs(organization)) if flags["can_assign_members"] else []
    unassigned_teacher_count = sum(1 for membership in teacher_options if membership.scope_unit_id is None)

    pagination_query = urlencode(
        {
            key: value
            for key, value in {
                "section": "org-kafedras",
                "kafedra_search": search,
                "kafedra_sort": sort,
                "kafedra_faculty": faculty_filter,
            }.items()
            if value
        }
    )

    return {
        "organization": organization,
        "can_view": can_view,
        "kafedras": page_obj,
        "kafedras_page_obj": page_obj,
        "kafedra_total_count": total_count,
        "filtered_count": page_obj.paginator.count,
        "faculty_total_count": len(faculty_options),
        "search_query": search,
        "sort_value": sort,
        "faculty_filter": faculty_filter,
        "faculty_options": faculty_options,
        "teacher_options": teacher_options,
        "unassigned_teacher_count": unassigned_teacher_count,
        "head_candidates": _head_candidates(organization) if flags["can_assign_members"] else [],
        "can_create": flags["can_create"] and bool(faculty_options),
        "can_edit": flags["can_edit"],
        "can_delete": flags["can_delete"],
        "can_assign_head": flags["can_assign_members"],
        "can_assign_teachers": flags["can_assign_members"],
        "pagination_query": pagination_query,
        "form_errors": form_errors or {},
        "form_values": form_values or {},
        "notice": notice,
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }


# --------------------------------------------------------------------------- #
# Yazma əməliyyatları
# --------------------------------------------------------------------------- #


def _clean_name_code(request):
    name = (request.POST.get("name") or "").strip()
    code = (request.POST.get("code") or "").strip()[:50]
    errors = {}
    if not name:
        errors["name"] = "Ad sahəsi mütləqdir."
    elif len(name) > 255:
        errors["name"] = "Ad maksimum 255 simvol ola bilər."
    return name, code, errors


def _get_visible_unit(organization, scope, unit_id, unit_types):
    if not unit_id:
        return None
    return (
        _visible_units_queryset(organization, scope)
        .filter(unit_type__in=unit_types, pk=unit_id)
        .select_related("parent")
        .first()
    )


def _assign_unit_head(request, organization, unit):
    """`head_user` boşdursa rəhbər silinir, doludursa aktiv üzv olmalıdır."""
    head_user_id = (request.POST.get("head_user") or "").strip()
    if not head_user_id:
        unit.head = None
        unit.save(update_fields=["head"])
        return {}, "Rəhbər təyinatı silindi."
    membership = (
        Membership.objects.filter(
            organization=organization,
            user_id=head_user_id,
            is_active=True,
            user__is_active=True,
        )
        .select_related("user")
        .first()
    )
    if membership is None:
        return {"general": "Seçilmiş istifadəçi bu təşkilatın aktiv üzvü deyil."}, ""
    unit.head = membership.user
    unit.save(update_fields=["head"])
    return {}, f"{unit.name} üçün rəhbər təyin edildi."


def _handle_faculty_action(request, organization, scope, flags):
    """Returns (errors, notice)."""
    action = (request.POST.get("action") or "create").strip()
    unit = _get_visible_unit(organization, scope, (request.POST.get("unit_id") or "").strip(), [OrgUnitType.FACULTY])

    if action == "create":
        if not (flags["can_create"] and scope.is_org_wide):
            return {"general": "Yeni fakültə yaratmaq üçün `unit.create` icazəsi və tam təşkilat scope-u lazımdır."}, ""
        name, code, errors = _clean_name_code(request)
        if errors:
            return errors, ""
        with transaction.atomic():
            OrgUnit.objects.create(
                organization=organization,
                parent=None,
                unit_type=OrgUnitType.FACULTY,
                name=name,
                slug=_unique_unit_slug(organization, name, "faculty"),
                code=code,
            )
        return {}, "Fakültə yaradıldı."

    if unit is None:
        return {"general": "Fakültə tapılmadı və ya bu fakültəyə girişiniz yoxdur."}, ""

    if action == "update":
        if not flags["can_edit"]:
            return {"general": "Fakültəni redaktə etmək üçün `unit.edit` icazəsi lazımdır."}, ""
        name, code, errors = _clean_name_code(request)
        if errors:
            return errors, ""
        unit.name = name
        unit.code = code
        unit.save(update_fields=["name", "code"])
        return {}, "Fakültə yeniləndi."

    if action == "delete":
        if not flags["can_delete"]:
            return {"general": "Fakültəni silmək üçün `unit.delete` icazəsi lazımdır."}, ""
        active_kafedra_count = unit.children.filter(is_active=True).count()
        if active_kafedra_count:
            return {
                "general": (
                    f"“{unit.name}” silinə bilməz: {active_kafedra_count} aktiv kafedra bu fakültəyə bağlıdır. "
                    "Əvvəlcə kafedraları silin və ya başqa fakültəyə köçürün."
                )
            }, ""
        scoped_member_count = unit.memberships.filter(is_active=True).count()
        if scoped_member_count:
            return {
                "general": (
                    f"“{unit.name}” silinə bilməz: {scoped_member_count} aktiv üzv bu fakültəyə təyin olunub. "
                    "Əvvəlcə üzv təyinatlarını dəyişin."
                )
            }, ""
        unit.is_active = False
        unit.save(update_fields=["is_active"])
        return {}, f"“{unit.name}” fakültəsi silindi."

    if action == "assign_head":
        if not flags["can_assign_members"]:
            return {"general": "Rəhbər təyin etmək üçün `member.edit` icazəsi lazımdır."}, ""
        return _assign_unit_head(request, organization, unit)

    return {"general": "Naməlum əməliyyat."}, ""


def _handle_kafedra_action(request, organization, scope, flags):
    """Returns (errors, notice)."""
    action = (request.POST.get("action") or "create").strip()
    unit = _get_visible_unit(organization, scope, (request.POST.get("unit_id") or "").strip(), KAFEDRA_UNIT_TYPES)

    def _resolve_parent_faculty():
        parent_id = (request.POST.get("parent") or "").strip()
        if not parent_id:
            return None, {"parent": "Kafedra üçün fakültə seçilməlidir."}
        parent = _visible_faculties_qs(organization, scope).filter(pk=parent_id).first()
        if parent is None:
            return None, {"parent": "Seçilmiş fakültəyə bu istifadəçi ilə giriş yoxdur."}
        return parent, {}

    if action == "create":
        if not flags["can_create"]:
            return {"general": "Yeni kafedra yaratmaq üçün `unit.create` icazəsi lazımdır."}, ""
        name, code, errors = _clean_name_code(request)
        parent, parent_errors = _resolve_parent_faculty()
        errors.update(parent_errors)
        if errors:
            return errors, ""
        with transaction.atomic():
            OrgUnit.objects.create(
                organization=organization,
                parent=parent,
                unit_type=OrgUnitType.CHAIR,
                name=name,
                slug=_unique_unit_slug(organization, name, "kafedra"),
                code=code,
            )
        return {}, "Kafedra yaradıldı."

    if unit is None:
        return {"general": "Kafedra tapılmadı və ya bu kafedraya girişiniz yoxdur."}, ""

    if action == "update":
        if not flags["can_edit"]:
            return {"general": "Kafedranı redaktə etmək üçün `unit.edit` icazəsi lazımdır."}, ""
        name, code, errors = _clean_name_code(request)
        parent, parent_errors = _resolve_parent_faculty()
        errors.update(parent_errors)
        if errors:
            return errors, ""
        with transaction.atomic():
            unit.name = name
            unit.code = code
            unit.parent = parent
            # save() level/path-i yenidən hesablayır və törəmələrə yayır.
            unit.save()
        return {}, "Kafedra yeniləndi."

    if action == "delete":
        if not flags["can_delete"]:
            return {"general": "Kafedranı silmək üçün `unit.delete` icazəsi lazımdır."}, ""
        scoped_member_count = unit.memberships.filter(is_active=True).count()
        if scoped_member_count:
            return {
                "general": (
                    f"“{unit.name}” silinə bilməz: {scoped_member_count} aktiv üzv (müəllim/tələbə) bu kafedraya "
                    "təyin olunub. Əvvəlcə təyinatları silin."
                )
            }, ""
        active_child_count = unit.children.filter(is_active=True).count()
        if active_child_count:
            return {"general": f"“{unit.name}” silinə bilməz: {active_child_count} aktiv alt bölmə var."}, ""
        unit.is_active = False
        unit.save(update_fields=["is_active"])
        return {}, f"“{unit.name}” kafedrası silindi."

    if action == "assign_head":
        if not flags["can_assign_members"]:
            return {"general": "Kafedra müdiri təyin etmək üçün `member.edit` icazəsi lazımdır."}, ""
        return _assign_unit_head(request, organization, unit)

    if action == "assign_teacher":
        if not flags["can_assign_members"]:
            return {"general": "Müəllim təyin etmək üçün `member.edit` icazəsi lazımdır."}, ""
        membership_id = (request.POST.get("membership_id") or "").strip()
        membership = _teacher_memberships_qs(organization).filter(pk=membership_id).first()
        if membership is None:
            return {"general": "Seçilmiş müəllim bu təşkilatın aktiv müəllim üzvü deyil."}, ""
        if membership.scope_unit_id == unit.id:
            return {"general": "Bu müəllim artıq həmin kafedraya təyin olunub."}, ""
        membership.scope_unit = unit
        try:
            membership.save(update_fields=["scope_unit"])
        except IntegrityError:
            return {"general": "Bu müəllimin həmin kafedrada eyni rolla üzvlüyü artıq mövcuddur."}, ""
        teacher_name = membership.user.get_full_name() or membership.user.username
        return {}, f"{teacher_name} “{unit.name}” kafedrasına təyin edildi."

    if action == "remove_teacher":
        if not flags["can_assign_members"]:
            return {"general": "Müəllim təyinatını silmək üçün `member.edit` icazəsi lazımdır."}, ""
        membership_id = (request.POST.get("membership_id") or "").strip()
        membership = _teacher_memberships_qs(organization).filter(pk=membership_id, scope_unit=unit).first()
        if membership is None:
            return {"general": "Bu kafedrada belə müəllim təyinatı tapılmadı."}, ""
        membership.scope_unit = None
        try:
            membership.save(update_fields=["scope_unit"])
        except IntegrityError:
            return {"general": "Müəllimin kafedrasız eyni rollu üzvlüyü artıq mövcuddur."}, ""
        teacher_name = membership.user.get_full_name() or membership.user.username
        return {}, f"{teacher_name} “{unit.name}” kafedrasından çıxarıldı."

    return {"general": "Naməlum əməliyyat."}, ""


# --------------------------------------------------------------------------- #
# View-lar
# --------------------------------------------------------------------------- #


def _structure_page_view(
    request,
    slug,
    *,
    section_name,
    context_builder,
    action_handler,
    partial_template,
    context_key,
    page_template,
    redirect_url_name,
):
    organization, scope, redirect_response = _get_org_or_redirect(request, slug)
    if redirect_response is not None:
        return redirect_response

    flags = _unit_permission_flags(request, organization)
    form_errors = {}
    form_values = {}
    notice = ""

    if request.method == "POST":
        form_values = {
            "action": (request.POST.get("action") or "").strip(),
            "unit_id": (request.POST.get("unit_id") or "").strip(),
            "name": (request.POST.get("name") or "").strip(),
            "code": (request.POST.get("code") or "").strip(),
            "parent": (request.POST.get("parent") or "").strip(),
        }
        form_errors, notice = action_handler(request, organization, scope, flags)
        if not form_errors:
            if _is_ajax_request(request):
                context = context_builder(request, organization, notice=notice)
                return _section_ajax_response(request, section_name, partial_template, context_key, context)
            messages.success(request, notice)
            return redirect(redirect_url_name, slug=organization.slug)
        if not _is_ajax_request(request):
            messages.error(request, form_errors.get("general") or "Əməliyyat yerinə yetirilə bilmədi.")

    context = context_builder(request, organization, form_errors=form_errors, form_values=form_values, notice=notice)
    context[context_key] = context

    if request.method == "POST" and _is_ajax_request(request):
        return _section_ajax_response(request, section_name, partial_template, context_key, context, status=400)

    return render(request, page_template, context)


@login_required
def organization_faculties(request, slug):
    """Fakültələrin idarə edilməsi (siyahı, yaratma, redaktə, silmə, dekan təyini)."""
    return _structure_page_view(
        request,
        slug,
        section_name="org-faculties",
        context_builder=build_organization_faculties_context,
        action_handler=_handle_faculty_action,
        partial_template="accounts/profile/sections/_org_faculties.html",
        context_key="org_faculties_section",
        page_template="organizations/faculties.html",
        redirect_url_name="organizations:structure_faculties",
    )


@login_required
def organization_kafedras(request, slug):
    """Kafedraların idarə edilməsi (siyahı, filtr, CRUD, müdir/müəllim təyinatı)."""
    return _structure_page_view(
        request,
        slug,
        section_name="org-kafedras",
        context_builder=build_organization_kafedras_context,
        action_handler=_handle_kafedra_action,
        partial_template="accounts/profile/sections/_org_kafedras.html",
        context_key="org_kafedras_section",
        page_template="organizations/kafedras.html",
        redirect_url_name="organizations:structure_kafedras",
    )
