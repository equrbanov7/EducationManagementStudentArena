"""``move_psixologiya_rows_20261115`` — Psixologiya fənlərini «Sosial iş kafedrası»nın 2026/2027 tapşırığından
«Psixologiya kafedrası»nın (yeni) tapşırığına köçürür (sahib 2026-11-15: «psixologiyanın fənləri də sosial iş
kafedrasında görünür»; qayda 2026-11-09: «fənn hansı kafedraya aiddirsə ora»).

Psixologiya kafedrasının 2026/2027 tapşırığı YOXDUR — bütün psixologiya sətirləri Sosial iş sənədindədir. Əmr:

* hədəf tapşırığı Sosial iş tapşırığının status / revision / göndərmə-bölgü sahələri ilə yaradır (varsa — onu
  götürür), köçən sətirlərin fakültələri üçün mənbənin cari dilimlərini (status, qərar) eyni ilə köçürür;
* hər sətir üçün qərar (ilk uyğun qayda): ``subject_chair`` — fənnin sahibi kafedra (``Subject.chair_unit``)
  Psixologiyadır / başqadır (qalır); ``psy_subject`` — fənnin adı psixologiyadır («psix…»); ``social_subject`` —
  sosial iş fənni (qalır); ``psy_teachers`` — bütün müəllimlərin ştat kafedrası Psixologiyadır;
  ``psy_specialty_vacant`` — müəllimsiz sətir, ixtisas psixologiya; qalanlar Sosial işdə qalır;
* patok ailəsi (eyni fənn + semestr + dövr, mühazirəsiz tərəfdaş və ya açıq bağ) BÖLÜNMÜR — aparıcı sətirlərin
  qərarı bütün ailəyə; aparıcılar razılaşmırsa ailə qalır;
* yalnız ``row.task`` dəyişir: bölgü, qrup, saat, jurnal, sillabus toxunulmaz (jurnal sahibliyi dəyişmir —
  açılış müəllimləri bölgüdən gəlir, bölgü silinmir). Başqa kafedranın müəllimi Psixologiyada ƏLAVƏ
  (``is_primary=False``) müəllim üzvlüyü alır (``join_chair_as_teacher`` — kafedra köçürməsi ilə eyni qayda).

Audit: hər sətir + bir xülasə sətri (``workload.task_row_move``). ``--undo`` xülasəyə görə sətirləri geri qaytarır,
əlavə üzvlükləri passivləşdirir, boş qalan yeni tapşırığı (dilimləri ilə) silir. Defolt dry-run; stdout-a YALNIZ
saylar (``psix_rows_move: açar=say``). Təkrar qaçış idempotentdir.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.audit import log_action, log_actions
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...constants import RowKind
from ...services.people import home_chairs, is_outside_teacher, join_chair_as_teacher

PREFIX = "psix_rows_move:"
RESOURCE = "workload.task_row_move"
APPLIED = "psix_rows_move_20261115"
UNDONE = "psix_rows_move_20261115_undo"
REASON = "Sahib 2026-11-15: psixologiya fənləri Sosial iş tapşırığından Psixologiya kafedrasının tapşırığına"
MEMBERSHIP_REASON = "workload.psix_rows_move_20261115: Psixologiya yükü — başqa kafedranın müəllimi (əlavə üzvlük)"

SOURCE_TASK = "a2415422-6b68-4752-920c-47502b6a5ae1"
SOSIAL_CHAIR = "30ab6eaf-ff06-4378-9800-1566a2cf3769"
PSIX_CHAIR = "98fdc9ab-c397-47f3-9f85-d77c9be19e29"

_PSY = re.compile(r"psix")
_SOCIAL = re.compile(
    r"sosial\s+i[şs]|sosial\s+siyas|sosial\s+müdafi|sosial\s+təminat|sosial\s+layih|keys\s+menecment|sosial\s+xidmət"
)
_TASK_COPY = ("status", "revision", "submitted_by_id", "submitted_at", "distributed_by_id", "distributed_at")
_SLICE_COPY = ("status", "submitted_at", "decided_by_id", "decided_at", "comment")


def _norm(text) -> str:
    return str(text or "").replace("İ", "i").replace("I", "ı").lower()


def _model(name):
    return django_apps.get_model(name)


def _rule(row, *, homes) -> str:
    """Sətrin qayda açarı; ``psy_*`` / ``subject_chair_psix`` — köçür, qalanlar — qalır."""
    subject = row.subject if row.subject_id else None
    if subject is not None and subject.chair_unit_id:
        return "subject_chair_psix" if str(subject.chair_unit_id) == PSIX_CHAIR else "subject_chair_other"
    name = _norm(subject.name if subject is not None else row.subject_text)
    if _PSY.search(name):
        return "psy_subject"
    if _SOCIAL.search(name):
        return "social_subject"
    teacher_ids = {a.teacher_id for a in row.assignments.all() if a.teacher_id}
    if teacher_ids:
        chairs = {(homes.get(pk) or {}).get("id") for pk in teacher_ids}
        return "psy_teachers" if chairs == {PSIX_CHAIR} else "other_teachers"
    specialty = _norm(row.specialty.name if row.specialty_id else row.specialty_text)
    return "psy_specialty_vacant" if _PSY.search(specialty) else "other_vacant"


def _moves(rule: str) -> bool:
    return rule.startswith("psy_") or rule == "subject_chair_psix"


def _is_partner(row) -> bool:
    return row.row_kind == RowKind.TEACHING and int(row.lecture_plan or 0) > 0 and int(row.lecture_total or 0) == 0


def plan(rows, *, homes, counts: Counter) -> list:
    """Köçəcək sətirlər (patok ailəsi bölünmür)."""
    decision = {}
    for row in rows:
        rule = _rule(row, homes=homes)
        counts["rule_" + rule] += 1
        decision[row.pk] = _moves(rule)
    families = defaultdict(list)
    for row in rows:
        if row.subject_id:
            families[(row.subject_id, row.season, row.period_id)].append(row)
    for family in families.values():
        if not any(_is_partner(r) or r.patok_lead_id for r in family) or len({decision[r.pk] for r in family}) == 1:
            continue
        leads = {decision[r.pk] for r in family if int(r.lecture_total or 0) > 0}
        aligned = len(leads) == 1
        verdict = next(iter(leads)) if aligned else False
        counts["patok_family_" + ("aligned" if aligned else "conflict_kept")] += 1
        for r in family:
            if decision[r.pk] != verdict:
                decision[r.pk] = verdict
                counts["patok_rows_realigned"] += 1
    return [row for row in rows if decision[row.pk]]


def _audit(*, organization, actor, obj=None, resource_id, old, new, reason):
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=obj,
        old_values=old,
        new_values=new,
        reason=reason,
        resource_type=RESOURCE,
        resource_id=str(resource_id),
    )


def _target_task(*, organization, actor, source, counts):
    TeachingTask = _model("workload.TeachingTask")
    target = (
        TeachingTask.objects.select_for_update()
        .filter(organization=organization, chair_id=PSIX_CHAIR, academic_year=source.academic_year)
        .first()
    )
    if target is not None:
        counts["target_task_existing"] += 1
        return target, False
    target = TeachingTask(
        organization=organization,
        chair_id=PSIX_CHAIR,
        academic_year=source.academic_year,
        created_by=actor,
        note=REASON,
        **{field: getattr(source, field) for field in _TASK_COPY},
    )
    target.save()
    counts["target_task_created"] += 1
    return target, True


def _copy_slices(*, organization, source, target, faculty_ids, counts) -> list:
    Slice = _model("workload.TaskFacultySlice")
    created = []
    for item in Slice.objects.filter(task=source, revision=source.revision, faculty_id__in=faculty_ids):
        if Slice.objects.filter(task=target, revision=target.revision, faculty_id=item.faculty_id).exists():
            counts["slices_existing"] += 1
            continue
        copy = Slice.objects.create(
            organization=organization,
            task=target,
            faculty_id=item.faculty_id,
            revision=target.revision,
            **{field: getattr(item, field) for field in _SLICE_COPY},
        )
        created.append(str(copy.pk))
        counts["slices_copied"] += 1
    return created


def _join_teachers(*, organization, actor, rows, counts) -> list:
    Membership = _model("organizations.Membership")
    chair = _model("organizations.OrgUnit").objects.get(organization=organization, pk=PSIX_CHAIR)
    teacher_ids = sorted({a.teacher_id for row in rows for a in row.assignments.all() if a.teacher_id})
    joined = []
    for teacher in get_user_model().objects.filter(pk__in=teacher_ids).order_by("pk"):
        if not is_outside_teacher(organization, chair, teacher):
            counts["teachers_already_in_chair"] += 1
            continue
        if join_chair_as_teacher(
            organization=organization, user=teacher, chair=chair, actor_user=actor, reason=MEMBERSHIP_REASON
        ):
            membership = Membership.objects.get(
                organization=organization, user=teacher, role__name="teacher", scope_unit=chair
            )
            joined.append(str(membership.pk))
            counts["memberships_added"] += 1
    return joined


def run(*, organization, actor, counts: Counter) -> None:
    TeachingTask = _model("workload.TeachingTask")
    TeachingTaskRow = _model("workload.TeachingTaskRow")
    source = TeachingTask.objects.select_for_update().filter(organization=organization, pk=SOURCE_TASK).first()
    if source is None or str(source.chair_id) != SOSIAL_CHAIR:
        raise CommandError("psix_rows_move_source_missing")
    if not _model("organizations.OrgUnit").objects.filter(organization=organization, pk=PSIX_CHAIR).exists():
        raise CommandError("psix_rows_move_target_chair_missing")
    rows = list(
        TeachingTaskRow.objects.select_for_update(of=("self",))
        .filter(organization=organization, task=source)
        .select_related("subject", "specialty")
        .prefetch_related("assignments")
        .order_by("pk")
    )
    counts["source_rows"] = len(rows)
    homes = home_chairs(organization, {a.teacher_id for row in rows for a in row.assignments.all() if a.teacher_id})
    chosen = plan(rows, homes=homes, counts=counts)
    counts["rows_to_move"] = len(chosen)
    counts["assignments_on_moved_rows"] = sum(len(row.assignments.all()) for row in chosen)
    if not chosen:
        return
    target, created = _target_task(organization=organization, actor=actor, source=source, counts=counts)
    slices = _copy_slices(
        organization=organization,
        source=source,
        target=target,
        faculty_ids={row.faculty_id for row in chosen if row.faculty_id},
        counts=counts,
    )
    memberships = _join_teachers(organization=organization, actor=actor, rows=chosen, counts=counts)
    log_actions(
        {
            "action": AuditAction.UPDATE,
            "user": actor,
            "organization": organization,
            "obj": row,
            "old_values": {"task": str(source.pk)},
            "new_values": {"task": str(target.pk)},
            "reason": REASON,
            "resource_type": RESOURCE,
            "resource_id": str(row.pk),
        }
        for row in chosen
    )
    moved = TeachingTaskRow.objects.filter(pk__in=[row.pk for row in chosen], task=source).update(task=target)
    counts["rows_moved"] = moved
    _audit(
        organization=organization,
        actor=actor,
        obj=target,
        resource_id=target.pk,
        old={"task": str(source.pk)},
        new={
            "rows": [str(row.pk) for row in chosen],
            "memberships": memberships,
            "slices": slices,
            "task_created": created,
        },
        reason=APPLIED,
    )


def undo(*, organization, actor, counts: Counter) -> None:
    AuditLog = _model("audit.AuditLog")
    TeachingTask = _model("workload.TeachingTask")
    receipts = list(
        AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason__in=(APPLIED, UNDONE))
        .order_by("created_at", "pk")
        .values("pk", "reason", "resource_id", "new_values")
    )
    undone = {str((r["new_values"] or {}).get("receipt")) for r in receipts if r["reason"] == UNDONE}
    pending = [r for r in receipts if r["reason"] == APPLIED and str(r["pk"]) not in undone]
    if not pending:
        counts["nothing_to_undo"] += 1
        return
    source = TeachingTask.objects.select_for_update().filter(organization=organization, pk=SOURCE_TASK).first()
    if source is None:
        raise CommandError("psix_rows_move_source_missing")
    for receipt in reversed(pending):
        data = receipt["new_values"] or {}
        target = TeachingTask.objects.select_for_update().filter(organization=organization, pk=receipt["resource_id"])
        target = target.first()
        if target is not None:
            back = _model("workload.TeachingTaskRow").objects.filter(
                organization=organization, task=target, pk__in=data.get("rows") or []
            )
            counts["rows_returned"] += back.update(task=source)
        counts["memberships_deactivated"] += (
            _model("organizations.Membership")
            .objects.filter(organization=organization, pk__in=data.get("memberships") or [], is_active=True)
            .update(is_active=False)
        )
        if target is not None and data.get("task_created") and not target.rows.exists():
            target.slices.all().delete()
            target.delete()
            counts["target_task_deleted"] += 1
        _audit(
            organization=organization,
            actor=actor,
            resource_id=receipt["resource_id"],
            old={"task": receipt["resource_id"]},
            new={"receipt": str(receipt["pk"]), "task": str(source.pk)},
            reason=UNDONE,
        )
        counts["receipts_undone"] += 1


class Command(BaseCommand):
    help = "Psixologiya fənlərini Sosial iş tapşırığından Psixologiya kafedrasının tapşırığına köçürür (dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Əvvəlki köçürməni geri qaytar")

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=str(options["actor"]).strip(), is_active=True, is_superuser=True)
            .first()
        )
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        Organization = _model("organizations.Organization")
        counts: Counter = Counter()
        try:
            with rls_worker_atomic(), bypass_rls():
                organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
                if organization is None:
                    raise CommandError("psix_rows_move_organization_unknown")
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
                with transaction.atomic():
                    (undo if options["undo"] else run)(organization=organization, actor=actor, counts=counts)
                    if not options["apply"]:
                        transaction.set_rollback(True)
        except CommandError:
            raise
        except Exception as exc:  # prod-data-ops traceback göstərmir — yalnız kod
            raise CommandError("psix_rows_move_failed_" + type(exc).__name__.lower()) from exc
        mode = ("undo_" if options["undo"] else "") + ("apply" if options["apply"] else "dry_run")
        self.stdout.write(f"{PREFIX} mode={mode}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
