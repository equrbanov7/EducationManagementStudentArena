"""Tam semestr jurnalları → qrup açılışları (``CourseOffering``) + qeydiyyat (``Enrollment``).

Açılış
    Legacy jurnal = fənn + müəllim + qrup(lar). Hər qrup ayrıca açılışdır (cutover J1 və tədris
    tapşırığı sinxronu ilə eyni: ``(fənn, dövr, qrup)`` unikal açardır). Açılış VARSA (tapşırıq/dərs
    yükü faylı yaradıb) ona bağlanılır; müəllimi BOŞDURSA legacy müəllim yazılır, FƏRQLİDİRSƏ toxunulmur
    (yeni sistem qalibdir — «konflikt»). Saat yalnız açılışda 0-dırsa ``fenn_saati`` ilə doldurulur.
    Ləğv edilmiş (``is_active=False``) və bağlı jurnal açılışına YAZILMIR.

Qeydiyyat
    Legacy jurnalın tələbə siyahısı (+ xanası olan tələbələr). Tələbə həmin fənn+dövr üzrə HƏR HANSI
    açılışda artıq qeydiyyatdadırsa ikinci sətir AÇILMIR (mövcud sətir istifadə olunur). Tələbənin
    qrupu açılışın qrupu deyilsə — alt qrupdan / başqa qrupdan əlavə: ``source_group`` + ``added_by``
    (``guest_roster.add_guest_student``-in yazdığı forma ilə eyni).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from .extract import parse_id_list
from .resolve import subject_key
from .structure import ensure_group, ensure_subject


class JournalSlices:
    """Bir legacy jurnalın hədəf açılışları."""

    __slots__ = ("journal", "offerings", "writable")

    def __init__(self, journal):
        self.journal = journal
        self.offerings: list = []
        self.writable: set = set()

    def pick(self, group_id, catalog):
        """Tələbənin qrupuna uyğun açılış: öz qrupu → alt/ana qrup → tək dilim → birinci dilim."""

        from apps.registrar.public import subgroup_rollup

        if not self.offerings:
            return None
        for offering in self.offerings:
            if offering.group_id == group_id:
                return offering
        unit = catalog.units.get(group_id)
        if unit is not None:
            for offering in self.offerings:
                other = catalog.units.get(offering.group_id)
                if other is not None and (
                    subgroup_rollup.is_subgroup_of(other.name, unit.name)
                    or subgroup_rollup.is_subgroup_of(unit.name, other.name)
                ):
                    return offering
        return self.offerings[0]


def build_offerings(run) -> dict:
    """``uniqid → JournalSlices`` (açılışları tapır/yaradır)."""

    from apps.registrar.public import handover

    slices: dict = {}
    periods = {}
    index = OfferingIndex(run)
    for journal in run.bundle["journals"]:
        if journal.get("fake") or journal.get("sonra_sil"):
            run.count("journal.skipped_fake")
            continue
        semestr = journal["semestr"]
        if semestr not in periods:
            legacy_period = run.legacy_periods.get(semestr)
            periods[semestr] = run.catalog.period_for(legacy_period) if legacy_period else None
        period = periods[semestr]
        if period is None:
            run.count("journal.period_unresolved")
            continue
        legacy_subject = run.legacy_subjects.get(journal["lesson_id"])
        subject = ensure_subject(run, legacy_subject) if legacy_subject else None
        if subject is None:
            run.count("journal.subject_unresolved")
            continue
        groups = []
        for group_id in parse_id_list(journal["groups_id"]):
            legacy_group = run.legacy_groups.get(group_id)
            unit = ensure_group(run, legacy_group) if legacy_group else None
            if unit is None:
                run.count("journal_slice.group_unresolved")
                continue
            if unit not in groups:
                groups.append(unit)
        if not groups:
            run.count("journal.no_group")
            continue
        teacher, _outcome = run.teachers.resolve(journal["teacher_id"])
        entry = JournalSlices(journal)
        for unit in groups:
            offering = _ensure_offering(run, index, subject, period, unit, teacher, journal)
            if offering is not None:
                entry.offerings.append(offering)
        closed = handover.closed_offering_ids([offering.pk for offering in entry.offerings])
        entry.writable = {offering.pk for offering in entry.offerings if offering.pk not in closed}
        run.count("journal_slice.closed", len(entry.offerings) - len(entry.writable))
        slices[journal["uniqid"]] = entry
        run.count("journal.mapped")
    return slices


class OfferingIndex:
    """Dövr üzrə mövcud açılışlar: ``(fənn, dövr, qrup)`` və ``(dövr, qrup, fənn adı açarı)``.

    İkinci açar ona görədir ki, tapşırıq idxalı bəzi fənləri YENİ ``Subject`` sətri ilə açıb (eyni ad,
    başqa kod) — legacy fənni ilə eyni adlı açılış həmin qrupda varsa İKİNCİ jurnal açılmır.
    """

    def __init__(self, run):
        self.run = run
        self.by_key: dict = {}
        self.by_name: dict = {}
        self._loaded: set = set()

    def _load(self, period) -> None:
        if period.pk in self._loaded:
            return
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        for offering in CourseOffering.objects.filter(organization=self.run.organization, period=period).select_related(
            "subject"
        ):
            self.add(offering)
        self._loaded.add(period.pk)

    def add(self, offering) -> None:
        self.by_key[(offering.subject_id, offering.period_id, offering.group_id)] = offering
        name_key = (offering.period_id, offering.group_id, subject_key(offering.subject.name))
        self.by_name.setdefault(name_key, []).append(offering)

    def find(self, subject, period, unit):
        self._load(period)
        found = self.by_key.get((subject.pk, period.pk, unit.pk))
        if found is not None:
            return found, "existing"
        same_name = [o for o in self.by_name.get((period.pk, unit.pk, subject_key(subject.name)), []) if o.is_active]
        if len(same_name) == 1:
            return same_name[0], "existing_same_name"
        return None, "missing"


def _ensure_offering(run, index, subject, period, unit, teacher, journal):
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    hours = int(journal.get("fenn_saati") or 0)
    offering, how = index.find(subject, period, unit)
    if offering is None:
        for candidate in (teacher, None) if teacher is not None else (None,):
            try:
                with transaction.atomic():
                    offering = CourseOffering.objects.create(
                        organization=run.organization,
                        subject=subject,
                        period=period,
                        group=unit,
                        instructor=candidate,
                        lesson_hours=max(hours, 0),
                        is_active=True,
                    )
                break
            except IntegrityError:
                run.count("offering.instructor_blocked")
        if offering is None:
            run.count("offering.create_failed")
            return None
        index.add(offering)
        run.created("offerings", offering.pk)
        run.count("offering.created")
        return offering
    if not offering.is_active:
        run.count("offering.inactive_skipped")
        return None
    run.count(f"offering.{how}")
    fields = []
    if offering.instructor_id is None and teacher is not None:
        offering.instructor = teacher
        fields.append("instructor")
    elif teacher is not None and offering.instructor_id != teacher.pk:
        run.count("offering.instructor_conflict_kept")
    if not offering.lesson_hours and hours > 0:
        offering.lesson_hours = hours
        fields.append("lesson_hours")
    if fields:
        try:
            with transaction.atomic():
                offering.save(update_fields=fields + ["updated_at"])
            run.count("offering.filled")
            run.touched("offerings", offering.pk, fields)
        except IntegrityError:
            run.count("offering.instructor_blocked")
            offering.refresh_from_db()
    return offering


def _pick(candidates, journal_offering_ids):
    """Eyni fənn+dövr üzrə bir neçə qeydiyyat varsa DETERMİNİSTİK seçim: aktiv olan, legacy jurnalın öz
    açılışındakı, ən erkən yaradılmış (sıra qaçışdan-qaçışa dəyişmir)."""

    if not candidates:
        return None
    enrolled = [e for e in candidates if e.status == "enrolled"]
    for pool in (
        [e for e in enrolled if e.offering_id in journal_offering_ids],
        enrolled,
        list(candidates),
    ):
        if pool:
            return pool[0]
    return None


def build_enrollments(run, slices: dict) -> dict:
    """``(uniqid, legacy_student_id) → Enrollment`` — mövcudu tapır, çatışmayanı yaradır."""

    Enrollment = django_apps.get_model("registrar", "Enrollment")
    offerings = {offering.pk: offering for entry in slices.values() for offering in entry.offerings}
    subject_period = {(o.subject_id, o.period_id) for o in offerings.values()}
    existing: dict = {}
    for enrollment in (
        Enrollment.objects.filter(
            organization=run.organization,
            offering__subject_id__in={key[0] for key in subject_period},
            offering__period_id__in={key[1] for key in subject_period},
        )
        .select_related("offering")
        .order_by("created_at", "pk")
    ):
        key = (enrollment.student_id, enrollment.offering.subject_id, enrollment.offering.period_id)
        existing.setdefault(key, []).append(enrollment)
    points_by_journal: dict = {}
    for point in run.bundle["points"]:
        points_by_journal.setdefault(point["journal_uniqid"], set()).add(point["student_id"])
    result: dict = {}
    pending: list = []
    now = timezone.now()
    for uniqid, entry in slices.items():
        legacy_ids = list(dict.fromkeys(parse_id_list(entry.journal["students_id"])))
        legacy_ids += [sid for sid in sorted(points_by_journal.get(uniqid, ())) if sid not in legacy_ids]
        for legacy_id in legacy_ids:
            user_id, _outcome = run.students.resolve(legacy_id)
            if user_id is None:
                run.count("enrollment.student_unresolved")
                continue
            group_id = run.students.group_of.get(user_id)
            offering = entry.pick(group_id, run.catalog)
            if offering is None:
                continue
            key = (user_id, offering.subject_id, offering.period_id)
            found = _pick(existing.get(key), {o.pk for o in entry.offerings})
            if found is not None:
                result[(uniqid, legacy_id)] = found
                run.count("enrollment.existing" if found.status == "enrolled" else "enrollment.existing_not_enrolled")
                continue
            if user_id not in run.students.active_ids:
                run.count("enrollment.student_not_active")
                continue
            if offering.pk not in entry.writable:
                run.count("enrollment.closed_journal")
                continue
            guest = group_id is not None and group_id != offering.group_id
            enrollment = Enrollment(
                organization=run.organization,
                student_id=user_id,
                offering=offering,
                kind="mandatory",
                status="enrolled",
                source_group_id=group_id if guest else None,
                added_by=run.actor if guest else None,
                added_at=now if guest else None,
            )
            existing.setdefault(key, []).append(enrollment)
            result[(uniqid, legacy_id)] = enrollment
            pending.append(enrollment)
            run.count("enrollment.created_guest" if guest else "enrollment.created")
    run.bulk_create(Enrollment, pending, "enrollments")
    return result


__all__ = ["JournalSlices", "build_enrollments", "build_offerings"]
