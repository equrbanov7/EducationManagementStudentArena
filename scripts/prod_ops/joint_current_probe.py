"""Birgə (çoxqruplu) yük sətri jurnalı müəllimin CARİ siyahısına niyə salmır — YALNIZ-OXU diaqnostika (2026-11-20).

Leyla Məmmədova «Malware analysis» 235 İ-1/İ-2: ayrıca İ-2 sətri silinəndə İ-2 jurnalı tarixçəyə düşdü, halbuki
birgə sətir (da34a218) hər iki qrupu daşıyır. Heç nə YAZMIR; şəxs məlumatı çap etmir (yalnız id/qrup adı).
"""

from apps.organizations.models import Organization, OrgUnit
from apps.registrar.models import CourseOffering
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services.journal_assignments import _assignment_map, _registered_children
from apps.workload.services.offering_shares import _assignment_group
from core.group_identity import canonical_aliases
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

TEACHER = 8302
OFFERINGS = ("670324f8-13e4-4011-854a-0f873e30bf38", "bad814fd-a7a5-4e24-8722-6e0d33e9ee13")
JOINT = "da34a218-839f-4e76-90b9-dd79f6270772"

with rls_worker_atomic(), bypass_rls():
    offs = list(CourseOffering.objects.filter(pk__in=OFFERINGS).select_related("group"))
    org = Organization.objects.get(pk=offs[0].organization_id)
    for o in offs:
        g = o.group
        print(
            f"offering {str(o.pk)[:8]} group={str(g.pk)[:8]} {g.name} instructor={o.instructor_id} active={o.is_active}"
        )
        print(f"   group.parent={str(g.parent_id)[:8]} settings_keys={sorted((g.settings or {}).keys())}")
        print(
            f"   parent_group={(g.settings or {}).get('parent_group')} alias={(g.settings or {}).get('alias_of') or (g.settings or {}).get('canonical')}"
        )
    row = TeachingTaskRow.objects.get(pk=JOINT)
    groups = list(row.groups.all())
    print(
        f"joint row status={row.task.status} kind={row.row_kind} patok_lead={row.patok_lead_id} groups={[g.name for g in groups]}"
    )
    for a in TeacherAssignment.objects.filter(row=row):
        print(
            f"   assignment {a.activity} h={a.hours} teacher={a.teacher_id} group={a.group_id} "
            f"note={a.groups_note!r} sub={a.sub_number}"
        )
        for g in groups:
            print(f"      applies[{g.name}]={_assignment_group(a, row, g, known_groups=groups)}")
    kids = _registered_children(org, groups)
    print("registered_children:", {str(k)[:8]: [c.name for c in v] for k, v in kids.items()})
    aliases = canonical_aliases(groups)
    print("aliases:", {str(k)[:8]: v.name for k, v in aliases.items()})
    found = _assignment_map(organization=org, teacher_id=TEACHER)
    subj = offs[0].subject_id
    for key, kinds in found.items():
        if key[0] == subj:
            name = OrgUnit.objects.filter(pk=key[2]).values_list("name", flat=True).first()
            print(f"map key group={str(key[2])[:8]} {name} kinds={sorted(kinds)}")
    rows = TeachingTaskRow.objects.filter(subject_id=subj, assignments__teacher_id=TEACHER).distinct()
    for r in rows:
        print(f"row {str(r.pk)[:8]} groups={[g.name for g in r.groups.all()]} plan={r.lecture_plan}/{r.seminar_plan}")
