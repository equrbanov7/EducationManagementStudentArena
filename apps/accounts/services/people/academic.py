"""Tələbə idarəetməsi — OXU qatı: akademik kart + köçürmə nəticəsinin ÖN BAXIŞI.

NİYƏ AYRICA MODUL (və niyə yeni mexanizm YOX)
─────────────────────────────────────────────
Qrup köçürməsinin özü artıq mövcuddur və möhkəmdir: iki fazalı, sübutlu axın
(:mod:`apps.registrar.transfer` → ``registrar_begin/finalize_student_group_transfer``
PG funksiyaları + :class:`GroupTransferEvidence`). Django tərəfdə
``validate_reference_identity``, DB tərəfdə ``registrar_student_group_transfer_guard``
``StudentAcademicRecord.group``-un başqa yolla dəyişməsini bloklayır — ``.update()``
də daxil. Bu modul həmin axını TƏKRAR YAZMIR; onun üstünə kataloqa xas İKİ qat
qoyur (``actions.py``-dakı naxışın eynisi):

1. **Struktur scope qapısı** — registrar servisi «kim kimi köçürə bilər»i bilmir
   (o, yalnız tenant/aktiv-üzvlük yoxlayır). Dekanın öz fakültəsindən kənar
   tələbəni köçürə bilməməsi məhz burada təmin olunur.
2. **NƏTİCƏNİN ÖN BAXIŞI** — sahibin açıq tələbi: «semestr ortasında köçürmə
   sürpriz olmasın». Köçürmə köhnə qeydiyyatı ``dropped`` edir və yeni qrupda
   TƏMİZ sətir açır; yəni qayıb saatı, giriş balı və buraxılış (barred) statusu
   SIFIRDAN başlayır. Köhnə bal DB-də qalır, amma heç bir UI səthində görünmür
   (jurnal grid-i, transkript, analitika, kabinet — hamısı ``dropped``-ı istisna
   edir). :func:`preview_group_transfer` bunu ƏMƏLDƏN ƏVVƏL rəqəmlə göstərir.

⚠️ ``get_permission_scope`` (``actor.scope_for``) işlədilir, ``get_unit_scope``
DEYİL — sonuncu HƏR aktiv üzvlüyün unitini toplayır və 2026-07-31 auditində PII
sızmasına səbəb olmuşdu.
"""

from __future__ import annotations

from django.db.models import Count, Exists, OuterRef
from django.urls import reverse
from django.utils.translation import pgettext_lazy

from ..rim.policy import RimAccessError
from .actions import assert_in_catalog_scope, load_target
from .permissions import PERM_MANAGE_ACADEMIC
from .rows import identity_row, resolve_unit_ancestors

_CTX = "accounts.people.academic"

#: Bir tələbənin göstərilən akademik qeydlərinin sayı (praktikada 1–2).
MAX_RECORDS = 12
#: Ön baxışda göstərilən fənn sətirlərinin yuxarı həddi (semestr ~12 fənn).
MAX_PREVIEW_ROWS = 40

#: Kurs nömrəsinin rum rəqəmləri (`registrar.page_contexts._course_number` ilə eyni
#: qayda; oradakı funksiya private-dir və cross-app import edilmir).
_ROMANS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}

STATUS_LABELS = {
    "enrolled": pgettext_lazy(_CTX, "Təhsilini davam etdirir"),
    "academic_leave": pgettext_lazy(_CTX, "Akademik məzuniyyət"),
    "expelled": pgettext_lazy(_CTX, "Xaric edilib"),
    "graduated": pgettext_lazy(_CTX, "Məzun olub"),
}

#: Statusun UI-dakı ton sinfi — rəng YALNIZ mövcud `--ems-*` ailələrindən.
STATUS_TONES = {
    "enrolled": "ok",
    "academic_leave": "warn",
    "expelled": "danger",
    "graduated": "info",
}


def _course_label(admission_year, period) -> str:
    """Tələbənin kursu (I…VI) — qəbul ilindən və dövrün başlama tarixindən."""
    start = getattr(period, "start_date", None)
    if not admission_year or start is None:
        return ""
    years = start.year - int(admission_year) + (1 if start.month >= 8 else 0)
    return _ROMANS.get(max(1, years), "")


def _current_period(organization):
    if organization is None:
        return None
    return organization.academic_periods.filter(is_current=True, is_active=True).order_by("-start_date").first()


