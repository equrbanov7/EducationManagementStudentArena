"""Qrup kartının boş xanaları — dil sektoru və təhsil forması (sahib 2026-10-26).

Sahib: «ana qrup əyanidirsə alt qrup da əyanidir, az dilidirsə alt qrup da az dilidir — boş xana qalmasın».

* **Dil** (``settings.language_sector``): köhnə datadan gələn qruplarda dəyər ``settings.sector`` açarındadır
  (``legacy_import``) — reyestr onu oxumurdu. Boş alt qrup ANA qrupun dilini alır; köhnə datada öz dili
  FƏRQLİDİRSƏ (məs. «329 F» az → «329 F1» en) o saxlanır, ziddiyyət sayılır. Ana qrupda yoxdursa alt qrupların
  YEKDİL dili.
* **Forma** (``settings.education_form``): alt qrup ana qrupdan; ana qrup — alt qrupların yekdil dəyərindən,
  yoxsa qrup kodu qaydasından (:func:`group_education_form.group_rule_form`); qayda tətbiq olunmursa (magistr,
  doktorantura…) qrupun aktiv tələbə qeydlərinin YEKDİL formasından.

Yalnız BOŞ xana doldurulur, dolu dəyər dəyişmir (alt qrupla ana qrup arasında ziddiyyət sayılır, toxunulmur).
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps

from .group_education_form import group_rule_form

LANGUAGE = "language_sector"
LEGACY_LANGUAGE = "sector"
FORM = "education_form"


def language_of(settings) -> str:
    """Qrupun dili: ``language_sector``, yoxsa köhnə datanın ``sector`` açarı."""
    raw = settings if isinstance(settings, dict) else {}
    return str(raw.get(LANGUAGE) or raw.get(LEGACY_LANGUAGE) or "").strip()


def _own(settings, key) -> str:
    raw = settings if isinstance(settings, dict) else {}
    return str(raw.get(key) or "").strip()


def _unanimous(values) -> str:
    values = {value for value in values if value}
    return values.pop() if len(values) == 1 else ""


def _record_forms(organization) -> dict:
    """``{qrup_pk: forma}`` — qrupun aktiv tələbə qeydlərinin YEKDİL forması (qayda tətbiq olunmayan qruplar üçün)."""
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    seen: dict = {}
    for group_id, form in (
        Record.objects.filter(organization=organization, is_active=True, group__isnull=False)
        .exclude(education_form="")
        .values_list("group_id", "education_form")
        .distinct()
    ):
        seen.setdefault(group_id, set()).add(form)
    return {group_id: forms.pop() for group_id, forms in seen.items() if len(forms) == 1}


def plan(organization) -> tuple[Counter, dict]:
    """``(counts, {unit_pk: {açar: dəyər}})`` — yazılacaq boş xanalar."""
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    units = list(OrgUnit.objects.filter(organization=organization, unit_type="group", is_active=True))
    by_pk = {unit.pk: unit for unit in units}
    by_text = {str(unit.pk): unit for unit in units}
    children: dict = {}
    parent_of: dict = {}
    # Ana ↔ alt qrup əlaqəsi reyestrin öz izi ilə (``settings.parent_group``, bax ``groups_registry._parent_links``).
    for unit in units:
        parent_pk = str((unit.settings or {}).get("parent_group") or "") if isinstance(unit.settings, dict) else ""
        parent = by_text.get(parent_pk)
        if parent is not None and parent.pk != unit.pk:
            children.setdefault(parent.pk, []).append(unit)
            parent_of[unit.pk] = parent.pk
    record_forms = _record_forms(organization)
    counts = Counter(groups=len(units))
    changes: dict = {}

    def put(unit, key, value, reason):
        if value and not _own(unit.settings, key):
            changes.setdefault(unit.pk, {})[key] = value
            counts[f"{key}.{reason}"] += 1

    # 1) Ana qruplar (alt qruplar onlardan alır, ona görə əvvəl).
    for parent_pk, subs in children.items():
        parent = by_pk[parent_pk]
        put(
            parent,
            LANGUAGE,
            language_of(parent.settings) or _unanimous(language_of(s.settings) for s in subs),
            "parent",
        )
        form = _unanimous(_own(s.settings, FORM) for s in subs) or (group_rule_form(parent)[0] or "")
        put(parent, FORM, form, "parent")
    # 2) Bütün qruplar: alt qrup ana qrupdan, qalanı öz köhnə açarından / koddan.
    for unit in units:
        parent = by_pk.get(parent_of.get(unit.pk))
        if parent is not None:
            parent_language = changes.get(parent.pk, {}).get(LANGUAGE) or language_of(parent.settings)
            parent_form = changes.get(parent.pk, {}).get(FORM) or _own(parent.settings, FORM)
            own_language = language_of(unit.settings)
            if parent_language and own_language and parent_language.lower() != own_language.lower():
                counts["language.conflict_with_parent"] += 1
            put(unit, LANGUAGE, own_language or parent_language, "legacy" if own_language else "from_parent")
            put(unit, FORM, parent_form or (group_rule_form(unit)[0] or ""), "from_parent" if parent_form else "rule")
        else:
            put(unit, LANGUAGE, language_of(unit.settings), "legacy")
            rule = group_rule_form(unit)[0] or ""
            put(unit, FORM, rule or record_forms.get(unit.pk, ""), "rule" if rule else "records")
    for unit in units:
        settings = {**(unit.settings or {}), **changes.get(unit.pk, {})}
        counts["still_empty.language"] += int(not _own(settings, LANGUAGE))
        counts["still_empty.form"] += int(not _own(settings, FORM))
    counts["groups_changed"] = len(changes)
    return counts, changes


def apply(organization, changes: dict, *, actor=None) -> int:
    """Boş xanaları yazır (çağıranın tranzaksiyasında) + audit. Yazılan qrup sayı."""
    from core.audit import log_action
    from core.constants import AuditAction

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    written = 0
    for unit in OrgUnit.objects.filter(organization=organization, pk__in=list(changes)).select_for_update():
        blob = dict(unit.settings or {})
        fill = {key: value for key, value in changes[unit.pk].items() if not _own(blob, key)}
        if not fill:
            continue
        blob.update(fill)
        unit.settings = blob
        unit.save(update_fields=["settings", "updated_at"])
        written += 1
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=unit,
            reason="groups: empty language/education form filled (owner rule 2026-10-26: subgroup follows parent)",
            old_values={key: "" for key in fill},
            new_values=fill,
        )
    return written


__all__ = ["apply", "language_of", "plan"]
