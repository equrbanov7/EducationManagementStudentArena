"""Keçilmiş dərsin MÜƏLLİMİ bərpası (sahib 2026-11-13: «keçilmiş dərslərdə müəllim nə vaxt nə yazıbsa görünsün»).

Problem
-------
``legacy_delta_apply`` 2026/2027 Payız dərslərini (köhnə sistem, 16.09–21.10) ``Lesson.instructor`` BOŞ yaradıb.
Boş müəllim «açılışın CARİ sahibi» kimi oxunur (``lessons_log.scoped_lessons``) — ona görə:

* köhnə sistemdə bir fənnin mühazirəsi bir müəllimdə, seminarı başqasında AYRI jurnal idi; yeni sistemdə bir
  açılışa birləşəndə HAMISI sahibə yazılır (Enzimologiya 234 BİO az: Nuray İsmayılzadənin 4 seminarı Səltənət
  Ağayevaya düşüb, Nuray «Keçilmiş dərslər»də görmür);
* fənn təhvili / yük bölgüsü sahibi dəyişəndə köhnə müəllimin keçdiyi dərslər YENİ sahibə «sürüşür».

Həll (YALNIZ boş ``instructor`` doldurulur — dolu sahəyə toxunulmur, fərq sayılır)
----------------------------------------------------------------------------------
1. **Köhnə sistem sübutu** (``apps/legacy_import/lesson_authors_2026_11_13.json``, ``legacy-lesson-authors/1``):
   hər köhnə jurnal — müəllimin legacy id-si, fənn, qrup(lar), dərs slotları (tarix + saat). Ad / FİN YOXDUR.
   Ledger-siz müəllim üçün faylda ``user`` var — 03.11 prod nüsxəsində eyni ad resolveri ilə (hesab yaratmadan)
   tapılmış istifadəçi id-si; yalnız AKTİV hesab qəbul olunur.
   Prod-da: müəllim ledger ``worker`` → istifadəçi; qrup :class:`Catalog` (ledger → slug → ad) + ALT qrupları
   (yol üzrə); dərs = həmin qrupların bu dövrdəki AKTİV açılışlarında EYNİ tarix + saat, fənni eyni olan
   (ledger fənni və ya qatlanmış ad bərabərdir). Bir dərsə iki müəllim iddia edirsə əvvəl dərsin ÖZ
   qrupunun jurnalı (alt qrup jurnalı ana qrupunkundan üstündür), sonra açılışın sahibi / aktiv pay müəllimi
   olan TƏK namizəd qəbul olunur, yoxsa ``conflict`` (toxunulmur — eyni anda iki müəllimli dərs).
2. **Yeni sistemdə yaradılmış** (``created_by`` dolu) boş dərs — cari sahibə, AMMA dərsdən SONRA təhvil qeydi
   varsa toxunulmur (``new_after_handover`` — əl ilə baxılır).

Köhnə sistem dərsi sübutla tapılmırsa BOŞ qalır (``teaching_hours``-da «naməlum saat» kimi görünür — saxta
müəllif yazılmır). Hər açılış üçün bir audit sətri (``lessons``: dərs → müəllim); ``undo`` həmin izlə yalnız
hələ də eyni müəllimdə olan dərsləri BOŞA qaytarır. Təkrar qaçış idempotentdir.
"""

from __future__ import annotations

import datetime
import json
import pathlib
from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils import timezone

from core.audit import log_actions
from core.constants import AuditAction

from .delta.resolve import Catalog, ledger_map, subject_key

FORMAT = "legacy-lesson-authors/1"
DEFAULT_FILE = pathlib.Path(__file__).resolve().parents[1] / "lesson_authors_2026_11_13.json"
RESOURCE = "legacy_import.lesson_authors_2026_11_13"
REASON = "Sahib 2026-11-13: keçilmiş dərsin müəllimi köhnə sistemin jurnalından / jurnal sahibindən bərpa olundu"
UNDO_REASON = "Sahib 2026-11-13: dərs müəllifi bərpası geri qaytarıldı"


def _model(app, name):
    return django_apps.get_model(app, name)


