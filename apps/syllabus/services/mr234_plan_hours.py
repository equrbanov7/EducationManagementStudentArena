"""MR-000234: Yeganə Hidayətovanın «Xarici dil-2» sillabusunda plan saatı yoxdur → cədvəl 16 sətirdə kəsilir.

Səbəb (MR-000145-də də görünən «16 sətirdən sonra x»): baza dosyedə (semestrsiz, köhnə sistemdən) ``plan_hours``
boşdur; ``week_plan.expected_week_rows({})`` = 0 → redaktor köhnə 16 sətirlik görünüşə düşür, 38 mövzunun 17–38-i
«plandan artıq» damğası alır. 434 R üçün səbəb başqa idi (``MAX_WEEK_ROWS`` 40 → 80, kod düzəlişi 2ffc5789f).
Eyni qrupun ikinci müəllimi Aytac Salmanlının 935 BM ing sillabusunda plan ``{"seminar": 75}`` (yükdən) var —
38 sətir. Düzəliş eynidir: kafedranın «Plan saatını düzəlt» yolu (``set_plan_hours_override``) ilə dosyeyə
``{"seminar": 75}``; bölmələrə (müəllimin həftəlik bölgüsünə) TOXUNULMUR.

Mənbə: köhnə jurnal 14383 (Yeganə, 935 ing, 75 s) → sillabus 6339 «Xarici dil-2» (75 s, 38 mövzu); yeni sistemdə
bu sillabus müəllimin QKU-539 baza dosyesidir. Rəsmi yük: 935 BM ing sətri (iki müəllim × seminar 75).
Defolt dry-run; yazı yalnız dry-run-ın ``baseline``-ı ilə; ``undo`` plan saatlarını əvvəlki (boş) halına qaytarır.
"""

import hashlib
import json

from django.apps import apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import EDITABLE_STATUSES, SyllabusStatus
from .drafts import recompute_completion, section_data_map
from .offerings import syllabus_for_offering
from .plan_override import set_plan_hours_override
from .reuse_rules import normalize_hours
from .scoping import resolve_actor

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
SYLLABUS = "9349c841-530f-4f5b-9d62-2c2101eb08d3"
APPROVED = "710d23f3-1e70-4677-82d5-2a286df21ea9"
AUTHOR = 8227
SUBJECT = "84b3654f-bf5d-497f-b351-a37e3c6f1f78"
TOPICS = 38
HOURS = {"seminar": 75}
REFERENCE_OFFERING = "9b213b20-2f8a-459d-ad20-841bfebdbcaf"
REFERENCE_SYLLABUS = "22e0b830-89a6-4328-a683-4d6864490ad7"
REFERENCE_AUTHOR = 8361
WORKLOAD_ROW = "33e875f2-b60c-4daa-81e4-92edf5ca2fca"
RESOURCE = "syllabus.mr234_plan_hours"
REASON = "MR-000234: «Xarici dil-2» plan saatı eyni qrupun (935 BM ing) rəsmi yükü ilə — seminar 75"


class MR234Error(ValueError):
    pass


def model(label):
    return apps.get_model(label)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _meta(obj):
    return {field.attname: getattr(obj, field.attname) for field in obj._meta.concrete_fields}


def _live_versions(syllabus):
    Version = model("syllabus.SyllabusVersion")
    rows = Version.objects.select_for_update(of=("self",)).filter(syllabus=syllabus).order_by("pk")
    return [v for v in rows if v.status != SyllabusStatus.ARCHIVED.value]


def _reference(org):
    """Eyni qrupun yükü və Aytac Salmanlının 935 BM ing sillabusu hələ də seminar 75-dir."""
    offering = model("registrar.CourseOffering").objects.get(pk=REFERENCE_OFFERING, organization=org)
    reference = model("syllabus.Syllabus").objects.select_related("approved_version").get(pk=REFERENCE_SYLLABUS)
    share = model("registrar.JournalShare").objects.filter(
        organization=org, offering=offering, teacher_id=AUTHOR, is_active=True
    )
    row = model("workload.TeachingTaskRow").objects.filter(pk=WORKLOAD_ROW, organization=org).first()
    assignment = model("workload.TeacherAssignment").objects.filter(
        organization=org, row=row, teacher_id=AUTHOR, activity="seminar", hours=HOURS["seminar"]
    )
    if (
        not offering.is_active
        or offering.lesson_hours != HOURS["seminar"]
        or offering.instructor_id != REFERENCE_AUTHOR
        or reference.offering_id != offering.pk
        or not reference.is_active
        or reference.approved_version is None
        or normalize_hours(reference.approved_version.plan_hours) != HOURS
        or not share.exists()
        or row is None
        or row.seminar_plan != HOURS["seminar"]
        or not assignment.exists()
    ):
        raise MR234Error("reference_group_plan_changed")
    return {"offering": _meta(offering), "reference": _meta(reference), "row": _meta(row)}


def _capture(org, syllabus, versions):
    return {
        "syllabus": _meta(syllabus),
        "versions": [_meta(v) for v in versions],
        "sections": {str(v.pk): section_data_map(v) for v in versions},
        "reference": _reference(org),
    }


def _dossier_hash(captured):
    """Undo yalnız dosyenin özünə baxır — istinad jurnalının sonrakı adi dəyişikliyi geri qaytarmanı bağlamır."""
    return digest({key: captured[key] for key in ("syllabus", "versions", "sections")})


