"""Profil "exam-chance" bölməsi — İmtahan Mərkəzi «imtahan şansı ver».

``section`` dict-ini YERİNDƏ mutasiya edir (kollokvium_windows pattern-i).
İmtahan siyahısı tədris ili / semestr (AcademicPeriod tarix aralığı —
imtahanda dövr FK-sı yoxdur, ``start_datetime`` aralığa salınır), fakültə /
kafedra (OrgUnit subtree, imtahanın icazəli qruplarının ``org_unit``-i
üzərindən) və ad axtarışı ilə daraldılır; kafedra seçimləri seçilmiş
fakültənin uşaqlarıdır. Tələbə axtarışı qrup adı / istifadəçi adı /
ad-soyad üzrə işləyir və nəticələr grant formunda checkbox kimi seçilir.
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params

from .exam_chance_people import identity_map, selected_student_ids, selected_students

RECENT_GRANT_LIMIT = 15
STUDENT_RESULT_LIMIT = 40

# Filtr açarları → GET parametr adları (qsub bölməsi ilə eyni yanaşma).
_FILTER_PARAMS = {
    "year": "chance_year",
    "period": "chance_period",
    "faculty": "chance_faculty",
    "kafedra": "chance_kafedra",
    "exam_q": "chance_exam_q",
    "student_q": "chance_student_q",
}


def _pick(options, raw_id):
    """Siyahıdan pk-sı uyğun gələn elementi tap (yanlış/yad id → None)."""
    if not raw_id:
        return None
    return next((item for item in options if str(item.pk) == raw_id), None)


def _read_filters(request) -> dict:
    return {key: (request.GET.get(param) or "").strip()[:100] for key, param in _FILTER_PARAMS.items()}


def _search_students(organization, query):
    """Org üzvləri arasında qrup adı / istifadəçi adı / ad-soyad axtarışı."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from apps.exams.public import unit_student_record_filter
    from apps.organizations.public import organization_user_queryset
    from core.search_text import code_regex, fold_regex, tokens_of

    User = get_user_model()
    # 2026-09-14 (W5 `w5left`, tapşırıq 1): qrup adı ilə axtarış reyestr qrupunu da
    # tapır (cari aktiv `StudentAcademicRecord.group` — `unit_assignment` ilə eyni şərt).
    # 2026-09-26 (sahib): dözümlü axtarış — tokenlər VƏ, hər token sahələr arasında
    # VƏ YA; adlar az/ing hərf qatlaması, qrup adı kod rejimi («234king» → «234 K ing»).
    # Qrup şərtləri öz təşkilat/aktiv-qeyd şərti ilə EYNİ `Q`-dadır (tək JOIN dəsti).
    tokens = tokens_of(query)
    if not tokens:
        return []
    condition = Q()
    for token in tokens:
        name_rx = fold_regex(token)
        code_rx = code_regex(token)
        condition &= (
            Q(username__iregex=name_rx)
            | Q(first_name__iregex=name_rx)
            | Q(last_name__iregex=name_rx)
            | Q(profile__patronymic__iregex=name_rx)  # 2026-10-24: ata adı ilə də (eyni adlı tələbələr)
            | Q(
                student_groups_as_student__organization=organization,
                student_groups_as_student__name__iregex=code_rx,
            )
            | Q(
                academic_records__organization=organization,
                academic_records__group__name__iregex=code_rx,
                **unit_student_record_filter("academic_records__"),
            )
        )
    return list(
        organization_user_queryset(organization, queryset=User.objects.filter(condition))
        .distinct()
        .order_by("first_name", "last_name", "username")[:STUDENT_RESULT_LIMIT]
    )


def _grant_value(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key)


def _legacy_grants(organization) -> dict:
    """2026-10-18 öncəsi şanslar (rəy LOW-10): rəsmi qeydi (``ExamChanceGrant``) olmayan köhnə
    ``StudentExamAttemptGrant`` sətirləri siyahıda və KPI-də itməsin — səbəb «Köhnə qeyd» kimi göstərilir."""
    from django.apps import apps as django_apps

    from apps.exams.models import StudentExamAttemptGrant

    log_model = django_apps.get_model("registrar", "ExamChanceGrant")
    logged = set(log_model.objects.filter(organization=organization).values_list("student_id", "exam_id"))
    logged_students = {student_id for student_id, _exam in logged}
    label = pgettext("accounts.exam_chance", "Köhnə qeyd (əsas yazılmayıb)")
    rows, students, attempts = [], set(), 0
    for grant in (
        StudentExamAttemptGrant.objects.filter(exam__organization=organization)
        .select_related("exam", "student", "granted_by")
        .order_by("-updated_at")
    ):
        if (grant.student_id, grant.exam_id) in logged:
            continue
        students.add(grant.student_id)
        attempts += grant.extra_attempts or 0
        granted_by = grant.granted_by
        rows.append(
            {
                "student": grant.student,
                "exam_id": grant.exam_id,
                "exam_title": grant.exam.title,
                "exam_category": grant.exam.exam_type_extended or "",
                "get_reason_display": label,
                "is_legacy": True,
                "reference_number": "",
                "reference_date": None,
                "note": "",
                "document": None,
                "extra_attempts": grant.extra_attempts,
                "granted_by_name": (
                    ((granted_by.get_full_name() or "").strip() or granted_by.username) if granted_by else ""
                ),
                "created_at": grant.updated_at,
            }
        )
    return {
        "rows": rows[:RECENT_GRANT_LIMIT],
        "count": len(rows),
        "attempts": attempts,
        "new_students": len(students - logged_students),
    }


