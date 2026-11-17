"""``move_ekologiya_rows_20261117`` — Ekologiya fənlərini «Yer kadastrı və meşəçilik kafedrası»nın 2026/2027
tapşırığından «Ekologiya və ətraf mühit kafedrası»nın (yeni) tapşırığına köçürür (MR-000475, sahib 2026-11-17:
«düzəlt bunu»; qayda 2026-11-09: «fənn hansı kafedraya aiddirsə ora»).

2026-10-15 idxalında «Ekologiya» vərəqi Yer kadastrına yazılıb — Ekologiya kafedrasının 2026/2027 tapşırığı YOXDUR.
Mexanizm ``move_psixologiya_rows_20261115`` ilə eynidir (hədəf tapşırıq mənbənin status/revision/dilimləri ilə,
yalnız ``row.task`` dəyişir, kənar müəllim ƏLAVƏ üzvlük alır, patok ailəsi bölünmür, ``--undo``). Qərar (ilk uyğun):
``subject_chair`` — ``Subject.chair_unit`` Ekologiyadır (köçür) / başqadır (qalır); ``explicit`` — açıq siyahı
(MR-000475 Ülkər Qədiyevanın qarışıq müəllimli «Ekoloji monitorinq» sətri); ``eko_teachers`` — bütün müəllimlərin ştat
kafedrası Ekologiyadır; qalanlar (vakant və başqa kafedra müəllimli) Yer kadastrında qalır.
Stdout-a YALNIZ saylar (``eko_rows_move: açar=say``).
"""

from __future__ import annotations

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

PREFIX = "eko_rows_move:"
RESOURCE = "workload.task_row_move"
APPLIED = "eko_rows_move_20261117"
UNDONE = "eko_rows_move_20261117_undo"
REASON = "MR-000475 (sahib 2026-11-17): ekologiya fənləri Yer kadastrı tapşırığından Ekologiya kafedrasının tapşırığına"
MEMBERSHIP_REASON = "workload.eko_rows_move_20261117: Ekologiya yükü — başqa kafedranın müəllimi (əlavə üzvlük)"

SOURCE_TASK = "f9e57565-648f-4365-b533-db04007796d2"
SOURCE_CHAIR = "6cb37f21-4d0f-4858-8c53-1f09d4d0efda"  # Yer kadastrı və meşəçilik
EKO_CHAIR = "f6b0f99c-5367-438f-9db0-924f3b92c7e7"  # Ekologiya və ətraf mühit
#: Qarışıq müəllimli, amma ekologiya kafedrasının sətri (MR-000475: Ülkər Qədiyeva — «Ekoloji monitorinq» 233 EKO ing).
EXPLICIT_ROWS = frozenset({"a798e86f"})
_TASK_COPY = ("status", "revision", "submitted_by_id", "submitted_at", "distributed_by_id", "distributed_at")
_SLICE_COPY = ("status", "submitted_at", "decided_by_id", "decided_at", "comment")


def _model(name):
    return django_apps.get_model(name)


def _rule(row, *, homes) -> str:
    """Sətrin qayda açarı; ``subject_chair_eko`` / ``explicit`` / ``eko_teachers`` — köçür, qalanlar — qalır."""
    if str(row.pk)[:8] in EXPLICIT_ROWS:  # mənbə tapşırığının 185 sətri arasında 8 simvollu prefiks unikaldır
        return "explicit"
    subject = row.subject if row.subject_id else None
    if subject is not None and subject.chair_unit_id:
        return "subject_chair_eko" if str(subject.chair_unit_id) == EKO_CHAIR else "subject_chair_other"
    teacher_ids = {a.teacher_id for a in row.assignments.all() if a.teacher_id}
    if not teacher_ids:
        return "vacant"
    chairs = {(homes.get(pk) or {}).get("id") for pk in teacher_ids}
    return "eko_teachers" if chairs == {EKO_CHAIR} else "other_teachers"


def _moves(rule: str) -> bool:
    return rule in {"subject_chair_eko", "explicit", "eko_teachers"}


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
        .filter(organization=organization, chair_id=EKO_CHAIR, academic_year=source.academic_year)
        .first()
    )
    if target is not None:
        counts["target_task_existing"] += 1
        return target, False
    target = TeachingTask(
        organization=organization,
        chair_id=EKO_CHAIR,
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
    chair = _model("organizations.OrgUnit").objects.get(organization=organization, pk=EKO_CHAIR)
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
    if source is None or str(source.chair_id) != SOURCE_CHAIR:
        raise CommandError("eko_rows_move_source_missing")
    if not _model("organizations.OrgUnit").objects.filter(organization=organization, pk=EKO_CHAIR).exists():
        raise CommandError("eko_rows_move_target_chair_missing")
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
        raise CommandError("eko_rows_move_source_missing")
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
    help = "MR-000475: ekologiya fənlərini Yer kadastrı tapşırığından Ekologiya kafedrasının tapşırığına köçürür (dry-run)."

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
                    raise CommandError("eko_rows_move_organization_unknown")
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
                with transaction.atomic():
                    (undo if options["undo"] else run)(organization=organization, actor=actor, counts=counts)
                    if not options["apply"]:
                        transaction.set_rollback(True)
        except CommandError:
            raise
        except Exception as exc:  # prod-data-ops traceback göstərmir — yalnız kod
            raise CommandError("eko_rows_move_failed_" + type(exc).__name__.lower()) from exc
        mode = ("undo_" if options["undo"] else "") + ("apply" if options["apply"] else "dry_run")
        self.stdout.write(f"{PREFIX} mode={mode}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