def scoped_records_qs(actor, *, request=None):
    """Aktorun İDARƏ edə bildiyi akademik qeydlər (fail-closed).

    Baxış scope-undan AYRIDIR: idarəetmə ``people.manage_academic`` açarını
    DAŞIYAN üzvlüyün alt-ağacı ilə məhduddur. Açar yoxdursa BOŞ queryset —
    çağıran unutsa belə heç nə qaytarılmır (ikiqat qapı).
    """
    from apps.registrar.models import StudentAcademicRecord

    organization = actor.organization
    if organization is None or not actor.can_manage_academic:
        return StudentAcademicRecord.objects.none()

    scope = actor.scope_for(PERM_MANAGE_ACADEMIC, request=request)
    if not scope.has_structure_access:
        return StudentAcademicRecord.objects.none()

    records = StudentAcademicRecord.objects.filter(organization=organization)
    if not scope.is_org_wide:
        records = records.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    return records


def scoped_groups_qs(actor, *, request=None):
    """Köçürmənin HƏDƏF qrupu ola bilən struktur vahidləri (fail-closed).

    Hədəf qrup da aktorun idarə sahəsində olmalıdır: əks halda dekan tələbəni
    öz fakültəsindən çıxarıb başqa fakültəyə «ata» bilərdi.
    """
    from apps.organizations.models import OrgUnit
    from core.constants import OrgUnitType

    organization = actor.organization
    if organization is None or not actor.can_manage_academic:
        return OrgUnit.objects.none()

    scope = actor.scope_for(PERM_MANAGE_ACADEMIC, request=request)
    if not scope.has_structure_access:
        return OrgUnit.objects.none()

    groups = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type=OrgUnitType.GROUP)
    if not scope.is_org_wide:
        groups = groups.filter(scope.unit_subtree_q())
    return groups


def load_record(actor, record_id, *, request=None):
    """Akademik qeydi aktorun İDARƏ sahəsindən yükləyir — yoxdursa 404.

    404 (403 deyil) qəsdəndir: sahədən kənar qeydin MÖVCUDLUĞU da məlumatdır.
    """
    if not record_id:
        raise RimAccessError("record_not_found", "Akademik qeyd tapılmadı.", status=404)
    record = (
        scoped_records_qs(actor, request=request)
        .select_related("student", "program", "curriculum", "group", "organization")
        .filter(pk=record_id)
        .first()
    )
    if record is None:
        raise RimAccessError("record_not_found", "Akademik qeyd tapılmadı.", status=404)
    return record


# ── Akademik kart ────────────────────────────────────────────────────────────


