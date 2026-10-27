"""İmtahan ↔ elektron jurnal (açılış) bağlantısı — registrar tərəfi (sahib 2026-10-24).

Sahib: «Midterm yaradılıb tələbələr verəndə nəticə jurnalın «Midterm» xanasına avtomatik düşsün». Prod
halı («JS Loop»): imtahan əvvəl YANLIŞ fənnə bağlanmış, tələbələr imtahanı verəndən SONRA fənn
«Mobil proqramlaşdırma»ya dəyişdirilmişdi — cəhdlər bitəndə körpü yanlış fənn üzrə qeydiyyat tapmadı
(``no_enrollment``), fənn dəyişəndə isə heç nə yenidən sinxronlaşmadı → jurnalda «Midterm» 0 qaldı.

Bu modul exams tərəfinə (``apps.registrar.public`` fasadı ilə) bunları verir:

* **Müəllimin fənləri** — :func:`teacher_offerings` / :func:`teacher_subject_ids`: cari dövrdə müəllimin
  TƏDRİS ETDİYİ açılışlar (jurnal sahibi ``CourseOffering.instructor`` və ya həmin jurnalda dərs aparmış
  ``Lesson.instructor``), istəyə görə imtahanın qruplarına (alt / ana qrup daxil) görə süzülmüş.
* **Bağlantı** — :func:`link_offering_ids`: imtahanın fənni + qrupları (+ müəllim) → hər qrupun ÖZ
  açılışı (açılış ``(fənn, dövr, qrup)`` üzrə unikaldır, yəni qrup başına ən çox bir jurnal).
* **Qrupun jurnal əhatəsi** — :func:`group_subject_coverage`: seçilən reyestr qrupunun neçə tələbəsi fənnin
  cari dövr jurnalında YOXDUR (sehrbaz xəbərdarlığı + məcburi əlavə səbəbi, sahib 2026-10-27).
* **Köhnə bağlantının təmizlənməsi** — :func:`clear_stale_midterm_scores`: bu imtahanın
  (``exam_source.exam_id``) yazdığı, amma artıq imtahanın fənninə / bağlı jurnalına aid olmayan
  avtomatik xanalar silinir (yalnız BU imtahanın yazdıqları; əl ilə yazılmış xanaya toxunulmur).
  Bağlanmış jurnal və sənədli düzəlişli xana toxunulmur; hər silinmə audit izinə yazılır
  (fail-closed — audit düşsə silinmə də geri qayıdır).
"""

from __future__ import annotations

import logging
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Q

from apps.registrar import exam_bridge, grade_audit, midterm_bridge, subgroup_rollup
from apps.registrar.audit_write import AuditWriteFailed
from apps.registrar.gradebook import journal_is_locked
from apps.registrar.models import (
    AcademicStatus,
    ComponentScore,
    ComponentScoreCorrection,
    CourseOffering,
    Enrollment,
    StudentAcademicRecord,
    Subject,
)

logger = logging.getLogger(__name__)

#: ``clear_stale_midterm_scores`` statusları.
CLEARED = "cleared"
KEPT_LOCKED = "kept_journal_locked"
KEPT_CORRECTED = "kept_corrected"
CLEAR_FAILED = "clear_failed"


def current_period(organization):
    """İmtahan körpüsünün işlətdiyi dövr (cari, yoxdursa ən son) — ``resolve_enrollment`` ilə EYNİ."""
    if organization is None:
        return None
    return exam_bridge._current_period(organization)


def expand_group_ids(organization, group_ids) -> set:
    """Qrup id-ləri + alt qrupları («234 K az» → 234 K-1/-2) + ana qrup namizədləri (alt qrup → ana)."""
    ids = {str(value) for value in group_ids or () if value}
    if not ids or organization is None:
        return set()
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    units = list(OrgUnit.objects.filter(organization=organization, pk__in=ids, unit_type="group"))
    out = {unit.pk for unit in units}
    out |= {unit.pk for unit in subgroup_rollup.subgroup_units(organization, units)}
    for unit in units:
        out |= {parent.pk for parent in subgroup_rollup.parent_group_candidates(organization, unit)}
    return out


def _period_offerings(organization, period):
    return CourseOffering.objects.filter(organization=organization, period=period, is_active=True)


