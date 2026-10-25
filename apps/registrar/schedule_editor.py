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

SLOTU APARAN MÜƏLLİM (2026-09-25, bölünmüş tədris): jurnal sahibliyinə TOXUNMADAN
slotun özünə müəllim yazıla bilər («Dərsi aparan müəllim», default «Jurnal sahibi»).
Seçim yalnız bu açılışı apara bilən müəllimlərdəndir — server yoxlayır
(:func:`resolve_slot_instructor`, qayda :mod:`apps.registrar.schedule_slot_teachers`).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.conf import settings
from django.utils.translation import pgettext

from apps.registrar import schedule as schedule_service
from apps.registrar import schedule_conflicts, schedule_grid, schedule_manage, schedule_slot_teachers
from apps.registrar.models import CourseOffering, SlotKind, Subject, WeekType

_CTX = "registrar.schedule_editor"


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


def allowed_subjects(*, organization, group, period, instructor=None) -> list[dict]:
    """Bu qrupa cədvələ yazıla bilən FƏNLƏR (müəllimin yükü + kurikulum + açılışlar).

    Sahibin tələbi «fənn seçilsin» — amma ixtiyari kataloq fənni yox. Mənbələr:

    * qrupun tədris planı (``CurriculumSubject``) — plan qrupun AKTİV
      tələbələrinin akademik qeydlərindəki kurikulumlardan gəlir;
    * artıq açılmış açılışların fənni (köçürmə/əl ilə açılan hallar üçün);
    * kafedra TAPŞIRIĞININ bu qrupa aid sətirləri (``workload.TeachingTaskRow``,
      ``get_model`` ilə — registrar workload-u import etmir);
    * **müəllim seçilibsə** (sahib 2026-09-21: «müəllimi seçirəm, fənni
      görünmür») — həmin müəllimin bu dövrdəki açılışları və dərs yükü
      bölgüsü (``workload.TeacherAssignment``).  Müəllimin fənləri qrup
      siyahısı ilə kəsişirsə kəsişmə, kəsişmirsə müəllimin öz fənləri
      göstərilir; müəllimin heç bir fənni yoxdursa qrup siyahısı qalır.

    Qrup siyahısı tamamilə boşdursa (ATİS köçürməsində akademik qeydin
    kurikulumu olmaya bilər) dövrün bütün açılışlarının fənləri, o da yoxdursa
    kataloq göstərilir — modal boş qalmasın.
    """
    if organization is None or period is None:
        return []
    from apps.registrar.models import AcademicStatus, CurriculumSubject, StudentAcademicRecord

    subject_ids: set = set()
    if group is not None:
        curriculum_ids = set(
            StudentAcademicRecord.objects.filter(
                organization=organization, group=group, status=AcademicStatus.ENROLLED
            ).values_list("curriculum_id", flat=True)
        )
        subject_ids |= set(
            CourseOffering.objects.filter(organization=organization, group=group, period=period).values_list(
                "subject_id", flat=True
            )
        )
        if curriculum_ids:
            subject_ids |= set(
                CurriculumSubject.objects.filter(
                    organization=organization, curriculum_id__in=curriculum_ids
                ).values_list("subject_id", flat=True)
            )
        subject_ids |= _task_subject_ids(organization, period, group=group)
    subject_ids.discard(None)

    if instructor is not None:
        teacher_ids = set(
            CourseOffering.objects.filter(organization=organization, period=period, instructor=instructor).values_list(
                "subject_id", flat=True
            )
        )
        teacher_ids |= _task_subject_ids(organization, period, teacher=instructor)
        teacher_ids.discard(None)
        if teacher_ids:
            subject_ids = (subject_ids & teacher_ids) or teacher_ids

    if not subject_ids:
        subject_ids = set(
            CourseOffering.objects.filter(organization=organization, period=period).values_list("subject_id", flat=True)
        )
        subject_ids.discard(None)
    # 2026-10-17: siyahı KƏSİLMİR (əvvəl `[:400]` kodla sıralanmış — köhnə semestrdə 600+ fənnin, kataloqda
    # 2 538-in qalanı səssizcə yox idi). Seçicidə axtarış var, menyu tənbəl qurulur; kataloq ehtiyatı (dövrdə
    # heç bir açılış yoxdursa) QKU klonunda 289 KB JSON / 97 KB gzip-dir. `values_list` — model nümunəsi yox.
    rows = Subject.objects.filter(organization=organization)
    if subject_ids:
        rows = rows.filter(pk__in=subject_ids)
    return [
        {"id": str(pk), "code": code or "", "name": name or ""}
        for pk, code, name in rows.order_by("code", "pk").values_list("pk", "code", "name")
    ]


