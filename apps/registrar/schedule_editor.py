"""Cədvəl redaktoru — OXU/VALİDASİYA qatı (hüceyrə → açılış bağlaması).

Yazma qatı ayrıdır: :mod:`apps.registrar.schedule_editor_actions`.

──────────────────────────────────────────────────────────────────────────────
HÜCEYRƏ DİALOQU MÖVCUD MODELƏ NECƏ OTURUR
──────────────────────────────────────────────────────────────────────────────
Slot ``CourseOffering``-dən asılıdır (fənn + semestr + qrup + müəllim oradadır),
ona görə «xanaya klik → müəllim/fənn seç» dialoqu YENİ model yaratmır, mövcud
açılışı tapır/yaradır (``services.get_or_create_offering``).

⚠️ ``uniq_offering_subject_period_group`` məhdudiyyəti: bir (təşkilat, fənn,
semestr, qrup) üçün YALNIZ BİR açılış ola bilər — yəni müəllim açılışın
xassəsidir, slotun yox. Buradan üç qayda çıxır:

1. açılış yoxdursa → yaradılır və seçilmiş müəllim ona təyin olunur;
2. açılış var, müəllimi BOŞDURSA → seçilmiş müəllim təyin olunur (audit);
3. açılış var, müəllimi BAŞQADIRSA → cədvəl redaktoru müəllimi SƏSSİZCƏ
   dəyişmir. Açılışın müəllimini dəyişmək jurnal sahibliyini və qiymətləri
   köçürmək deməkdir; onun öz auditli axını var — «Fənn təhvili»
   (``apps.registrar.handover``). Ona görə burada AYDIN xəta qaytarılır.

Beləliklə cədvəl redaktoru heç vaxt jurnal sahibliyini gizli dəyişmir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils.translation import pgettext

from apps.registrar import schedule as schedule_service
from apps.registrar import schedule_conflicts, schedule_grid, schedule_manage
from apps.registrar.models import CourseOffering, SlotKind, Subject, WeekType

_CTX = "registrar.schedule_editor"

#: Müəllim/fənn seçicilərində göstərilən maksimum sətir (canlı axtarış var).
CHOICE_LIMIT = 400


class CellError(Exception):
    """Hüceyrə əməlinin sahə-səviyyəli xətası (``errors`` UI-a gedir)."""

    def __init__(self, code: str, message: str, errors=None, status: int = 400, extra=None):
        errors = dict(errors or {})
        extra = dict(extra or {})
        super().__init__(code, message, errors, status, extra)
        self.code = code
        self.message = message
        self.errors = errors
        self.status = status
        self.extra = extra


def _person_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


# ── Seçici siyahıları ────────────────────────────────────────────────────────


def allowed_subjects(*, organization, group, period) -> list[dict]:
    """Bu qrupa cədvələ yazıla bilən FƏNLƏR (kurikulum + açıq açılışlar).

    Sahibin tələbi «fənn seçilsin» — amma ixtiyari kataloq fənni yox: qrupun
    tədris planı (``CurriculumSubject``) nə deyirsə o. Plan qrupun AKTİV
    tələbələrinin akademik qeydlərindəki kurikulumlardan gəlir; artıq açılmış
    açılışların fənni həmişə əlavə olunur (köçürmə/əl ilə açılan hallar üçün).
    """
    if organization is None or group is None or period is None:
        return []
    from apps.registrar.models import AcademicStatus, CurriculumSubject, StudentAcademicRecord

    curriculum_ids = set(
        StudentAcademicRecord.objects.filter(
            organization=organization, group=group, status=AcademicStatus.ENROLLED
        ).values_list("curriculum_id", flat=True)
    )
    subject_ids = set(
        CourseOffering.objects.filter(organization=organization, group=group, period=period).values_list(
            "subject_id", flat=True
        )
    )
    if curriculum_ids:
        subject_ids |= set(
            CurriculumSubject.objects.filter(organization=organization, curriculum_id__in=curriculum_ids).values_list(
                "subject_id", flat=True
            )
        )
    if not subject_ids:
        return []
    rows = Subject.objects.filter(organization=organization, pk__in=subject_ids).order_by("code")[:CHOICE_LIMIT]
    return [{"id": str(row.pk), "code": row.code or "", "name": row.name or ""} for row in rows]


def teacher_choices(organization) -> list[dict]:
    """Cədvələ qoyula bilən müəllimlər — təşkilatın AKTİV müəllim üzvlükləri."""
    if organization is None:
        return []
    Membership = django_apps.get_model("organizations", "Membership")
    rows = (
        Membership.objects.filter(organization=organization, is_active=True)
        .exclude(role__name__in=("student", "lead_student", "alumni"))
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    seen, out = set(), []
    for membership in rows:
        user = membership.user
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        out.append({"id": str(user.pk), "name": _person_name(user)})
        if len(out) >= CHOICE_LIMIT:
            break
    return sorted(out, key=lambda row: row["name"].lower())


# ── Payload ──────────────────────────────────────────────────────────────────


def parse_cell(data, *, organization) -> dict:
    """Hüceyrə dialoqunun xam sözlüyünü təmizlənmiş dəyərlərə çevirir.

    Vaxt YALNIZ nömrələnmiş dərs saatlarından seçilə bilər (grid sətirləri
    məhz onlardır); köhnə sərbəst vaxtlı slotlar redaktə edilərkən öz
    dəyərlərini saxlasın deyə mövcud slotun açarı da qəbul edilir.
    """
    errors: dict = {}
    cleaned: dict = {}

    try:
        weekday = int(str(data.get("weekday") or "").strip() or 0)
    except (TypeError, ValueError):
        weekday = 0
    if not 1 <= weekday <= 7:
        errors["weekday"] = pgettext(_CTX, "Həftənin günü seçilməlidir.")
    cleaned["weekday"] = weekday

    key = str(data.get("time_slot") or "").strip()
    period_row = schedule_grid.period_by_key(organization).get(key)
    if period_row is not None:
        cleaned["start_time"], cleaned["end_time"] = period_row["start"], period_row["end"]
    else:
        start, end = schedule_service.parse_time_slot(key)
        cleaned["start_time"], cleaned["end_time"] = start, end
    if cleaned["start_time"] is None or cleaned["end_time"] is None:
        errors["time_slot"] = pgettext(_CTX, "Dərs saatı seçilməlidir.")

    week_type = str(data.get("week_type") or "").strip()
    cleaned["week_type"] = week_type if week_type in dict(WeekType.choices) else WeekType.ALL
    kind = str(data.get("slot_kind") or data.get("kind") or "").strip()
    cleaned["kind"] = kind if kind in dict(SlotKind.choices) else SlotKind.LECTURE

    room = str(data.get("room") or "").strip()
    if len(room) > 64:
        errors["room"] = pgettext(_CTX, "Auditoriya adı 64 simvoldan uzun ola bilməz.")
    cleaned["room"] = room
    return cleaned, errors


# ── Açılış bağlaması ─────────────────────────────────────────────────────────


def resolve_offering(*, actor, organization, group, period, subject, instructor, create=True):
    """Hüceyrə seçimini ``CourseOffering``-ə bağlayır (tap / yarat / rədd et).

    Qaytarır ``(offering, created, instructor_assigned)``. Modul başlığındakı
    üç qayda burada tətbiq olunur — müəllim dəyişikliyi «Fənn təhvili»nə
    yönləndirilir, səssiz köçürmə YOXDUR.

    ``create=False`` — YALNIZ-OXU rejim: açılış hələ yoxdursa YARADILMIR,
    əvəzinə YADDA SAXLANMAMIŞ nüsxə qaytarılır. Bu, «Konflikti yoxla» axını
    üçündür: quru yoxlama bazada sətir qoymamalıdır (əks halda hər dialoq
    açılışı boş `CourseOffering` doğururdu).
    """
    from apps.registrar import services

    if subject is None:
        raise CellError(
            "invalid", pgettext(_CTX, "Fənn seçilməlidir."), errors={"subject_id": pgettext(_CTX, "Fənn seçilməlidir.")}
        )
    if period is None or group is None:
        raise CellError("invalid", pgettext(_CTX, "Semestr və qrup seçilməlidir."))

    offering = (
        CourseOffering.objects.filter(organization=organization, subject=subject, period=period, group=group)
        .select_related("organization", "subject", "group", "period", "instructor")
        .first()
    )
    created = False
    if offering is None:
        if not create:
            return (
                CourseOffering(
                    organization=organization,
                    subject=subject,
                    period=period,
                    group=group,
                    instructor=instructor,
                ),
                False,
                False,
            )
        offering = services.get_or_create_offering(
            organization=organization, subject=subject, period=period, group=group
        )
        created = True

    assigned = False
    if instructor is not None and offering.instructor_id != getattr(instructor, "pk", None):
        if offering.instructor_id:
            raise CellError(
                "instructor_locked",
                pgettext(
                    _CTX,
                    "Bu fənn həmin qrupda artıq %(teacher)s müəlliminə bağlıdır. Müəllimi dəyişmək üçün "
                    "«Fənn təhvili» bölməsindən istifadə edin — cədvəl redaktoru jurnal sahibliyini dəyişmir.",
                )
                % {"teacher": _person_name(offering.instructor)},
                errors={"instructor_id": pgettext(_CTX, "Açılışın müəllimi «Fənn təhvili» ilə dəyişilir.")},
                status=409,
            )
        offering.instructor = instructor
        if create:
            offering.save(update_fields=["instructor", "updated_at"])
        assigned = True

    # Cədvələ dərs qoyulursa açılış təbii olaraq AKTİVDİR (arxivlənmiş açılışa
    # slot yazmaq mənasızdır) — yalnız-oxu rejimdə bu da yazılmır.
    if create and not offering.is_active:
        offering.is_active = True
        offering.save(update_fields=["is_active", "updated_at"])
    return offering, created, assigned


# ── Yoxlama (heç nə yazmır) ──────────────────────────────────────────────────


def check_cell(*, organization, offering, cleaned, exclude_id=None) -> dict:
    """Saxlama-öncəsi tam yoxlama: dövr pəncərəsi + konfliktlər + tövsiyələr."""
    errors: dict = {}
    window = schedule_manage.period_window_error(offering)
    if window:
        errors["period"] = window
        return {"ok": False, "errors": errors, "conflicts": [], "suggestions": []}

    # Açılış hələ bazada yoxdursa (quru yoxlama) təkrar slot da ola bilməz.
    # ⚠️ `offering.pk` YARAMIR: `UUIDModel` pk-nı yaradılış anında təyin edir —
    # yaddaşdakı nüsxənin də pk-sı var. Kanonik yoxlama `_state.adding`-dir.
    duplicate = (
        None
        if offering._state.adding
        else schedule_manage.duplicate_slot(
            offering=offering,
            weekday=cleaned["weekday"],
            start_time=cleaned["start_time"],
            end_time=cleaned["end_time"],
            week_type=cleaned["week_type"],
            room=cleaned["room"],
            exclude_id=exclude_id,
        )
    )
    if duplicate is not None and not duplicate.is_parked:
        errors["time_slot"] = pgettext(_CTX, "Bu slot artıq cədvəldədir.")
        return {"ok": False, "errors": errors, "conflicts": [], "suggestions": []}

    conflicts = schedule_conflicts.detect(
        organization=organization,
        weekday=cleaned["weekday"],
        start_time=cleaned["start_time"],
        end_time=cleaned["end_time"],
        week_type=cleaned["week_type"],
        room=cleaned["room"],
        group_id=offering.group_id,
        instructor_id=offering.instructor_id,
        exclude_ids=(exclude_id,) if exclude_id else (),
    )
    suggestions = []
    if conflicts:
        suggestions = schedule_conflicts.suggest(
            organization=organization,
            group_id=offering.group_id,
            instructor_id=offering.instructor_id,
            week_type=cleaned["week_type"],
            room=cleaned["room"],
            shift=schedule_grid.shift_of(cleaned["start_time"]),
            exclude_ids=(exclude_id,) if exclude_id else (),
            limit=6,
        )
    return {"ok": not conflicts, "errors": errors, "conflicts": conflicts, "suggestions": suggestions}


__all__ = [
    "CHOICE_LIMIT",
    "CellError",
    "allowed_subjects",
    "check_cell",
    "parse_cell",
    "resolve_offering",
    "teacher_choices",
]
