"""Məktəb → ixtisas → qrup → aktiv tələbə ağacı (YALNIZ OXU, sahib 2026-11-12).

«Hər ixtisasın tələbəsi öz məktəbində olsun; dekanlığa şikayət ixtisasın məktəbinin dekanlığına getsin.» Müraciət
marşrutu tələbənin qrupundan yuxarı ilk ``faculty`` əcdadını götürür (``applications.routing.resolve_scope_unit``).
Bu prob hər məktəbin ixtisaslarını, qrup / aktiv tələbə sayını və problemləri çap edir: məktəbə çatmayan qruplar,
məktəb altında olmayan ixtisaslar. Şəxs adı çap olunmur.
"""

from collections import Counter, defaultdict

from django.apps import apps

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


@rls_worker_atomic()
@bypass_rls()
def main():
    OrgUnit = apps.get_model("organizations", "OrgUnit")
    Organization = apps.get_model("organizations", "Organization")
    SAR = apps.get_model("registrar", "StudentAcademicRecord")
    org = Organization.objects.filter(slug="qku").first()
    units = {u.pk: u for u in OrgUnit.objects.filter(organization=org, is_active=True)}
    children = defaultdict(list)
    for u in units.values():
        children[u.parent_id].append(u)
    students = Counter(
        SAR.objects.filter(organization=org, is_active=True, group__isnull=False).values_list("group_id", flat=True)
    )

    def faculty_of(u):
        seen = set()
        while u is not None and u.pk not in seen:
            seen.add(u.pk)
            if u.unit_type == "faculty":
                return u
            u = units.get(u.parent_id)
        return None

    def subtree_groups(u):
        out, stack = [], list(children[u.pk])
        while stack:
            c = stack.pop()
            if students.get(c.pk) or c.unit_type not in ("specialty", "faculty", "chair", "department"):
                out.append(c)
            stack.extend(children[c.pk])
        return out

    for fac in sorted((u for u in units.values() if u.unit_type == "faculty"), key=lambda x: x.name):
        print(f"=== MƏKTƏB {fac.name}")
        specs = [u for u in units.values() if u.unit_type == "specialty" and faculty_of(u) is fac]
        for spec in sorted(specs, key=lambda x: x.name):
            groups = subtree_groups(spec)
            n = sum(students.get(g.pk, 0) for g in groups)
            parent = units.get(spec.parent_id)
            print(f"    ixtisas {spec.name} (valideyn: {getattr(parent, 'name', '—')}) qrup={len(groups)} tələbə={n}")
    print("=== MƏKTƏB ALTINDA OLMAYAN İXTİSASLAR")
    for spec in (u for u in units.values() if u.unit_type == "specialty" and faculty_of(u) is None):
        print(f"    {spec.name} (valideyn: {getattr(units.get(spec.parent_id), 'name', '—')})")
    print("=== AKTİV TƏLƏBƏSİ OLAN, AMMA İXTİSAS ALTINDA OLMAYAN QRUPLAR")
    for gid, n in sorted(students.items(), key=lambda x: -x[1]):
        g = units.get(gid)
        if g is None:
            continue
        chain, u = [], units.get(g.parent_id)
        while u is not None and u.unit_type != "specialty":
            chain.append(u.unit_type)
            u = units.get(u.parent_id)
        if u is None:
            fac = faculty_of(g)
            print(f"    qrup {g.name} tələbə={n} məktəb={getattr(fac, 'name', 'YOX')} zəncir={'>'.join(chain)}")


main()
