"""Staff-facing HİERARXİK akademik-qeyd icmalı — read-only, batched aggregation.

Dekan / kafedra müdiri / rektor / registrator öz görünüş sahəsindəki (unit scope)
tələbələrin akademik nəticələrini fakültə → kafedra → ixtisas → qrup → tələbə
süzgəcləri ilə görür: hər kəs yalnız özündən BİR ALT səviyyəni (və daha aşağını)
görür (:mod:`apps.organizations.scoping`). Kiçik "box"-lar seçilmiş süzgəc üzrə
ümumi mənzərəni verir (neçə tələbə, toplanmış kredit, neçə kəsr — q/b vs 25%
ayrımı, orta ÜOMG).

**Performans müqaviləsi:** icmal sabit sayda sorğudan qurulur (tələbə/enrollment
sayından ASILI DEYİL) — per-enrollment nəticələr :func:`analytics.evaluate_enrollment`
+ :func:`analytics.build_evaluation_maps` bulk map-larından hesablanır, yəni
``compute_final_result`` N dəfə çağırılmır. q/b vs 25% ayrımı
:func:`transcript._fail_reason_code` semantikası ilə eynidir.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from apps.organizations.models import OrgUnit
from apps.organizations.scoping import UnitScope
from apps.registrar import analytics, transcript
from apps.registrar.models import Enrollment, StudentAcademicRecord

_TWO = Decimal("0.01")
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def _round2(value) -> Decimal:
    return Decimal(value).quantize(_TWO, rounding=ROUND_HALF_UP)


def _fail_reason(result) -> str:
    """Bir KƏSİLMİŞ nəticənin səbəb kodu — transcript._fail_reason_code güzgüsü.

    ``qb``     → davamiyyətdən (barred) imtahana buraxılmayıb → fənn yenidən keçilir.
    ``exam25`` → imtahana girib, kəsilib → 25% ilə təkrar imtahan hüququ.
    ``other``  → nadir/qeyri-müəyyən (imtahan qeyd olunmayıb, barred deyil).
    """
    if result["barred"]:
        return "qb"
    if result["graded"] and not result["passed"]:
        return "exam25"
    return "other"


def _scoped_records(organization, scope: UnitScope, filters: dict):
    """StudentAcademicRecord queryset-i — scope alt-ağacı + aktiv süzgəclər.

    Scope: unit-scoped istifadəçi yalnız öz fakültə/kafedra alt-ağacındakı
    qruplara bağlı qeydləri görür (``group__path``); org-wide hamısını görür;
    scope yoxdursa (adi müəllim/tələbə) heç nə."""
    qs = StudentAcademicRecord.objects.filter(organization=organization, is_active=True).select_related(
        "student", "program", "group"
    )
    # İyerarxiya scoping — hər kəs özündən aşağını görür.
    qs = qs.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))

    # Ən dərin verilmiş struktur süzgəci (qrup > ixtisas > kafedra > fakültə).
    if filters.get("student"):
        qs = qs.filter(student_id=filters["student"])
    if filters.get("program"):
        qs = qs.filter(program_id=filters["program"])
    unit_id = filters.get("group") or filters.get("department") or filters.get("faculty")
    if unit_id:
        unit = OrgUnit.objects.filter(organization=organization, pk=unit_id).only("id", "path").first()
        if unit is None:
            return qs.none()
        if unit.path:
            qs = qs.filter(Q(group_id=unit.id) | Q(group__path__startswith=f"{unit.path}/"))
        else:
            qs = qs.filter(group_id=unit.id)
    return qs


def _aggregate_students(organization, records, *, year=None, season=None):
    """Per-student aqreqasiya (kredit/kəsr/qb/exam25/ÜOMG) + ümumi box-lar + il seçimləri.

    Bir dəfə bütün enrollment-ləri çəkir, tədris ili/semestr süzgəcini (verilibsə)
    tətbiq edir, bulk map qurur, hər enrollment-i :func:`analytics.evaluate_enrollment`
    ilə qiymətləndirir. Qaytarır: ``(rows, box, year_options)``."""
    students = {r.student_id: r for r in records}
    if not students:
        return [], _empty_summary(), []

    all_enrollments = list(
        Enrollment.objects.filter(organization=organization, student_id__in=list(students))
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering", "offering__subject", "offering__period")
    )
    # Tədris ili seçimləri — scope-dakı bütün dövrlərdən (süzgəcdən ƏVVƏL, ki dropdown
    # həmişə mövcud illəri göstərsin). Ən yeni öndə.
    year_options = sorted(
        {e.offering.period.year_display for e in all_enrollments if e.offering.period_id},
        reverse=True,
    )
    # Tədris ili / semestr süzgəci — seçiləndə box-lar həmin dövrü əks etdirir.
    enrollments = all_enrollments
    if year:
        enrollments = [e for e in enrollments if e.offering.period_id and e.offering.period.year_display == year]
    if season:
        enrollments = [
            e for e in enrollments if e.offering.period_id and transcript._season_of(e.offering.period) == season
        ]
    maps = analytics.build_evaluation_maps(organization, enrollments)

    per_student: dict = {
        sid: {"credits_earned": 0, "fails": 0, "qb": 0, "exam25": 0, "quality_points": Decimal("0"), "gpa_credits": 0}
        for sid in students
    }
    for enrollment in enrollments:
        acc = per_student.get(enrollment.student_id)
        if acc is None:
            continue
        result = analytics.evaluate_enrollment(enrollment, maps)
        if result["passed"] or result["failed"]:
            # ÜOMG 100 bal: Σ(yekun_bal × kredit) / Σ(kredit) (transcript ilə eyni).
            acc["quality_points"] += result["total"] * result["credit"]
            acc["gpa_credits"] += result["credit"]
        if result["passed"]:
            acc["credits_earned"] += result["credit"]
        elif result["failed"]:
            acc["fails"] += 1
            reason = _fail_reason(result)
            if reason == "qb":
                acc["qb"] += 1
            elif reason == "exam25":
                acc["exam25"] += 1

    rows = []
    box = _empty_summary()
    box["students"] = len(students)
    for sid, acc in per_student.items():
        record = students[sid]
        gpa = _round2(acc["quality_points"] / acc["gpa_credits"]) if acc["gpa_credits"] else Decimal("0.00")
        student = record.student
        rows.append(
            {
                "student_id": str(sid),
                "name": (student.get_full_name() or "").strip() or student.username,
                "username": student.username,
                "group": record.group.name if record.group_id else "—",
                "program": record.program.name if record.program_id else "—",
                "program_code": record.program.code if record.program_id else "",
                "credits_earned": acc["credits_earned"],
                "fails": acc["fails"],
                "qb": acc["qb"],
                "exam25": acc["exam25"],
                "gpa": str(gpa),
            }
        )
        box["credits_earned"] += acc["credits_earned"]
        box["fails"] += acc["fails"]
        box["qb"] += acc["qb"]
        box["exam25"] += acc["exam25"]
        box["quality_points"] += acc["quality_points"]
        box["gpa_credits"] += acc["gpa_credits"]

    box["avg_gpa"] = str(_round2(box["quality_points"] / box["gpa_credits"]) if box["gpa_credits"] else Decimal("0.00"))
    del box["quality_points"], box["gpa_credits"]
    # Kəsri çox olan öndə, sonra ad üzrə — problemli tələbələr görünsün.
    rows.sort(key=lambda r: (-r["fails"], r["name"].lower()))
    return rows, box, year_options


def _empty_summary() -> dict:
    return {
        "students": 0,
        "credits_earned": 0,
        "fails": 0,
        "qb": 0,
        "exam25": 0,
        "quality_points": Decimal("0"),
        "gpa_credits": 0,
        "avg_gpa": "0.00",
    }


def build_records_overview(*, organization, scope: UnitScope, filters=None, offset=0, limit=DEFAULT_PAGE_SIZE):
    """İcmal payload-u: xülasə box-ları + səhifələnmiş tələbə siyahısı.

    Scope ``none`` olduqda (struktur görünüşü yoxdur) boş nəticə qaytarır."""
    filters = filters or {}
    limit = max(1, min(int(limit or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    offset = max(0, int(offset or 0))

    if not scope.has_structure_access:
        summary = _empty_summary()
        del summary["quality_points"], summary["gpa_credits"]
        return {
            "has_access": False,
            "summary": summary,
            "results": [],
            "has_more": False,
            "total": 0,
            "year_options": [],
        }

    records = list(_scoped_records(organization, scope, filters))
    rows, summary, year_options = _aggregate_students(
        organization, records, year=filters.get("year"), season=filters.get("season")
    )
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "has_access": True,
        "summary": summary,
        "results": page,
        "has_more": offset + limit < total,
        "total": total,
        "year_options": year_options,
    }


def student_is_in_scope(*, organization, scope: UnitScope, student_id) -> bool:
    """Verilmiş tələbə istifadəçinin görünüş sahəsindədirmi (drill-down mühafizəsi)."""
    if not scope.has_structure_access:
        return False
    qs = StudentAcademicRecord.objects.filter(organization=organization, is_active=True, student_id=student_id)
    qs = qs.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    return qs.exists()
