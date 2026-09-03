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

from django.db.models import Count

from apps.registrar import exam_eligibility
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    FinalGrade,
    LessonMark,
    ResitRecord,
    SelfWorkMark,
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
    ``component_scores`` / ``selfwork_done`` / ``marks`` arqumentləri;
    qalan metodlar ``finals.compute_final_result``-un sətir-sətir sorğularını
    əvəz edir.  ``with_finals=False`` olduqda yalnız giriş balı hissəsi yüklənir
    (jurnal qridi və «Yekun» tab-ı onsuz da donma/istisna dəstini özü qurur).
    """

    __slots__ = (
        "components_by_offering",
        "scores_by_enrollment",
        "selfwork_done",
        "marks_by_enrollment",
        "final_grades",
        "resits",
        "frozen_ids",
        "hours_map",
        "exempt_student_ids",
        "limit_percent_by_group",
        "with_finals",
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
            "selfwork_done": self.selfwork_done.get((enrollment.id, offering_id), 0),
        }
        if self.marks_by_enrollment is not None:
            kwargs["marks"] = self.marks_by_enrollment.get(enrollment.id, [])
        return kwargs

    # ── Yekun sətri ──────────────────────────────────────────────────────────

    def final_grade_for(self, enrollment):
        return self.final_grades.get(enrollment.id)

    def resit_for(self, enrollment):
        return self.resits.get(enrollment.id)

    def frozen_for(self, offering) -> bool:
        return offering.id in self.frozen_ids

    def exempt_for(self, enrollment) -> bool:
        return enrollment.student_id in self.exempt_student_ids

    def limit_percent_for(self, offering) -> int:
        key = (offering.organization_id, getattr(offering, "group_id", None))
        return self.limit_percent_by_group.get(key, DEFAULT_ABSENCE_LIMIT)


def build(enrollments, *, marks_by_enrollment=None, with_finals=True) -> FinalsBatch:
    """Yazılış siyahısı üçün toplu dəsti qur — sabit sayda sorğu.

    ``marks_by_enrollment`` — çağıran ``LessonMark``-ları ONSUZ DA oxuyubsa
    (jurnal qridi) təkrar sorğu edilmir.  Əks halda dərs balları YALNIZ GENERIC
    komponenti OLMAYAN açılışlar üçün oxunur (komponent varsa onlar dərs
    cəmini əvəz edir — bax ``gradebook_components.entry_score_for``).
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
    if offering_ids:
        for comp in AssessmentComponent.objects.filter(offering_id__in=offering_ids):
            components_by_offering[comp.offering_id].append(comp)
    component_ids = [c.id for comps in components_by_offering.values() for c in comps]

    scores_by_enrollment: dict = defaultdict(list)
    if component_ids and enr_ids:
        for score in ComponentScore.objects.filter(component_id__in=component_ids, enrollment_id__in=enr_ids):
            scores_by_enrollment[score.enrollment_id].append(score)

    selfwork_done: dict = {}
    selfwork_offerings = [
        oid for oid, comps in components_by_offering.items() if any(c.kind == ComponentKind.SELF_WORK for c in comps)
    ]
    if selfwork_offerings and enr_ids:
        rows = (
            SelfWorkMark.objects.filter(enrollment_id__in=enr_ids, topic__offering_id__in=selfwork_offerings, done=True)
            .values("enrollment_id", "topic__offering_id")
            .annotate(total=Count("id"))
        )
        selfwork_done = {(r["enrollment_id"], r["topic__offering_id"]): r["total"] for r in rows}

    if marks_by_enrollment is None:
        lesson_sum_offerings = [
            oid
            for oid in offering_ids
            if not any(c.kind == ComponentKind.GENERIC for c in components_by_offering.get(oid, []))
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
        "selfwork_done": selfwork_done,
        "marks_by_enrollment": marks_by_enrollment,
        "with_finals": with_finals,
        "final_grades": {},
        "resits": {},
        "frozen_ids": frozenset(),
        "hours_map": {},
        "exempt_student_ids": frozenset(),
        "limit_percent_by_group": {},
    }

    if with_finals and enr_ids:
        data["final_grades"] = {fg.enrollment_id: fg for fg in FinalGrade.objects.filter(enrollment_id__in=enr_ids)}
        data["resits"] = {r.enrollment_id: r for r in ResitRecord.objects.filter(enrollment_id__in=enr_ids)}
        data["frozen_ids"] = exam_eligibility.frozen_offering_ids(offering_ids)
        data["hours_map"] = exam_eligibility.lesson_hours_map(offering_ids)
        data["limit_percent_by_group"] = absence_limit_percent_map(offerings.values())
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
        data["exempt_student_ids"] = frozenset(exempt)

    return FinalsBatch(**data)


def entry_batch(enrollments, *, marks_by_enrollment=None) -> FinalsBatch:
    """Yalnız GİRİŞ BALI üçün toplu dəst (donma/istisna yüklənmir)."""
    return build(enrollments, marks_by_enrollment=marks_by_enrollment, with_finals=False)


__all__ = ["FinalsBatch", "absence_limit_percent_map", "build", "entry_batch", "DEFAULT_ABSENCE_LIMIT"]