def _task_subject_ids(organization, period, *, group=None, teacher=None) -> set:
    """Kafedra tapşırığından fənn id-ləri — qrupa görə və/və ya müəllimə görə."""
    try:
        TaskRow = django_apps.get_model("workload", "TeachingTaskRow")
        Assignment = django_apps.get_model("workload", "TeacherAssignment")
    except LookupError:
        return set()
    if teacher is not None:
        rows = Assignment.objects.filter(
            organization=organization, teacher=teacher, row__period=period, row__subject__isnull=False
        )
        if group is not None:
            rows = rows.filter(row__groups=group)
        return set(rows.values_list("row__subject_id", flat=True))
    if group is None:
        return set()
    rows = TaskRow.objects.filter(organization=organization, period=period, groups=group, subject__isnull=False)
    return set(rows.values_list("subject_id", flat=True))


def teacher_choices(organization) -> list[dict]:
    """Cədvələ qoyula bilən müəllimlər — təşkilatın AKTİV müəllim üzvlükləri.

    PERF-1 F-16: siyahı təşkilat üzrə keşlənir (``core.cache.SCHEDULE_TEACHER_CHOICES_TTL``; üzvlük / rol
    yazısı keşi silir) — hər redaktor açılışında bütün üzvlüklərin skanı + model nümunələri idi.
    """
    if organization is None:
        return []
    from core.cache import SCHEDULE_TEACHER_CHOICES_TTL, cached_or_compute, schedule_teacher_choices_key

    return cached_or_compute(
        schedule_teacher_choices_key(organization.pk),
        lambda: _teacher_choices(organization),
        timeout=SCHEDULE_TEACHER_CHOICES_TTL,
    )


def _teacher_choices(organization) -> list[dict]:
    """Jurnal sahibi ola bilən HƏR müəllim — aktiv üzvlüyü aktiv ``grade.input`` rolundan gələn aktiv istifadəçi.

    Dəst ``schedule_slot_teachers.authorized_teacher_ids`` / ``integrity.eligible_instructor_user_ids`` ilə
    EYNİDİR (yazı onu yoxlayır). 2026-10-17 (PERF-1 F-16 ardı): əvvəl siyahı ad üzrə sıralanıb 400-də kəsilirdi
    (`CHOICE_LIMIT`, indi yoxdur) — 871 heyətli təşkilatda əlifbanın sonundakı müəllimlər redaktorda yox idi; tələbə rolları
    ad ilə çıxarılırdı. İndi kəsilmir, soyad → ad üzrə sıralanır (seçicidə axtarış var). İki yüngül sorğu
    (rol icazəsi rol başına bir dəfə), nəticə ``teacher_choices``-də 5 dəqiqə keşlənir."""
    from .schedule_teachers import instructor_role_ids

    Membership = django_apps.get_model("organizations", "Membership")
    role_ids = instructor_role_ids(organization)
    if not role_ids:
        return []
    member_ids = Membership.objects.filter(
        organization=organization,
        organization__is_active=True,
        is_active=True,
        role_id__in=role_ids,
    ).values("user_id")
    User = django_apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    rows = (
        User.objects.filter(pk__in=member_ids, is_active=True)
        .order_by("last_name", "first_name", "username", "pk")
        .values_list("pk", "first_name", "last_name", "username")
    )
    # Ad `User.get_full_name()` ilə eyni (``_person_name``): «ad soyad», boşdursa istifadəçi adı.
    return [
        {"id": str(pk), "name": f"{first_name or ''} {last_name or ''}".strip() or str(username or "")}
        for pk, first_name, last_name, username in rows
    ]


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


# ── Slotu aparan müəllim ─────────────────────────────────────────────────────


