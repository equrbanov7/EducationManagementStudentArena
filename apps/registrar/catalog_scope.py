"""Kataloq reyestrlərinin («İxtisaslar», «Fənn kataloqu») struktur ƏHATƏSİ.

Sahib (2026-10-14, dekan kimi baxış): «özünə aid olduğu ixtisasları görsün»,
«ancaq özünə aid olan fənlər görünsün, fakültədəki». Qayda — «hər rol öz
səlahiyyəti qədər»: əhatə ``catalog.view`` açarını DAŞIYAN üzvlükdən çıxır
(``get_permission_scope``):

* ORGANIZATION rolu (rektor, Tədris şöbəsi, RİM …) → bütün təşkilat (dəyişməyib);
* UNIT rolu (dekan, kafedra müdiri, tyutor/koordinator) → öz alt-ağacı;
* əhatəsiz aktor → HEÇ NƏ (fail-closed, «əhatə yoxdur ≠ bütün universitet»).

İxtisas əhatədədir ⇔ ``specialty_unit`` alt-ağacdadır (bölməsiz ixtisas unit-
əhatəli aktora görünmür). Fənn əhatədədir ⇔ sahibi kafedra (``chair_unit``)
alt-ağacdadır VƏ YA fənn alt-ağacdakı ixtisasın tədris planında / alt-ağacdakı
qrupun dərs təklifində (``CourseOffering``) işlənir — fakültənin öz qruplarına
başqa kafedranın verdiyi ümumi fənlər də «fakültədəki» fənlərdir.

YAZI (``catalog.manage``) bu modula BAĞLI DEYİL — dəyişməyib.

MODUL SƏRHƏDİ: ``apps.organizations`` statik import EDİLMİR — dar əhatə
``OrgUnit.user_permission_scope`` ilə (``curriculum_registry.plan_scope`` naxışı), oxu əhatəsi
isə funksiya daxilində lazy ``apps.organizations.public.faculty_read_scope`` ilə.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db.models import Q

PERM_VIEW = "catalog.view"

#: Kafedra seçicisinin vahid tipləri (``catalog_registry.chair_options`` ilə eyni).
CHAIR_UNIT_TYPES = ("chair", "department")


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def catalog_scope(request, organization):
    """Aktorun ``catalog.view`` OXU əhatəsi — kafedra kökü valideyn FAKÜLTƏYƏ genişlənir.

    Sahib (2026-10-14, kafedra müdiri kimi baxış): «ixtisaslarda ancaq öz fakültəmizə aid olanı görsün» —
    ixtisaslar fakültənin altındadır, kafedra alt-ağacında ixtisas yoxdur (``faculty_read_scope``).
    """
    # Lazy public-API importu (``semester_actions._org_wide`` ilə eyni naxış) — statik kənar yaratmır.
    from apps.organizations.public import faculty_read_scope

    return faculty_read_scope(getattr(request, "user", None), organization, PERM_VIEW)


def catalog_owner_scope(request, organization):
    """Fənnin SAHİBİ kafedra üçün DAR əhatə (genişlənməsiz ``catalog.view``) — kafedra müdiri öz kafedrası."""
    return _org_unit_model().user_permission_scope(getattr(request, "user", None), organization, PERM_VIEW)


def scope_programs(queryset, scope):
    """``Program`` queryset-i — ``specialty_unit`` alt-ağacı ilə (fail-closed)."""
    if scope.is_org_wide:
        return queryset
    if not scope.is_unit_scoped:
        return queryset.none()
    return queryset.filter(scope.unit_subtree_q(path_field="specialty_unit__path", id_field="specialty_unit_id"))


def subject_scope_q(organization, scope, owner_scope=None) -> Q | None:
    """``Subject`` üçün əhatə filtri; org-wide → ``None`` (filtr yoxdur), əhatəsiz → heç nə.

    ``scope`` — plan/dərs təklifi üçün OXU əhatəsi (fakültə); ``owner_scope`` — sahibi kafedra üçün
    DAR əhatə (verilməzsə ``scope``). Dekan üçün ikisi eynidir; kafedra müdiri öz kafedrasının fənlərini
    + fakültəsinin planlarında/qruplarında işlənən fənləri görür.
    """
    owner_scope = scope if owner_scope is None else owner_scope
    if scope.is_org_wide:
        return None
    if not scope.is_unit_scoped:
        return Q(pk__in=[])
    CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    planned = CurriculumSubject.objects.filter(organization=organization).filter(
        scope.unit_subtree_q(
            path_field="curriculum__program__specialty_unit__path",
            id_field="curriculum__program__specialty_unit_id",
        )
    )
    offered = CourseOffering.objects.filter(organization=organization).filter(
        scope.unit_subtree_q(path_field="group__path", id_field="group_id")
    )
    return (
        owner_scope.unit_subtree_q(path_field="chair_unit__path", id_field="chair_unit_id")
        | Q(pk__in=planned.values("subject_id"))
        | Q(pk__in=offered.values("subject_id"))
    )


def scope_subjects(queryset, organization, scope, owner_scope=None):
    """``Subject`` queryset-i əhatə ilə."""
    scope_q = subject_scope_q(organization, scope, owner_scope)
    return queryset if scope_q is None else queryset.filter(scope_q)


def scoped_chair_options(organization, scope, *, extra_unit_ids=None) -> list:
    """«Kafedra» seçicisi — YALNIZ əhatədəki kafedralar.

    Unit əhatəsi: alt-ağacdakı kafedralar + əhatə köklərinin ƏCDADLARI (ixtisas
    koordinatoru öz kafedrasını seçə bilsin) + ``extra_unit_ids`` (məs. görünən
    fənlərin sahibi kafedraları). Org əhatəsi → hamısı; əhatəsiz → boş.
    """
    OrgUnit = _org_unit_model()
    queryset = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=CHAIR_UNIT_TYPES)
    if not scope.is_org_wide:
        if not scope.is_unit_scoped:
            return []
        ancestor_ids = {part for path in scope.unit_paths for part in str(path or "").split("/") if part}
        allowed = scope.unit_subtree_q() | Q(pk__in=list(ancestor_ids))
        if extra_unit_ids is not None:
            allowed |= Q(pk__in=extra_unit_ids)
        queryset = queryset.filter(allowed)
    return [{"value": str(unit.id), "label": unit.name} for unit in queryset.order_by("name")]


def program_visible(request, organization, program_id) -> bool:
    """«Ətraflı» çekmecəsi (birbaşa ``id`` parametri) — ixtisas aktorun əhatəsindədirmi."""
    Program = django_apps.get_model("registrar", "Program")
    scope = catalog_scope(request, organization)
    try:
        return scope_programs(Program.objects.filter(organization=organization, pk=program_id), scope).exists()
    except (TypeError, ValueError, ValidationError):
        return False


__all__ = [
    "PERM_VIEW",
    "catalog_owner_scope",
    "catalog_scope",
    "program_visible",
    "scope_programs",
    "scope_subjects",
    "scoped_chair_options",
    "subject_scope_q",
]
