"""recover_legacy_syllabi_20261107 canlı vəziyyət qapıları — jurnal, rəsmi plan, dosye; burada heç nə yazılmır.

Prod snapshot-dan fərqlənə bilər (PR #232, 11-07 yük düzəlişləri), ona görə hər qapı hədəfi TƏK-TƏK keçir
(:class:`Skip` + kod → ``skipped_<kod>`` sayı); qalan hədəflər işlənməyə davam edir.
"""

from django.db.models import Q
from django.utils import timezone

from apps.registrar.public import plan_hours_for_offering
from apps.syllabus.public import content_fingerprints, section_data_map, syllabus_for_offering
from apps.workload.public import journal_academic_fingerprint

from . import exact_syllabus_recovery as core
from .legacy_syllabi_20261107_plan import plan_of, week_hours

RestoreError = core.RestoreError
#: Akademik məzmun (dərs, xana, qeydiyyat, qiymət…) — sillabus cədvəlləri xaricində heç nə dəyişməməlidir.
PROTECTED_EXCLUDE = ("syllabus", "syllabus_share", "version", "section", "review")
#: Boş qaralamada yalnız «info» bölməsində avtomatik dəyər (müəllim adı, dil, saat) ola bilər.
BLANK_DRAFT_NONBLANK = {"info"}


