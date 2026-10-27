"""``syllabi_share`` — köhnə sistemin «BİR sillabus — bir neçə jurnal» faktı (sahib 2026-10-27, OPT-IN faza).

Sahib: «Sillabus köçən zaman: sillabus 1 ədəddir tutalım, amma müəllim köhnə jurnalda o sillabusu 2 qrup üçün
istifadə edib; jurnalı aktivləşdirərkən indi o bir qrup üçün görünür, 2-ci üçün yox … köhnədən gələndə elə olsun —
bir sillabus. Əgər müəllim eyni sillabusu 2 qrup və s. üçün də istifadə edibsə əvvəl, elə də olsun (məsələn potok
dərsləri)».

Sübut — paketin cari semestr jurnalları: hər jurnalın ``sillabus_id``-si və qrupları (``groups_id``). Eyni köhnə
sillabusu (``L``) işlədən jurnalların qrup açılışları (YALNIZ OXU: ``Catalog.group_for`` + ``OfferingIndex.find``
— açılış/qrup YARADILMIR) açılışın müəllimi üzrə qruplaşdırılır. Hər müəllim üçün:

* **lövbər** — həmin açılışlardan birinin ÖZ aktiv dosyesi, köçürmə versiyasının (``change_kind=imported``)
  məzmunu ``L``-in çeviricidən keçmiş məzmunu ilə EYNİDİR (həftəlik mövzular + təsvir + nəticələr);
  bir neçəsi varsa ən erkən yaradılan (qalanları öz nüsxələrini saxlayır — üstünə yazılmır);
* **hədəf** — eyni ``L``-i işlədən, jurnalda HEÇ BİR sillabusu görünməyən (``syllabus_for_offering`` boş) açılış
  → lövbərə ``SyllabusShare(source=legacy)`` (surət yox — təsdiq, versiya, plan BİRDİR).

FILL-ONLY və idempotentdir: sillabusu olan jurnal (öz dosye, paylaşım, fənn+semestr, baza) toxunulmur; ikinci
qaçış ``linked 0`` verir. Başqa müəllimin sillabusu heç vaxt paylaşılmır (açılışın müəllimi = lövbərin müəllifi).
Lövbər yoxdursa (köhnə sillabus heç bir açılışa köçməyib) — sayılır (``no_anchor``), yazılmır: belə müəllimə
``syllabi_backfill`` baza dosye gətirir və o, müəllimin bütün qruplarını onsuz da örtür.

Saylar: ``syllabi_share.<açar> <say>`` (``COUNTER_KEYS`` — 0 da çap olunur).
"""

from __future__ import annotations

import re
from collections import defaultdict

from django.apps import apps as django_apps

from ..rehearsal_syllabus_targets import build_section_data
from .extract import parse_id_list
from .journals import OfferingIndex
from .syllabi import _same_subject, document_for

PHASE = "syllabi_share"
COUNTER_KEYS = (
    "legacy_syllabi",
    "multi_group",
    "offerings",
    "unmapped_groups",
    "empty",
    "anchored",
    "no_anchor",
    "own_copy",
    "covered",
    "linked",
    "already",
    "has_own",
    "taken",
    "not_sibling",
    "other_teacher",
    "teacher_filtered",
)

_SPACE = re.compile(r"\s+")


def _flag(value) -> bool:
    return str(value or "0").strip() not in ("", "0")


def _norm(value) -> str:
    return _SPACE.sub(" ", str(value or "")).strip().casefold()


def fingerprint(section_data: dict) -> tuple:
    """Məzmun izi — həftəlik mövzular + təsvir + nəticələr (bal bölgüsü / info SAYILMIR: sonradan normallaşır)."""

    week = (section_data.get("week") or {}).get("rows") or []
    topics = tuple(_norm(row.get("topic")) for row in week if isinstance(row, dict))
    description = _norm((section_data.get("desc") or {}).get("description"))
    outcomes = tuple(_norm(item) for item in (section_data.get("out") or {}).get("outcomes") or ())
    if not any(topics) and not description and not any(outcomes):
        return ()
    return (topics, description, outcomes)


def _legacy_fingerprint(legacy: dict, memo: dict) -> tuple:
    if legacy["id"] not in memo:
        memo[legacy["id"]] = fingerprint(build_section_data(document_for(legacy))[0])
    return memo[legacy["id"]]


def journal_offerings(run, journal, index) -> tuple[list, int]:
    """Jurnalın AKTİV qrup açılışları (yalnız oxu) və tapılmayan qrup sayı."""

    period = run.period_of(journal.get("semestr"))
    legacy_subject = run.legacy_subjects.get(journal.get("lesson_id"))
    subject = run.catalog.subject_for(legacy_subject)[0] if legacy_subject else None
    group_ids = parse_id_list(journal.get("groups_id"))
    if period is None or subject is None:
        return [], len(group_ids)
    found, missing = [], 0
    for group_id in group_ids:
        legacy_group = run.legacy_groups.get(group_id)
        unit = run.catalog.group_for(legacy_group)[0] if legacy_group else None
        offering = index.find(subject, period, unit)[0] if unit is not None else None
        if offering is None or not offering.is_active:
            missing += 1
            continue
        found.append(offering)
    return found, missing


