"""Tarixi boşluq cütləri → qeydiyyat qərarı (``history`` fazasının planı; YAZI yalnız ``create_enrollments``-də).

Cüt = ``(uniqid, legacy tələbə)``; paketə yalnız cutover ledger-ində ``migrated`` sətri OLMAYAN cütlər düşür.
Qaydalar ``repair_enrollments_select``-in qaydalarıdır (yeni paralel qayda yoxdur):

1. **Mövcud** — tələbənin jurnalın ÖZ açılışlarından birində yazılışı varsa o istifadə olunur (yalnız boş xanalar
   doldurulur). Bu, təkrar qaçışı da 0 yazı edir.
2. **Əkiz** — həmin fənn (eyni ``Subject`` və ya eyni ad açarı) + dövr üzrə BAŞQA açılışda yazılışı varsa cüt
   BƏRPA OLUNMUR (fənn transkriptdə/ÜOMG-də iki dəfə sayılmasın) — hesabata düşür.
3. **Real məzmun** — yeni yazılış yalnız ən azı bir REAL xana (bal / «iə» / üzrlü «qb») və ya rəqəm imtahan balı
   (``im``/``im2``) olan cüt üçün açılır; yalnız «qb» olan cüt boş fənn sətri yaratmır (K9 «no_cells» qaydasının
   tarixi forması).
4. **Dilim** (ledger açılışı olan jurnal) — ``_choose_slice``: tələbənin cari (SAR) qrupu → həmin dövrdəki digər
   yazılışlarının qrupu → jurnalın ilk dilimi. Cari qrupdan fərqli dilim = qonaq (``source_group``).
5. **Karantin** (heç bir dilimi köçməyən — qrupu mənbədə silinmiş — jurnal) — ``_evidence_slice``: tələbənin HƏMİN
   dövrdəki yazılışlarının TƏK qrupu; sübutsuz / çoxqruplu hal təxmin edilmir. Açılış (fənn + dövr + qrup) yoxdursa
   yaradılır və cutover J7 kimi KİLİDLƏNİR (``apply_lock``: tarixi nəticə dəyişməz).
6. DB qapısı (``registrar_guard_active_member``): yazılış yalnız AKTİV üzvlüyü (``student`` və ya arxiv ``alumni``)
   olan hesaba açılır.
"""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from .resolve import ledger_map, subject_key

EXAM_MONTHS = frozenset({"im", "im2"})


def pair_flags(points) -> dict:
    """``(uniqid, tələbə)`` → ``{"real": bool, "final": bool}`` (boş xana paketə düşmür)."""

    flags: dict = {}
    for row in points:
        key = (row["journal_uniqid"], row["student_id"])
        entry = flags.setdefault(key, {"real": False, "final": False})
        token = str(row.get("point") or "").strip().lower()
        if row["month_id"] in EXAM_MONTHS:
            entry["final"] = entry["final"] or token.replace(".", "", 1).isdigit()
        elif token.isdigit() or token == "ie" or (token == "qb" and int(row.get("excusable") or 0) == 1):
            entry["real"] = True
    return flags


class TargetState:
    """Boşluq tələbələrinin tarixi dövrlərdəki MÖVCUD yazılışları + SAR qrupu + DB qapısı (bir dəfə oxunur)."""

    def __init__(self, organization, user_ids, period_ids):
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        Membership = django_apps.get_model("organizations", "Membership")
        users = sorted(set(user_ids))
        self.by_offering: dict = {}
        self.by_subject: dict = defaultdict(list)
        self.groups: dict = defaultdict(set)
        for enrollment in (
            Enrollment.objects.filter(
                organization=organization, student_id__in=users, offering__period_id__in=period_ids
            )
            .select_related("offering__subject")
            .order_by("created_at", "pk")
        ):
            self.add(enrollment)
        self.sar = {
            student: str(group)
            for student, group in Record.objects.filter(
                organization=organization, student_id__in=users, is_active=True
            ).values_list("student_id", "group_id")
            if group is not None
        }
        self.enrollable = set(
            Membership.objects.filter(
                organization=organization,
                user_id__in=users,
                is_active=True,
                role__is_active=True,
                role__organization=organization,
                user__is_active=True,
            ).values_list("user_id", flat=True)
        )

    def add(self, enrollment) -> None:
        offering = enrollment.offering
        key = (enrollment.student_id, offering.pk)
        current = self.by_offering.get(key)
        if current is None or (current.status != "enrolled" and enrollment.status == "enrolled"):
            self.by_offering[key] = enrollment
        self.by_subject[(enrollment.student_id, offering.period_id)].append(
            (offering.subject_id, subject_key(offering.subject.name), offering.pk)
        )
        if offering.group_id is not None:
            self.groups[(enrollment.student_id, offering.period_id)].add(str(offering.group_id))

    def twin(self, user_id, period_id, subject, own_offerings) -> bool:
        name = subject_key(subject.name)
        return any(
            offering_id not in own_offerings and (subject_id == subject.pk or key == name)
            for subject_id, key, offering_id in self.by_subject.get((user_id, period_id), ())
        )