class Skip(Exception):
    """Hədəf bu icrada işlənmir (canlı vəziyyət plana uyğun deyil) — ``skipped_<code>`` sayılır."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def query(label, org, **filters):
    return core.model(label).objects.filter(organization=org, **filters)


def resolved_for(offering):
    return syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


def _offering(org, plan, target):
    offerings = (
        core.model("registrar.CourseOffering")
        .objects.select_for_update(of=("self",))
        .select_related("subject", "period", "organization")
        .filter(organization=org)
    )
    if target["offering_id"]:
        offering = offerings.filter(pk=target["offering_id"]).first()
    else:
        found = list(
            offerings.filter(
                period_id=plan["period_id"],
                group_id=target["group_id"],
                subject_id__in=target["subject_ids"],
                is_active=True,
            ).order_by("pk")
        )
        if len(found) > 1:
            raise Skip("journal_ambiguous")
        offering = found[0] if found else None
    if offering is None:
        raise Skip("journal_missing")
    return offering


def offering_scope(org, plan, target):
    """Hədəf jurnal: aktiv, cari açıq semestr; müəllim, qrup, fənn, saat və RƏSMİ plan pinlə eynidir."""
    offering = _offering(org, plan, target)
    period = offering.period
    checks = (
        (offering.is_active, "journal_inactive"),
        (str(offering.period_id) == plan["period_id"], "period_changed"),
        (
            period.is_active
            and period.locked_at is None
            and period.start_date <= timezone.localdate() <= period.end_date,
            "period_closed",
        ),
        (offering.instructor_id == target["teacher"], "teacher_changed"),
        (str(offering.group_id) == target["group_id"], "group_changed"),
        (str(offering.subject_id) in target["subject_ids"], "subject_changed"),
        (offering.lesson_hours == target["lesson_hours"], "hours_changed"),
    )
    for ok, code in checks:
        if not ok:
            raise Skip(code)
    author = core.model("auth.User").objects.filter(pk=target["teacher"], is_active=True).first()
    profile = core.model("accounts.UserProfile").objects.filter(user_id=target["teacher"], organization=org).first()
    if author is None or profile is None or profile.access_state != "active":
        raise Skip("author_inactive")
    if plan_of(plan_hours_for_offering(offering)) != target["plan"]:
        raise Skip("plan_changed")
    return offering


def links(org, syllabus):
    """Dosye başqa jurnala paylaşılıb / təkrar istifadə olunubsa — məzmunu buradan dəyişmək olmaz."""
    return (
        query("syllabus.SyllabusShare", org, syllabus=syllabus).exists()
        or query("syllabus.Syllabus", org, reused_from=syllabus).exists()
        or query("syllabus.SyllabusVersion", org, source_version__syllabus=syllabus).exclude(syllabus=syllabus).exists()
    )


def live_versions(org, syllabus):
    return list(
        query("syllabus.SyllabusVersion", org, syllabus=syllabus)
        .exclude(status="archived")
        .select_for_update(of=("self",))
        .order_by("pk")
    )


def _blank_draft(org, version):
    if version.status != "draft" or version.approval_source != "human":
        return False
    nonblank = {
        s["section_id"]
        for s in content_fingerprints(section_data_map(version))["sections"]
        if s["nonblank_string_present"]
    }
    return nonblank <= BLANK_DRAFT_NONBLANK and not query("syllabus.SyllabusReview", org, version=version).exists()


def retirable(org, dossier):
    """Arxivə keçəcək versiyalar: köçürülmüş TƏSDİQLİ + müəllifin BOŞ qaralaması. Başqa hər şey müəllimin işidir."""
    out = []
    for version in live_versions(org, dossier):
        if version.status == "approved" and version.approval_source == "migration":
            out.append((version, "approved"))
        elif _blank_draft(org, version):
            out.append((version, "draft"))
        else:
            raise Skip("teacher_content")
    return out


def same_content(version, digest, plan):
    return (
        version is not None
        and version.status == "approved"
        and core.digest(section_data_map(version)) == digest
        and plan_of(version.plan_hours) == plan
    )


def restore_plan(org, target, source, offering):
    """→ ``(action, dossier, retire)``; action ∈ create | replace | already_ok."""
    own = list(query("syllabus.Syllabus", org, offering=offering).select_for_update(of=("self",)))
    shown = resolved_for(offering)
    digest = source["content_sha256"]
    if not own:
        if (
            shown is not None
            and shown.author_id == target["teacher"]
            and same_content(shown.approved_version, digest, target["plan"])
        ):
            return "already_ok", shown, []
        return "create", None, []
    (dossier,) = own
    if not dossier.is_active:
        raise Skip("dossier_inactive")
    if dossier.subject_id != offering.subject_id or dossier.period_id not in (None, offering.period_id):
        raise Skip("dossier_scope")
    if shown is None or shown.pk != dossier.pk:
        raise Skip("dossier_not_shown")
    if same_content(dossier.approved_version, digest, target["plan"]) and dossier.current_version_id == (
        dossier.approved_version_id
    ):
        return "already_ok", dossier, []
    if dossier.author_id != target["teacher"]:
        raise Skip("dossier_author")
    if links(org, dossier):
        raise Skip("dossier_shared")
    return "replace", dossier, retirable(org, dossier)


def base_to_retire(org, target, offering):
    """MR-250 tipli: jurnalın əvvəl göstərdiyi SƏHV baza dosye — tək, pinlənmiş, başqa jurnalda görünmür."""
    pins = target.get("retire_base")
    if not pins:
        return None
    base = query("syllabus.Syllabus", org, pk=pins["syllabus_id"]).select_for_update(of=("self",)).first()
    if (
        base is None
        or not base.is_active
        or base.author_id != target["teacher"]
        or base.offering_id is not None
        or base.period_id is not None
        or base.subject_id != offering.subject_id
        or links(org, base)
    ):
        return None
    versions = live_versions(org, base)
    if [str(v.pk) for v in versions] != [pins["version_id"]]:
        return None
    (old,) = versions
    if (
        old.status != "approved"
        or old.approval_source != "migration"
        or core.digest(section_data_map(old)) != pins["content_digest"]
    ):
        return None
    others = (
        core.model("registrar.CourseOffering")
        .objects.filter(organization=org, instructor_id=target["teacher"], subject_id=base.subject_id, is_active=True)
        .exclude(pk=offering.pk)
        .select_related("organization")
    )
    if any(getattr(resolved_for(other), "pk", None) == base.pk for other in others):
        return None
    return old


def plan_versions(org, target, offering):
    """``plan_sync``: jurnalın ÖZ təsdiqli dosyesi → ``(dossier, [plan saatı fərqli versiyalar], week_gap)``."""
    shown = resolved_for(offering)
    if shown is None:
        raise Skip("no_syllabus")
    if shown.offering_id != offering.pk:
        raise Skip("not_own_dossier")
    approved = shown.approved_version
    if approved is None or approved.status != "approved":
        raise Skip("not_approved")
    if plan_of(shown.plan_hours_override):
        raise Skip("plan_override")
    gap = week_hours(section_data_map(approved)) != target["plan"]
    if gap and not target.get("week_gap_ok"):
        raise Skip("week_hours_mismatch")
    stale = [v for v in live_versions(org, shown) if plan_of(v.plan_hours) != target["plan"]]
    if stale and links(org, shown):
        raise Skip("dossier_shared")
    return shown, stale, gap


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


def chair_for(org, offering, author_id):
    if offering.subject.chair_unit_id:
        return offering.subject.chair_unit
    membership = (
        core.model("organizations.Membership")
        .objects.filter(organization=org, user_id=author_id, is_active=True, scope_unit__unit_type="chair")
        .select_related("scope_unit")
        .order_by("pk")
        .first()
    )
    return membership.scope_unit if membership else None