def _recent_rows(organization):
    """Son qeydlər (rəsmi + köhnə, ən yenisi əvvəl) və köhnə qeydlərin KPI cəmləri."""
    from apps.registrar.public import retake_chance

    official = retake_chance.recent(organization=organization, limit=RECENT_GRANT_LIMIT)
    legacy = _legacy_grants(organization)
    rows = sorted([*official, *legacy["rows"]], key=lambda row: _grant_value(row, "created_at"), reverse=True)
    return rows[:RECENT_GRANT_LIMIT], legacy


def _set(row, key, value):
    if isinstance(row, dict):
        row[key] = value
    else:
        setattr(row, key, value)  # yalnız yaddaşda — append-only qeyd SAXLANMIR


def _decorate_recent(rows, identities, selected_reason) -> list:
    """Hər sətrə ata adı, qrup və «formanı doldur» keçidi (tələbə + imtahan + cari əsas) əlavə et."""
    base = reverse("accounts:profile")
    for row in rows:
        student = _grant_value(row, "student")
        info = identities.get(student.pk, {})
        _set(row, "student_patronymic", info.get("patronymic", ""))
        _set(row, "student_group", info.get("group", ""))
        _set(
            row,
            "prefill_url",
            _append_query_params(
                base,
                section="exam-chance",
                chance_student=str(student.pk),
                chance_exam=str(_grant_value(row, "exam_id") or ""),
                chance_reason=selected_reason,
                chance_focus="grant",
            ),
        )
    return list(rows)