def ledger_slices(run, journals: dict) -> dict:
    """``uniqid`` → ``[(group_ref, unit, offering)]`` — cutover ledger-inin (``course_offering``) aktiv dilimləri."""

    from .extract import parse_id_list

    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    refs: dict = defaultdict(dict)
    for key, target in ledger_map(run.organization, "course_offering").items():
        uniqid, _sep, group_ref = str(key).partition(":")
        if uniqid in journals:
            refs[uniqid][group_ref] = target
    targets = sorted({target for value in refs.values() for target in value.values()})
    offerings = {
        str(offering.pk): offering
        for offering in CourseOffering.objects.filter(organization=run.organization, pk__in=targets).select_related(
            "subject", "period"
        )
    }
    out: dict = {}
    for uniqid, journal in journals.items():
        found = refs.get(uniqid)
        if not found:
            continue
        slices, seen = [], set()
        ordered = [str(gid) for gid in parse_id_list(journal["groups_id"])]
        ordered += sorted(ref for ref in found if ref not in ordered)
        for group_ref in ordered:
            offering = offerings.get(str(found.get(group_ref)))
            if offering is None or offering.pk in seen:
                continue
            if not offering.is_active:
                run.count("history.slice.inactive_offering")
                continue
            seen.add(offering.pk)
            slices.append((group_ref, str(offering.group_id or ""), offering))
        out[uniqid] = slices
    return out


