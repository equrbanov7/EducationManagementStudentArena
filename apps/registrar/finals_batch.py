"""Toplu (batch) primitivlər — yekun/jurnal səthlərində N+1-in qarşısını alır.

``finals.compute_final_result`` və ``gradebook.entry_score_for`` TƏK sətir üçün
yazılıb: hər çağırışda komponentləri, komponent ballarını, sərbəst iş sayğacını,
``FinalGrade``/``ResitRecord`` sətrini, davamiyyət həddini və idmançı istisnasını
AYRICA sorğulayır.  Roster səthləri (müəllim jurnalı, transkript, «Nəticələrim»,
«Ümumi tədris məlumatı») isə həmin funksiyaları DÖNGÜDƏ çağırır — 555 yazılışlı
açılışda bu, 10 000-dən çox sorğu deməkdir (2026-09-02 performans ölçməsi).

Bu modul həmin sorğuları BİR dəfə, sabit sayda (≈11) edir və nəticəni sətir-sətir
paylayır.  Riyaziyyat BURADA TƏKRAR YAZILMIR — dəyərlər eyni funksiyalara
arqument kimi ötürülür, yəni nəticə bayt-bayt eynidir (bax
``apps/registrar/tests/test_finals_batch.py`` — hər sətri toplu və tək-sətir
yolu ilə hesablayıb müqayisə edir).

⚠️ YAZI YOLLARINDA İŞLƏTMƏYİN.  Toplu dəst sorğunun ƏVVƏLİNDƏ oxunur; eyni
tranzaksiyada bal dəyişən yollar (``finals.set_exam_score`` → ``evaluate_resit``)
köhnə dəyəri görməsin deyə batch OLMADAN çağırılır (``compute_final_result``-un
batch-siz davranışı dəyişməyib).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from django.db.models import F

from apps.registrar import entry_standard, exam_eligibility, selfwork_points
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    FinalGrade,
    LessonMark,
    ResitRecord,
    StudentAcademicRecord,
)

#: ``gradebook._DEFAULT_ABSENCE_LIMIT`` ilə eyni dəyər — dövri importdan
#: qaçmaq üçün burada təkrarlanır (``gradebook`` bu modulu import edir).
DEFAULT_ABSENCE_LIMIT = 25


def absence_limit_percent_map(offerings) -> dict:
    """``(organization_id, group_id)`` → qayıb həddi (%) — **tək sorğu**.

    :func:`gradebook.absence_limit_percent_for`-un toplu güzgüsü: o, qrupun
    İLK akademik qeydinin proqramına baxır (``.first()`` sıralanmamış queryset-də
    ``pk`` ilə sıralayır — burada da eyni sıra saxlanılır).
    """
    keys = {(o.organization_id, o.group_id) for o in offerings if getattr(o, "group_id", None)}
    if not keys:
        return {}
    rows = (
        StudentAcademicRecord.objects.filter(
            organization_id__in={k[0] for k in keys}, group_id__in={k[1] for k in keys}
        )
        .select_related("program")
        .order_by("pk")
    )
    result: dict = {}
    for record in rows:
        key = (record.organization_id, record.group_id)
        if key in keys and key not in result:
            result[key] = record.program.absence_limit_percent if record.program else DEFAULT_ABSENCE_LIMIT
    return result


class FinalsBatch:
    """Bir roster (yazılış siyahısı) üçün əvvəlcədən oxunmuş xəritələr.

    :meth:`entry_kwargs` → ``gradebook.entry_score_for``-un ``components`` /
    ``component_scores`` / ``selfwork_points`` (sərbəst iş BALI — kanonik
    :mod:`apps.registrar.selfwork_points` qaydası) / ``marks`` arqumentləri;
    qalan metodlar ``finals.compute_final_result``-un sətir-sətir sorğularını
    əvəz edir.  ``with_finals=False`` olduqda yalnız giriş balı hissəsi yüklənir
    (jurnal qridi və «Yekun» tab-ı onsuz da donma/istisna dəstini özü qurur).

    MIDTERM REJİMİ (2026/2027-dən, :mod:`apps.registrar.entry_standard`): hər açılışın
    rejimi (``midterm_by_offering``) komponent sorğusunun ÖZÜNDƏN (dövr sahələri JOIN-lə)
    və ya keşlənmiş dövr/təşkilatdan oxunur — əlavə sorğu yoxdur.  Midterm açılışında
    :meth:`entry_kwargs` davamiyyət girişlərini də (buraxılış qərarının saatı / həddi /
    istisnası) ``rule`` kimi ötürür: ``with_finals=True``-da hazır xəritələrdən, yalnız giriş
    balı dəstində isə çağıranın :meth:`provide_attendance` ilə verdiyi dəyərlərdən (verməyibsə
    — Midterm açılışları üçün BİR dəfə toplu oxunur).
    """

    __slots__ = (
        "components_by_offering",
        "scores_by_enrollment",
        "selfwork_points",
        "marks_by_enrollment",
        "final_grades",
        "resits",
        "frozen_ids",
        "hours_map",
        "exempt_student_ids",
        "limit_percent_by_group",
        "limit_percent_by_student",
        "with_finals",
        "midterm_by_offering",
        "enrollments",
        "attendance_ready",
        "attendance_provided",
    )

    def __init__(self, **kwargs):
        for name in self.__slots__:
            setattr(self, name, kwargs.get(name))

    # ── Giriş balı ───────────────────────────────────────────────────────────

    def entry_kwargs(self, enrollment) -> dict:
        """``gradebook.entry_score_for`` üçün hazır (sorğusuz) arqumentlər."""
        offering_id = enrollment.offering_id
        kwargs = {
            "components": self.components_by_offering.get(offering_id, []),
            "component_scores": self.scores_by_enrollment.get(enrollment.id, []),
            "selfwork_points": self.selfwork_points.get((enrollment.id, offering_id), 0),
            "rule": self.rule_for(enrollment),
        }
        if self.marks_by_enrollment is not None:
            kwargs["marks"] = self.marks_by_enrollment.get(enrollment.id, [])
        return kwargs

    # ── Giriş balı standartı (Midterm rejimi) ────────────────────────────────

    def is_midterm(self, offering) -> bool:
        flag = self.midterm_by_offering.get(offering.id)
        if flag is None:  # dəstdə olmayan açılış — kanonik tək yol
            flag = self.midterm_by_offering[offering.id] = entry_standard.offering_is_midterm(offering)
        return flag

    def rule_for(self, enrollment):
        """Açılışın rejimi + (Midterm-də) buraxılış qərarının İŞLƏTDİYİ davamiyyət girişləri."""
        offering = enrollment.offering
        if not self.is_midterm(offering):
            return entry_standard.LEGACY
        if not self.attendance_ready:
            self._load_attendance()
        return entry_standard.EntryRule(
            midterm=True,
            lesson_hours=exam_eligibility.lesson_hours_for(offering, hours_map=self.hours_map),
            limit_percent=self.limit_percent_for_enrollment(enrollment),
            exempt=self.exempt_for(enrollment),
        )

    def provide_attendance(self, *, hours_map=None, limits=None, exempt_ids=None) -> None:
        """Çağıranın buraxılış qərarında ONSUZ DA işlətdiyi girişlər — giriş balının davamiyyəti
        EYNİ dəyərlərdən çıxsın və sorğu olmasın.

        ``hours_map`` — ``offering_id → saat`` (``lesson_hours_map`` nəticəsi və ya
        ``{offering.id: lesson_hours_for(...)}``); ``limits`` — ``student_id → faiz`` (və ya
        ``absence_limit.RowLimit``) xəritəsi, ya da bir tələbəlik səthdə tək faiz; ``exempt_ids`` —
        idmançı ``student_id`` dəsti, ya da tək tələbəlik səthdə ``bool``.  Verilməyən hissə
        lazım olanda toplu oxunur (:meth:`_load_attendance`)."""
        student_ids = {e.student_id for e in self.enrollments or ()}
        provided = set(self.attendance_provided or ())
        if hours_map is not None:
            self.hours_map = dict(hours_map)
            provided.add("hours")
        if isinstance(limits, Mapping):
            self.limit_percent_by_student = {sid: getattr(v, "percent", v) for sid, v in limits.items()}
            provided.add("limits")
        elif limits is not None:
            self.limit_percent_by_student = {sid: int(limits) for sid in student_ids}
            provided.add("limits")
        if isinstance(exempt_ids, bool):
            exempt_ids = student_ids if exempt_ids else ()
        if exempt_ids is not None:
            self.exempt_student_ids = frozenset(exempt_ids)
            provided.add("exempt")
        self.attendance_provided = provided
        self.attendance_ready = bool(self.with_finals) or provided >= _ATTENDANCE_PARTS

    def _load_attendance(self) -> None:
        """Yalnız giriş balı dəstində Midterm açılışı var, çağıran girişləri verməyib → TOPLU oxu
        (``with_finals=True`` ilə EYNİ mənbələr, yalnız Midterm açılışlarının sətirləri üçün)."""
        provided = self.attendance_provided or set()
        rows = [e for e in self.enrollments or () if self.midterm_by_offering.get(e.offering_id)]
        if "hours" not in provided:
            missing = {e.offering_id for e in rows if not (e.offering.lesson_hours or 0) > 0}
            self.hours_map = exam_eligibility.lesson_hours_map(list(missing)) if missing else {}
        if "limits" not in provided:
            self.limit_percent_by_student = _student_limits(rows)
        if "exempt" not in provided:
            self.exempt_student_ids = _exempt_ids(rows)
        self.attendance_ready = True

    # ── Yekun sətri ──────────────────────────────────────────────────────────

    def final_grade_for(self, enrollment):
        return self.final_grades.get(enrollment.id)

    def resit_for(self, enrollment):
        return self.resits.get(enrollment.id)

    def frozen_for(self, offering) -> bool:
        return offering.id in self.frozen_ids

    def exempt_for(self, enrollment) -> bool:
        return enrollment.student_id in (self.exempt_student_ids or ())

    def limit_percent_for(self, offering) -> int:
        """Açılış-səviyyəli (qrupun ilk qeydi) hədd — yalnız başlıq/etiket üçün qalır."""
        if self.limit_percent_by_group is None:
            self.limit_percent_by_group = absence_limit_percent_map(e.offering for e in self.enrollments)
        key = (offering.organization_id, getattr(offering, "group_id", None))
        return self.limit_percent_by_group.get(key, DEFAULT_ABSENCE_LIMIT)

    def limit_percent_for_enrollment(self, enrollment) -> int:
        """TƏLƏBƏNİN ÖZ həddi (F-06, 2026-09-14) — ``compute_final_result`` bunu işlədir."""
        return (self.limit_percent_by_student or {}).get(enrollment.student_id, DEFAULT_ABSENCE_LIMIT)


#: :meth:`FinalsBatch.provide_attendance` hissələri — hamısı verilibsə toplu oxu lazım deyil.
_ATTENDANCE_PARTS = frozenset({"hours", "limits", "exempt"})


def _student_limits(enrollments) -> dict:
    """``student_id → hədd %`` — təşkilat başına TƏK sorğu, tək mənbə (``absence_limit``)."""
    from apps.registrar import absence_limit

    students_by_org: dict = defaultdict(set)
    for enrollment in enrollments:
        students_by_org[enrollment.organization_id].add(enrollment.student_id)
    return {
        sid: pct
        for org_id, sids in students_by_org.items()
        for sid, pct in absence_limit.limit_percent_map_for_students(organization_id=org_id, student_ids=sids).items()
    }


def _exempt_ids(enrollments) -> frozenset:
    """İdmançı istisnalı tələbələr — təşkilat başına TƏK sorğu."""
    exempt: set = set()
    by_org: dict = defaultdict(list)
    for enrollment in enrollments:
        by_org[enrollment.organization_id].append(enrollment.student_id)
    # ``organization`` yerinə pk ötürülür — FK-nı obyekt kimi oxumaq
    # açılış başına bir sorğu yaradardı (``exempt_student_ids`` onu yalnız
    # ``filter(organization=…)``-da işlədir, pk tamamilə kifayətdir).
    for org_id, student_ids in by_org.items():
        if org_id is None:
            continue
        exempt |= set(exam_eligibility.exempt_student_ids(org_id, student_ids))
    return frozenset(exempt)


def _components_with_period(offering_ids):
    """Açılışların komponentləri + (JOIN) dövr sahələri və təşkilatın ``midterm_from_year`` açarı.

    Rejim (``entry_standard``) üçün lazım olan hər şey EYNİ sorğudan gəlir — ayrıca dövr
    oxunuşu yoxdur.  Qaytarır ``(komponentlər, {offering_id: (tədris ili, başlanğıc, xam il)})``."""
    rows = AssessmentComponent.objects.filter(offering_id__in=offering_ids).annotate(
        ems_period_year=F("offering__period__academic_year"),
        ems_period_start=F("offering__period__start_date"),
        ems_from_year=F("offering__organization__settings__registrar__midterm_from_year"),
    )
    components: dict = defaultdict(list)
    carried: dict = {}
    for comp in rows:
        components[comp.offering_id].append(comp)
        carried.setdefault(comp.offering_id, (comp.ems_period_year, comp.ems_period_start, comp.ems_from_year))
    return components, carried


def build(
    enrollments,
    *,
    marks_by_enrollment=None,
    with_finals=True,
    selfwork_loader=None,
    organization=None,
    period=None,
) -> FinalsBatch:
    """Yazılış siyahısı üçün toplu dəsti qur — sabit sayda sorğu.

    ``marks_by_enrollment`` — çağıran ``LessonMark``-ları ONSUZ DA oxuyubsa
    (jurnal qridi) təkrar sorğu edilmir. ``selfwork_loader(enrollment_ids,
    offering_ids) -> {(enrollment_id, offering_id): bal}`` — sərbəst iş cəmini
    oxuyan TƏK sorğu çağıranın öz sorğusu ilə əvəz olunur (məs. «Fənlərim» slot-slot
    göstərişi üçün mövzuları da oxuyur; qayda eynidir — :mod:`apps.registrar.selfwork_points`).
    Yalnız SELF_WORK komponentli açılış varsa çağırılır — sorğu sayı dəyişmir.  Əks halda dərs balları YALNIZ GENERIC
    komponenti OLMAYAN açılışlar üçün oxunur (komponent varsa onlar dərs
    cəmini əvəz edir — bax ``gradebook_components.entry_score_for``); Midterm rejimli açılışda
    dərs balları HƏMİŞƏ oxunur (aktivlik ortası — ``entry_standard``).

    ``organization`` / ``period`` — rejim üçün çağıranın əlindəki obyektlər (id uyğun gəlsə
    işlədilir); komponenti olmayan və dövrü keşdə olmayan açılışlar üçün yalnız o halda TƏK sorğu.
    """
    enrollments = list(enrollments)
    enr_ids = [e.id for e in enrollments]
    offerings = {}
    for enrollment in enrollments:
        offering = enrollment.offering
        if offering is not None:
            offerings.setdefault(offering.id, offering)
    offering_ids = list(offerings)

    components_by_offering: dict = defaultdict(list)
    carried: dict = {}
    if offering_ids:
        components_by_offering, carried = _components_with_period(offering_ids)
    component_ids = [c.id for comps in components_by_offering.values() for c in comps]
    # Rejim — komponent sorğusunun daşıdığı dövr sahələrindən / keşdən (bax ``entry_standard``).
    midterm_by_offering = entry_standard.midterm_flags(
        [e.offering for e in enrollments], organization=organization, period=period, carried=carried
    )

    scores_by_enrollment: dict = defaultdict(list)
    if component_ids and enr_ids:
        for score in ComponentScore.objects.filter(component_id__in=component_ids, enrollment_id__in=enr_ids):
            scores_by_enrollment[score.enrollment_id].append(score)

    selfwork_totals: dict = {}
    selfwork_offerings = [
        oid for oid, comps in components_by_offering.items() if any(c.kind == ComponentKind.SELF_WORK for c in comps)
    ]
    if selfwork_offerings and enr_ids:
        loader = selfwork_loader or selfwork_points.selfwork_totals_by_offering
        selfwork_totals = loader(enr_ids, selfwork_offerings)

    if marks_by_enrollment is None:
        lesson_sum_offerings = [
            oid
            for oid in offering_ids
            if midterm_by_offering.get(oid)
            or not any(c.kind == ComponentKind.GENERIC for c in components_by_offering.get(oid, []))
        ]
        if lesson_sum_offerings:
            wanted = [e.id for e in enrollments if e.offering_id in set(lesson_sum_offerings)]
            marks_by_enrollment = defaultdict(list)
            for mark in LessonMark.objects.filter(enrollment_id__in=wanted):
                marks_by_enrollment[mark.enrollment_id].append(mark)
            marks_by_enrollment = {eid: marks_by_enrollment.get(eid, []) for eid in wanted}

    data = {
        "components_by_offering": components_by_offering,
        "scores_by_enrollment": scores_by_enrollment,
        "selfwork_points": selfwork_totals,
        "marks_by_enrollment": marks_by_enrollment,
        "with_finals": with_finals,
        "final_grades": {},
        "resits": {},
        "frozen_ids": frozenset(),
        "hours_map": {},
        "exempt_student_ids": frozenset(),
        "limit_percent_by_group": None,
        "limit_percent_by_student": {},
        "midterm_by_offering": midterm_by_offering,
        "enrollments": enrollments,
        "attendance_ready": bool(with_finals),
        "attendance_provided": set(),
    }

    if with_finals and enr_ids:
        data["final_grades"] = {fg.enrollment_id: fg for fg in FinalGrade.objects.filter(enrollment_id__in=enr_ids)}
        data["resits"] = {r.enrollment_id: r for r in ResitRecord.objects.filter(enrollment_id__in=enr_ids)}
        data["frozen_ids"] = exam_eligibility.frozen_offering_ids(offering_ids)
        data["hours_map"] = exam_eligibility.lesson_hours_map(offering_ids)
        # Tələbə üzrə hədd (təşkilat başına tək sorğu, tək mənbə — `absence_limit`).
        data["limit_percent_by_student"] = _student_limits(enrollments)
        data["exempt_student_ids"] = _exempt_ids(enrollments)

    return FinalsBatch(**data)


def group_marks(marks) -> dict:
    """Artıq oxunmuş işarələri yazılışa görə qruplaşdırır; təkrar DB oxunuşu yoxdur."""
    grouped = defaultdict(list)
    for mark in marks:
        grouped[mark.enrollment_id].append(mark)
    return grouped


def entry_batch(enrollments, *, marks_by_enrollment=None, organization=None, period=None) -> FinalsBatch:
    """Yalnız GİRİŞ BALI üçün toplu dəst (donma/istisna yüklənmir).

    Midterm açılışının davamiyyət girişlərini çağıran :meth:`FinalsBatch.provide_attendance`
    ilə verir (onsuz da əlindədir); verməsə onlar lazım olanda toplu oxunur."""
    return build(
        enrollments,
        marks_by_enrollment=marks_by_enrollment,
        with_finals=False,
        organization=organization,
        period=period,
    )


def student_entry_batch(enrollments, record, period, marks_by_enrollment, hours_map, organization=None) -> FinalsBatch:
    """BİR tələbənin fənləri üçün giriş balı dəsti («Qiymətlərim», ana səhifə) — davamiyyət
    girişləri tələbənin öz qeydindən (hədd, istisna) və çağıranın saat xəritəsindən, sorğusuz.

    ``organization`` verilməsə qeydin ARTIQ keşlənmiş təşkilatı işlədilir (FK sorğusu edilmir)."""
    from apps.registrar import absence_limit

    if organization is None:
        organization = getattr(getattr(record, "_state", None), "fields_cache", {}).get("organization")
    batch = entry_batch(
        enrollments,
        marks_by_enrollment=marks_by_enrollment,
        organization=organization,
        period=period,
    )
    batch.provide_attendance(
        hours_map=hours_map,
        limits=absence_limit.limit_percent_for_record(record),
        exempt_ids=bool(record is not None and record.national_athlete_exemption),
    )
    return batch


__all__ = [
    "FinalsBatch",
    "absence_limit_percent_map",
    "build",
    "entry_batch",
    "student_entry_batch",
    "DEFAULT_ABSENCE_LIMIT",
]
