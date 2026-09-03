"""Jurnal struktur-əhatə (scope) köməkçiləri — kim hansı jurnalı görür/bağlayır.

TARİXÇƏ (SAHİBİN QƏRARI, 2026-08): bu modul əvvəllər «qiymət təsdiq zənciri»
idi (müəllim → kafedra → dekan). Zəncir TAM LƏĞV EDİLDİ:

    «Jurnal təsdiqə getməyi yoxdur… Müəllim balı yazır və bitir; jurnalı müəllim
    kimsəyə təsdiqə göndərmir. Sadəcə semestr sonunda RİM mərkəzi fakültə-fakültə
    jurnalları bağlaya bilməlidir.»

Ona görə burada YALNIZ scope hesablaması qalıb:

* :func:`permission_scope_q` — bir icazənin unit alt-ağacı üzrə queryset filtri;
* :func:`analytics_scope_q` / :func:`can_view_analytics` — analitika panelinin əhatəsi;
* :func:`can_close_journals` / :func:`close_scope_q` — RİM-in jurnal bağlama əhatəsi
  (əməliyyatın özü :mod:`apps.registrar.journal_close`-dadır).

Jurnalın kilid vəziyyəti ``AssessmentScheme.is_published`` + ``approval_status``
cütündən oxunur (bax :func:`apps.registrar.gradebook.journal_is_locked`) — indi
yalnız İKİ məna var: DRAFT = açıq, APPROVED + published = bağlı.
"""

from __future__ import annotations

#: Jurnalları toplu bağlamaq/açmaq icazəsi (RİM). Köhnə ``grade.approve_chair`` /
#: ``grade.approve_final`` açarlarını əvəz edir — təsdiq zənciri artıq yoxdur.
JOURNAL_CLOSE_PERMISSION = "journal.close"


def _permission_scope(user, organization, permission):
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.user_permission_scope(user, organization, permission)


def offering_in_actor_scope(user, organization, offering, *, permission=JOURNAL_CLOSE_PERMISSION) -> bool:
    """Aktorun unit alt-ağacı bu dərs açılışını əhatə edirmi.

    İcazə rol ADINDAN deyil, rolun mərkəzi permission tərifindən gəlir. UNIT
    rolunda etibarlı ``scope_unit`` yoxdursa nəticə fail-closed-dur.

    MODUL SƏRHƏDİ: registrar ``apps.organizations``-u Python səviyyəsində import
    ETMİR (dövr yaranardı) — model app registry ilə həll olunur, alt-ağac
    yoxlaması isə ``OrgUnit.user_scope_covers`` daxilində, öz modulundadır.
    """
    scope = _permission_scope(user, organization, permission)
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    group_id = getattr(offering, "group_id", None)
    if group_id is None:
        return False
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.objects.filter(organization=organization, pk=group_id).filter(scope.unit_subtree_q()).exists()


def permission_scope_q(user, organization, permission, *, path_field, id_field):
    """Fail-closed queryset filter for one permission's structural scope."""
    return _permission_scope(user, organization, permission).unit_subtree_q(
        path_field=path_field,
        id_field=id_field,
    )


# ── Jurnal bağlama (RİM) ─────────────────────────────────────────────────────


def can_close_journals(user, organization) -> bool:
    """``journal.close`` icazəsi struktur əhatəsi verirmi (org və ya unit)."""
    return _permission_scope(user, organization, JOURNAL_CLOSE_PERMISSION).has_structure_access


def close_scope(user, organization):
    """RİM aktorunun jurnal-bağlama əhatəsi (``UnitScope``)."""
    return _permission_scope(user, organization, JOURNAL_CLOSE_PERMISSION)


def close_scope_q(user, organization, *, path_field, id_field):
    """``journal.close`` əhatəsi üçün queryset filtri (fail-closed)."""
    return permission_scope_q(
        user,
        organization,
        JOURNAL_CLOSE_PERMISSION,
        path_field=path_field,
        id_field=id_field,
    )


# ── Analitika əhatəsi ────────────────────────────────────────────────────────


def can_view_analytics(user, organization) -> bool:
    return bool(_analytics_scopes(user, organization))


def _analytics_scopes(user, organization):
    all_scope = _permission_scope(user, organization, "analytics.view_all")
    unit_scope = _permission_scope(user, organization, "analytics.view_unit")
    scopes = [all_scope] if all_scope.has_structure_access else []
    if unit_scope.has_structure_access:
        scopes.append(unit_scope)
    return scopes


def analytics_scope_q(user, organization, *, path_field, id_field):
    scopes = _analytics_scopes(user, organization)
    if any(scope.is_org_wide for scope in scopes):
        from django.db.models import Q

        return Q()
    if not scopes:
        from django.db.models import Q

        return Q(pk__in=[])
    query = scopes[0].unit_subtree_q(path_field=path_field, id_field=id_field)
    for scope in scopes[1:]:
        query |= scope.unit_subtree_q(path_field=path_field, id_field=id_field)
    return query
