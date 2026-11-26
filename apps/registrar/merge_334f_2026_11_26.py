"""MR-000836 (sahib 2026-11-26, «Yes, do it»): 334F1 + 334F2 → bir ana qrup «334F» və hər fənn üçün BİR jurnal.

Filologiya — İngilis dili və ədəbiyyatı. Tyutor iki qrupun birləşdirilməsini istəyib; prod-da «334F» qrupu yoxdur
(aktiv / arxiv), 334F1 və 334F2-nin ana qrup izi yoxdur; payız 2026/2027-nin 7 fənninin hər birində iki jurnal var
(hər qrupa bir, cütlərdə müəllim eynidir). Sahibin modeli: ana qrup alt qrupların cəmidir, tələbələr RƏSMİ qrupunda
qalır (334F1 / 334F2 — reyestr trigger-i çılpaq qrup yazısını bloklayır, burada tələbənin qrupuna TOXUNULMUR), alt
qruplar ana jurnalın İÇİNDƏ seminar alt qrupudur, bir fənn + dövr üçün bir jurnal.

Addımlar (hamısı :func:`apps.registrar.management.commands.relocate_twin_enrollment.run_plan` tranzaksiyasında; dry-run
geri qaytarılır):

1. **Ana qrup** — :func:`apps.registrar.parent_groups.create_parent_group` (``ensure_parent_groups``-un tək-ailə
   qaydası: alt qrupların ixtisası altında qardaş ``OrgUnit(group)``, ``COPY_KEYS`` metadatası,
   ``created_by_command``) və :func:`~apps.registrar.parent_groups.link_parent_group` (alt qrupda
   ``settings.parent_group`` izi). Ad (boşluqsuz, ``casefold``) qeyri-müəyyəndirsə — imtina, heç nə yazılmır. Bu
   əmrin əvvəlki (geri qaytarılmış) qaçışının arxivlədiyi «334F» yenidən aktiv olur.
2. **Jurnallar** — payız 2026/2027-də HƏR İKİ alt qrupun aktiv jurnalı olan hər fənn bir ailədir və
   :class:`apps.registrar.subgroup_journal_merge_2026_11_08.Merger` ilə (bütün qoruyucuları: fərqli müəllim, lab
   qrupu, yekun nəticə, ayrı mühazirə saatı, boş xana, rəsmi düzəliş, pay …) «334F» jurnalına birləşir; seminar alt
   qrupları ``SeminarGroup(unit=334F1 / 334F2)``. Qoruyucudan keçməyən ailə savepoint-də geri qaytarılır və səbəbi
   hesabatdadır (``status=blocked_<səbəb>``).
3. **Dərs yükü** — ``Merger._load_rows``: fənnin həmin dövrdəki 334F1/334F2 sətrinə ana qrup ƏLAVƏ olunur (alt qruplar
   və saatlar qalır). Yük sinxronu (``workload.offering_sync``) passiv alt qrup jurnalını YENİDƏN yaratmır və aktiv
   etmir (``inactive_skipped`` / ``inactive_subgroup_journal``), «334F» açarı isə birləşmiş jurnalı yeniləyir.

Hər qaçışın ``batch`` id-si (``m334f-YYYYMMDD-HHMMSS-xxxx``) audit sətirlərindədir; geri qaytarma —
:mod:`.merge_334f_undo_2026_11_26`. Stdout-a YALNIZ saylar və id prefiksləri (şəxs adı yoxdur).
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from collections import Counter

from django.apps import apps as django_apps
from django.db import IntegrityError
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from .parent_groups import CONSISTENT_KEYS, ORIGIN_KEY, create_parent_group, link_parent_group
from .subgroup_journal_merge_2026_11_08 import Blocked, Merger

RESOURCE = "registrar.merge_334f_20261126"
REASON = "MR-000836: 334F1 + 334F2 → ana qrup 334F, hər fənn üçün bir jurnal (seminar alt qrupları)"
UNDO_REASON = "MR-000836: 334F birləşməsinin geri qaytarılması"
ORIGIN = "merge_334f_journals_20261126"
PARENT_NAME = "334F"
SUBGROUP_NAMES = ("334F1", "334F2")
ACADEMIC_YEAR = "2026/2027"
_FALL_ROOTS = ("payız", "payiz", "güz", "guz", "fall", "autumn")
_OTHER_ROOTS = ("yaz", "bahar", "spring", "yay", "summer")
#: Say açarlarında rəqəm olmur (prod-data-ops xülasə süzgəci ``[a-z_]+``).
_ORDINAL = ("first", "second")
_TRANSLIT = str.maketrans({"ə": "e", "ı": "i", "ö": "o", "ü": "u", "ş": "s", "ç": "c", "ğ": "g"})


class MergeRefused(Exception):
    """Qoruyucu pozuldu — heç nə yazılmır (əmr ``CommandError: f334_merge_refused_<kod>`` verir)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"m334f-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def name_key(name) -> str:
    return re.sub(r"\s+", "", str(name or "")).casefold()


