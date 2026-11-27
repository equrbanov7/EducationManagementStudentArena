"""Ekran 06 «Qruplar» — qrupun TƏLƏBƏ SİYAHISI (JSON, oxu-only).

Sahib rəyi 2026-09-07: «qrupları açanda ordakı tələbələri də açmaq olsun».
Siyahı çekmecədə göstərilir (`teaching_office_groups.js`); hər sətirdə
«qrupdan çıxar» (qrup əməli), «dondur» / «uzaqlaşdır» (tələbə hərəkəti) və
rəsmi «Fərdi tədris planı» DOCX linki var. Düymələrin görünməsi üçün iki bayraq
qaytarılır: ``can_manage`` (`unit.group_manage`) və ``can_move_students``
(`student.movement`) — server tərəfi hər halda öz qapısını yenidən yoxlayır.

QAPI `group_action` ilə EYNİDİR: tenant + `unit.view` + struktur əhatəsi +
görünən (scope daxilində) qrup — əhatədən kənar id 404 alır (IDOR).
MODUL SƏRHƏDİ: registrar modeli `django_apps.get_model` ilə açılır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.person_names import person_label

from .group_actions import _error, _visible_group
from .group_add_other import OTHER_ID_PREFIX
from .group_roster_union import roster_group_ids
from .groups_registry import (
    can_manage_groups,
    can_move_students,
    can_view_group_students,
    can_view_groups,
    group_manage_scope,
    group_scope,
    movement_scope,
    student_record_scope_q,
)
from .models import Organization
from .subgroup_targets import eligible_records_q, reusable_children, subgroup_number
from .university_wide_scope import candidate_scope

_CTX = "accounts.groups"


def _row(record) -> dict:
    student = record.student
    program = record.program
    return {
        "id": str(record.pk),
        "name": (student.get_full_name() or "").strip() or student.username,
        "username": student.username,
        "status": record.status,
        "admission_year": record.admission_year,
        # İxtisas ŞİFRİ ayrıca — sahib (2026-09-07): siyahıda «qeydiyyat qrupu»
        # əvəzinə ixtisas kodu + qısa adı görünsün.
        "program_code": getattr(program, "display_code", "") or "",
        "program_name": getattr(program, "name", "") or "",
        "program": getattr(program, "display_label", "") or getattr(program, "name", "") or "",
        "education_form": record.education_form or "",
        "education_form_label": str(record.get_education_form_display() or "") if record.education_form else "",
        "group_name": getattr(record.group, "name", "") or "",
        # Tələbənin adına klik → açıq profil (sahib, 2026-09-08).
        "profile_url": reverse("accounts:public_profile", kwargs={"username": student.username}),
    }


def _candidate_row(record, *, group_specialty_id, other=False) -> dict:
    """Namizəd seçicisi (`EMSSearchableSelect`) müqaviləsi: {id, text, hint}.

    ``other`` — tələbə BAŞQA aktiv qrupdadır (sahib 2026-11-18): id «x:» önəkli gəlir ki, dialoq «əlavə olaraq /
    məcburi köçür» seçimini göstərsin (server önəki təmizləyir, uyğunluğu özü yenidən yoxlayır)."""
    student = record.student
    program = record.program
    code = getattr(program, "display_code", "") or ""
    name = person_label(student)  # «Soyad Ad Ata adı» (sahib 2026-11-15)
    meta = ["@" + student.username]
    if code:
        meta.append(code)
    if getattr(program, "name", ""):
        meta.append(program.name)
    if record.group_id and record.group is not None:
        if other:
            label = pgettext(_CTX, "başqa qrupdadır: %s")
        elif record.group.is_active:
            label = pgettext(_CTX, "ana qrup: %s")
        else:
            label = pgettext(_CTX, "arxiv qrup: %s")
        meta.append(label % record.group.name)
    return {
        "id": (OTHER_ID_PREFIX if other else "") + str(record.pk),
        "text": f"{name} · {' · '.join(meta)}",
        "hint": "",
        "same_specialty": bool(
            group_specialty_id and getattr(program, "specialty_unit_id", None) == group_specialty_id
        ),
    }


@login_required
@require_GET
def group_students(request, slug, unit_id):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    if not can_view_groups(request):
        return _error(pgettext(_CTX, "Qrup reyestrinə səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    # QA-2 F-03 (2026-10-17): `unit.view` STRUKTUR oxusudur — tələbə siyahısı tələbə tərəfi açarı istəyir.
    if not can_view_group_students(request):
        return _error(
            pgettext(_CTX, "Qrupun tələbə siyahısına baxmaq səlahiyyətiniz yoxdur."), status=403, code="forbidden"
        )
    scope = group_scope(request, organization)
    if not scope.has_structure_access:
        return _error(pgettext(_CTX, "Struktur əhatəniz yoxdur."), status=403, code="forbidden")
    unit = _visible_group(organization, scope, str(unit_id), include_archived=True)
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")

    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    # Perf auditi 2026-09-13 F-01: `_row()` `record.group.name` oxuyur — `group`
    # `select_related`-də olmayanda hər tələbə üçün ayrıca `orgunit` SELECT-i
    # atılırdı (25 tələbə → 16→39 sorğu). Qrup sətri ilə birlikdə JOIN-lənir.
    records = (
        StudentAcademicRecord.objects.filter(
            organization=organization, group_id__in=roster_group_ids(organization, [unit])[str(unit.pk)], is_active=True
        )
        .select_related("student", "program", "group")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    removed = _removed_rows(organization, unit, StudentAcademicRecord)
    extra = _extra_rows(organization, unit, StudentAcademicRecord)
    # Audit 2026-09-28 S4: idarə düymələri yalnız qrup `unit.group_manage`
    # əhatəsindədirsə (server yazıda onsuz da bu əhatəni yoxlayır).
    rows = [_row(record) for record in records]
    # Sahib 2026-11-25: «Tarixçə» düyməsi — `student.records_view` daşıyana (dondurulmuşlar daxil, oxu).
    from .group_student_history import can_view_history, history_allowed, history_url

    if can_view_history(request) and history_allowed(request, organization, unit):
        for row in rows + removed + extra:
            row["history_url"] = history_url(organization, unit, row["id"])
    manage_scope = group_manage_scope(request, organization)
    can_manage = can_manage_groups(request) and (
        _visible_group(organization, manage_scope, str(unit.pk), include_archived=True) is not None
    )
    return JsonResponse(
        {
            "ok": True,
            "group": {"id": str(unit.pk), "name": unit.name, "is_active": unit.is_active},
            "rows": rows,
            # 2026-10-15 (sahib): «çıxardığım birini sonra əlavə edə bilim» — məzuniyyətdə / xaric
            # edilmiş tələbələr qrupun FK-sını saxlayır (status dəyişir, qrup yox); çekmecədə ayrıca
            # görünür və «Bərpa et» (reinstatement əmri) ilə bu qrupa qaytarılır.
            "removed_rows": removed,
            # Sahib 2026-11-18: öz qrupu başqa olan, amma bu qrupun cari jurnallarında oxuyan tələbələr (əcnəbilər).
            "extra_rows": extra,
            "subgroups": (
                [
                    {"id": str(child.pk), "name": child.name, "number": subgroup_number(unit, child)}
                    for child in reusable_children(unit)
                ]
                if can_manage
                else []
            ),
            "can_manage": can_manage,
            # Sahib 2026-11-27 (dekanlıq): düymələr yalnız qrup HƏRƏKƏT əhatəsindədirsə — oxu əhatəsi fakültəyə
            # genişlənə bilər, əmr isə dar əhatə ilə yazılır (server `movements.create_movement`-də yenidən yoxlayır).
            "can_move_students": can_move_students(request)
            and _visible_group(organization, movement_scope(request, organization), str(unit.pk), include_archived=True)
            is not None,
        }
    )


#: Qrupun aktiv siyahısından ÇIXMIŞ, amma qeydi bu qrupda qalan statuslar (bərpa oluna bilər).
#: Məzun (2026-10-25) da burada görünür — «Bərpa et» səhv məzun etməni geri qaytarır.
REMOVED_STATUSES = ("academic_leave", "expelled", "graduated")
_REMOVING_KINDS = ("academic_leave", "expulsion", "graduation")


def _removed_rows(organization, unit, record_model) -> list:
    """Məzuniyyətdə / xaric edilmiş tələbələr + onları çıxaran SON əmr (bir əlavə sorğu).

    Akademik məzuniyyət və xaric etmə yalnız STATUSU dəyişir (``registrar.movements``):
    ``group`` FK-sı qalır, ``is_active`` isə ``False`` olur — ona görə aktiv siyahıda
    görünmürdülər və «hara düşdülər?» sualı yaranırdı.
    """
    records = list(
        record_model.objects.filter(organization=organization, group=unit, status__in=REMOVED_STATUSES)
        .select_related("student", "program", "group")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    if not records:
        return []
    movement_model = django_apps.get_model("registrar", "StudentMovement")
    last = {}
    for movement in (
        movement_model.objects.filter(
            organization=organization, record_id__in=[r.pk for r in records], kind__in=_REMOVING_KINDS
        )
        .only("record_id", "kind", "order_number", "order_date", "effective_until", "leave_reason", "created_at")
        .order_by("-created_at")
    ):
        last.setdefault(movement.record_id, movement)
    rows = []
    for record in records:
        row = _row(record)
        movement = last.get(record.pk)
        row["order_number"] = movement.order_number if movement else ""
        row["order_date"] = movement.order_date.strftime("%d.%m.%Y") if movement and movement.order_date else ""
        row["until"] = movement.effective_until.strftime("%d.%m.%Y") if movement and movement.effective_until else ""
        # Dondurma səbəbinin kateqoriyası (sahib 2026-11-04); köhnə əmrlərdə boşdur.
        row["leave_reason_label"] = movement.leave_reason_label if movement else ""
        rows.append(row)
    return rows


def _extra_rows(organization, unit, record_model) -> list:
    """«Əlavə üzvlər» — öz qrupunda qalaraq bu qrupun cari semestr jurnallarında olan tələbələr (oxu)."""
    from .student_transfer import extra_group_members

    period = organization.academic_periods.filter(is_current=True, is_active=True).first()
    members = {
        item["student_id"]: item["subjects"]
        for item in extra_group_members(organization=organization, group=unit, period=period)
    }
    if not members:
        return []
    rows = []
    for record in (
        record_model.objects.filter(organization=organization, student_id__in=list(members), is_active=True)
        .select_related("student", "program", "group")
        .order_by("student__last_name", "student__first_name", "student__username")
    ):
        row = _row(record)
        row["extra"] = True
        row["extra_subjects"] = members.get(record.student_id, [])
        rows.append(row)
    return rows


#: Namizəd axtarışının səhifə ölçüsü (searchable-select lazy scroll ilə uzanır).
CANDIDATE_PAGE_DEFAULT = 20
CANDIDATE_PAGE_MAX = 50
MAX_QUERY_LENGTH = 80
#: Bu uzunluqdan axtarışda başqa qrupdakı tələbələr də namizəddir (sahib 2026-11-18).
OTHER_GROUP_MIN_QUERY = 2


@login_required
@require_GET
def group_student_candidates(request, slug, unit_id):
    """Qrupsuzlar və alt qrupun doğrulanmış ana qrupundakı qeydiyyatlı tələbələr.

    Əlaqəsiz aktiv qrupdan tələbə göstərilmir. Axtarış ad, istifadəçi adı və
    ixtisas üzrədir; qrupun öz ixtisası əvvəl gəlir.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    if not can_view_groups(request) or not can_manage_groups(request):
        return _error(pgettext(_CTX, "Qrupları idarə etmək səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    # Audit 2026-09-28 S4: namizəd siyahısı yazı əməlinin hissəsidir — idarə əhatəsi.
    scope = group_manage_scope(request, organization)
    if not scope.has_structure_access:
        return _error(pgettext(_CTX, "Struktur əhatəniz yoxdur."), status=403, code="forbidden")
    unit = _visible_group(organization, scope, str(unit_id))
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")

    from django.db.models import Case, IntegerField, Q, Value, When

    from core.program_codes import PROGRAM_CODE_SEARCH_FIELDS
    from core.search_text import tolerant_q

    eligible, parent = eligible_records_q(unit)
    if parent is not None and _visible_group(organization, scope, str(parent.pk)) is None:
        eligible = Q(group__isnull=True) | Q(group__is_active=False)
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    query = (request.GET.get("q") or "").strip()[:MAX_QUERY_LENGTH]
    records = StudentAcademicRecord.objects.filter(organization=organization, is_active=True, status="enrolled")
    # Sahib 2026-11-18: axtarış yazılanda BÜTÜN tələbələr (başqa qrupdakı da — «əlavə olaraq» və ya «məcburi
    # köçür» seçimi ilə); boş axtarışda əvvəlki kimi yalnız qrupsuzlar (siyahı nəhəng olmasın).
    # Əcnəbi qrupu (sahib 2026-11-25): boş axtarışda da bütün tələbələr (səhifə-səhifə) — öz qrupu başqadır.
    from .group_kind import is_foreign

    show_all = len(query) >= OTHER_GROUP_MIN_QUERY or is_foreign(unit)
    records = records.exclude(group=unit) if show_all else records.filter(eligible)
    # Audit 2026-09-28 S3: başqa fakültənin tələbələri görünmür — universitet əhatəli kafedranın (Xarici dillər)
    # qrupunda isə bütün təşkilat (sahib 2026-11-22, ``university_wide_scope``).
    candidates = candidate_scope(organization, scope, unit)
    records = records.filter(student_record_scope_q(candidates)).select_related("student__profile", "program", "group")
    # Dözümlü axtarış (sahib 2026-09-26): ad/ixtisas adı az/ing hərfinə, şifr ayırıcıya dözümlü.
    search_q = tolerant_q(
        query,
        (
            "student__first_name",
            "student__last_name",
            "student__username",
            "student__profile__patronymic",
            "program__name",
        ),
        compact_fields=tuple(f"program__{field}" for field in PROGRAM_CODE_SEARCH_FIELDS),
    )
    if search_q is not None:
        records = records.filter(search_q)
    records = records.annotate(
        _free=Case(When(eligible, then=Value(0)), default=Value(1), output_field=IntegerField()),
        _same=Case(
            When(program__specialty_unit_id=unit.parent_id, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
    ).order_by("_free", "_same", "student__last_name", "student__first_name", "student__username")

    try:
        offset = max(0, int(request.GET.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = max(1, min(int(request.GET.get("limit") or CANDIDATE_PAGE_DEFAULT), CANDIDATE_PAGE_MAX))
    except (TypeError, ValueError):
        limit = CANDIDATE_PAGE_DEFAULT
    window = list(records[offset : offset + limit + 1])
    return JsonResponse(
        {
            "has_access": True,
            "results": [
                _candidate_row(record, group_specialty_id=unit.parent_id, other=record._free == 1)
                for record in window[:limit]
            ],
            "has_more": len(window) > limit,
        }
    )


__all__ = ["group_student_candidates", "group_students"]
