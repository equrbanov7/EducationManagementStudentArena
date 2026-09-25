"""Nəticə analitikası (III) — «Sorğu nəticələri» UI-ının əlavə aqreqatları.

Hamısı SQL aqreqasiyasıdır və SABİT sayda sorğu işlədir (cavab/müəllim sayından
asılı deyil; yeganə istisna — iştirak hesabı kampaniya başına ~5 sorğu, F1
``participation`` ilə eyni). k-anonimlik ``analytics`` modulundakı qaydalarla
EYNİDİR (``n < k`` gizli + daraldıcı filtrdə tamamlayıcı qayda) və iki addım da
irəli gedir:

* **Bölgü cədvəllərində ikinci dərəcəli gizlətmə** (:func:`secondary_suppress`).
  Cədvəlin CƏMİ ekranda görünürsə, görünən sətirlərdən kənarda qalan «qalıq»
  (gizli sətirlər + siyahıya düşməyən cavablar) ya 0, ya da ≥ k olmalıdır. Əks
  halda «cəm − görünən sətirlər» çıxması kiçik qrupun ortasını açardı; belə halda
  ən kiçik görünən sətirlər də gizlədilir (``secondary=True``).
* **Bölgü sətirlərində tamamlayıcı qayda** (:func:`safe_breakdown`) — daraldıcı
  filtr varsa hər sətir öz daralmamış sayı ilə də yoxlanır (F1 ``breakdown``-u
  sətir səviyyəsində yalnız ``n ≥ k`` yoxlayır).

İştirak (:func:`participation_rows`) müəllim üzrə bölgü verir və iki yerdə F1
``participation``-dan dəqiqdir: (1) gözlənilən hədəf «1 müəllim üzrə tələbədən 1»
qaydası ilə (tələbə, müəllim) cütüdür (f5b4441c — müəllim bir neçə fənn desə də bir
forma); (2) fakültə filtri qəbzlərə də tətbiq olunur (F1-də qəbz sayı fakültə üzrə
süzülmür — fakültə seçiləndə faiz 100%-i keçə bilirdi).

Heç bir funksiya cavab id-si, qəbz sətri, tələbə və ya vaxt qaytarmır.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Avg, Count, Q
from django.utils.translation import pgettext

from .. import registrar_bridge as bridge
from ..constants import QuestionKind, Section
from ..models import SurveyAnswer, SurveyCampaign, SurveyReceipt
from . import filters as flt
from .access import receipt_scope_q, unit_in_scope
from .analytics import _metrics, _round, aggregate_metrics, is_visible, question_stats

#: Gizlədilən sətirdə boşaldılan göstəricilər (say ``n`` qalır — o, iştirakı bildirir).
METRIC_KEYS = (
    "avg_overall",
    "likert_index",
    "likert_index_pct",
    "recommend_top2",
    "delta_department_overall",
    "delta_org_overall",
    "delta_department_index",
    "delta_org_index",
    "satisfaction",
    "facilities",
    "question_avg",
)

#: ``breakdown(by=…)`` ölçüsü → ``SurveyResponse`` qruplaşma sahəsi.
BREAKDOWN_KEYS = {
    "faculty": "faculty_id",
    "department": "teacher_department_id",
    "subject": "subject_id",
    "program": "program_id",
    "course_year": "course_year",
    "group": "group_id",
}

_SCORED = (QuestionKind.LIKERT5, QuestionKind.SCALE10)


# ── Gizlətmə köməkçiləri ─────────────────────────────────────────────────────


def hide_row(row, *, secondary=False) -> dict:
    """Sətri gizli edir: göstəricilər ``None``, ``suppressed=True`` (say qalır)."""
    row["suppressed"] = True
    if secondary:
        row["secondary"] = True
    for key in METRIC_KEYS:
        if key in row:
            row[key] = None
    return row


def secondary_suppress(rows, *, k, total_n, label_key="label") -> list:
    """Qardaş xanaların çıxmaya qarşı qorunması — ``analytics_guard.sibling_suppress``.

    Görünən cəmin altında gizli xana varsa, gizli xana sayı ≥ 2 və gizli cəm ≥ k olana
    qədər ən kiçik görünən sətirlər də gizlədilir (``secondary=True``). ``total_n`` —
    ekranda görünən cəmin dəqiq sayı (cəm gizlidirsə ``None``).
    """
    from .analytics_guard import sibling_suppress

    sibling_suppress(rows, k=k, total_n=total_n, label_key=label_key)
    for row in rows:
        if row.get("suppressed") and row.get("secondary"):
            hide_row(row, secondary=True)
    return rows


# ── Dəstin göstəriciləri ─────────────────────────────────────────────────────


def _empty_summary(k=0, campaign_ids=()):
    return {
        "k": k,
        "campaign_ids": list(campaign_ids),
        **_metrics({"n": 0}, False),
        "complement_blocked": False,
        "teachers": 0,
        "teachers_visible": 0,
        "teacher_counts": {},
        "questions": [],
        "general_n": 0,
        "general_suppressed": True,
        "general_complement_blocked": False,
        "general_questions": [],
        "participation": {},
    }


def _general_filtered(filters) -> bool:
    """Ümumi bölmədə HƏR filtr daraldıcıdır (cavab tələbənin qrupu/ixtisası/fakültəsi ilə)."""
    return any(
        value is not None
        for value in (
            filters.faculty_id,
            filters.department_id,
            filters.teacher_id,
            filters.subject_id,
            filters.group_id,
            filters.program_id,
            filters.course_year,
        )
    )


def results_summary(organization, scope, filters=None, *, with_participation=True, all_campaign_ids=None) -> dict:
    """KPI zolağı üçün xülasə (F1 ``summary`` + müəllim sayı + düzgün iştirak).

    Əlavə açarlar: ``complement_blocked`` (``n ≥ k``, amma tamamlayıcı qayda
    gizlədib), ``teachers`` / ``teachers_visible`` (``n ≥ k`` olan müəllimlər),
    ``general_suppressed``. ``participation`` — :func:`participation_rows` cəmi.
    ``all_campaign_ids`` — BÜTÜN bağlı kampaniyalar: seçim onların alt-dəstidirsə,
    kampaniya seçimi də daraldıcı sayılır (``analytics_guard``).
    """
    from .analytics_guard import campaign_counts, campaign_narrowed, complement_ok

    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not campaign_ids or not scope.has_structure_access:
        return _empty_summary(campaign_ids=campaign_ids)
    k = flt.k_threshold(campaign_ids)
    base = flt.responses(organization, scope, filters, campaign_ids)
    general = flt.responses(organization, scope, filters, campaign_ids, section=Section.GENERAL)
    row = aggregate_metrics(base)
    n = row["n"] or 0
    general_n = general.count()
    baseline = general_baseline = None
    if filters.is_narrowed:
        baseline = flt.responses(organization, scope, filters.without_narrowing(), campaign_ids).count()
    if _general_filtered(filters):
        general_baseline = flt.responses(
            organization, scope, flt.ResultFilters(), campaign_ids, section=Section.GENERAL
        ).count()
    visible = is_visible(n, k, baseline)
    general_visible = is_visible(general_n, k, general_baseline)
    if campaign_narrowed(campaign_ids, all_campaign_ids):
        wide_ids = list(all_campaign_ids)
        visible = visible and complement_ok(n, k, campaign_counts(organization, scope, filters, wide_ids))
        general_visible = general_visible and complement_ok(
            general_n, k, campaign_counts(organization, scope, filters, wide_ids, section=Section.GENERAL)
        )
    teacher_counts = dict(
        base.exclude(teacher__isnull=True).values("teacher_id").annotate(c=Count("id")).values_list("teacher_id", "c")
    )
    return {
        "k": k,
        "campaign_ids": campaign_ids,
        **_metrics(row, visible),
        "complement_blocked": n >= k and not visible,
        "teachers": len(teacher_counts),
        "teachers_visible": sum(1 for count in teacher_counts.values() if count >= k),
        "teacher_counts": teacher_counts,
        "questions": question_stats(base, visible=visible),
        "general_n": general_n,
        "general_suppressed": not general_visible,
        "general_complement_blocked": general_n >= k and not general_visible,
        "general_questions": question_stats(general, visible=general_visible),
        "participation": (
            participation_rows(organization, scope, filters, campaign_ids, per_teacher=False)
            if with_participation
            else {}
        ),
    }


def withhold(summary) -> dict:
    """Dəstin göstəricilərini gizlədir (say qalır) — dərc olunmayan müəllimə aid dəst üçün."""
    summary.update(
        suppressed=True,
        secondary=True,
        avg_overall=None,
        likert_index=None,
        likert_index_pct=None,
        recommend_top2=None,
        questions=[{**row, "avg": None, "top2": None} for row in summary.get("questions", [])],
    )
    return summary


def set_metrics(organization, scope, filters, campaign_ids, *, all_campaign_ids=None) -> dict:
    """Verilmiş kampaniya dəstinin göstəriciləri (əvvəlki dövrlə müqayisə üçün) — k,
    daraldıcı filtr və kampaniya seçimi üzrə tamamlayıcı qayda ilə."""
    from .analytics_guard import campaign_counts, campaign_narrowed, complement_ok

    campaign_ids = list(campaign_ids or [])
    if not campaign_ids or not scope.has_structure_access:
        return {"k": 0, **_metrics({"n": 0}, False)}
    k = flt.k_threshold(campaign_ids)
    row = aggregate_metrics(flt.responses(organization, scope, filters, campaign_ids))
    n = row["n"] or 0
    baseline = None
    if filters.is_narrowed:
        baseline = flt.responses(organization, scope, filters.without_narrowing(), campaign_ids).count()
    visible = is_visible(n, k, baseline)
    if visible and campaign_narrowed(campaign_ids, all_campaign_ids):
        visible = complement_ok(n, k, campaign_counts(organization, scope, filters, list(all_campaign_ids)))
    return {"k": k, **_metrics(row, visible)}


# ── Paylanmalar və müqayisə nöqtələri ────────────────────────────────────────


def buckets_for(counts, kind) -> dict:
    """``{score: say}`` → ``{"n", "buckets": [1..5|10], "avg", "top2", "bottom2"}``."""
    high = 10 if kind == QuestionKind.SCALE10 else 5
    buckets = [int(counts.get(score, 0) or 0) for score in range(1, high + 1)]
    total = sum(buckets)
    avg = sum(score * count for score, count in zip(range(1, high + 1), buckets)) / total if total else None
    is_likert = kind == QuestionKind.LIKERT5
    return {
        "n": total,
        "buckets": buckets,
        "avg": _round(avg),
        "top2": _round((buckets[3] + buckets[4]) / total, 4) if is_likert and total else None,
        "bottom2": _round((buckets[0] + buckets[1]) / total, 4) if is_likert and total else None,
    }


def distribution_rows(queryset) -> list:
    """Dəstin bütün ballı sualları üzrə paylanma (TƏK qruplaşdırılmış sorğu)."""
    rows = (
        SurveyAnswer.objects.filter(response__in=queryset.values("pk"), score__isnull=False, question__kind__in=_SCORED)
        .values("question__code", "question__kind", "question__text", "question__order", "score")
        .annotate(c=Count("id"))
        .order_by("question__order", "question__code", "score")
    )
    by_code: dict = {}
    for row in rows:
        item = by_code.setdefault(
            row["question__code"],
            {
                "code": row["question__code"],
                "kind": row["question__kind"],
                "text": pgettext("surveys.question", row["question__text"]),
                "order": row["question__order"],
                "counts": defaultdict(int),
            },
        )
        item["order"] = min(item["order"], row["question__order"])
        item["counts"][row["score"]] += row["c"]
    result = []
    for item in sorted(by_code.values(), key=lambda entry: (entry["order"], entry["code"])):
        counts = item.pop("counts")
        item.pop("order")
        result.append({**item, **buckets_for(counts, item["kind"])})
    return result


def question_distributions(organization, scope, filters=None, *, section=Section.TEACHER, visible=None) -> dict:
    """``{"k", "n", "suppressed", "questions": [{"code", "kind", "text", "n", "buckets",
    "avg", "top2", "bottom2"}]}`` — dəst görünmürsə (k / tamamlayıcı qayda) suallar boşdur.

    ``visible`` — çağıranın EYNİ dəst üçün artıq hesabladığı görünürlük (məs.
    ``results_summary`` — kampaniya tamamlayıcısı daxil); verilməyibsə burada hesablanır.
    """
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not campaign_ids or not scope.has_structure_access:
        return {"k": 0, "n": 0, "suppressed": True, "questions": []}
    k = flt.k_threshold(campaign_ids)
    base = flt.responses(organization, scope, filters, campaign_ids, section=section)
    if visible is None:
        n = base.count()
        baseline = None
        if filters.is_narrowed:
            baseline = flt.responses(
                organization, scope, filters.without_narrowing(), campaign_ids, section=section
            ).count()
        visible = is_visible(n, k, baseline)
    return {"k": k, "suppressed": not visible, "questions": distribution_rows(base) if visible else []}


def _question_avgs(queryset, k) -> dict:
    rows = (
        SurveyAnswer.objects.filter(response__in=queryset.values("pk"), score__isnull=False)
        .values("question__code")
        .annotate(n=Count("id"), avg=Avg("score"))
    )
    return {row["question__code"]: _round(row["avg"]) for row in rows if row["n"] >= k}


def question_benchmarks(
    organization, scope, campaign_ids, *, department_id=None, section=Section.TEACHER, all_campaign_ids=None
) -> dict:
    """``{"k", "org": {code: orta}, "department": {code: orta}}`` — hər biri ≥ k cavabla.

    Universitet ortası F1 ``department_benchmarks`` kimi ƏHATƏDƏN ASILI DEYİL (aqreqat
    müqayisə nöqtəsi); kafedra ortası isə istifadəçinin ƏHATƏSİ ilə hesablanır —
    əhatədən kənar kafedranın ortası heç vaxt qaytarılmır.
    """
    from apps.organizations.public import ORG_WIDE_SCOPE

    campaign_ids = list(campaign_ids or [])
    if not campaign_ids or not scope.has_structure_access:
        return {"k": 0, "org": {}, "department": {}}
    from .analytics_guard import campaign_counts, campaign_narrowed, complement_ok

    k = flt.k_threshold(campaign_ids)
    narrowed = campaign_narrowed(campaign_ids, all_campaign_ids)

    def safe(scope_, filters_):
        # Kampaniya alt-dəsti: bütün bağlı kampaniyalardan fərq 0 < d < k olarsa müqayisə nöqtəsi YOX.
        if not narrowed:
            return True
        n = campaign_counts(organization, scope_, filters_, campaign_ids, section=section)
        return complement_ok(n, k, campaign_counts(organization, scope_, filters_, all_campaign_ids, section=section))

    org_filters = flt.ResultFilters()
    org_base = flt.responses(organization, ORG_WIDE_SCOPE, org_filters, campaign_ids, section=section)
    result = {"k": k, "org": _question_avgs(org_base, k) if safe(ORG_WIDE_SCOPE, org_filters) else {}, "department": {}}
    if department_id is not None:
        dept_filters = flt.ResultFilters(department_id=department_id)
        if safe(scope, dept_filters):
            dept_base = flt.responses(organization, scope, dept_filters, campaign_ids, section=section)
            result["department"] = _question_avgs(dept_base, k)
    return result


def teacher_question_scores(organization, scope, filters, question_code) -> dict:
    """``{teacher_id: {"avg", "n"}}`` — seçilmiş sual üzrə müəllim ortası.

    Görünürlüyü ÇAĞIRAN müəllim sətrindən götürür (gizli sətrə yazılmamalıdır).
    """
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not question_code or not campaign_ids or not scope.has_structure_access:
        return {}
    base = flt.responses(organization, scope, filters, campaign_ids).exclude(teacher__isnull=True)
    rows = (
        SurveyAnswer.objects.filter(response__in=base.values("pk"), question__code=question_code, score__isnull=False)
        .values("response__teacher_id")
        .annotate(avg=Avg("score"), n=Count("id"))
    )
    return {row["response__teacher_id"]: {"avg": _round(row["avg"]), "n": row["n"]} for row in rows}


def safe_breakdown(
    organization, scope, filters=None, *, by="faculty", section=Section.TEACHER, total_n=None, all_campaign_ids=None
) -> dict:
    """F1 ``breakdown`` + sətir səviyyəsində tamamlayıcı qayda (daraldıcı filtr VƏ kampaniya
    seçimi üzrə; ümumi bölmədə hər filtr daraldıcıdır) + qardaş xanalar + gizli sətrin
    aqreqatlarının (``n`` daxil) silinməsi (``analytics_guard.finalize``)."""
    from .analytics_detail import breakdown
    from .analytics_guard import campaign_counts, campaign_narrowed, complement_ok, finalize

    if by not in BREAKDOWN_KEYS:
        raise ValueError(f"naməlum qruplaşma: {by}")
    filters = filters or flt.ResultFilters()
    data = breakdown(organization, scope, filters, by=by, section=section)
    rows, k = data["rows"], data["k"]
    key = BREAKDOWN_KEYS[by]
    campaign_ids = flt.campaign_ids_for(organization, filters)
    wide_filters = None
    if section == Section.GENERAL and _general_filtered(filters):
        wide_filters = flt.ResultFilters()
    elif filters.is_narrowed:
        wide_filters = filters.without_narrowing()
    baselines = []
    if rows and wide_filters is not None:
        baselines.append(campaign_counts(organization, scope, wide_filters, campaign_ids, key=key, section=section))
    if rows and campaign_narrowed(campaign_ids, all_campaign_ids):
        baselines.append(
            campaign_counts(organization, scope, filters, list(all_campaign_ids), key=key, section=section)
        )
    for row in rows:
        if not row["suppressed"] and not all(complement_ok(row["n"], k, base.get(row["key"])) for base in baselines):
            hide_row(row)
    finalize(rows, k=k, total_n=total_n)
    return data


# ── İştirak (müəllim üzrə) ───────────────────────────────────────────────────


def _unit_path(unit_id):
    if unit_id is None:
        return None
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return OrgUnit.objects.filter(pk=unit_id).values_list("path", flat=True).first() or ""


def _under(path, ancestor_path) -> bool:
    return bool(path) and bool(ancestor_path) and (path == ancestor_path or path.startswith(f"{ancestor_path}/"))


def _enrollment_students(organization_id, period_id, filters) -> dict:
    """``{offering_id: {student_id, …}}`` — dövrün bağlı jurnallı (DROPPED olmayan) qeydiyyatları."""
    offerings = bridge.closed_offerings(organization_id, period_id)
    if filters.subject_id is not None:
        offerings = offerings.filter(subject_id=filters.subject_id)
    if filters.group_id is not None:
        offerings = offerings.filter(group_id=filters.group_id)
    students: dict = defaultdict(set)
    for offering_id, student_id in (
        bridge.closed_enrollments(organization_id, period_id)
        .filter(offering_id__in=offerings.values("pk"))
        .values_list("offering_id", "student_id")
    ):
        students[offering_id].add(student_id)
    return students


def _expected_by_teacher(campaign, scope, filters, faculty_path) -> dict:
    """``{teacher_id: gözlənilən hədəf}`` — «1 müəllim üzrə tələbədən 1» (f5b4441c): hədəf
    (tələbə, müəllim) cütüdür, müəllim tələbəyə bir neçə fənn desə də BİR dəfə sayılır."""
    students = _enrollment_students(campaign.organization_id, campaign.period_id, filters)
    if not students:
        return {}
    teachers = bridge.offering_teachers(list(students))
    pairs = [
        (offering_id, teacher_id)
        for offering_id, ids in teachers.items()
        for teacher_id in ids
        if filters.teacher_id is None or teacher_id == filters.teacher_id
    ]
    need_units = not scope.is_org_wide or filters.department_id is not None or faculty_path is not None
    departments = bridge.resolve_departments(campaign.organization_id, pairs) if need_units else {}
    paths = bridge.unit_paths(departments.values()) if departments else {}
    reached: dict = defaultdict(set)
    for pair in pairs:
        if need_units:
            department_id = departments.get(pair)
            path = paths.get(department_id)
            if filters.department_id is not None and department_id != filters.department_id:
                continue
            if faculty_path is not None and not _under(path, faculty_path):
                continue
            if not unit_in_scope(scope, department_id, path):
                continue
        reached[pair[1]] |= students.get(pair[0], set())
    return {teacher_id: len(ids - {teacher_id}) for teacher_id, ids in reached.items()}


def _receipts_by_teacher(campaign_ids, scope, filters, faculty_path) -> dict:
    queryset = SurveyReceipt.objects.filter(campaign_id__in=campaign_ids, scope=Section.TEACHER).filter(
        receipt_scope_q(scope)
    )
    for field, value in (
        ("teacher_id", filters.teacher_id),
        ("teacher_department_id", filters.department_id),
        ("offering__subject_id", filters.subject_id),
        ("offering__group_id", filters.group_id),
    ):
        if value is not None:
            queryset = queryset.filter(**{field: value})
    if faculty_path is not None:
        queryset = queryset.filter(
            Q(teacher_department__path=faculty_path) | Q(teacher_department__path__startswith=f"{faculty_path}/")
        )
    return dict(queryset.values("teacher_id").annotate(c=Count("id")).values_list("teacher_id", "c"))


def _rate(receipts, expected):
    return round(receipts / expected, 4) if expected else None


def participation_rows(organization, scope, filters, campaign_ids, *, per_teacher=True) -> dict:
    """``{"receipts", "expected", "rate", "approximate", "teachers": {teacher_id: {...}}}``.

    Gözlənilən = bağlı jurnalların (DROPPED olmayan) qeydiyyatlarından yaranan FƏRQLİ
    (tələbə, müəllim) cütləri. ``approximate=True`` — ixtisas/kurs filtri iştiraka
    tətbiq olunmur (qəbzdə bu sahələr yoxdur); UI faizi göstərmir. Fənn/qrup filtrində
    qəbz müəllimin «əsas» açılışına (ən kiçik id) aid olduğundan bir neçə fənn deyən
    müəllimin faizi təxminidir. Yalnız SAYLAR qaytarılır — şəxs siyahısı yoxdur.
    """
    filters = filters or flt.ResultFilters()
    campaign_ids = list(campaign_ids or [])
    result = {"receipts": 0, "expected": 0, "rate": None, "approximate": False, "teachers": {}}
    if not campaign_ids or not scope.has_structure_access:
        return result
    faculty_path = _unit_path(filters.faculty_id) if filters.faculty_id is not None else None
    expected: dict = defaultdict(int)
    for campaign in SurveyCampaign.objects.filter(organization=organization, pk__in=campaign_ids).only(
        "pk", "organization_id", "period_id"
    ):
        for teacher_id, count in _expected_by_teacher(campaign, scope, filters, faculty_path).items():
            expected[teacher_id] += count
    receipts = _receipts_by_teacher(campaign_ids, scope, filters, faculty_path)
    total_receipts, total_expected = sum(receipts.values()), sum(expected.values())
    result.update(
        receipts=total_receipts,
        expected=total_expected,
        rate=_rate(total_receipts, total_expected),
        approximate=filters.program_id is not None or filters.course_year is not None,
    )
    if per_teacher:
        result["teachers"] = {
            teacher_id: {
                "receipts": receipts.get(teacher_id, 0),
                "expected": expected.get(teacher_id, 0),
                "rate": _rate(receipts.get(teacher_id, 0), expected.get(teacher_id, 0)),
            }
            for teacher_id in set(expected) | set(receipts)
            if teacher_id
        }
    return result
