"""Çatışmayan QRUP və FƏNN-in yaradılması (cutover qaydaları ilə eyni forma).

Qrup
    Cutover-in ``academic_structure`` fazası ilə eyni: ``OrgUnit(unit_type=group)``, slug
    ``myedu-grp-<legacy id>`` (təkrar qaçışda bu slug ilə tapılır), ata = legacy ixtisasın ledger
    vahidi (yoxdursa kafedra/fakültə). ``settings``: ``legacy`` izi + ``sector`` / ``degree_level`` /
    ``admission_year`` / ``education_form`` (forma qrup kodundan — ``group_rule_form``, sahib 2026-10-25). Ad alt qrup şablonuna uyğundursa («536 TB1» ← «536 TB»)
    ``parent_group`` izi yazılır — qrup bölgüsü (``group_split``) ilə eyni açar, jurnal birləşik görünür.
    YALNIZ istinad olunan (jurnalı və ya yaradılacaq tələbəsi olan) qruplar yaradılır.

Fənn
    Kod ``QKU-<legacy lessons.id>`` — cutover + ``finalize_university_identity`` qaydası (``MYEDU-L<n>``
    → ``QKU-<n>``); ad HTML entity-lərdən təmizlənir.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from ..rehearsal_contracts import SOURCE_SYSTEM
from .resolve import GROUP_SLUG_PREFIX, SUBJECT_CODE_PREFIX, text

_DEGREE = {"bak": "bachelor", "mag": "master"}
_FORM = {"qiyabi": "part_time"}
_SECTORS = {"az", "en", "ru"}


def ensure_group(run, legacy: dict):
    """Legacy qrup → ``OrgUnit`` (tapılır və ya yaradılır). Qaytarır: ``unit | None``."""

    catalog = run.catalog
    unit, how = catalog.group_for(legacy)
    if unit is not None:
        run.count(f"group.{how}")
        return unit
    if how == "ambiguous":
        run.count("group.ambiguous")
        run.names("group_ambiguous", text(legacy.get("name")), str(legacy["id"]))
        return None
    name = text(legacy.get("name"), limit=200)
    if not name or name.casefold() == "test":
        run.count("group.unusable_name")
        return None
    base = _base_group(catalog, name)
    parent = (
        catalog.unit_for_speciality(legacy.get("speciality_id"))
        or (catalog.units.get(base.parent_id) if base is not None else None)
        or catalog.unit_for_department(legacy.get("department_id"))
    )
    if parent is None:
        run.count("group.parent_unresolved")
        run.names("group_parent_unresolved", name, str(legacy["id"]))
        return None
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    settings = {
        "legacy": {
            "id": legacy["id"],
            "table": "groups",
            "source_system": SOURCE_SYSTEM,
            "speciality_id": legacy.get("speciality_id"),
            "department_id": legacy.get("department_id"),
            "kollec_or_uni": legacy.get("kollec_or_uni") or "",
            "imported_by": "legacy_delta",
        },
        "sector": legacy.get("sector") if legacy.get("sector") in _SECTORS else "az",
        # Reyestr dili ``language_sector``-dan oxuyur (sahib 2026-10-26: qrup kartında boş dil xanası).
        "language_sector": legacy.get("sector") if legacy.get("sector") in _SECTORS else "az",
        "degree_level": _DEGREE.get(str(legacy.get("bak_or_mag") or "").strip().lower(), "bachelor"),
        "education_form": _FORM.get(text(legacy.get("eyani_qiyabi")).casefold(), "full_time"),
    }
    _apply_form_rule(run, name, parent, settings)
    year = str(legacy.get("start_year") or "")[:4]
    if year.isdigit() and int(year) > 1990:
        settings["admission_year"] = int(year)
    parent_group = base if base is not None and base.parent_id == parent.pk else None
    if parent_group is not None:
        settings["parent_group"] = str(parent_group.pk)
        settings["parent_group_name"] = parent_group.name
    unit = OrgUnit.objects.create(
        organization=run.organization,
        unit_type="group",
        name=name,
        slug=f"{GROUP_SLUG_PREFIX}{legacy['id']}",
        parent=parent,
        settings=settings,
        is_active=True,
    )
    catalog.index_group(unit)
    run.created("groups", unit.pk)
    run.count("group.created")
    run.names("group_created", name, parent.name)
    return unit


def _apply_form_rule(run, name: str, parent, settings: dict) -> None:
    """Sahib 2026-10-25: forma qrup kodundan (3 rəqəm əyani, 4 rəqəm qiyabi) — legacy ``eyani_qiyabi`` ziddirsə
    qayda qalibdir (``group.form_rule_override`` sayılır). Magistr/kollec/qeyri-standart adda legacy dəyəri qalır."""

    from apps.organizations.public import group_chain_names, group_rule_form_for

    form, _reason = group_rule_form_for(name, settings=settings, names=group_chain_names(parent))
    if form is None:
        return
    if form != settings["education_form"]:
        run.count("group.form_rule_override")
        settings["education_form"] = form


def _base_group(catalog, name: str):
    """Ad alt qrup şablonuna uyğun gələn TƏK aktiv ana qrup («536 TB1» → «536 TB»), yoxsa ``None``."""

    from apps.registrar.public import subgroup_rollup

    found = [
        unit
        for unit in catalog.units.values()
        if unit.unit_type == "group"
        and unit.is_active
        and unit.name != name
        and subgroup_rollup.is_subgroup_of(unit.name, name)
    ]
    return found[0] if len(found) == 1 else None


def ensure_subject(run, legacy: dict):
    """Legacy fənn → ``Subject`` (tapılır və ya ``QKU-<id>`` kodu ilə yaradılır)."""

    catalog = run.catalog
    subject, how = catalog.subject_for(legacy)
    if subject is not None:
        run.count(f"subject.{how}")
        return subject
    if how == "ambiguous":
        run.count("subject.ambiguous")
        run.names("subject_ambiguous", text(legacy.get("name")), str(legacy["id"]))
        return None
    if how == "code_collision":
        # ``QKU-<id>`` başqa fənnin kartıdır — jurnal ötürülür; düzəliş ``subject_collisions`` fazasındadır.
        run.count("subject.code_collision")
        run.names("subject_code_collision", text(legacy.get("name")), str(legacy["id"]))
        return None
    name = text(legacy.get("name"))
    if not name:
        run.count("subject.unreadable")
        return None
    Subject = django_apps.get_model("registrar", "Subject")
    chair = catalog.unit_for_department(legacy.get("department_id"))
    subject = Subject.objects.create(
        organization=run.organization,
        code=f"{SUBJECT_CODE_PREFIX}{legacy['id']}",
        name=name,
        chair_unit=chair if chair is not None and chair.unit_type == "chair" else None,
        is_active=True,
    )
    catalog.index_subject(subject)
    run.created("subjects", subject.pk)
    run.count("subject.created")
    return subject


__all__ = ["ensure_group", "ensure_subject"]