def teacher_offerings(organization, teacher, *, group_ids=None, period=None):
    """Müəllimin cari dövrdə tədris etdiyi açılışlar (jurnal sahibi və ya həmin jurnalda dərs aparan).

    ``group_ids`` verilibsə (``None`` deyil) yalnız həmin qrupların (alt / ana qrup daxil) açılışları."""
    period = period or current_period(organization)
    if organization is None or teacher is None or period is None:
        return CourseOffering.objects.none()
    teacher_id = getattr(teacher, "pk", teacher)
    from .journal_shares import shared_offering_ids

    # Bölünmüş jurnalın pay sahibi də (səviyyə müəllimi öz jurnalına Midterm yaradır — sahib 2026-10-26).
    offerings = _period_offerings(organization, period).filter(
        Q(instructor_id=teacher_id) | Q(lessons__instructor_id=teacher_id) | Q(pk__in=shared_offering_ids(teacher_id))
    )
    if group_ids is not None:
        offerings = offerings.filter(group_id__in=expand_group_ids(organization, group_ids))
    return offerings.distinct()


def teacher_subject_ids(organization, teacher, *, group_ids=None, period=None) -> set:
    """Müəllimin cari dövrdə tədris etdiyi fənlərin id-ləri."""
    return set(
        teacher_offerings(organization, teacher, group_ids=group_ids, period=period).values_list(
            "subject_id", flat=True
        )
    )


def teacher_subjects(organization, teacher, *, group_ids=None, period=None):
    """Müəllimin cari dövrdə tədris etdiyi fənlər (``Subject`` queryset — exams seçicisi süzür / sıralayır)."""
    if organization is None:
        return Subject.objects.none()
    return Subject.objects.filter(
        organization=organization,
        pk__in=teacher_subject_ids(organization, teacher, group_ids=group_ids, period=period),
    )


def link_offering_ids(organization, *, subject_id, group_ids=(), teacher=None, period=None) -> list:
    """İmtahanın bağlanacağı jurnal açılışları (pk siyahısı).

    * qruplar seçilibsə — fənnin cari dövrdə HƏR qrupun (alt / ana qrup daxil) öz açılışı;
    * qrup yoxdur, müəllim var — müəllimin həmin fənn üzrə açılışları;
    * heç biri yoxdur — boş (körpü tələbənin fənn üzrə qeydiyyatına düşür, əvvəlki kimi)."""
    period = period or current_period(organization)
    if organization is None or not subject_id or period is None:
        return []
    offerings = _period_offerings(organization, period).filter(subject_id=subject_id)
    expanded = expand_group_ids(organization, group_ids)
    if expanded:
        offerings = offerings.filter(group_id__in=expanded)
    elif teacher is not None:
        offerings = teacher_offerings(organization, teacher, period=period).filter(subject_id=subject_id)
    else:
        return []
    return sorted(offerings.values_list("pk", flat=True).distinct(), key=str)


def enrollment_coverage(organization, subject_id, student_ids, period=None) -> dict:
    """Tələbələrin fənn üzrə CARİ dövr jurnalı → ``{"ok": n, "none": [id], "multiple": [id]}`` (≤ 2 sorğu).

    Sahib 2026-10-26: «tələbənin imtahan nəticəsi sistemə düşəcəkmi?» — imtahan yaradılanda / saxlananda /
    aktivləşdiriləndə müəllimə bloklamayan xəbərdarlıq: ``none`` — bu fənn üzrə cari semestr jurnalında
    ``enrolled`` qeydiyyatı yoxdur (nəticə jurnala düşməyəcək); ``multiple`` — iki (və daha çox) jurnalda
    (körpü ``exam_bridge.pick_enrollment`` qaydası ilə birini seçir: bağlı jurnal → öz qrup → ən son)."""
    student_ids = sorted({int(value) for value in student_ids or () if value is not None})
    empty = {"ok": 0, "none": [], "multiple": []}
    if organization is None or not subject_id or not student_ids:
        return empty
    period = period or current_period(organization)
    if period is None:
        return {**empty, "none": student_ids}
    counts = Counter(
        Enrollment.objects.filter(
            organization=organization,
            student_id__in=student_ids,
            offering__subject_id=subject_id,
            offering__period=period,
            status=Enrollment.Status.ENROLLED,
        ).values_list("student_id", flat=True)
    )
    return {
        "ok": sum(1 for sid in student_ids if counts.get(sid) == 1),
        "none": [sid for sid in student_ids if not counts.get(sid)],
        "multiple": [sid for sid in student_ids if counts.get(sid, 0) > 1],
    }