class HistoryPlanner:
    """Cüt üzrə qərar; yeni yazılışlar ``pending``-ə toplanır, ``flush`` bir dəfəyə yazır."""

    def __init__(self, run, *, state: TargetState, slices: dict):
        from .journals import OfferingIndex

        self.run = run
        self.state = state
        self.slices = slices
        self.index = OfferingIndex(run)
        self.result: dict = {}
        self.pending: list = []
        self.now = timezone.now()

    def skip(self, reason: str, display: str = "", detail: str = "") -> None:
        self.run.count(f"history.pair.skipped.{reason}")
        if display:
            self.run.names(f"history_pair_{reason}", display, detail)

    def decide(self, uniqid, legacy_id, user_id, journal, flags, *, display: str = "") -> None:
        slices = self.slices.get(uniqid)
        if slices:
            self._sliced(uniqid, legacy_id, user_id, journal, flags, slices, display)
        elif slices is not None:
            self.skip("no_active_slice")
        else:
            self._quarantined(uniqid, legacy_id, user_id, journal, flags, display)

    def _use_existing(self, key, user_id, offerings) -> bool:
        found = [
            self.state.by_offering[(user_id, o.pk)] for o in offerings if (user_id, o.pk) in self.state.by_offering
        ]
        if not found:
            return False
        chosen = next((e for e in found if e.status == "enrolled"), found[0])
        self.result[key] = chosen
        self.run.count("history.pair.existing" if chosen.status == "enrolled" else "history.pair.existing_not_enrolled")
        return True

    def _can_create(self, user_id, period_id, subject, own, flags, display, uniqid) -> bool:
        if self.state.twin(user_id, period_id, subject, own):
            self.skip("twin_other_offering", display, f"{uniqid} · {subject.name}")
            return False
        if not (flags["real"] or flags["final"]):
            self.skip("absent_only")
            return False
        if user_id not in self.state.enrollable:
            self.skip("student_not_enrollable", display, uniqid)
            return False
        return True

    def _sliced(self, uniqid, legacy_id, user_id, journal, flags, slices, display) -> None:
        from ..repair_enrollments_select import _choose_slice

        key = (uniqid, legacy_id)
        offerings = [offering for _ref, _unit, offering in slices]
        if self._use_existing(key, user_id, offerings):
            return
        first = offerings[0]
        if not self._can_create(
            user_id, first.period_id, first.subject, {o.pk for o in offerings}, flags, display, uniqid
        ):
            return
        group_ref, _unit, rule = _choose_slice(
            [(ref, unit) for ref, unit, _offering in slices],
            sar_unit=self.state.sar.get(user_id, ""),
            same_period_units=self.state.groups.get((user_id, first.period_id), set()),
        )
        offering = next(offering for ref, _unit, offering in slices if ref == group_ref)
        self.run.count(f"history.slice.{rule}")
        self._create(key, user_id, offering)

    def _quarantined(self, uniqid, legacy_id, user_id, journal, flags, display) -> None:
        from ..repair_enrollments_select import _evidence_slice

        key = (uniqid, legacy_id)
        legacy_subject = self.run.legacy_subjects.get(journal["lesson_id"])
        subject = self.run.catalog.subject_for(legacy_subject)[0] if legacy_subject else None
        period = self.run.period_of(journal["semestr"])
        if subject is None or period is None:
            self.skip("quarantine_reference_unresolved")
            return
        evidence = self.state.groups.get((user_id, period.pk), set())
        chosen, why = _evidence_slice(evidence, {unit: unit for unit in evidence})
        if why:
            self.skip(f"quarantine_{why}", display, uniqid)
            return
        unit = self.run.catalog.units.get(_uuid(chosen[0][1]))
        if unit is None:
            self.skip("quarantine_no_slice")
            return
        offering, _how = self.index.find(subject, period, unit)
        own = [offering] if offering is not None else []
        if offering is not None and not offering.is_active:
            self.skip("quarantine_offering_inactive")
            return
        if self._use_existing(key, user_id, own):
            return
        if not self._can_create(user_id, period.pk, subject, {o.pk for o in own}, flags, display, uniqid):
            return
        if offering is None:
            offering = self._create_offering(subject, period, unit, journal)
            if offering is None:
                return
        self.run.count("history.slice.quarantine_evidence_group")
        self._create(key, user_id, offering)

    def _create_offering(self, subject, period, unit, journal):
        """Karantin jurnalı üçün açılış — müəllim yalnız ledger-dən (yeni hesab yaradılmır); J7 kimi kilidli."""

        from ..rehearsal_journal_lock_phase import apply_lock

        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        teacher = ledger_map(self.run.organization, "worker", [journal.get("teacher_id")]).get(
            str(journal.get("teacher_id"))
        )
        offering = None
        for instructor_id in (teacher, None) if teacher else (None,):
            try:
                with transaction.atomic():
                    offering = CourseOffering.objects.create(
                        organization=self.run.organization,
                        subject=subject,
                        period=period,
                        group=unit,
                        instructor_id=instructor_id,
                        lesson_hours=max(int(journal.get("fenn_saati") or 0), 0),
                        is_active=True,
                    )
                break
            except IntegrityError:
                self.run.count("history.offering.instructor_blocked")
        if offering is None:
            self.skip("quarantine_offering_create_failed")
            return None
        apply_lock(SimpleNamespace(organization=self.run.organization), offering_pk=offering.pk)
        self.index.add(offering)
        self.run.created("history_offerings", offering.pk)
        self.run.count("history.offering.created_locked")
        return offering

    def _create(self, key, user_id, offering) -> None:
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        own = self.state.sar.get(user_id, "")
        guest = bool(own) and own != str(offering.group_id)
        enrollment = Enrollment(
            organization=self.run.organization,
            student_id=user_id,
            offering=offering,
            kind="mandatory",
            status="enrolled",
            source_group_id=own if guest else None,
            added_by=self.run.actor if guest else None,
            added_at=self.now if guest else None,
        )
        self.state.add(enrollment)
        self.result[key] = enrollment
        self.pending.append(enrollment)
        self.run.count("history.pair.created_guest" if guest else "history.pair.created")

    def flush(self) -> None:
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        self.run.bulk_create(Enrollment, self.pending, "history_enrollments")
        for enrollment in self.pending:
            self.run.created("history_enrollments", enrollment.pk)
        self.pending = []


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return value


__all__ = ["HistoryPlanner", "TargetState", "ledger_slices", "pair_flags"]
