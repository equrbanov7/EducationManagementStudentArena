"""Ana qrup / alt qrup jurnal ailələrinin həlli (sahib 2026-11-08) — ``resolve_subgroup_families_20261108``.

Sahib: «ana qrup alt qruplardakı uşaqların cəmidir … müqayisə zamanı yazılan günlərdə fərq çıxacaqsa 2 alt qrupu
göstərəcəksənsə ana qrupu sil, yox ana qrupu göstərəcəksənsə digərlərini sil … bütün jurnallarda yoxla … birləşdirmə
zamanı xana itəcək, dərs pozulacaqsa — ən optimal qərar: ana qrupu silərsən, alt qruplar görünər».

Ailə — cari semestrdə eyni fənnin ana qrup (``OrgUnit``) jurnalı və onun alt qruplarının (``parent`` = ana qrup)
jurnalları; üstəgəl :data:`subgroup_journal_merge_2026_11_08.PLAN`-dakı ad üzrə tapılmış ailələr. Hər ailə üçün:

1. birləşmə (:class:`~.subgroup_journal_merge_2026_11_08.Merger`) — alt qrupların dərsləri eynidir, heç bir boş xana
   artmır → bir jurnal (ana qrup), alt qruplar seminar alt qrupu olur, alt qrup jurnalları passiv;
2. birləşmə dərsləri pozardısa (``family_adds_empty_cells`` / ``family_lectures_separate`` /
   ``family_instructors_differ``) və ana jurnal varsa → :class:`~.subgroup_parent_retire_2026_11_08.Splitter`: ana
   jurnalın qeydləri alt qrup jurnallarına (yalnız boş xanaya), ana jurnal passiv — alt qruplar görünür;
3. digər qoruyucular (bölünmüş pay, yekun nəticə, başqa moduldan istinad …) → ailə toxunulmur, səbəbi sayılır.

Hər addım öz savepoint-ində; stdout-a yalnız saylar və jurnal id-sinin ilk 8 simvolu.
"""

from __future__ import annotations

from collections import defaultdict

from django.db import IntegrityError, transaction

from core.constants import OrgUnitType

from .subgroup_journal_merge_2026_11_08 import PLAN, Blocked, Merger, _model
from .subgroup_parent_retire_2026_11_08 import Splitter

SPLIT_REASONS = frozenset({"family_adds_empty_cells", "family_lectures_separate", "family_instructors_differ"})


def current_period(organization):
    return (
        _model("AcademicPeriod", "organizations")
        .objects.filter(organization=organization, is_current=True, is_active=True)
        .order_by("-start_date")
        .first()
    )


def discover(organization) -> list[dict]:
    """Ailələr (sabit sıra): ``{"name", "target", "group", "sources"}`` — :class:`Merger` planı formasında."""
    period = current_period(organization)
    if period is None:
        return []
    OrgUnit, Offering = _model("OrgUnit", "organizations"), _model("CourseOffering")
    parent_of = dict(
        OrgUnit.objects.filter(
            organization=organization,
            unit_type=OrgUnitType.GROUP,
            parent__unit_type=OrgUnitType.GROUP,
            is_active=True,
        ).values_list("pk", "parent_id")
    )
    groups = set(parent_of) | set(parent_of.values())
    found = defaultdict(lambda: {"target": None, "sources": []})
    offerings = (
        Offering.objects.filter(organization=organization, period=period, is_active=True, group_id__in=groups)
        .select_related("group", "subject")
        .order_by("group__name", "subject__name", "pk")
    )
    names = {}
    for offering in offerings:
        if offering.group_id in parent_of:
            key = (parent_of[offering.group_id], offering.subject_id)
            found[key]["sources"].append(str(offering.pk))
        else:
            key = (offering.group_id, offering.subject_id)
            found[key]["target"] = str(offering.pk)
        names.setdefault(key, offering.subject.name)
    families = []
    for (group_id, _subject), row in found.items():
        if row["sources"] and (row["target"] or len(row["sources"]) > 1):
            families.append({"name": names[(group_id, _subject)], "group": str(group_id), **row})
    seen = {frozenset(row["sources"]) for row in families}
    for family in PLAN:  # adla tapılmış ailələr (alt qrup ``parent``-ə bağlanmayıbsa)
        if frozenset(family["sources"]) not in seen:
            families.append(dict(family))
    return families


def _parent(organization, family, live):
    Offering = _model("CourseOffering")
    if family.get("target"):
        return Offering.objects.filter(organization=organization, pk=family["target"]).first()
    return Offering.objects.filter(
        organization=organization,
        subject_id=live[0].subject_id,
        period_id=live[0].period_id,
        group_id=family.get("group"),
        is_active=True,
    ).first()


class Resolver:
    def __init__(self, *, organization, actor, counts):
        self.organization, self.actor, self.counts = organization, actor, counts
        self.report = []

    def run(self, families) -> None:
        for index, family in enumerate(families, start=1):
            before = dict(self.counts)
            merger = Merger(organization=self.organization, actor=self.actor, counts=self.counts)
            merger.run(plan=[family])
            _index, delta = merger.report[0]
            detail = {key: value for key, value in delta.items() if isinstance(value, str)}
            reason = next((key for key in delta if key in SPLIT_REASONS), "")
            if not delta.get("families_merged") and reason:
                detail.update(self._split(family))
            delta = {
                key: value - before.get(key, 0) for key, value in self.counts.items() if value != before.get(key, 0)
            }
            self.report.append((index, {**delta, **detail}))

    def _split(self, family) -> dict:
        Offering = _model("CourseOffering")
        live = list(
            Offering.objects.select_for_update(of=("self",)).filter(
                organization=self.organization, pk__in=family["sources"], is_active=True
            )
        )
        parent = _parent(self.organization, family, live) if live else None
        if parent is None or not parent.is_active:
            self.counts["subgroups_kept_no_parent"] += 1
            return {}
        before = dict(self.counts)
        try:
            with transaction.atomic():
                Splitter(organization=self.organization, actor=self.actor, counts=self.counts).split(
                    parent, live, family["name"]
                )
        except (Blocked, IntegrityError) as exc:
            reason, detail = (exc.reason, exc.detail) if isinstance(exc, Blocked) else ("split_integrity_error", {})
            self.counts.clear()
            self.counts.update(before)
            self.counts[reason] += 1
            return {"parent": str(parent.pk)[:8], **detail}
        return {"parent": str(parent.pk)[:8]}