def organization_subject(organization, subject_id):
    """Təşkilatın fənni (``Subject``) və ya ``None`` — exams JSON endpoint-ləri tenant yoxlaması üçün."""
    if organization is None or not subject_id:
        return None
    return Subject.objects.filter(organization=organization, pk=subject_id).first()


def group_subject_coverage(organization, subject_id, group_ids, *, period=None) -> dict:
    """Reyestr qrupları → fənnin CARİ dövr jurnalında OLMAYAN tələbələr (sahib 2026-10-27, «236 QM» halı).

    → ``{qrup_pk: {"students": [id], "uncovered": [id], "has_journal": bool}}`` (qrup sayından asılı olmayaraq
    ≤ 6 sorğu). Qrupun tələbələri — aktiv ``enrolled`` akademik qeydi qrupun özündə və ya ALT qruplarında
    olanlar (giriş siyasəti ``unit_assigned_student_ids`` ilə eyni); ``uncovered`` — :func:`enrollment_coverage`
    ``none`` (fənnin cari dövr jurnalında ``enrolled`` qeydiyyatı yoxdur); ``has_journal`` — fənnin cari dövrdə
    qrupun (alt / ana qrup daxil, :func:`link_offering_ids` kimi) aktiv açılışı var."""
    group_ids = {str(value) for value in group_ids or () if value}
    if organization is None or not subject_id or not group_ids:
        return {}
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    units = list(
        OrgUnit.objects.filter(organization=organization, pk__in=group_ids, unit_type="group").only(
            "id", "name", "parent_id", "settings"
        )
    )
    if not units:
        return {}
    family = subgroup_rollup.group_family(organization, units)
    own, linked = {}, {}
    for unit in units:
        subs, parents = family.get(unit.pk, ((), ()))
        own[unit.pk] = {unit.pk} | {sub.pk for sub in subs}
        linked[unit.pk] = own[unit.pk] | {parent.pk for parent in parents}
    by_group: dict = {}
    for student_id, group_id in StudentAcademicRecord.objects.filter(
        organization=organization,
        group_id__in=set().union(*own.values()),
        is_active=True,
        status=AcademicStatus.ENROLLED,
    ).values_list("student_id", "group_id"):
        by_group.setdefault(group_id, set()).add(student_id)
    students = {unit.pk: set().union(*(by_group.get(gid, set()) for gid in own[unit.pk])) for unit in units}
    period = period or current_period(organization)
    uncovered = set(
        enrollment_coverage(organization, subject_id, set().union(*students.values()), period=period)["none"]
    )
    journal_groups = set()
    if period is not None:
        journal_groups = set(
            _period_offerings(organization, period)
            .filter(subject_id=subject_id, group_id__in=set().union(*linked.values()))
            .values_list("group_id", flat=True)
        )
    return {
        unit.pk: {
            "students": sorted(students[unit.pk]),
            "uncovered": sorted(students[unit.pk] & uncovered),
            "has_journal": bool(linked[unit.pk] & journal_groups),
        }
        for unit in units
    }


def subject_journal_hints(organization, subject_ids, *, teacher=None, period=None) -> dict:
    """Fənn seçicisinin ayırd edici işarəsi → ``{subject_id: {"teacher_groups": [ad], "count": n}}`` (≤ 3 sorğu).

    ``teacher_groups`` — müəllimin cari dövrdə bu fənn üzrə jurnallarının qrup adları; ``count`` — fənnin cari
    dövrdəki aktiv jurnal sayı (bütün müəllimlər). Sahib 2026-10-26: «təkrar fənn varsa göstərməsin» —
    eyni görünən iki fənn adı seçicidə ayırd edilsin (məlumat birləşdirilmir)."""
    subject_ids = [value for value in subject_ids or () if value]
    period = period or current_period(organization)
    if organization is None or period is None or not subject_ids:
        return {}
    rows = list(
        _period_offerings(organization, period)
        .filter(subject_id__in=subject_ids)
        .values_list("pk", "subject_id", "group__name")
    )
    mine = set()
    if teacher is not None:
        mine = set(
            teacher_offerings(organization, teacher, period=period)
            .filter(subject_id__in=subject_ids)
            .values_list("pk", flat=True)
        )
    hints = {sid: {"teacher_groups": [], "count": 0} for sid in subject_ids}
    for offering_id, subject_id, group_name in rows:
        hint = hints.setdefault(subject_id, {"teacher_groups": [], "count": 0})
        hint["count"] += 1
        if offering_id in mine and group_name and group_name not in hint["teacher_groups"]:
            hint["teacher_groups"].append(group_name)
    for hint in hints.values():
        hint["teacher_groups"].sort()
    return hints


