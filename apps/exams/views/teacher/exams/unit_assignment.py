"""teacher exams paketi — reyestr qrupu (OrgUnit GROUP) təyinatı + sehrbaz xəta addımı.

2026-09-14 (W4 `w4wizard`):

* **R2** — sehrbazın «Qruplar (reyestr)» seçicisi: namizədlər imtahanın
  təşkilatının AKTİV `group` tipli vahidləridir; unit-skoplu (dekan / kafedra)
  istifadəçi yalnız öz alt-ağacını görür. Göndərilən id-lər eyni namizəd
  dəstinə görə yoxlanılır — başqa tenantın / əhatədən kənar qrupu 400 ilə
  rədd edilir (mövcudluq sızmır: «tapılmadı» kimi cavablanır).
* **R1** — server 400 cavabı `step` / `field` daşıyır ki, sehrbaz xətanın
  OLDUĞU addıma keçsin (əvvəl `end_after_start` qeyri-sahə xətası idi və
  sehrbaz həmişə 1-ci addıma qayıdırdı, xəta isə 2-ci addımın idi).

`ExamForm` (`apps/exams/forms/exam.py`) toxunulmur: reyestr qrupu forma sahəsi
deyil, view qatında oxunub yoxlanılır və `form.save_m2m()`-dən sonra yazılır.
"""

from uuid import UUID

from django.utils.translation import pgettext

from apps.organizations.models import OrgUnit
from apps.organizations.public import get_permission_scope, scope_org_units
from core.constants import OrgUnitType

#: POST / GET-də reyestr qrupu id-lərinin sahə adı.
UNITS_FIELD_NAME = "allowed_units"

#: Sehrbaz addımı ↔ forma sahələri (şablondakı `data-ew-panel` sırası ilə).
WIZARD_STEP_FIELDS = {
    0: ("organization", "title", "description", "exam_type", "exam_type_extended", "subject"),
    1: (
        "random_question_count",
        "start_datetime",
        "end_datetime",
        "total_duration_minutes",
        "default_question_time_seconds",
        "fair_question_distribution_enabled",
        "ai_difficulty_balance_enabled",
        "max_attempts_per_user",
    ),
    2: (
        "is_active",
        "is_public",
        "enable_paint",
        "allowed_groups",
        UNITS_FIELD_NAME,
        "allowed_users",
        "excluded_users",
    ),
}

#: Qeyri-sahə xətaları — formanın `clean()`-i sahə adı vermir; addımı burada
#: mesaj açarı ilə tapırıq (`end_after_start` → vaxt addımı, `end_datetime`).
NON_FIELD_ERROR_TARGETS = {
    "end_after_start": (1, "end_datetime"),
    "enable_paint_written_only": (2, "enable_paint"),
}


def exam_unit_candidates(request, organization, *, permission="exam.create"):
    """Sehrbaz seçicisi üçün reyestr qrupu namizədləri (təşkilat + əhatə)."""
    queryset = OrgUnit.objects.filter(
        organization=organization,
        unit_type=OrgUnitType.GROUP,
        is_active=True,
    )
    scope = get_permission_scope(request.user, organization, permission, request=request)
    if scope.is_unit_scoped:
        # Dekan / kafedra müdürü kimi unit-skoplu rol → yalnız öz alt-ağacı.
        # Kurs-skoplu adi müəllim (`EMPTY_SCOPE`) və org-wide rol → bütün təşkilat.
        queryset = scope_org_units(queryset, scope)
    return queryset.select_related("parent").order_by("name")


def unit_display_label(unit) -> str:
    """Seçicidə / təsdiq dialoqunda görünən ad: «634 ing — Dizayn (Qrafik)»."""
    parent = getattr(unit, "parent", None)
    if parent is not None and parent.name:
        return f"{unit.name} — {parent.name}"
    return unit.name


def parse_requested_unit_ids(data) -> list[str]:
    """Göndərilən id-ləri (UUID mətni) təkrarsız, sıra ilə qaytarır; zibil atılır."""
    raw_values = data.getlist(UNITS_FIELD_NAME) if hasattr(data, "getlist") else []
    ids: list[str] = []
    for raw in raw_values:
        for piece in str(raw or "").split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                normalized = str(UUID(piece))
            except (TypeError, ValueError):
                normalized = piece  # yoxlamada «tapılmadı» kimi rədd olunur
            if normalized not in ids:
                ids.append(normalized)
    return ids


def resolve_requested_units(request, organization, data, *, permission="exam.create"):
    """`(units, error)` — göndərilən reyestr qrupları namizəd dəstində olmalıdır.

    Boş seçim → `([], None)`. Hər hansı id namizəd deyilsə (başqa təşkilat,
    əhatədən kənar, arxiv, GROUP olmayan vahid, yanlış UUID) → bütün seçim
    rədd edilir və lokalizə mesaj qaytarılır (tenant izolyasiyası, R2).
    """
    requested = parse_requested_unit_ids(data)
    if not requested:
        return [], None
    valid_ids = [value for value in requested if _is_uuid(value)]
    found = {}
    if valid_ids and organization is not None:
        found = {
            str(unit.pk): unit
            for unit in exam_unit_candidates(request, organization, permission=permission).filter(pk__in=valid_ids)
        }
    if len(found) != len(requested):
        return [], pgettext("exams.view.exams.error", "allowed_units_invalid")
    return [found[value] for value in requested], None


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (TypeError, ValueError):
        return False
    return True


