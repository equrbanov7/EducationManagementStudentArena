"""MR-000250/251 canlı vəziyyət qapıları — jurnal, rəsmi yük, dosye; heç nə yazılmır."""

from django.db.models import Q
from django.utils import timezone

from apps.registrar.public import plan_hours_for_offering
from apps.syllabus.public import content_fingerprints, section_data_map, syllabus_for_offering
from apps.workload.public import journal_academic_fingerprint

from . import exact_syllabus_recovery as core
from . import govher_syllabi_spec as spec

RestoreError = core.RestoreError
#: Akademik məzmun (dərs, xana, qeydiyyat, qiymət…) — sillabus cədvəlləri xaricində heç nə dəyişməməlidir.
PROTECTED_EXCLUDE = ("syllabus", "syllabus_share", "version", "section", "review")
#: Boş qaralamada yalnız «info» bölməsində avtomatik dəyər (müəllim adı, dil, saat) ola bilər.
BLANK_DRAFT_NONBLANK = {"info"}


def query(label, org, **filters):
    return core.model(label).objects.filter(organization=org, **filters)


def plan_of(hours):
    return {kind: int(value) for kind, value in (hours or {}).items() if int(value or 0)}


def actor_scope(org, actor):
    if (
        str(org.pk) != spec.ORG
        or not org.is_active
        or org.status != "active"
        or not actor.is_active
        or not actor.is_superuser
    ):
        raise RestoreError("active_fixed_tenant_superadmin_required")


def resolved_for(offering):
    return syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


def offering_scope(org, case):
    """Cari, açıq semestrin jurnalı; müəllim, qrup, fənn, saat və rəsmi yük pinlə eynidir."""
    offering = (
        core.model("registrar.CourseOffering")
        .objects.select_for_update(of=("self",))
        .select_related("subject", "period", "organization")
        .get(pk=case["offering_id"], organization=org)
    )
    period = offering.period
    if (
        str(offering.period_id) != spec.PERIOD
        or offering.instructor_id != spec.AUTHOR
        or not offering.is_active
        or str(offering.group_id) != case["group_id"]
        or str(offering.subject_id) not in case["subject_ids"]
        or offering.lesson_hours != case["hours"]
        or not period.is_active
        or period.locked_at is not None
        or not (period.start_date <= timezone.localdate() <= period.end_date)
    ):
        raise RestoreError("live_journal_scope_changed")
    author = core.model("auth.User").objects.filter(pk=spec.AUTHOR, is_active=True).first()
    profile = core.model("accounts.UserProfile").objects.filter(user_id=spec.AUTHOR, organization=org).first()
    if author is None or profile is None or profile.access_state != "active":
        raise RestoreError("author_identity_scope")
    if plan_of(plan_hours_for_offering(offering)) != case["plan"]:
        raise RestoreError("official_plan_hours_changed")
    row = (
        query("workload.TeachingTaskRow", org, pk=case["workload_row"], subject_id__in=case["subject_ids"])
        .filter(groups__id=offering.group_id)
        .first()
    )
    plan = case["plan"]
    if row is None or (row.lecture_plan, row.seminar_plan, row.lab_plan) != (
        plan.get("lecture", 0),
        plan.get("seminar", 0),
        0,
    ):
        raise RestoreError("official_workload_changed")
    assigned = {
        (a.activity, a.hours)
        for a in query("workload.TeacherAssignment", org, row=row, teacher_id=spec.AUTHOR, hours__gt=0)
    }
    if assigned != set(plan.items()):
        raise RestoreError("official_assignment_changed")
    return offering


def _no_links(org, syllabus):
    if (
        query("syllabus.SyllabusShare", org, syllabus=syllabus).exists()
        or query("syllabus.Syllabus", org, reused_from=syllabus).exists()
        or query("syllabus.SyllabusVersion", org, source_version__syllabus=syllabus).exists()
    ):
        raise RestoreError("dossier_shared_or_reused")