def _anchor(offerings, legacy_print) -> object | None:
    """Açılışlardan birinin ``L``-dən köçmüş ÖZ dosyesi (ən erkən yaradılan) və ya ``None``."""

    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    SyllabusSection = django_apps.get_model("syllabus", "SyllabusSection")
    candidates = list(
        Syllabus.objects.filter(
            offering_id__in=[offering.pk for offering in offerings],
            is_active=True,
            reused_from__isnull=True,
            versions__change_kind="imported",
        )
        .select_related("offering")
        .distinct()
        .order_by("created_at", "pk")
    )
    if not candidates:
        return None
    versions: dict = defaultdict(dict)
    owner: dict = {}
    for version_id, syllabus_id, section_id, data in SyllabusSection.objects.filter(
        version__syllabus_id__in=[row.pk for row in candidates],
        version__change_kind="imported",
        section_id__in=("week", "desc", "out"),
    ).values_list("version_id", "version__syllabus_id", "section_id", "data"):
        versions[version_id][section_id] = data or {}
        owner[version_id] = syllabus_id
    # Bir dosyedə bir neçə köçürmə versiyası ola bilər — hansısa ``L`` ilə eynidirsə dosye ``L``-dəndir.
    matched = {owner[version_id] for version_id, data in versions.items() if fingerprint(data) == legacy_print}
    for syllabus in candidates:
        if syllabus.pk in matched:
            return syllabus
    return None


def _uses(run) -> dict:
    """``legacy sillabus id → [jurnal, …]`` — saxta / «sonra sil» atılır, fənni uyğun gəlməyən jurnal sayılmır."""

    by_id = {row["id"]: row for row in run.bundle.get("syllabi") or ()}
    uses: dict = defaultdict(list)
    for journal in run.bundle.get("journals") or ():
        if _flag(journal.get("fake")) or _flag(journal.get("sonra_sil")):
            continue
        legacy = by_id.get(journal.get("sillabus_id"))
        if legacy is None or not _same_subject(run, legacy.get("lesson_id"), journal.get("lesson_id")):
            continue
        uses[legacy["id"]].append(journal)
    return {key: (by_id[key], journals) for key, journals in uses.items()}


def share_legacy_syllabi(run) -> None:
    """Bax modul docstring-i. ``run.share_teacher_id`` (ixtiyari) — yalnız bu müəllimin jurnalları."""

    from apps.syllabus.public import link_legacy_share, syllabus_for_offering

    for key in COUNTER_KEYS:
        run.counters.setdefault(f"{PHASE}.{key}", 0)
    only_teacher = getattr(run, "share_teacher_id", None)
    index = OfferingIndex(run)
    prints: dict = {}
    for _legacy_id, (legacy, journals) in sorted(_uses(run).items()):
        run.count(f"{PHASE}.legacy_syllabi")
        offerings: dict = {}
        for journal in journals:
            found, missing = journal_offerings(run, journal, index)
            run.count(f"{PHASE}.unmapped_groups", missing)
            for offering in found:
                offerings.setdefault(offering.pk, offering)
        by_teacher: dict = defaultdict(list)
        for offering in offerings.values():
            if offering.instructor_id is not None:
                by_teacher[offering.instructor_id].append(offering)
        for teacher_id, group in sorted(by_teacher.items()):
            if len(group) < 2:
                continue
            if only_teacher is not None and teacher_id != only_teacher:
                run.count(f"{PHASE}.teacher_filtered")
                continue
            run.count(f"{PHASE}.multi_group")
            run.count(f"{PHASE}.offerings", len(group))
            legacy_print = _legacy_fingerprint(legacy, prints)
            if not legacy_print:
                run.count(f"{PHASE}.empty")
                continue
            anchor = _anchor(group, legacy_print)
            if anchor is None:
                run.count(f"{PHASE}.no_anchor")
                continue
            run.count(f"{PHASE}.anchored")
            for offering in group:
                if offering.pk == anchor.offering_id:
                    continue
                found = syllabus_for_offering(
                    organization=run.organization,
                    offering_id=offering.pk,
                    subject_id=offering.subject_id,
                    period_id=offering.period_id,
                    instructor_id=offering.instructor_id,
                )
                if found is not None:
                    # ``own_copy`` — açılışın ÖZ (əvvəlki köçürmədən) nüsxəsi: FILL-ONLY, üstünə yazılmır.
                    run.count(f"{PHASE}.{'own_copy' if found.offering_id == offering.pk else 'covered'}")
                    continue
                outcome = link_legacy_share(syllabus=anchor, offering=offering, user=run.actor)
                run.count(f"{PHASE}.{outcome}")
                if outcome == "linked":
                    run.created("syllabus_shares", offering.pk)


__all__ = ["COUNTER_KEYS", "PHASE", "fingerprint", "journal_offerings", "share_legacy_syllabi"]