def selected_units_for_form(request, organization, form, exam, *, permission="exam.create"):
    """Yalnız SEÇİLİ reyestr qruplarını qaytarır (lazy render — `_selected_access_entities` kimi).

    Bağlı formada göndərilən id-lər, redaktədə imtahanın mövcud qrupları.
    Redaktədə mövcud qruplar əhatədən asılı olmadan göstərilir ki, dekan
    başqa fakültənin qrupunu «görməsə də» seçimin olduğunu bilsin.
    """
    if form.is_bound:
        ids = [value for value in parse_requested_unit_ids(form.data) if _is_uuid(value)]
        if not ids or organization is None:
            return []
        candidates = exam_unit_candidates(request, organization, permission=permission)
        by_id = {str(unit.pk): unit for unit in candidates.filter(pk__in=ids)}
        return _with_subgroups(organization, [by_id[value] for value in ids if value in by_id])
    if exam is not None and exam.pk:
        return _with_subgroups(organization, list(exam.allowed_units.select_related("parent").order_by("name")))
    return []


def _with_subgroups(organization, units):
    """Hər seçili qrupa `subgroups_json` (alt qrupların id/ad siyahısı) yapışdırır —
    sehrbaz ana qrupu yenidən seçəndə alt qrupları avtomatik seçir (sahib 2026-09-21)."""
    import json

    from apps.registrar.public import subgroup_rollup

    mapping = subgroup_rollup.subgroup_map(organization, units) if organization is not None and units else {}
    for unit in units:
        subs = mapping.get(unit.pk, [])
        unit.subgroups_json = json.dumps([{"id": str(sub.pk), "text": unit_display_label(sub)} for sub in subs])
    return units


def apply_allowed_units(request, organization, exam, units, *, permission="exam.edit") -> None:
    """`exam.allowed_units`-i yeni seçimlə əvəz edir; əhatədən KƏNAR mövcud
    qruplar qorunur (unit-skoplu redaktor onları görmür, deməli silə də bilməz)."""
    keep_ids = set()
    if exam.pk:
        visible_ids = set(
            exam_unit_candidates(request, organization, permission=permission).values_list("pk", flat=True)
        )
        keep_ids = {pk for pk in exam.allowed_units.values_list("pk", flat=True) if pk not in visible_ids}
    exam.allowed_units.set(list(keep_ids | {unit.pk for unit in units}))


def legacy_groups_available(form, selected_groups) -> bool:
    """Köhnə kohort (`StudentGroup`) bölməsi yalnız belə qrup VARSA göstərilir.

    Sahibin 2026-09-07 qərarı: kohort səthi silinməyə gedir — reyestr qrupu
    əsas seçicidir; kohortlar «Köhnə kohortlar» kimi ikinci dərəcəli qalır.
    """
    if selected_groups:
        return True
    field = form.fields.get("allowed_groups")
    if field is None:
        return False
    return field.queryset.exists()


def first_error_target(form, *, allowed_units_error: str | None = None):
    """`(step, field)` — sehrbazın fokuslanacağı ilk xəta; xəta yoxdursa `(None, "")`.

    Sıra: addım sırası ilə sahə xətaları; qeyri-sahə xətaları açar üzrə
    xəritələnir (`NON_FIELD_ERROR_TARGETS`), tanınmayan qeyri-sahə xətası
    1-ci addımdır (köhnə davranış). Reyestr qrupu xətası 3-cü addımdır.
    """
    errors = getattr(form, "errors", None) or {}
    for step, fields in WIZARD_STEP_FIELDS.items():
        for field in fields:
            if field in errors:
                return step, field
    if allowed_units_error:
        return 2, UNITS_FIELD_NAME
    non_field = errors.get("__all__")
    if non_field:
        for error in non_field.as_data():
            for key, target in NON_FIELD_ERROR_TARGETS.items():
                # Mesaj lokalizə olunur; açar olduğu kimi (`pgettext` msgid) tərcümə
                # olunmayanda da, tərcümə olunanda da müqayisə tərcümə mətni ilə aparılır.
                if str(error.message) == str(pgettext("exams.form.exam.error", key)):
                    return target
        return 0, ""
    for field in errors:
        if field != "__all__":
            return 3, field
    return None, ""


__all__ = [
    "NON_FIELD_ERROR_TARGETS",
    "UNITS_FIELD_NAME",
    "WIZARD_STEP_FIELDS",
    "apply_allowed_units",
    "exam_unit_candidates",
    "first_error_target",
    "legacy_groups_available",
    "parse_requested_unit_ids",
    "resolve_requested_units",
    "selected_units_for_form",
    "unit_display_label",
]
