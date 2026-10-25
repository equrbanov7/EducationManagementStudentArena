"""«Xarici nəticənin tanınması» — OXU qatı: əhatə, transkript sətirləri, kabinet nişanları, heyət bölməsi.

Yazı (yaratma / ləğv) :mod:`apps.registrar.credit_recognition`-dadır; bu modul onu import ETMİR ki,
transkript / «Fəndən azad» oxuları yazı qatına (və ``subject_exempt``-ə) dövri bağlanmasın.

SƏLAHİYYƏT (açarla, rol adı ilə yox): ``student.credit_recognition`` — dekanlıq (dekan, dekan müavini), tədris
şöbəsi, RİM; rektor ``*`` ilə. Əhatə ``journal_scope.permission_scope_for``: ORGANIZATION rolu → bütün təşkilat,
UNIT rolu → ``scope_unit`` alt-ağacındakı qrupların tələbələri (dekan öz fakültəsi). Açar yoxdursa bölmə
görünmür / HTTP 403; tələbə əhatədən kənardadırsa 404 (mövcudluq sızmasın).

TRANSKRİPT QAYDASI: qüvvədə olan tanınma (tələbə + fənn + semestr) həmin cütün jurnal sətrini ƏVƏZ edir —
yekun = tanınmış bal (hərf tenant şkalasından), kredit = qərar anındakı plan krediti, ÜOMG-yə və toplanmış krediyə
daxildir. Jurnal sətri onsuz da ``dropped``-dur (azadlıq); jurnal bağlı olduğundan azad edilə bilməyən sətir də
transkriptdə tanınmış nəticə ilə əvəzlənir — iki sətir yaranmır.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import pgettext

from core.search_text import tolerant_q

from . import grading_scale, journal_scope
from .models import AssessmentScheme, Enrollment, ExternalCreditRecognition, RecognitionProgram, StudentAcademicRecord

_CTX = "registrar.recognition"

PERM = "student.credit_recognition"
SECTION = "credit-recognition"
SEARCH_LIMIT = 20
RECENT_LIMIT = 30


# ── Əhatə ────────────────────────────────────────────────────────────────────


def _authenticated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def scope(user, organization):
    return journal_scope.permission_scope_for(user, organization, PERM)


def can_manage(user, organization) -> bool:
    """Açar struktur əhatəsi verirmi (bölmə görünüşü + yazı qapısı)."""
    if not _authenticated(user) or organization is None:
        return False
    return scope(user, organization).has_structure_access


def records_in_scope(user, organization):
    """Aktorun əhatəsindəki tələbə akademik qeydləri (açarsız → boş queryset)."""
    queryset = StudentAcademicRecord.objects.filter(organization=organization)
    if not _authenticated(user) or organization is None:
        return queryset.none()
    unit_scope = scope(user, organization)
    if not unit_scope.has_structure_access:
        return queryset.none()
    if unit_scope.is_org_wide:
        return queryset
    return queryset.filter(unit_scope.unit_subtree_q(path_field="group__path", id_field="group_id"))


def student_in_scope(user, organization, student_id) -> bool:
    if not student_id:
        return False
    return records_in_scope(user, organization).filter(student_id=student_id).exists()


def pass_score() -> int:
    """Keçid həddi — ``AssessmentScheme.pass_threshold``-in standartı (51): tanınma yalnız keçmiş nəticəyədir."""
    return int(AssessmentScheme._meta.get_field("pass_threshold").default)


# ── Tanınmış nəticə ──────────────────────────────────────────────────────────


def active_for_student(organization, student_id) -> list:
    """Tələbənin qüvvədə olan tanınmaları (fənn + dövr ilə; transkript üçün tək sorğu)."""
    if organization is None or not student_id:
        return []
    return list(
        ExternalCreditRecognition.objects.filter(
            organization=organization, student_id=student_id, revoked_at__isnull=True
        ).select_related("subject", "period")
    )


def override_keys(recognitions) -> set:
    """Tanınmanın əvəz etdiyi (fənn, dövr) cütləri."""
    return {(item.subject_id, item.period_id) for item in recognitions}


def badge(recognition, organization=None) -> dict:
    """Ekran / kabinet nişanı — xarici nəticənin qısa izi + bizim şkalada qarşılığı."""
    letter, _gpa = grading_scale.score_to_letter(recognition.recognized_score, organization)
    return {
        "id": str(recognition.pk),
        "label": pgettext(_CTX, "Xarici nəticə tanınıb"),
        "program": recognition.program,
        "program_label": str(recognition.get_program_display()),
        "institution": recognition.institution,
        "country": recognition.country,
        "foreign_subject": recognition.foreign_subject,
        "foreign_credit": recognition.foreign_credit,
        "foreign_grade": recognition.foreign_grade,
        "study_period": recognition.study_period,
        "score": recognition.recognized_score,
        "letter": letter,
        "credit": recognition.credit,
        "code": recognition.subject.code,
        "name": recognition.subject.name,
    }


def recognized_result(score, organization=None) -> dict:
    """``finals.compute_final_result`` ilə EYNİ açarlar — transkript / PDF / «Ümumi tədris məlumatı» şablonları
    sətri ayırd etmədən oxuyur; giriş/çıxış balı yoxdur (``None``), yekun = tanınmış bal, nəticə «keçib»."""
    total = Decimal(int(score))
    letter, gpa = grading_scale.score_to_letter(total, organization)
    label = pgettext(_CTX, "Xarici nəticə tanınıb")
    return {
        "entry_score": None,
        "entry_parts": None,
        "exam_score": None,
        "effective_exam": None,
        "total": total,
        "letter": letter,
        "gpa": gpa,
        "barred": False,
        "graded": True,
        "exam_ok": True,
        "passed": True,
        "failed": False,
        "resit": None,
        "resit_done": False,
        "pass_threshold": pass_score(),
        "min_final_exam_score": 0,
        "exam_score_max": 0,
        "is_published": True,
        "eligibility": {},
        "status_code": "recognized",
        "status_label": label,
        "status_notice": "",
    }


def transcript_row(recognition, organization=None) -> dict:
    """Transkript sətri (``transcript._build_row`` forması) — jurnal qeydiyyatı yoxdur."""
    result = recognized_result(recognition.recognized_score, organization)
    credit = int(recognition.credit or 0)
    return {
        "enrollment": None,
        "enrollment_id": None,
        "offering": None,
        "subject": recognition.subject,
        "period": recognition.period,
        "credit": credit,
        "result": result,
        "in_gpa": True,
        "quality_points": Decimal(str(result["gpa"])) * credit,
        "legacy": None,
        "legacy_grade_facts": [],
        "legacy_grade_review_required": False,
        "retake": None,
        "recognition": badge(recognition, organization),
    }


def student_period_badges(record, period) -> dict:
    """Kabinet «Fənlərim» / «Jurnalım»: ``subject_id`` → nişan (bu dövrün qüvvədə olan tanınmaları)."""
    if record is None or period is None:
        return {}
    rows = ExternalCreditRecognition.objects.filter(
        organization_id=record.organization_id,
        student_id=record.student_id,
        period=period,
        revoked_at__isnull=True,
    ).select_related("subject")
    return {row.subject_id: badge(row, record.organization) for row in rows}


# ── Heyət bölməsi ────────────────────────────────────────────────────────────


def _student_label(user) -> str:
    return ((user.get_full_name() or "").strip() or user.username) if user is not None else ""


def _scoped_recognitions(user, organization):
    students = records_in_scope(user, organization).values("student_id")
    return ExternalCreditRecognition.objects.filter(organization=organization, student_id__in=students)


def _search(user, organization, query):
    search = tolerant_q(
        query,
        ("student__first_name", "student__last_name"),
        compact_fields=("student__username",),
    )
    if search is None:
        return []
    records = (
        records_in_scope(user, organization)
        .filter(search)
        .select_related("student", "group", "program")
        .order_by("student__last_name", "student__first_name")[:SEARCH_LIMIT]
    )
    return [
        {"record": record, "student": record.student, "label": _student_label(record.student)} for record in records
    ]


def target_enrollments(organization, student_id) -> list:
    """Tanınmanın hədəfi ola bilən jurnal qeydiyyatları (dövr → fənn), qüvvədə tanınması olanlar çıxılır."""
    taken = set(
        ExternalCreditRecognition.objects.filter(
            organization=organization, student_id=student_id, revoked_at__isnull=True
        ).values_list("subject_id", "period_id")
    )
    enrollments = (
        Enrollment.objects.filter(organization=organization, student_id=student_id)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering__subject", "offering__period")
        .order_by("-offering__period__start_date", "offering__subject__name")
    )
    return [
        {
            "id": str(item.pk),
            "label": f"{item.offering.period.name} · {item.offering.subject.code} {item.offering.subject.name}",
        }
        for item in enrollments
        if (item.offering.subject_id, item.offering.period_id) not in taken
    ]


def _rows(queryset, organization, limit=None) -> list:
    items = queryset.select_related("student", "subject", "period", "exempt_decision").order_by("-created_at")
    if limit:
        items = items[:limit]
    rows = []
    for item in items:
        decision = item.exempt_decision
        rows.append(
            {
                "item": item,
                "badge": badge(item, organization),
                "student_label": _student_label(item.student),
                "exempted": bool(decision is not None and decision.reverted_at is None),
            }
        )
    return rows


def build(request, organization) -> dict:
    """Bölmə datası: axtarış (``cr_q``), seçilmiş tələbə (``cr_student``) və ya son qərarlar."""
    user = getattr(request, "user", None)
    if not can_manage(user, organization):
        return {"has_access": False}
    query = str(request.GET.get("cr_q") or "").strip()[:100]
    raw_student = str(request.GET.get("cr_student") or "").strip()
    scoped = _scoped_recognitions(user, organization)
    data = {
        "has_access": True,
        "section": SECTION,
        "query": query,
        "matches": _search(user, organization, query) if query else [],
        "selected": None,
        "programs": list(RecognitionProgram.choices),
        "pass_score": pass_score(),
    }
    data["kpis"] = [
        {
            "label": pgettext(_CTX, "Qüvvədə olan tanınma"),
            "value": scoped.filter(revoked_at__isnull=True).count(),
            "tone": "accent-success",
        },
        {
            "label": pgettext(_CTX, "Ləğv edilib"),
            "value": scoped.filter(revoked_at__isnull=False).count(),
            "tone": "accent-warning",
        },
    ]
    record = None
    if raw_student.isdigit():
        record = (
            records_in_scope(user, organization)
            .filter(student_id=int(raw_student))
            .select_related("student", "group", "program")
            .first()
        )
    if record is not None:
        data["selected"] = {
            "record": record,
            "student": record.student,
            "label": _student_label(record.student),
            "rows": _rows(scoped.filter(student_id=record.student_id), organization),
            "targets": target_enrollments(organization, record.student_id),
        }
    else:
        data["recent"] = _rows(scoped, organization, limit=RECENT_LIMIT)
    return data


__all__ = [
    "PERM",
    "SECTION",
    "active_for_student",
    "badge",
    "build",
    "can_manage",
    "override_keys",
    "pass_score",
    "recognized_result",
    "records_in_scope",
    "student_in_scope",
    "student_period_badges",
    "target_enrollments",
    "transcript_row",
]