def _slot_teacher_error() -> CellError:
    message = pgettext(
        _CTX,
        "Bu müəllim bu fənnin dərsini apara bilməz — yalnız jurnal sahibi, fənnin dərs yükü bölgüsündəki "
        "və ya jurnalında dərs aparmış aktiv müəllim seçilə bilər.",
    )
    return CellError("invalid", message, errors={"slot_instructor_id": message})


def resolve_slot_instructor(*, offering, data):
    """Dialoqun «Dərsi aparan müəllim» seçimi → istifadəçi və ya ``None`` (= jurnal sahibi).

    SERVER yoxlaması (klientə etibar yoxdur): boş və ya jurnal sahibinin özü → ``None`` (NULL
    saxlanır ki, sahib dəyişəndə slot onu izləsin); başqa müəllim yalnız
    ``schedule_slot_teachers.allowed_teacher_ids`` daxilindədirsə qəbul olunur — ixtiyari müəllim
    400 (``errors.slot_instructor_id``). Redaktə olunan slotun DƏYİŞMƏYƏN müəllimi (məs. generatorun
    dərc etdiyi axın mühazirəçisi) siyahıda olmasa da saxlanır — yalnız hələ aktiv ``grade.input``
    üzvüdürsə (PostgreSQL qoruyucusu onsuz da başqasını yazmağa icazə verməzdi)."""
    raw = str(data.get("slot_instructor_id") or "").strip()
    if not raw:
        return None
    pk = schedule_slot_teachers.user_pk(raw)
    if pk is not None and str(pk) == str(offering.instructor_id or ""):
        return None
    allowed = pk is not None and pk in schedule_slot_teachers.allowed_teacher_ids(offering)
    if not allowed and not schedule_slot_teachers.is_current_override(offering, data.get("slot_id"), pk):
        raise _slot_teacher_error()
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(pk=pk).first()


def slot_teacher_options(*, organization, group, period, subject_id, instructor_id="") -> dict:
    """«Dərsi aparan müəllim» seçicisi: seçilmiş fənn + qrup + semestr açılışını APARA BİLƏNLƏR.

    Açılış hələ yoxdursa (yeni hüceyrə) yaddaşdakı nüsxə ilə hesablanır — bazaya heç nə yazılmır;
    ``owner`` — jurnal sahibi (seçicinin «Jurnal sahibi» sətri), ``teachers`` — qalan müəllimlər."""
    from django.contrib.auth import get_user_model

    from core.http_ids import parse_uuid

    subject_pk = parse_uuid(subject_id)
    if organization is None or group is None or period is None or subject_pk is None:
        return {"owner": None, "teachers": []}
    offering = (
        CourseOffering.objects.filter(organization=organization, subject_id=subject_pk, period=period, group=group)
        .select_related("instructor")
        .first()
    )
    chosen_pk = schedule_slot_teachers.user_pk(instructor_id)
    chosen = get_user_model().objects.filter(pk=chosen_pk).first() if chosen_pk is not None else None
    if offering is None:
        offering = CourseOffering(
            organization=organization, subject_id=subject_pk, period=period, group=group, instructor=chosen
        )
    elif offering.instructor_id is None and chosen is not None:
        offering.instructor = chosen  # yalnız yaddaşda — `resolve_offering` qayda 2 ilə eyni
    owner = offering.instructor
    return {
        "owner": {"id": str(owner.pk), "name": _person_name(owner)} if owner is not None else None,
        "teachers": schedule_slot_teachers.choices(offering),
    }


