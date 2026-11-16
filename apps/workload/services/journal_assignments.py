"""Read-only teacher journal identity from positive, released workload assignments."""

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Prefetch, Q

from core.group_identity import canonical_aliases

from ..constants import Activity, RowKind, TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from .offering_shares import KINDS, _assignment_group
from .patok import taught_partner_rows


def _registered_children(organization, groups):
    """Only explicit same-tenant split pointers, never name guesses or sector mixing."""
    parents = {str(group.pk): group for group in groups}
    found = defaultdict(list)
    candidates = django_apps.get_model("organizations", "OrgUnit").objects.filter(
        organization=organization, is_active=True, unit_type="group", settings__parent_group__in=list(parents)
    )
    for child in candidates:
        parent = parents.get(str((child.settings or {}).get("parent_group")))
        if parent is None or child.pk == parent.pk or child.parent_id != parent.parent_id:
            continue
        if any(
            (child.settings or {}).get(key)
            and (parent.settings or {}).get(key)
            and (child.settings or {}).get(key) != (parent.settings or {}).get(key)
            for key in ("sector", "language", "degree_level", "education_form")
        ):
            continue
        found[parent.pk].append(child)
    return found


def _assignment_map(*, organization, teacher_id, include_hours=False):
    """Canonical (subject, period, group) → kinds; (None, None, id) is an exact intensive offering.

    Draft/cancelled/vacant/zero-hour entries and ambiguous free-text subgroup notes
    supply no current journal; on a single-group row such a note names a part of that
    one group, never its registered children. Physical subgroup IDs remain distinct. Explicit
    managed logical aliases are folded without altering any historical FK.
    """
    if organization is None or teacher_id is None:
        return {}
    assignments = TeacherAssignment.objects.filter(
        organization=organization, teacher_id=teacher_id, hours__gt=0, activity__in=KINDS
    )
    released = Q(task__status__in=(TaskStatus.APPROVED, TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)) | Q(
        task__status=TaskStatus.DISTRIBUTING, task__submitted_at__isnull=False
    )
    # Authorized intensive creation opens its own explicit journal immediately,
    # independently of the ordinary chair-plan approval lifecycle.
    intensive = Q(row_kind=RowKind.INTENSIVE, intensive_offering__is_active=True) & ~Q(
        task__status=TaskStatus.CANCELLED
    )
    # Sahib 2026-11-08: açıq bağlı patok tərəfdaşı (``patok_lead`` → bu müəllimin mühazirə apardığı sətir) — öz
    # bölgüsü olmasa da mühazirəçinin jurnalıdır (alt sorğu; sorğu sayı dəyişmir).
    lectured = assignments.filter(activity=Activity.LECTURE).values("row_id")
    rows = list(
        TeachingTaskRow.objects.filter(organization=organization, task__organization=organization)
        .filter(Q(pk__in=assignments.values("row_id")) | Q(patok_lead_id__in=lectured))
        .filter(released | intensive)
        .select_related("task", "intensive_offering")
        .prefetch_related("groups", Prefetch("assignments", queryset=assignments, to_attr="journal_assignments"))
        .distinct()
    )
    # Patokun ikinci/üçüncü qrupu: mühazirəsi bu müəllimin aparıcı sətrindədir (sahib 2026-11-07, :mod:`.patok`).
    partners = taught_partner_rows(rows, teacher_id, owns=lambda row: bool(row.journal_assignments))
    groups = [group for row in rows for group in row.groups.all()]
    children = _registered_children(organization, groups) if groups else {}
    aliases = canonical_aliases(groups)
    result = defaultdict(lambda: defaultdict(int)) if include_hours else defaultdict(set)
    caps: dict = {}
    per_row = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if row.row_kind == RowKind.INTENSIVE:
            offering = row.intensive_offering
            if (
                offering is not None
                and offering.is_active
                and offering.is_intensive
                and offering.organization_id == organization.pk
                and offering.subject_id == row.subject_id
                and offering.period_id == row.period_id
            ):
                for assignment in row.journal_assignments:
                    key = (None, None, offering.pk)
                    if include_hours:
                        result[key][assignment.activity] += assignment.hours
                    else:
                        result[key].add(assignment.activity)
            continue
        row_groups = list(row.groups.all())
        known = row_groups + [child for group in row_groups for child in children.get(group.pk, ())]
        for parent in row_groups:
            if parent.organization_id != organization.pk:
                continue
            for group in (parent, *children.get(parent.pk, ())):
                canonical = aliases.get(group.pk, group)
                for assignment in row.journal_assignments:
                    applies = _assignment_group(assignment, row, group, known_groups=known)
                    if group.pk != parent.pk:
                        applies = (
                            applies is True or _assignment_group(assignment, row, parent, known_groups=known) is True
                        )
                    elif applies is None and len(row_groups) == 1:
                        # MR123 (2026-11-02): tək qruplu sətirdə sərbəst qeyd («935 ing» səviyyəsi)
                        # yalnız həmin qrupun özüdür — alt qrupa yayılmır; siyahı yenə sahib/pay tələb edir.
                        applies = True
                    if applies is True:
                        key = (row.subject_id, row.period_id, canonical.pk)
                        if include_hours:
                            per_row[(key, row.pk)][assignment.activity] += assignment.hours
                            share = _group_subgroups(row, row_groups, parent, group, children)
                            _cap(caps, (key, row.pk), row, assignment, share)
                        else:
                            result[key].add(assignment.activity)
    if include_hours:
        # Sahib 2026-11-08: jurnal BİR qrupundur — başlıqda fənnin qrup başına saatı (L30 + S10 + Lab5 = 45), müəllimin
        # bütün axınlar üzrə yükü (30 + 2×10 + 3×5 = 65) yox. Bölgü saatı HƏR SƏTRİN ``*_plan``-ı ilə məhdudlaşır,
        # sonra sətirlər toplanır: 2026-11-12 (135 TSPX) seminar iki sətirdə (TSPX-1 30 + TSPX-2 30) → 60, 30 yox.
        for (key, _row_pk), kinds in per_row.items():
            limits = caps.get((key, _row_pk), {})
            for activity, hours in kinds.items():
                limit = limits.get(activity)
                result[key][activity] += min(hours, limit) if limit else hours
    for row in partners:
        for parent in row.groups.all():
            if parent.organization_id != organization.pk:
                continue
            for group in (parent, *children.get(parent.pk, ())):
                key = (row.subject_id, row.period_id, aliases.get(group.pk, group).pk)
                if include_hours:
                    result[key]["lecture"] = max(result[key]["lecture"], int(row.lecture_plan))
                else:
                    result[key].add("lecture")
    return dict(result)