def _locked_versions(org, syllabus):
    return list(
        query("syllabus.SyllabusVersion", org, syllabus=syllabus).select_for_update(of=("self",)).order_by("pk")
    )


def check_base(org, case, offering, base):
    """MR-250: jurnalın göstərdiyi səhv (ingilis dilli) baza dosye — tək, təsdiqli, pinlənmiş məzmun."""
    pins = case["replace"]
    if (
        not base.is_active
        or base.author_id != spec.AUTHOR
        or base.offering_id is not None
        or base.period_id is not None
        or base.subject_id != offering.subject_id
        or base.reused_from_id is not None
    ):
        raise RestoreError("base_dossier_scope_changed")
    versions = _locked_versions(org, base)
    if [str(v.pk) for v in versions] != [pins["version_id"]]:
        raise RestoreError("base_dossier_versions_changed")
    (old,) = versions
    if (
        old.status != "approved"
        or old.approval_source != "migration"
        or str(base.approved_version_id) != pins["version_id"]
        or core.digest(section_data_map(old)) != pins["content_digest"]
    ):
        raise RestoreError("wrong_language_content_changed")
    _no_links(org, base)
    others = (
        core.model("registrar.CourseOffering")
        .objects.filter(organization=org, instructor_id=spec.AUTHOR, subject_id=base.subject_id, is_active=True)
        .exclude(pk=offering.pk)
        .select_related("organization")
    )
    if any(getattr(resolved_for(other), "pk", None) == base.pk for other in others):
        raise RestoreError("base_dossier_used_by_other_journal")
    return old


def check_blank_draft(org, offering, dossier):
    """MR-251: jurnalın öz dosyesi varsa YALNIZ müəllifin boş qaralaması ola bilər."""
    if (
        not dossier.is_active
        or dossier.author_id != spec.AUTHOR
        or dossier.subject_id != offering.subject_id
        or dossier.reused_from_id is not None
        or dossier.approved_version_id is not None
    ):
        raise RestoreError("journal_dossier_scope_changed")
    versions = _locked_versions(org, dossier)
    if len(versions) != 1 or versions[0].status != "draft" or versions[0].approval_source != "human":
        raise RestoreError("journal_dossier_not_single_draft")
    (draft,) = versions
    nonblank = {
        s["section_id"]
        for s in content_fingerprints(section_data_map(draft))["sections"]
        if s["nonblank_string_present"]
    }
    if not nonblank <= BLANK_DRAFT_NONBLANK:
        raise RestoreError("journal_draft_not_blank")
    if query("syllabus.SyllabusReview", org, version__syllabus=dossier).exists():
        raise RestoreError("journal_draft_has_review_history")
    _no_links(org, dossier)
    return draft


def dossier_plan(org, case, offering):
    """→ ``(action, dossier, retired_version)``; action ∈ replace | beside_blank_draft | create."""
    own = list(query("syllabus.Syllabus", org, offering=offering).select_for_update(of=("self",)))
    resolved = resolved_for(offering)
    if case["replace"]:
        base = query("syllabus.Syllabus", org, pk=case["replace"]["syllabus_id"]).select_for_update(of=("self",)).get()
        if own or resolved is None or resolved.pk != base.pk:
            raise RestoreError("journal_resolution_changed")
        return "replace", base, check_base(org, case, offering, base)
    if not own:
        return "create", None, None
    (dossier,) = own
    return "beside_blank_draft", dossier, check_blank_draft(org, offering, dossier)


def protected(org, offering):
    return journal_academic_fingerprint(organization_id=org.pk, offerings=[offering], exclude=PROTECTED_EXCLUDE)


def dossier_state(org, syllabus):
    versions = query("syllabus.SyllabusVersion", org, syllabus=syllabus).order_by("pk")
    return {
        "syllabus": core.metadata_digest(syllabus),
        "versions": {str(v.pk): core.metadata_digest(v) for v in versions},
        "content": {str(v.pk): core.digest(section_data_map(v)) for v in versions},
        "shares": query("syllabus.SyllabusShare", org).filter(Q(syllabus=syllabus)).count(),
    }
