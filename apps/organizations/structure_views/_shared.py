"""structure_views paketi — _shared."""

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.models import CourseOffering
from core.constants import OrgUnitType

from ..models import AcademicPeriod, Membership, Organization, OrgUnit
from ..views import (
    _can_manage_organization,
    _can_view_structure,
    _get_structure_scope,
    _has_org_permission,
    _is_ajax_request,
    _unique_unit_slug,
    _visible_units_queryset,
)
from .constants import (
    _SORT_OPTIONS,
    HEAD_CANDIDATE_MIN_LEVEL,
    KAFEDRA_UNIT_TYPES,
    TEACHER_ROLE_NAMES,
)


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


def _current_academic_year_period_ids(organization):
    """Cari tədris ilinin (bütün semestrlərinin) dövr id-ləri.

    "Aktiv müəllim" tərifi cari SEMESTRLƏ (``AcademicPeriod.is_current``) yox,
    cari TƏDRİS İLİ ilə bağlıdır: bir tədris ili adətən Payız+Yaz semestrindən
    ibarətdir və Yaz semestri "cari" olanda Payızda dərs demiş müəllim də "bu il
    aktivdir" sayılmalıdır. Ona görə əvvəlcə ``is_current`` dövr tapılır, sonra
    onun ``year_display``-inə (bax ``AcademicPeriod.format_year``) uyğun BÜTÜN
    dövrlərin id-ləri götürülür. ``is_current`` dövr yoxdursa (heç kim təyin
    etməyib) ən son başlayan dövrün ili istifadə olunur — layihədə mövcud
    ``AcademicPeriod.objects.filter(is_current=True).first()`` nümunəsinin
    (bax ``apps/registrar/public.py``, ``apps/registrar/views.py``) təbii
    genişlənməsidir. Dövrlərin sayı azdır (onluqlarla) — TƏK yüngül sorğu."""
    periods = list(
        AcademicPeriod.objects.filter(organization=organization).only("id", "academic_year", "start_date", "is_current")
    )
    if not periods:
        return []
    current = next((p for p in periods if p.is_current), None)
    if current is None:
        current = max(periods, key=lambda p: p.start_date)
    target_year = current.year_display
    return [p.id for p in periods if p.year_display == target_year]


def _active_teacher_user_ids(organization, period_ids):
    """Cari tədris ilində ən azı bir ``CourseOffering``-in instruktoru olan
    istifadəçi id-ləri — TƏK sorğu, çağıran səhifədəki vahid sayından ASILI
    DEYİL (bir dəfə hesablanır, sonra hər vahid üçün Python-da yoxlanılır)."""
    if not period_ids:
        return set()
    return set(
        CourseOffering.objects.filter(
            organization=organization,
            is_active=True,
            period_id__in=period_ids,
            instructor_id__isnull=False,
        )
        .values_list("instructor_id", flat=True)
        .distinct()
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
            messages.error(
                request,
                form_errors.get("general")
                or pgettext("organizations.views.message", "Əməliyyat yerinə yetirilə bilmədi."),
            )

    context = context_builder(request, organization, form_errors=form_errors, form_values=form_values, notice=notice)
    context[context_key] = context

    if request.method == "POST" and _is_ajax_request(request):
        return _section_ajax_response(request, section_name, partial_template, context_key, context, status=400)

    return render(request, page_template, context)