def _sharing_journals(org, syllabus):
    """Bu baza dosyeni göstərən digər jurnalların sayı (yalnız məlumat üçün; çıxışda görünür)."""
    offerings = model("registrar.CourseOffering").objects.filter(
        organization=org, instructor_id=AUTHOR, subject_id=SUBJECT, is_active=True
    )
    return sum(
        1
        for o in offerings
        if getattr(
            syllabus_for_offering(
                organization=org,
                offering_id=o.pk,
                subject_id=o.subject_id,
                period_id=o.period_id,
                instructor_id=o.instructor_id,
            ),
            "pk",
            None,
        )
        == syllabus.pk
    )


def _scope(org, syllabus, versions, *, expected_hours):
    if (
        not syllabus.is_active
        or syllabus.author_id != AUTHOR
        or str(syllabus.subject_id) != SUBJECT
        or syllabus.offering_id is not None
        or syllabus.period_id is not None
        or syllabus.reused_from_id is not None
        or normalize_hours(syllabus.plan_hours_override) != expected_hours
    ):
        raise MR234Error("dossier_scope_changed")
    approved = [v for v in versions if v.status == SyllabusStatus.APPROVED.value]
    opened = [v for v in versions if v.status != SyllabusStatus.APPROVED.value]
    if [str(v.pk) for v in approved] != [APPROVED] or len(opened) > 1:
        raise MR234Error("dossier_versions_changed")
    if any(normalize_hours(v.plan_hours) != expected_hours for v in versions):
        raise MR234Error("plan_hours_changed")
    rows = section_data_map(approved[0]).get("week", {}).get("rows", [])
    if (
        len(rows) != TOPICS
        or sum(bool(str(r.get("topic") or "").strip()) for r in rows if isinstance(r, dict)) != TOPICS
    ):
        raise MR234Error("week_topics_changed")


def _receipt(org):
    logs = model("audit.AuditLog").objects.filter(organization_id=org.pk, resource_id=SYLLABUS)
    return (
        logs.filter(resource_type=RESOURCE).order_by("-created_at").first(),
        logs.filter(resource_type=RESOURCE + ".undo").order_by("-created_at").first(),
    )


@transaction.atomic
def repair_mr234_plan_hours(*, organization, user, apply=False, expected_baseline="", undo=False):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise MR234Error("fixed_tenant_active_superadmin_required")
    syllabus = model("syllabus.Syllabus").objects.select_for_update().get(pk=SYLLABUS, organization=organization)
    versions = _live_versions(syllabus)
    receipt, undone = _receipt(organization)
    applied = receipt is not None and (undone is None or undone.created_at < receipt.created_at)
    if not undo and applied:
        _scope(organization, syllabus, versions, expected_hours=HOURS)
        return {"already_present": 1}
    if undo and not applied:
        return {"already_undone": 1} if receipt else {"nothing_to_undo": 1}
    _scope(organization, syllabus, versions, expected_hours=HOURS if undo else {})
    before = _capture(organization, syllabus, versions)
    baseline = digest(before)
    if undo and _dossier_hash(before) != receipt.new_values.get("after_hash"):
        raise MR234Error("undo_live_state_changed")
    if expected_baseline and expected_baseline != baseline:
        raise MR234Error("live_baseline_changed")
    result = {"baseline": baseline, "sharing_journals": _sharing_journals(organization, syllabus)}
    if not apply:
        result["versions_to_restore" if undo else "versions_to_plan"] = len(versions)
        return result
    if not expected_baseline:
        raise MR234Error("fresh_live_baseline_required")
    if undo:
        Version = model("syllabus.SyllabusVersion")
        model("syllabus.Syllabus").objects.filter(pk=SYLLABUS).update(plan_hours_override={})
        for item in receipt.new_values["versions"]:
            version = Version.objects.get(pk=item["id"], syllabus=syllabus)
            Version.objects.filter(pk=version.pk).update(plan_hours=item["old"])
            if version.status in EDITABLE_STATUSES:
                version.refresh_from_db()
                recompute_completion(version)
        touched = receipt.new_values["versions"]
    else:
        old = {str(v.pk): dict(v.plan_hours or {}) for v in versions}
        done = set_plan_hours_override(syllabus=syllabus, hours=HOURS, actor=resolve_actor(user, organization))
        if done["effective"] != HOURS or len(done["versions"]) != len(versions):
            raise MR234Error("plan_override_incomplete")
        touched = [{"id": key, "old": value} for key, value in old.items()]
    syllabus.refresh_from_db()
    after_versions = _live_versions(syllabus)
    _scope(organization, syllabus, after_versions, expected_hours={} if undo else HOURS)
    if [section_data_map(v) for v in after_versions] != [before["sections"][str(v.pk)] for v in versions]:
        raise MR234Error("section_content_changed")
    after = _dossier_hash(_capture(organization, syllabus, after_versions))
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE + (".undo" if undo else ""),
        resource_id=SYLLABUS,
        resource_repr=f"{SUBJECT} plan_hours",
        reason=REASON,
        new_values={"versions": touched, "before_hash": baseline, "after_hash": after, "hours": HOURS},
    )
    return {"versions_restored" if undo else "versions_planned": len(touched), "baseline": baseline}