def load(path=None) -> dict:
    with open(path or DEFAULT_FILE, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("format_unknown")
    return data


def _period(organization, spec: dict):
    AcademicPeriod = _model("organizations", "AcademicPeriod")
    year, season = str(spec.get("academic_year") or ""), str(spec.get("name") or "")
    found = [
        period
        for period in AcademicPeriod.objects.filter(organization=organization, academic_year=year).order_by("pk")
        if season and season.casefold() in str(period.name or "").casefold()
    ]
    return found[0] if len(found) == 1 else None


def _slot(text: str):
    try:
        day, clock = str(text).split(" ", 1)
        return datetime.date.fromisoformat(day), datetime.time.fromisoformat(clock[:5])
    except ValueError:
        return None


class _Index:
    """Dövrün aktiv açılışlarındakı dərslər: ``(qrup, tarix, saat) → [dərs]`` + açılışın sahib / pay müəllimləri."""

    def __init__(self, organization, period, cutoff):
        Lesson, JournalShare = _model("registrar", "Lesson"), _model("registrar", "JournalShare")
        self.by_slot = defaultdict(list)
        self.offerings = {}
        rows = Lesson.objects.filter(
            organization=organization,
            offering__period=period,
            offering__is_active=True,
            date__lte=cutoff,
            start_time__isnull=False,
        ).values_list(
            "pk",
            "offering_id",
            "offering__group_id",
            "offering__subject_id",
            "offering__subject__name",
            "offering__instructor_id",
            "date",
            "start_time",
            "instructor_id",
        )
        self.lessons = {}
        for pk, offering_id, group_id, subject_id, subject_name, owner_id, date, start, instructor_id in rows:
            self.lessons[pk] = {"offering_id": offering_id, "instructor_id": instructor_id}
            self.offerings[offering_id] = (subject_id, subject_key(subject_name), owner_id)
            self.by_slot[(group_id, date, start.replace(second=0, microsecond=0))].append(pk)
        self.holders = defaultdict(set)
        for offering_id, (_subject, _key, owner_id) in self.offerings.items():
            if owner_id:
                self.holders[offering_id].add(owner_id)
        for offering_id, teacher_id in JournalShare.objects.filter(
            offering_id__in=list(self.offerings), is_active=True
        ).values_list("offering_id", "teacher_id"):
            self.holders[offering_id].add(teacher_id)


def _subtree(catalog, unit) -> set:
    prefix = f"{unit.path}/" if getattr(unit, "path", "") else None
    found = {unit.pk}
    if prefix:
        found |= {pk for pk, other in catalog.units.items() if str(other.path or "").startswith(prefix)}
    return found


def _claims(organization, data, index, counts) -> dict:
    """``dərs pk → {müəllim id}`` — köhnə sistem jurnallarının iddiaları."""
    catalog = Catalog(organization)
    journals = data.get("journals") or []
    teachers = ledger_map(organization, "worker", {str(entry.get("teacher")) for entry in journals})
    User = _model("auth", "User")
    teacher_pks = [int(pk) for pk in teachers.values() if str(pk).isdigit()]
    teacher_pks += [int(entry["user"]) for entry in journals if str(entry.get("user") or "").isdigit()]
    # Ledger-siz müəllim (köçürmədə adla tapılıb): fayldakı ``user`` — prod nüsxəsində ledger → ad resolveri ilə
    # (hesab YARATMADAN) həll olunmuş id. Ledger üstündür; bloklanmış / birləşdirilmiş (passiv) hesaba yazılmır.
    existing = set(User.objects.filter(pk__in=teacher_pks, is_active=True).values_list("pk", flat=True))
    claims = defaultdict(dict)  # dərs → {müəllim: dəqiqlik} (0 — jurnalın öz qrupu, 1 — onun alt qrupu)
    for entry in journals:
        counts["journals"] += 1
        target = teachers.get(str(entry.get("teacher"))) or entry.get("user")
        teacher_id = int(target) if target and str(target).isdigit() and int(target) in existing else None
        if teacher_id is None:
            counts["journal_teacher_unresolved"] += 1
            counts["slot_teacher_unresolved"] += len(entry.get("slots") or [])
            continue
        legacy_subject = entry.get("subject") or {}
        subject, _how = catalog.subject_for(legacy_subject) if legacy_subject.get("id") else (None, "missing")
        wanted_key = subject_key(legacy_subject.get("name"))
        groups = {}
        for legacy_group in entry.get("groups") or []:
            unit, _how = catalog.group_for(legacy_group)
            if unit is not None:
                for group_id in _subtree(catalog, unit):
                    groups[group_id] = min(groups.get(group_id, 1), 0 if group_id == unit.pk else 1)
        if not groups:
            counts["journal_group_unresolved"] += 1
            continue
        for text in entry.get("slots") or []:
            slot = _slot(text)
            if slot is None:
                counts["slot_invalid"] += 1
                continue
            hits = [
                (pk, depth)
                for group_id, depth in groups.items()
                for pk in index.by_slot.get((group_id, slot[0], slot[1]), ())
                if _same_subject(index, pk, subject, wanted_key)
            ]
            if not hits:
                counts["slot_no_lesson"] += 1
                continue
            counts["slot_matched"] += 1
            for pk, depth in hits:
                claims[pk][teacher_id] = min(claims[pk].get(teacher_id, depth), depth)
    return claims


def _same_subject(index, lesson_pk, subject, wanted_key) -> bool:
    subject_id, key, _owner = index.offerings[index.lessons[lesson_pk]["offering_id"]]
    return (subject is not None and subject_id == subject.pk) or (bool(wanted_key) and key == wanted_key)


def _decide(index, claims, counts) -> dict:
    """``dərs pk → müəllim`` — yalnız boş ``instructor``.

    Çoxlu iddiada əvvəl DƏQİQ qrup qalib gəlir (alt qrupun öz jurnalı ana qrupun jurnalından üstündür), sonra
    sahib / pay müəllimi olan TƏK namizəd; qalanı ``lesson_conflict`` (toxunulmur).
    """
    plan = {}
    for pk, ranked in claims.items():
        lesson = index.lessons[pk]
        best = min(ranked.values())
        teachers = {teacher for teacher, depth in ranked.items() if depth == best}
        if len(teachers) < len(ranked):
            counts["lesson_conflict_resolved_by_group"] += 1
        if len(teachers) > 1:
            teachers = teachers & index.holders.get(lesson["offering_id"], set())
            if len(teachers) != 1:
                counts["lesson_conflict"] += 1
                continue
            counts["lesson_conflict_resolved_by_holder"] += 1
        teacher_id = next(iter(teachers))
        current = lesson["instructor_id"]
        if current == teacher_id:
            counts["lesson_already"] += 1
        elif current is not None:
            counts["lesson_differs_kept"] += 1
        else:
            plan[pk] = teacher_id
    counts["lesson_legacy_planned"] += len(plan)
    return plan


def _new_system_plan(organization, period, plan, counts) -> dict:
    """Yeni sistemdə yaradılmış boş-müəllimli dərs → cari sahib (dərsdən sonra təhvil yoxdursa)."""
    Lesson, Handover = _model("registrar", "Lesson"), _model("registrar", "TeachingHandover")
    rows = list(
        Lesson.objects.filter(
            organization=organization,
            offering__period=period,
            offering__is_active=True,
            instructor__isnull=True,
            created_by__isnull=False,
            date__lte=timezone.localdate(),
        )
        .exclude(pk__in=list(plan))
        .values_list("pk", "offering_id", "offering__instructor_id", "date")
    )
    last = {}
    for offering_id, created in Handover.objects.filter(
        organization=organization, offering_id__in={row[1] for row in rows}, reverted_at__isnull=True
    ).values_list("offering_id", "created_at"):
        day = timezone.localdate(created)
        last[offering_id] = max(last.get(offering_id, day), day)
    out = {}
    for pk, offering_id, owner_id, date in rows:
        if owner_id is None:
            counts["new_no_owner"] += 1
        elif offering_id in last and last[offering_id] > date:
            counts["new_after_handover"] += 1
        else:
            out[pk] = owner_id
    counts["lesson_new_planned"] += len(out)
    return out


def run(*, organization, actor, counts, apply=False, path=None) -> None:
    Lesson = _model("registrar", "Lesson")
    data = load(path)
    period = _period(organization, data.get("period") or {})
    if period is None:
        counts["period_unresolved"] += 1
        return
    cutoff = datetime.date.fromisoformat(str(data.get("cutoff")))
    index = _Index(organization, period, cutoff)
    plan = _decide(index, _claims(organization, data, index, counts), counts)
    plan.update(_new_system_plan(organization, period, plan, counts))
    by_offering = defaultdict(dict)
    owners = {}
    for pk, offering_id, owner_id in Lesson.objects.filter(pk__in=list(plan)).values_list(
        "pk", "offering_id", "offering__instructor_id"
    ):
        by_offering[offering_id][pk] = plan[pk]
        owners[offering_id] = owner_id
    Offering = _model("registrar", "CourseOffering")
    entries = []
    now = timezone.now()
    for offering in Offering.objects.filter(pk__in=list(by_offering)).order_by("pk"):
        lessons = by_offering[offering.pk]
        by_teacher = defaultdict(list)
        for pk, teacher_id in lessons.items():
            by_teacher[teacher_id].append(pk)
        written = {}
        for teacher_id, pks in by_teacher.items():
            changed = Lesson.objects.filter(pk__in=pks, instructor__isnull=True).update(
                instructor_id=teacher_id, updated_at=now
            )
            counts["lessons_stamped"] += changed
            written.update({str(pk): teacher_id for pk in pks})
            if teacher_id != owners.get(offering.pk):
                counts["lessons_to_non_owner"] += changed
        counts["offerings_touched"] += 1
        entries.append(
            {
                "action": AuditAction.UPDATE,
                "user": actor,
                "organization": organization,
                "obj": offering,
                "old_values": {"instructor": None},
                "new_values": {"lessons": written},
                "reason": REASON,
                "resource_type": RESOURCE,
                "resource_id": str(offering.pk),
            }
        )
    for start in range(0, len(entries), 500):
        log_actions(entries[start : start + 500])
    counts["lesson_null_left"] += Lesson.objects.filter(
        organization=organization, offering__period=period, offering__is_active=True, instructor__isnull=True
    ).count()


def undo(*, organization, actor, counts, apply=False, path=None) -> None:
    Lesson, AuditLog = _model("registrar", "Lesson"), _model("audit", "AuditLog")
    now = timezone.now()
    for entry in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE).order_by("created_at"):
        lessons = (entry.new_values or {}).get("lessons") or {}
        by_teacher = defaultdict(list)
        for pk, teacher_id in lessons.items():
            by_teacher[teacher_id].append(pk)
        for teacher_id, pks in by_teacher.items():
            counts["undo_lessons_cleared"] += Lesson.objects.filter(Q(pk__in=pks) & Q(instructor_id=teacher_id)).update(
                instructor=None, updated_at=now
            )
        counts["undo_offerings"] += 1


__all__ = ["DEFAULT_FILE", "FORMAT", "RESOURCE", "load", "run", "undo"]