def build_exam_chance_section(request, section, *, active_organization, allowed_sections, active_section):
    if "exam-chance" not in allowed_sections or active_section != "exam-chance":
        return

    from django.db.models import Q

    from apps.accounts.services.exam_center_decide import can_exam_center_decide
    from apps.exams.models import Exam
    from apps.exams.public import SECURE_EXAM_CATEGORIES
    from apps.organizations.models import AcademicPeriod, OrgUnit
    from apps.organizations.public import KAFEDRA_UNIT_TYPES
    from apps.registrar.public import retake_chance
    from core.constants import OrgUnitType
    from core.search_text import tolerant_q

    organization = active_organization
    section["selected_org"] = organization
    # 2026-10-13 (rol auditi B1): bölmə mərkəz istifadəçisinə görünür, «Şans ver» forması isə yalnız
    # `exam_center.decide` açarı ilə (POST da eyni açarla qapılıdır — bax views/exam_chance.py).
    section["can_decide"] = can_exam_center_decide(request)
    section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section="exam-chance")
    if organization is None:
        return

    filters = _read_filters(request)

    # ── Tədris ili + semestr seçimləri ──────────────────────────────────────
    all_periods = list(AcademicPeriod.active.filter(organization=organization).order_by("-start_date"))
    years = sorted({p.academic_year for p in all_periods}, reverse=True)
    if filters["year"] not in years:
        filters["year"] = ""
    year_periods = [p for p in all_periods if p.academic_year == filters["year"]]
    periods = year_periods if filters["year"] else all_periods
    period = _pick(periods, filters["period"])
    if period is None:
        filters["period"] = ""

    # ── Fakültə → kafedra (asılı seçimlər) ──────────────────────────────────
    faculties = list(OrgUnit.active.filter(organization=organization, unit_type=OrgUnitType.FACULTY).order_by("name"))
    faculty = _pick(faculties, filters["faculty"])
    if faculty is None:
        filters["faculty"] = ""
    kafedra_qs = OrgUnit.active.filter(organization=organization, unit_type__in=KAFEDRA_UNIT_TYPES)
    if faculty is not None:
        kafedra_qs = kafedra_qs.filter(parent=faculty)
    kafedras = list(kafedra_qs.order_by("name"))
    kafedra = _pick(kafedras, filters["kafedra"])
    if kafedra is None:
        filters["kafedra"] = ""

    # ── İmtahan siyahısı (filtrli) ──────────────────────────────────────────
    exams_qs = Exam.objects.filter(
        organization=organization,
        exam_type_extended__in=sorted(SECURE_EXAM_CATEGORIES),
        is_deleted=False,
        is_archived=False,
    )
    exam_title_q = tolerant_q(filters["exam_q"], ("title",))
    if exam_title_q is not None:
        exams_qs = exams_qs.filter(exam_title_q)
    unit = kafedra or faculty
    if unit is not None:
        # 2026-09-14 (W5 `w5left`, tapşırıq 1): reyestr qrupuna (`allowed_units`,
        # fakültə/kafedra alt-ağacı) təyin olunmuş imtahanlar da filtrə düşür —
        # əvvəl yalnız kohortun `org_unit`-i yoxlanırdı. Tək `filter()` → tək JOIN dəsti.
        exams_qs = exams_qs.filter(
            Q(allowed_groups__org_unit__path__startswith=unit.path) | Q(allowed_units__path__startswith=f"{unit.path}/")
        )
    if period is not None:
        exams_qs = exams_qs.filter(start_datetime__date__range=(period.start_date, period.end_date))
    elif filters["year"] and year_periods:
        ranges = Q()
        for p in year_periods:
            ranges |= Q(start_datetime__date__range=(p.start_date, p.end_date))
        exams_qs = exams_qs.filter(ranges)
    section["exams"] = list(
        exams_qs.only("id", "title", "exam_type", "exam_type_extended", "start_datetime", "subject_id")
        .distinct()
        .order_by("-start_datetime", "-id")[:300]
    )

    # ── Tələbə axtarışı (qrup / istifadəçi adı / ad-soyad) + hər tələbənin 25% müraciətləri ─────────
    # 2026-10-18 (sahib): şans KONKRET tələbəyə verilir; «25% müraciəti» səbəbi yalnız ödənişi təsdiqlənmiş +
    # buraxılmış müraciəti olan tələbəyə açıqdır — müraciətlər TƏK sorğu ilə qoşulur.
    # 2026-10-24 (sahib): ön-doldurma — `chance_student` (nəticələr səhifəsi / «Son verilən» sətri) tələbəni
    # axtarışsız da çipə çıxarır və işarələyir; ata adı + qrup eyni adlı tələbələri ayırır.
    picked_ids = selected_student_ids(request.GET.get("chance_student"))
    picked = selected_students(organization, picked_ids)
    found = _search_students(organization, filters["student_q"]) if filters["student_q"] else []
    found_ids = {user.pk for user in found}
    found = [user for user in picked if user.pk not in found_ids] + found
    picked_set = {user.pk for user in picked}
    grantable = retake_chance.grantable_applications(organization=organization, student_ids=[u.pk for u in found])
    recent_rows, legacy = _recent_rows(organization)
    identities = identity_map(
        organization, [u.pk for u in found] + [_grant_value(r, "student").pk for r in recent_rows]
    )
    section["student_results"] = [
        {
            "user": user,
            "patronymic": identities.get(user.pk, {}).get("patronymic", ""),
            "group_name": identities.get(user.pk, {}).get("group", ""),
            "selected": user.pk in picked_set,
            "retake_apps": grantable.get(user.pk, []),
            "subject_ids": ",".join(str(app.subject_id) for app in grantable.get(user.pk, [])),
        }
        for user in found
    ]
    section["selected_student_param"] = ",".join(str(user.pk) for user in picked)
    section["focus_grant"] = (request.GET.get("chance_focus") or "") == "grant"

    # ── Son verilən şanslar — rəsmi append-only qeyd (səbəb, əsas, müraciət) ─────────────────────────
    section["reasons"] = retake_chance.reason_choices()
    selected_reason = (request.GET.get("chance_reason") or "").strip()
    section["selected_reason"] = selected_reason if selected_reason in dict(section["reasons"]) else ""
    section["recent_grants"] = _decorate_recent(recent_rows, identities, section["selected_reason"])

    # ── KPI: filtrə uyğun imtahanların ƏSL sayı (siyahı 300-lə kəsilib) + rəsmi qeydlərin cəmi ────────
    section["exam_count"] = exams_qs.distinct().count()
    totals = retake_chance.totals(organization=organization)
    section["grant_count"] = totals["count"] + legacy["count"]
    section["grant_students"] = totals["students"] + legacy["new_students"]
    section["grant_attempts"] = totals["attempts"] + legacy["attempts"]

    section["filters"] = filters
    section["years"] = years
    section["periods"] = periods
    section["faculties"] = faculties
    section["kafedras"] = kafedras
    selected_exam = (request.GET.get("chance_exam") or "").strip()
    section["selected_exam_id"] = selected_exam if selected_exam.isdigit() else ""
    if section["selected_exam_id"] and all(str(exam.pk) != selected_exam for exam in section["exams"]):
        # Ön-doldurulmuş imtahan süzgəcdən / 300 limitindən kənardırsa da siyahıda olsun (eyni org + kateqoriya qaydası).
        extra_exam = (
            Exam.objects.filter(
                pk=int(selected_exam),
                organization=organization,
                exam_type_extended__in=sorted(SECURE_EXAM_CATEGORIES),
                is_deleted=False,
            )
            .only("id", "title", "exam_type", "exam_type_extended", "start_datetime", "subject_id")
            .first()
        )
        if extra_exam is not None:
            section["exams"].insert(0, extra_exam)
        else:
            section["selected_exam_id"] = ""