def code_slug(text) -> str:
    """Fənn kodu → stdout-a təhlükəsiz dəyər (``[0-9a-z_-]``)."""
    value = unicodedata.normalize("NFKD", str(text or "").casefold().translate(_TRANSLIT))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^0-9a-z_-]+", "_", value).strip("_-")
    return value[:40] or "unknown"


def _settings(unit) -> dict:
    return unit.settings if isinstance(unit.settings, dict) else {}


def _groups(organization) -> list:
    return list(
        _model("OrgUnit", "organizations").objects.filter(organization=organization, unit_type=OrgUnitType.GROUP)
    )


def resolve_subgroups(organization, units=None) -> list:
    """``[334F1, 334F2]`` — hər ad üzrə TƏK aktiv qrup, eyni ixtisas, uyğun metadata; yoxsa imtina."""
    units = _groups(organization) if units is None else units
    found = []
    for name in SUBGROUP_NAMES:
        matches = [unit for unit in units if unit.is_active and name_key(unit.name) == name_key(name)]
        if not matches:
            raise MergeRefused("subgroup_missing")
        if len(matches) > 1:
            raise MergeRefused("subgroup_ambiguous")
        found.append(matches[0])
    if len({unit.parent_id for unit in found}) != 1 or found[0].parent_id is None:
        raise MergeRefused("subgroups_specialty_differs")
    for key in CONSISTENT_KEYS:
        if len({str(_settings(unit).get(key) or "").strip() for unit in found} - {""}) > 1:
            raise MergeRefused("subgroups_metadata_conflict")
    return found


def resolve_parent(organization, subgroups, units=None):
    """Mövcud «334F» (aktiv, eyni ixtisas) və ya ``None`` (yaradılacaq). Bu əmrin arxivlədiyi «334F» —
    ``("revive", unit)``. Başqa hər hal (bir neçə ad, başqa ixtisas, yad arxiv, alt qrupun başqa izi) — imtina."""
    units = _groups(organization) if units is None else units
    matches = [unit for unit in units if name_key(unit.name) == name_key(PARENT_NAME)]
    if len(matches) > 1:
        raise MergeRefused("parent_ambiguous")
    parent = matches[0] if matches else None
    trails = {str(_settings(unit).get("parent_group") or "") for unit in subgroups} - {""}
    if parent is None:
        if trails:
            raise MergeRefused("subgroup_trail_conflict")
        return None, ""
    if parent.parent_id != subgroups[0].parent_id:
        raise MergeRefused("parent_in_other_specialty")
    if _settings(parent).get("parent_group"):
        raise MergeRefused("parent_is_subgroup")
    if trails - {str(parent.pk)}:
        raise MergeRefused("subgroup_trail_conflict")
    if not parent.is_active:
        if _settings(parent).get(ORIGIN_KEY) != ORIGIN:
            raise MergeRefused("parent_archived_name_clash")
        return parent, "revive"
    return parent, "existing"


def resolve_period(organization, subgroups):
    """Payız 2026/2027 — alt qrupların aktiv jurnalı olan dövrlərdən; tək olmalıdır."""
    AcademicPeriod = _model("AcademicPeriod", "organizations")
    period_ids = (
        _model("CourseOffering")
        .objects.filter(organization=organization, group__in=subgroups, is_active=True)
        .values_list("period_id", flat=True)
        .distinct()
    )
    found = []
    for period in AcademicPeriod.objects.filter(organization=organization, pk__in=list(period_ids)):
        if AcademicPeriod.format_year(period.academic_year) != ACADEMIC_YEAR:
            continue
        words = re.findall(r"\w+", (period.name or "").casefold())
        fall = any(word.startswith(root) for word in words for root in _FALL_ROOTS)
        other = any(word.startswith(root) for word in words for root in _OTHER_ROOTS)
        if fall or (not other and period.start_date.month >= 8):
            found.append(period)
    if not found:
        raise MergeRefused("period_missing")
    if len(found) > 1:
        raise MergeRefused("period_ambiguous")
    return found[0]


def plan_families(organization, subgroups, parent, period, counts) -> list:
    """``[{"name", "code", "target", "group", "sources", "revive_target"}]`` — hər iki alt qrupun aktiv jurnalı olan
    fənlər. Hər iki jurnalı passivdirsə və «334F» jurnalı aktivdirsə — ``already_merged`` (yenə ailədir, Merger deyir).
    """
    CourseOffering = _model("CourseOffering")
    rows = CourseOffering.objects.filter(organization=organization, period=period, group__in=subgroups).select_related(
        "subject"
    )
    by_subject: dict = {}
    for row in rows:
        by_subject.setdefault(row.subject_id, {})[row.group_id] = row
    own = {
        row.subject_id: row
        for row in CourseOffering.objects.filter(organization=organization, period=period, group=parent)
    }
    families = []
    for subject_id, pair in by_subject.items():
        sources = [pair.get(unit.pk) for unit in subgroups]
        if any(source is None for source in sources):
            counts["subjects_single_subgroup"] += 1
            continue
        active = [source.is_active for source in sources]
        target = own.get(subject_id)
        if not all(active) and not (not any(active) and target is not None and target.is_active):
            counts["subjects_not_both_active"] += 1
            continue
        families.append(
            {
                "name": f"{PARENT_NAME} · {sources[0].subject.code}",
                "code": code_slug(sources[0].subject.code or sources[0].subject.name),
                "target": None,
                "group": str(parent.pk),
                "sources": [str(source.pk) for source in sources],
                "revive_target": _revivable(organization, target),
            }
        )
    families.sort(key=lambda family: (family["code"], family["sources"]))
    return families


