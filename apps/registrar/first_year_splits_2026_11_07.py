"""1-ci kurslar — köhnə sistemin alt qrup bölgüləri (sahib 2026-11-07: «bütün 1-ci kurslara bax, lab qruplarına bax,
bölündükləri alt qrupları da gətir»).

Köhnə sistemdə (2026/2027 payız, qəbul ili 2026) eyni fənn + qrup + növ üçün bir neçə aktiv jurnal yalnız iki halda
var (dil səviyyə qrupları ayrıca mexanizmdir — :mod:`.language_cohort_journal`):

* **laboratoriya** Lab-1 / Lab-2 — Fizika 236 BİO az / SBİO / K / KE, «Fizikanın əsasları» 236 EM, «Ümumi kimya»
  236 M (236 SBİO kimya/biologiya 2026-11-06-da yazılıb). Yük faylında «4*5» / «2*15» — seminar qrup üzrə, lab
  hər qrupda iki alt qrup. Bölgü ``Enrollment.lab_group``-a yazılır (:mod:`.lab_groups_apply_2026_11_06` qaydası);
  qrupsuz lab dərsi bütün xanaları bir qrupdadırsa həmin qrupa bağlanır;
* **ADİAK** («Azərbaycan dilində işgüzar və akademik kommunikasiya») 236 SBİO / M / EM / KE / İT — qrup iki
  müəllimə bölünüb. EMS-də tək jurnal və iki müəllimin tam payı var; hər paya öz alt qrupunun siyahısı yazılır
  (MR-000188 qaydası, :func:`.journal_shares.journal_scope`): ikinci müəllim yalnız öz tələbələrini, sahib öz
  alt qrupunu + heç bir alt qrupa düşməyənləri görür. Sahibin payı yoxdursa «köhnə sistem» mənbəli pay
  yaradılır — yük sinxronu yalnız ``workload`` mənbəli paylara toxunur.

Köhnə siyahılar EMS qeydiyyatlarına ad üzrə (2026-11-07, prod jurnal siyahısı) tutuşdurulub; plan faylında YALNIZ
id-lər var (``first_year_splits_2026_11_07.json``). Siyahıda olmayan tələbə (sonradan gələn, təkrar keçən) qrupsuz
qalır. İdempotentdir; başqa dəyərin üzərinə yazmır (``*_conflict``); qeydiyyatı dəyişmiş jurnal atlanır.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from .lab_groups_apply_2026_11_06 import _group_lessons

PLAN_PATH = Path(__file__).with_name("first_year_splits_2026_11_07.json")
REASON = "Sahib 2026-11-07: 1-ci kurslar — köhnə sistemin lab / alt qrup bölgüsü"
RESOURCE = "registrar.first_year_splits"
#: Say açarlarında rəqəm olmur (prod-data-ops süzgəci ``[a-z_]+=``).
_WORD = {1: "first", 2: "second"}


@lru_cache(maxsize=1)
def plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _model(name):
    return django_apps.get_model("registrar", name)


def _enrolled(offering) -> dict:
    Enrollment = _model("Enrollment")
    return {
        str(row.pk): row
        for row in Enrollment.objects.select_for_update().filter(
            organization_id=offering.organization_id, offering=offering, status=Enrollment.Status.ENROLLED
        )
    }


def _audit(actor, organization, obj, old, new, resource_id) -> None:
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=obj,
        old_values=old,
        new_values=new,
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=resource_id,
    )


def _lab(key, spec, offering, counts) -> dict:
    Enrollment = _model("Enrollment")
    rows = _enrolled(offering)
    changed = []
    for raw_group, enrollment_ids in spec["groups"].items():
        group = int(raw_group)
        for enrollment_id in enrollment_ids:
            row = rows.get(enrollment_id)
            if row is None:
                counts[f"{key}_not_enrolled"] += 1
            elif row.lab_group == group:
                counts[f"{key}_already"] += 1
            elif row.lab_group is not None:
                counts[f"{key}_conflict"] += 1
            else:
                row.lab_group = group
                changed.append(row)
                counts[f"{key}_lab_{_WORD[group]}"] += 1
    if changed:
        Enrollment.objects.bulk_update(changed, ["lab_group"])
    counts[f"{key}_ungrouped"] += sum(1 for row in rows.values() if row.lab_group is None)
    group_of = {row.pk: row.lab_group for row in rows.values()}
    _group_lessons({"key": key}, offering, group_of, counts)
    return {"lab_groups": sorted(str(row.pk) for row in changed)}


def _share_rows(share, wanted, counts, key, side) -> tuple[set, set] | None:
    current = {str(pk) for pk in share.enrollments.values_list("pk", flat=True)}
    if current == wanted:
        counts[f"{key}_{side}_already"] += 1
        return None
    if current and not current <= wanted:
        counts[f"{key}_{side}_conflict"] += 1  # başqa siyahı əl ilə qoyulub — toxunulmur
        return None
    share.enrollments.set(wanted)
    counts[f"{key}_{side}_split"] += 1
    return current, wanted


def _shares(key, spec, offering, actor, counts) -> None:
    from .journal_shares import forget
    from .models import JournalShare, JournalShareSource

    if offering.instructor_id != spec["owner"]:
        counts[f"{key}_owner_changed_skipped"] += 1
        return
    rows = _enrolled(offering)
    owner_rows, other_rows = set(spec["owner_rows"]), set(spec["other_rows"])
    if not (owner_rows | other_rows) <= set(rows):
        counts[f"{key}_roster_changed_skipped"] += 1
        return
    active = list(JournalShare.objects.select_for_update().filter(offering=offering, is_active=True))
    others = [share for share in active if share.teacher_id != offering.instructor_id]
    if len(others) != 1:
        counts[f"{key}_other_share_ambiguous_skipped"] += 1
        return
    own = next((share for share in active if share.teacher_id == offering.instructor_id), None)
    if own is None:
        own = JournalShare.objects.create(
            organization_id=offering.organization_id,
            offering=offering,
            teacher_id=offering.instructor_id,
            kinds=list(others[0].kinds or []),
            source=JournalShareSource.LEGACY,
            created_by=actor,
        )
        counts[f"{key}_owner_share_created"] += 1
    for share, wanted, side in ((own, owner_rows, "owner"), (others[0], other_rows, "other")):
        change = _share_rows(share, wanted, counts, key, side)
        if change is not None:
            old, new = change
            _audit(
                actor,
                offering.organization,
                share,
                {"enrollments": sorted(old)},
                {"enrollments": sorted(new)},
                str(share.pk),
            )
    counts[f"{key}_ungrouped"] += len(set(rows) - owner_rows - other_rows)
    forget(offering)


def run(*, organization, actor, counts, data=None) -> None:
    """data — eyni formatda başqa plan (sahib 2026-11-08: Mexanika lab qrupları); yoxdursa repo planı."""
    CourseOffering = _model("CourseOffering")
    data = data or plan()

    def offering_for(spec):
        return (
            CourseOffering.objects.select_for_update()
            .filter(organization=organization, pk=spec["offering"], is_active=True)
            .first()
        )

    for key, spec in data["lab"].items():
        offering = offering_for(spec)
        if offering is None:
            counts[f"{key}_offering_missing"] += 1
            continue
        new = _lab(key, spec, offering, counts)
        if new["lab_groups"]:
            _audit(actor, organization, offering, {}, new, str(offering.pk))
    for key, spec in data["shares"].items():
        offering = offering_for(spec)
        if offering is None:
            counts[f"{key}_offering_missing"] += 1
            continue
        _shares(key, spec, offering, actor, counts)


__all__ = ["PLAN_PATH", "REASON", "plan", "run"]