_PLAN_FIELDS = {Activity.LECTURE: "lecture_plan", Activity.SEMINAR: "seminar_plan", Activity.LAB: "lab_plan"}


def _group_subgroups(row, row_groups, parent, group, children) -> int | None:
    """Bu qrupun sətirdəki REAL alt qrup sayı; tək qruplu sətirdə ``None`` (sətrin ``subgroup_count``-u keçərlidir).

    MR-000383 (2026-11-16, 234 BİO/SBİO Mikrobiologiya lab): 3 lab alt qrupu 2 qrupa ``ceil(3 ÷ 2) = 2`` ilə
    bölünürdü — tək alt qruplu qrupun jurnalı da 2 × plan (60, 30 yox) göstərirdi. Sahib 2026-11-08: lab həddi qrup
    başına plandır, alt qrupa yalnız REAL say qədər vurulur. Mənbə sırası:

    * qrupun özü qeydiyyatlı alt qrupdursa (``parent_group``) — 1;
    * qrupun qeydiyyatlı alt qrupları varsa — onların sayı;
    * qalan qruplar sətrin qalan alt qruplarını yalnız BƏRABƏR bölünəndə paylaşır (4 ÷ 2 = 2); bölünmürsə hər
      qrup 1 sayılır — hansı qrupun ikinci alt qrupu olduğunu bilmədən heç bir jurnala artıq plan yazılmır."""
    if len(row_groups) <= 1:
        return 1 if group.pk != parent.pk else None
    if group.pk != parent.pk:
        return 1
    own = len(children.get(parent.pk, ()))
    if own:
        return own
    known = sum(len(children.get(item.pk, ())) for item in row_groups)
    unknown = sum(1 for item in row_groups if not children.get(item.pk))
    rest = int(row.subgroup_count or 1) - known
    return rest // unknown if unknown and rest >= unknown and rest % unknown == 0 else 1


def _cap(caps, key, row, assignment, share) -> None:
    """Açar + fəaliyyət üzrə plan saatı: qrup başına plan × müəllimin bu qrupda apardığı alt qrup sayı.

    Sahib 2026-11-12 (135 TSPX): mühazirə 30 + seminar iki alt qrupa bölünür (30 + 30) → başlıq 90, 60 yox.
    Alt qrup sayı: müəllimin bölgülərindəki fərqli ``sub_number``-lar; yoxdursa tək qruplu sətirdə sətrin
    ``subgroup_count``-u, çox qruplu axında qrupun REAL alt qrup sayı (``share`` — :func:`_group_subgroups`).
    Çox qruplu sətirdə qrupa bağlanmamış nömrələr (``group`` boş) da həmin saydan çox ola bilməz (MR-000383).
    """
    activity = assignment.activity
    field = _PLAN_FIELDS.get(activity)
    plan = int(getattr(row, field, 0) or 0) if field else 0
    if not plan:
        return
    bucket = caps.setdefault(key, {})
    if activity == Activity.LECTURE:
        bucket[activity] = max(bucket.get(activity, 0), plan)
        return
    subs = bucket.setdefault(("subs", activity), set())
    if assignment.sub_number:
        subs.add(assignment.sub_number)
    if share is None:
        multiplier = max(1, len(subs), int(row.subgroup_count or 1) if not assignment.sub_number else 1)
    elif assignment.sub_number and getattr(assignment, "group_id", None) is None:
        multiplier = max(1, min(len(subs), share))
    else:
        multiplier = max(1, len(subs), 1 if assignment.sub_number else share)
    bucket[activity] = max(bucket.get(activity, 0), plan * multiplier)


def teacher_journal_assignments(*, organization, teacher_id):
    return _assignment_map(organization=organization, teacher_id=teacher_id)


def teacher_journal_plan_hours(*, organization, teacher_id):
    return _assignment_map(organization=organization, teacher_id=teacher_id, include_hours=True)