def _revivable(organization, target) -> str:
    """Bu əmrin yaratdığı və geri qaytarmada passiv qalan «334F» jurnalı — təkrar qaçışda yenidən aktiv olur."""
    if target is None or target.is_active:
        return ""
    AuditLog = _model("AuditLog", "audit")
    created = AuditLog.objects.filter(
        organization=organization,
        resource_type=RESOURCE,
        new_values__op="family",
        changes__manifest__target_created__contains=[str(target.pk)],
    )
    return str(target.pk) if created.exists() else ""


class F334Merger(Merger):
    """2026-11-08 birləşdiricisi öz audit izi ilə (``batch``) və ailə nəticəsi (``outcome``)."""

    audit_resource, audit_reason = RESOURCE, REASON

    def __init__(self, *, organization, actor, counts, batch):
        super().__init__(organization=organization, actor=actor, counts=counts)
        self.batch = batch
        self.outcome: dict = {}

    def _family(self, family) -> None:
        revive = family.get("revive_target") or ""
        self.audit_extra = {"batch": self.batch, "op": "family", "revived_target": revive}
        try:
            if revive:
                _model("CourseOffering").objects.filter(pk=revive, is_active=False).update(
                    is_active=True, updated_at=timezone.now()
                )
                self.counts["targets_revived"] += 1
            super()._family(family)
        except Blocked as exc:
            self.outcome[family["name"]] = exc.reason
            raise
        except IntegrityError:
            self.outcome[family["name"]] = "family_integrity_error"
            raise
        self.outcome[family["name"]] = "merged"


def _ensure_parent(organization, actor, counts, batch, subgroups, units):
    parent, state = resolve_parent(organization, subgroups, units)
    manifest = {"created": "", "revived": "", "linked": []}
    if parent is None:
        parent = create_parent_group(
            organization,
            subgroups=subgroups,
            name=PARENT_NAME,
            reason=REASON,
            origin=ORIGIN,
            actor=actor,
            audit_values={"batch": batch},
        )
        manifest["created"] = str(parent.pk)
        counts["parent_created"] += 1
    elif state == "revive":
        type(parent).objects.filter(pk=parent.pk).update(is_active=True, updated_at=timezone.now())
        parent.is_active = True
        manifest["revived"] = str(parent.pk)
        counts["parent_revived"] += 1
    else:
        counts["parent_existing"] += 1
    for unit in subgroups:
        old = _settings(unit).get("parent_group")
        if link_parent_group(organization, unit, parent, reason=REASON, actor=actor, audit_values={"batch": batch}):
            manifest["linked"].append([str(unit.pk), str(old or "")])
            counts["subgroups_linked"] += 1
        else:
            counts["subgroups_already_linked"] += 1
    return parent, manifest


def run(*, organization, actor, counts: Counter, batch: str = "", report=None) -> str:
    """Bir qaçış; ``report`` — ``[(ailə, nəticə, delta)]`` (stdout üçün). Qaytarır ``batch``."""
    batch = batch or new_batch()
    units = _groups(organization)
    subgroups = resolve_subgroups(organization, units)
    period = resolve_period(organization, subgroups)
    Record = _model("StudentAcademicRecord")
    for ordinal, unit in zip(_ORDINAL, subgroups):
        counts[f"subgroup_{ordinal}_students"] = Record.objects.filter(
            organization=organization, group=unit, is_active=True
        ).count()
    parent, manifest = _ensure_parent(organization, actor, counts, batch, subgroups, units)
    if manifest["created"] or manifest["revived"] or manifest["linked"]:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=parent,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(parent.pk),
            new_values={"batch": batch, "op": "parent", "parent": str(parent.pk), **manifest},
        )
    families = plan_families(organization, subgroups, parent, period, counts)
    counts["families"] = len(families)
    merger = F334Merger(organization=organization, actor=actor, counts=counts, batch=batch)
    merger.run(plan=families)
    for family, (_index, delta) in zip(families, merger.report):
        if report is not None:
            report.append((family, merger.outcome.get(family["name"], "unknown"), delta))
    return batch


__all__ = [
    "ORIGIN",
    "PARENT_NAME",
    "REASON",
    "RESOURCE",
    "SUBGROUP_NAMES",
    "UNDO_REASON",
    "F334Merger",
    "MergeRefused",
    "code_slug",
    "new_batch",
    "plan_families",
    "resolve_parent",
    "resolve_period",
    "resolve_subgroups",
    "run",
]