def _enrollment_rows(record, period, *, limit=MAX_PREVIEW_ROWS):
    """Cari dövrün AKTİV qeydiyyatları — kartın «yazılışlar» bölməsi (1 sorğu)."""
    from apps.registrar.models import Enrollment

    if period is None:
        return []
    enrollments = (
        Enrollment.objects.filter(
            organization_id=record.organization_id,
            student_id=record.student_id,
            offering__period=period,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering__subject", "offering__group", "source_group")
        .order_by("offering__subject__code")[:limit]
    )
    return [
        {
            "id": str(enrollment.pk),
            "subject_code": enrollment.offering.subject.code if enrollment.offering.subject_id else "",
            "subject_name": enrollment.offering.subject.name if enrollment.offering.subject_id else "",
            "group_name": getattr(enrollment.offering.group, "name", "") or "",
            "absence_hours": int(enrollment.absence_hours or 0),
            "kind": enrollment.kind,
            # Alt qrupdan əlavə olunmuş sətir — köçürmə ona TOXUNMUR (o, öz
            # qrupunun açılışı deyil), ona görə kartda ayrıca işarələnir.
            "is_guest": enrollment.source_group_id is not None,
            "source_group_name": getattr(enrollment.source_group, "name", "") or "",
        }
        for enrollment in enrollments
    ]


def _record_payload(record, *, period, ancestors, enrollments):
    unit = ancestors.get(record.group_id, {})
    status = record.status
    return {
        "id": str(record.pk),
        # Ad ŞİFRSİZ, şifr AYRICA nişanda — JS ikincini birincinin içinə əlavə
        # edir (`people_academic.js`), ona görə `display_label` («Ad · şifr»)
        # versək cari şifr İKİ DƏFƏ çıxır. Naxış `context_builder/_helpers.py`
        # ilə eynidir. ⚠️ Daxili `MYEDU-*` kodu heç bir halda GÖSTƏRİLMİR.
        "program_label": record.program.name if record.program_id else "",
        "program_code": record.program.official_code_pair if record.program_id else "",
        "curriculum": str(record.curriculum) if record.curriculum_id else "",
        "group_id": str(record.group_id or ""),
        "group_name": getattr(record.group, "name", "") or "",
        "faculty_name": unit.get("faculty", ""),
        "kafedra_name": unit.get("kafedra", ""),
        "admission_year": record.admission_year,
        "course_label": _course_label(record.admission_year, period),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "status_tone": STATUS_TONES.get(status, "info"),
        "is_active": bool(record.is_active),
        "athlete_exemption": bool(record.national_athlete_exemption),
        "enrollments": enrollments,
    }


def build_student_card(*, actor, user_id, request=None, today=None) -> dict:
    """Tələbə kartı — şəxsi məlumat, akademik qeyd(lər), yazılışlar, əməllər.

    Detal kartından (``detail.build_detail``) FƏRQİ: bu, İDARƏETMƏ kartıdır —
    idarə scope-una görə süzülür və hər qeyd üçün hansı əməlin mümkün olduğunu
    qaytarır. Baxış kartı olduğu kimi qalır (heç bir səlahiyyət dəyişmir).
    """
    target = load_target(actor, user_id)
    catalog = assert_in_catalog_scope(actor, target, request=request)
    if catalog != "student":
        raise RimAccessError("not_a_student", "Bu hesab tələbə kataloqunda deyil.", status=404)

    organization = actor.organization
    period = _current_period(organization)
    can_manage = actor.can_manage_academic

    records = list(
        scoped_records_qs(actor, request=request)
        .filter(student=target)
        .select_related("program", "curriculum", "group")
        .order_by("-is_active", "-admission_year")[:MAX_RECORDS]
    )
    ancestors = _ancestors_for(records, organization=organization)

    payload_records = []
    for record in records:
        payload_records.append(
            _record_payload(
                record,
                period=period,
                ancestors=ancestors,
                enrollments=_enrollment_rows(record, period) if can_manage else [],
            )
        )

    person = identity_row(target, actor=actor, today=today)
    person["profile_url"] = reverse("accounts:public_profile", kwargs={"username": target.username})

    return {
        "has_access": True,
        "can_manage": can_manage,
        "person": person,
        "records": payload_records,
        "period": {"id": str(period.pk), "label": _period_label(period)} if period is not None else None,
        "status_options": [{"key": key, "label": label} for key, label in STATUS_LABELS.items()],
    }


def _period_label(period) -> str:
    if period is None:
        return ""
    return f"{period.academic_year} · {period.name}".strip(" ·")


def _ancestors_for(records, *, organization):
    """Qeydlərin qrupları üçün fakültə/kafedra adları — sətir sayından ASILI DEYİL."""
    group_ids = {record.group_id for record in records if record.group_id}
    if not group_ids or organization is None:
        return {}
    from apps.organizations.models import OrgUnit

    units = list(
        OrgUnit.objects.filter(organization=organization, pk__in=group_ids).only("id", "name", "path", "unit_type")
    )
    return resolve_unit_ancestors(units, organization=organization)


# ── Köçürmənin ön baxışı ─────────────────────────────────────────────────────


def _limit_percent(record) -> int:
    from apps.registrar.attendance import DEFAULT_ABSENCE_LIMIT_PERCENT

    program = record.program if record.program_id else None
    return int(getattr(program, "absence_limit_percent", None) or DEFAULT_ABSENCE_LIMIT_PERCENT)


def _moving_enrollments(record, period, old_group):
    """Köçürmənin TARİXÇƏYƏ keçirəcəyi qeydiyyatlar + onların bal/qayıb ağırlığı.

    Bir sorğu: sətir sayı fənn sayı qədərdir, hər sətir üçün ƏLAVƏ sorğu YOXDUR
    (``Count`` annotasiyaları + ``Exists``).
    """
    from apps.registrar.models import Enrollment, FinalGrade

    if old_group is None or period is None:
        return []
    final_grades = FinalGrade.objects.filter(enrollment=OuterRef("pk"))
    return list(
        Enrollment.objects.filter(
            organization_id=record.organization_id,
            student_id=record.student_id,
            offering__period=period,
            offering__group=old_group,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering__subject")
        .annotate(
            mark_count=Count("lesson_marks", distinct=True),
            component_count=Count("component_scores", distinct=True),
            has_final=Exists(final_grades),
        )
        .order_by("offering__subject__code")[:MAX_PREVIEW_ROWS]
    )


def _target_subject_ids(record, period, new_group):
    """Hədəf qrupda AÇILIŞI olan fənnlərin id-ləri (1 sorğu)."""
    from apps.registrar.models import CourseOffering

    if period is None or new_group is None:
        return set()
    return set(
        CourseOffering.objects.filter(
            organization_id=record.organization_id,
            period=period,
            group=new_group,
            is_active=True,
        ).values_list("subject_id", flat=True)
    )


def preview_group_transfer(*, actor, record_id, new_group_id, request=None) -> dict:
    """Köçürmənin NƏTİCƏSİNİ əvvəlcədən göstərir — heç nə yazmır.

    Qaytarır: hansı fənn tarixçəyə keçir, hər birində neçə qayıb saatı və neçə
    jurnal işarəsi «görünməz» olur, buraxılış (barred) statusu necə dəyişir,
    hədəf qrupda açılışı OLMAYAN fənnlər hansılardır. ``blocking`` doludursa
    əməl ümumiyyətlə aparıla bilməz.
    """
    from apps.registrar.attendance import attendance_score

    record = load_record(actor, record_id, request=request)
    new_group = scoped_groups_qs(actor, request=request).filter(pk=new_group_id).first() if new_group_id else None

    blocking = []
    if new_group is None:
        blocking.append("target_group_outside_scope")
    elif record.group_id and str(new_group.pk) == str(record.group_id):
        blocking.append("same_group")

    period = _current_period(record.organization)
    if period is None:
        blocking.append("no_current_period")

    old_group = record.group
    limit_percent = _limit_percent(record)
    exempt = bool(record.national_athlete_exemption)

    rows = []
    if not blocking:
        target_subjects = _target_subject_ids(record, period, new_group)
        for enrollment in _moving_enrollments(record, period, old_group):
            offering = enrollment.offering
            absence_hours = int(enrollment.absence_hours or 0)
            _score, barred_before = attendance_score(
                offering.lesson_hours,
                absence_hours,
                limit_percent=limit_percent,
                exempt=exempt,
            )
            rows.append(
                {
                    "subject_code": offering.subject.code if offering.subject_id else "",
                    "subject_name": offering.subject.name if offering.subject_id else "",
                    "absence_hours": absence_hours,
                    "mark_count": int(enrollment.mark_count or 0),
                    "component_count": int(enrollment.component_count or 0),
                    "has_final_grade": bool(enrollment.has_final),
                    # Hədəf qrupda bu fənnin açılışı yoxdursa köçürmə onu
                    # AVTOMATİK yaradır (services.enroll_student_in_subject) —
                    # müəllimsiz və dərssiz. İstifadəçi bunu ƏVVƏLCƏDƏN bilməlidir.
                    "target_offering_exists": offering.subject_id in target_subjects,
                    "barred_before": bool(barred_before),
                }
            )

    totals = {
        "subjects": len(rows),
        "marks": sum(row["mark_count"] for row in rows),
        "components": sum(row["component_count"] for row in rows),
        "absence_hours": sum(row["absence_hours"] for row in rows),
        "final_grades": sum(1 for row in rows if row["has_final_grade"]),
        "missing_in_target": sum(1 for row in rows if not row["target_offering_exists"]),
        "barred_now": sum(1 for row in rows if row["barred_before"]),
    }

    warnings = []
    if totals["marks"] or totals["absence_hours"]:
        # Yeni sətir TƏMİZ açılır: qayıb 0, giriş balı 0 — köhnəsi yalnız audit
        # və DB tarixçəsində qalır (heç bir UI səthində görünmür).
        warnings.append("attendance_resets")
    if totals["barred_now"]:
        warnings.append("barred_cleared")
    if totals["final_grades"]:
        warnings.append("final_grades_hidden")
    if totals["missing_in_target"]:
        warnings.append("offerings_created")

    return {
        "ok": not blocking,
        "record_id": str(record.pk),
        "student_name": (record.student.get_full_name() or record.student.username).strip(),
        "from_group": {"id": str(old_group.pk), "name": old_group.name} if old_group else None,
        "to_group": {"id": str(new_group.pk), "name": new_group.name} if new_group else None,
        "period_label": _period_label(period),
        "limit_percent": limit_percent,
        "rows": rows,
        "totals": totals,
        "warnings": warnings,
        "blocking": blocking,
    }


__all__ = [
    "MAX_PREVIEW_ROWS",
    "MAX_RECORDS",
    "STATUS_LABELS",
    "STATUS_TONES",
    "build_student_card",
    "load_record",
    "preview_group_transfer",
    "scoped_groups_qs",
    "scoped_records_qs",
]