def plan_target(*, organization, group, period, data):
    """«Uyğun vaxtlar» (``action=plan``) üçün ``(müəllim id, fənn id, açılış id)`` — ``check`` ilə EYNİ həll.

    Fənn seçilibsə açılış yalnız-oxu tapılır (``resolve_offering(create=False)`` — bazaya heç nə yazılmır)
    və müəllim slotun EFFEKTİV müəllimidir («Dərsi aparan müəllim», yoxdursa jurnal sahibi); fənn hələ
    seçilməyibsə dialoqdakı müəllim. Yararsız seçim ``CellError`` (``check`` ilə eyni 400/409)."""
    from django.contrib.auth import get_user_model

    from core.http_ids import parse_uuid

    raw = str(data.get("instructor_id") or "").strip()
    instructor = get_user_model().objects.filter(pk=int(raw)).first() if raw.isdigit() else None
    subject_pk = parse_uuid(data.get("subject_id"))
    subject = Subject.objects.filter(organization=organization, pk=subject_pk).first() if subject_pk else None
    if subject is None:
        return getattr(instructor, "pk", None), None, None
    offering, _created, _assigned = resolve_offering(
        actor=None,
        organization=organization,
        group=group,
        period=period,
        subject=subject,
        instructor=instructor,
        create=False,
    )
    slot_teacher = resolve_slot_instructor(offering=offering, data=data)
    teacher_id = getattr(slot_teacher, "pk", None) or offering.instructor_id
    return teacher_id, subject.pk, (None if offering._state.adding else offering.pk)


# ── Yoxlama (heç nə yazmır) ──────────────────────────────────────────────────


def scope_filter(actor, organization):
    """Toqquşan slotun redaktorun ``schedule.manage`` əhatəsində olub-olmadığı (açılış üzrə keşlə).

    ``actor`` yoxdursa ``None`` — mühərrik bütün slotları əhatədə sayır (köhnə davranış)."""
    if actor is None:
        return None
    cache: dict = {}

    def visible(slot) -> bool:
        key = slot.offering_id
        if key not in cache:
            cache[key] = schedule_manage.can_manage_offering(actor, organization, slot.offering)
        return cache[key]

    return visible


def check_cell(*, organization, offering, cleaned, exclude_id=None, slot_instructor_id=None, actor=None) -> dict:
    """Saxlama-öncəsi tam yoxlama: dövr pəncərəsi + konfliktlər + tövsiyələr.

    Müəllim toqquşması slotun EFFEKTİV müəllimi ilə yoxlanır: ``slot_instructor_id`` (dialoqda
    seçilmiş «Dərsi aparan müəllim»), verilməyibsə açılışın müəllimi. Yalnız açılışın SEMESTRİNİN
    slotları sayılır və birləşmiş mühazirə (axın) toqquşma deyil — ``schedule.find_conflict`` ilə
    eyni qaydalar (bax ``schedule_conflicts`` modul başlığı).

    ``actor`` (2026-10-14) — redaktor: onun əhatəsindən KƏNAR toqquşma minimal açıqlama ilə və
    ``can_force=False`` qayıdır (başqa fakültənin dərsi parklanmır, detalı sızmır)."""
    teacher_id = slot_instructor_id or offering.instructor_id
    rules = {
        "period_id": offering.period_id,
        "subject_id": offering.subject_id,
        "kind": cleaned["kind"],
        # Yaddaşdakı (hələ yazılmamış) açılışın paralel alt qrupu ola bilməz.
        "offering_id": None if offering._state.adding else offering.pk,
    }
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
        instructor_id=teacher_id,
        exclude_ids=(exclude_id,) if exclude_id else (),
        visible=scope_filter(actor, organization),
        **rules,
    )
    suggestions = []
    if conflicts:
        suggestions = schedule_conflicts.suggest(
            organization=organization,
            group_id=offering.group_id,
            instructor_id=teacher_id,
            week_type=cleaned["week_type"],
            room=cleaned["room"],
            shift=schedule_grid.shift_of(cleaned["start_time"]),
            exclude_ids=(exclude_id,) if exclude_id else (),
            limit=6,
            **rules,
        )
    return {
        "ok": not conflicts,
        "errors": errors,
        "conflicts": conflicts,
        "suggestions": suggestions,
        # UI yalnız bunu oxuyur: «Yenə də yerləşdir» düyməsi göstərilsinmi (qrup / əhatədən kənar
        # toqquşmada YOX). Server `save`/`move`-da eyni qaydanı yenidən tətbiq edir.
        "force_allowed": bool(conflicts) and all(row.get("can_force") for row in conflicts),
    }


__all__ = [
    "CellError",
    "allowed_subjects",
    "check_cell",
    "parse_cell",
    "plan_target",
    "resolve_offering",
    "resolve_slot_instructor",
    "scope_filter",
    "slot_teacher_options",
    "teacher_choices",
]