def _is_stale(row, *, subject_id, offering_ids) -> bool:
    offering = row.enrollment.offering
    if not subject_id or offering.subject_id != subject_id:
        return True  # imtahanın fənni dəyişib — bal köhnə fənnin jurnalındadır
    if not offering_ids or offering.pk in offering_ids:
        return False
    # Eyni fənnin BAŞQA jurnalı: tələbə bağlı jurnalda qeydiyyatdadırsa bal oraya köçür.
    return Enrollment.objects.filter(
        student_id=row.enrollment.student_id,
        offering_id__in=list(offering_ids),
        status=Enrollment.Status.ENROLLED,
    ).exists()


def stale_midterm_rows(*, organization, exam_id, subject_id, offering_ids=()) -> list:
    """Bu imtahanın yazdığı, amma artıq onun fənninə / bağlı jurnalına aid olmayan avtomatik xanalar."""
    offering_ids = set(offering_ids or ())
    rows = ComponentScore.objects.filter(organization=organization, exam_source__exam_id=int(exam_id)).select_related(
        "component", "enrollment", "enrollment__offering", "enrollment__student"
    )
    return [row for row in rows if _is_stale(row, subject_id=subject_id, offering_ids=offering_ids)]


def _clear_one(row, *, exam_id, by_user) -> str:
    offering = row.enrollment.offering
    with transaction.atomic():
        CourseOffering.objects.select_for_update().filter(pk=offering.pk).exists()
        if journal_is_locked(offering):
            return KEPT_LOCKED  # bağlanmış jurnalın giriş balı dəyişmir — RİM sənədli düzəlişi ilə
        if ComponentScoreCorrection.objects.filter(
            component_id=row.component_id, enrollment_id=row.enrollment_id, reversal__isnull=True
        ).exists():
            return KEPT_CORRECTED  # RİM-in sənədli düzəlişi qalib gəlir
        old_score = row.score
        # DELETE 2 saat trigger-inə düşmür (o yalnız UPDATE-i bağlayır, bax registrar 0024).
        ComponentScore.objects.filter(pk=row.pk).delete()
        change = {
            "student": grade_audit.student_label(row.enrollment),
            "item": row.component.name,
            "old": grade_audit.score_repr(old_score),
            "new": grade_audit.score_repr(None),
            "source": f"exam:{exam_id}",
            "note": "imtahan mərkəzi · fənn / jurnal bağlantısı dəyişdi — avtomatik bal köhnə jurnaldan silindi",
        }
        grade_audit.log_grade_changes(
            offering=offering, by_user=by_user, kind=midterm_bridge.AUDIT_KIND, changes=[change], fail_closed=True
        )
    return CLEARED


def clear_stale_midterm_scores(*, organization, exam_id, subject_id, offering_ids=(), by_user=None) -> Counter:
    """Köhnə bağlantıdan qalan avtomatik midterm xanalarını sil → status sayları (``Counter``)."""
    counts: Counter = Counter()
    if organization is None or exam_id is None:
        return counts
    writer = midterm_bridge._writer(organization, by_user)
    for row in stale_midterm_rows(
        organization=organization, exam_id=exam_id, subject_id=subject_id, offering_ids=offering_ids
    ):
        try:
            status = _clear_one(row, exam_id=exam_id, by_user=writer)
        except AuditWriteFailed:
            logger.exception("exam_journal_link: audit failed while clearing score %s", row.pk)
            status = CLEAR_FAILED
        counts[status] += 1
    return counts


__all__ = [
    "CLEARED",
    "CLEAR_FAILED",
    "KEPT_CORRECTED",
    "KEPT_LOCKED",
    "clear_stale_midterm_scores",
    "current_period",
    "enrollment_coverage",
    "expand_group_ids",
    "group_subject_coverage",
    "link_offering_ids",
    "organization_subject",
    "stale_midterm_rows",
    "subject_journal_hints",
    "teacher_offerings",
    "teacher_subject_ids",
    "teacher_subjects",
]
