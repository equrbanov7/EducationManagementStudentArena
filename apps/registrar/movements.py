"""Tələbə hərəkəti — DOMEN servisi (state maşını + append-only ledger yazısı).

Yer: niyə ``apps/registrar/services/movement.py`` DEYİL?
``apps/registrar/services.py`` MODULDUR (paket deyil) — eyni adda paket
yaradılsa idxal yolu ikiləşərdi. Ona görə modul adı ``movements.py``-dır.

Bu qat İCAZƏ YOXLAMIR və BİLDİRİŞ GÖNDƏRMİR — o iş
``apps/accounts/services/people/movements.py``-dədir (aktor + scope + kapasitet
+ bildiriş). Buradaki müqavilə: «keçid qanunidirmi → tətbiq et → ledger-ə yaz».

MEXANİZM TƏKRAR YARADILMIR:

* qrup dəyişikliyi → :func:`apps.registrar.transfer.transfer_student_group`
  (iki fazalı sübut axını, ``Enrollment.superseded_by`` ilə nəsil zənciri);
* status dəyişikliyi → :mod:`apps.registrar.status` (``is_active`` ardıcıllığı
  + audit sətri).

State maşını (handoff §5/09 + §6.2):

    enrolled ──group_transfer────> enrolled        (yeni qrup MƏCBURİ)
    enrolled ──program_transfer──> enrolled        (yeni ixtisas MƏCBURİ)
    enrolled ──form_change───────> enrolled        (yeni forma MƏCBURİ, fərqli)
    enrolled ──academic_leave────> academic_leave  (müddət MƏCBURİ)
    enrolled | academic_leave ──expulsion──> expelled
    academic_leave | expelled ──reinstatement──> enrolled  (qrup MƏCBURİ)

Qanunsuz keçid SƏSSİZ keçmir — :class:`MovementError` atılır.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.registrar.models import (
    MOVEMENT_REASON_MIN_LENGTH,
    AcademicStatus,
    MovementKind,
    StudentAcademicRecord,
    StudentMovement,
)
from core.ui import status_catalog

#: Səbəbin yuxarı həddi — DB TextField-dir, amma UI/audit üçün kəsilir.
REASON_MAX_LENGTH = 2000

#: Əmr nömrəsinin yuxarı həddi (model sahəsi ilə eyni).
ORDER_NUMBER_MAX_LENGTH = 64


class MovementError(Exception):
    """İstifadəçiyə göstərilən hərəkət xətası (kod + mesaj + HTTP statusu)."""

    # Bütün arqumentlər `super().__init__()`-ə ötürülür və kwargs YOXDUR ki,
    # exception `pickle` / `copy.copy()` ilə düzgün bərpa olunsun (flake8 B042 —
    # `RimAccessError` ilə eyni naxış).
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(code, message, status)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class MovementRule:
    """Bir hərəkət növünün qaydası."""

    kind: str
    #: Hansı akademik statuslardan başlaya bilər.
    from_statuses: tuple[str, ...]
    #: Nəticə statusu (``None`` — status dəyişmir).
    to_status: str | None
    requires_group: bool = False
    requires_program: bool = False
    requires_form: bool = False
    requires_until: bool = False


RULES: dict[str, MovementRule] = {
    MovementKind.GROUP_TRANSFER: MovementRule(
        kind=MovementKind.GROUP_TRANSFER,
        from_statuses=(AcademicStatus.ENROLLED,),
        to_status=None,
        requires_group=True,
    ),
    MovementKind.PROGRAM_TRANSFER: MovementRule(
        kind=MovementKind.PROGRAM_TRANSFER,
        from_statuses=(AcademicStatus.ENROLLED,),
        to_status=None,
        requires_program=True,
    ),
    MovementKind.FORM_CHANGE: MovementRule(
        kind=MovementKind.FORM_CHANGE,
        from_statuses=(AcademicStatus.ENROLLED,),
        to_status=None,
        requires_form=True,
    ),
    MovementKind.ACADEMIC_LEAVE: MovementRule(
        kind=MovementKind.ACADEMIC_LEAVE,
        from_statuses=(AcademicStatus.ENROLLED,),
        to_status=AcademicStatus.ACADEMIC_LEAVE,
        requires_until=True,
    ),
    MovementKind.REINSTATEMENT: MovementRule(
        kind=MovementKind.REINSTATEMENT,
        from_statuses=(AcademicStatus.ACADEMIC_LEAVE, AcademicStatus.EXPELLED),
        to_status=AcademicStatus.ENROLLED,
        requires_group=True,
    ),
    MovementKind.EXPULSION: MovementRule(
        kind=MovementKind.EXPULSION,
        from_statuses=(AcademicStatus.ENROLLED, AcademicStatus.ACADEMIC_LEAVE),
        to_status=AcademicStatus.EXPELLED,
    ),
}


def rule_for(kind: str) -> MovementRule:
    try:
        return RULES[kind]
    except KeyError as exc:
        raise MovementError("unknown_kind", "Naməlum hərəkət növü.") from exc


def normalize_reason(reason) -> str:
    text = str(reason or "").strip()
    if len(text) < MOVEMENT_REASON_MIN_LENGTH:
        raise MovementError(
            "reason_too_short",
            f"Əsaslandırma ən azı {MOVEMENT_REASON_MIN_LENGTH} simvol olmalıdır.",
        )
    return text[:REASON_MAX_LENGTH]


def normalize_order_number(value) -> str:
    text = str(value or "").strip()
    if not text:
        raise MovementError("order_number_required", "Əmr nömrəsi məcburidir.")
    return text[:ORDER_NUMBER_MAX_LENGTH]


def _group_label(group) -> str:
    return str(getattr(group, "name", "") or "")


def _program_label(program) -> str:
    if program is None:
        return ""
    label = getattr(program, "display_label", None)
    return str(label or getattr(program, "name", "") or "")


def _status_label(value: str) -> str:
    """Akademik statusun etiketi — REGİSTRAR-ın öz enum-undan.

    ⚠️ ``apps.accounts...people.academic.STATUS_LABELS`` QƏSDƏN çağırılmır:
    ``registrar`` yuxarı qatı (accounts) statik import etməməlidir
    (``scripts/module_deps.py``). Etiket mətni orada daha zəngin ola bilər,
    amma ledger sətrinə yazılan mətn domen enum-undan gəlməlidir.
    """
    try:
        return str(AcademicStatus(value).label)
    except ValueError:
        return str(value)


def _apply_group(record, *, new_group, period, actor, reason):
    from apps.registrar import transfer as group_transfer

    return group_transfer.transfer_student_group(
        record=record,
        new_group=new_group,
        period=period,
        by_user=actor,
        reason=reason,
    )


def _apply_program(record, *, new_program):
    """İxtisas dəyişikliyi — kurikulum YENİ ixtisasdan bağlanır."""
    from apps.registrar.models import Curriculum

    if new_program.organization_id != record.organization_id:
        raise MovementError("program_outside_tenant", "Yeni ixtisas tələbənin təşkilatına aid deyil.", status=404)
    if new_program.pk == record.program_id:
        raise MovementError("program_unchanged", "Tələbə onsuz da bu ixtisasdadır.", status=409)
    clash = (
        StudentAcademicRecord.objects.filter(
            organization_id=record.organization_id,
            student_id=record.student_id,
            program_id=new_program.pk,
        )
        .exclude(pk=record.pk)
        .exists()
    )
    if clash:
        raise MovementError(
            "program_record_exists",
            "Bu tələbənin həmin ixtisasda artıq akademik qeydi var — köçürmə yeni qeyd yaratmır.",
            status=409,
        )
    curriculum = (
        Curriculum.objects.filter(
            organization_id=record.organization_id,
            program_id=new_program.pk,
            admission_year=record.admission_year,
        )
        .only("id")
        .first()
    )
    if curriculum is None:
        raise MovementError(
            "curriculum_missing",
            "Yeni ixtisasın bu qəbul ili üçün tədris planı yoxdur — əvvəlcə plan bağlanmalıdır.",
            status=409,
        )
    record.program = new_program
    record.curriculum = curriculum
    # ⚠️ `update_fields` MƏCBURİDİR: tam save `group_id`-ni də yoxlayır və
    # rəsmi köçürmə sübutu olmadan `ValidationError` atır (bax
    # `reference_identity.validate_reference_identity`).
    record.save(update_fields=["program", "curriculum", "updated_at"])


def _apply_form(record, *, new_form):
    if new_form == record.education_form:
        raise MovementError("form_unchanged", "Tələbə onsuz da bu təhsil formasındadır.", status=409)
    record.education_form = new_form
    record.save(update_fields=["education_form", "updated_at"])


def _apply_status(record, *, to_status, actor, reason):
    from apps.registrar import status as academic_status

    previous = record.status
    if previous == to_status:
        raise MovementError("status_unchanged", "Tələbə onsuz da bu statusdadır.", status=409)
    record.status = to_status
    record.is_active = academic_status.is_active_for(to_status)
    record.save(update_fields=["status", "is_active", "updated_at"])
    academic_status.audit_status_change(record=record, previous=previous, by_user=actor, reason=reason)
    _sync_access_state(record, to_status=to_status)
    return previous


def _sync_access_state(record, *, to_status) -> None:
    """Xaric/məzun → hesabın girişi bağlanır; bərpa → açılır (QA 2026-09-05 STUDENT-MGMT-08).

    Əvvəl yalnız akademik qeyd dəyişirdi — xaric edilmiş tələbə məhdudiyyətsiz giriş
    edib kabinetdə qrupun aktiv tələbəsi kimi görünürdü. `UserProfile.access_state`
    tərifən «ARCHIVED — məzun/xaric (giriş bağlıdır)»dır; portal qapısı onu yoxlayır.
    accounts modelinə Python-səviyyəli import yoxdur (dövr) — app registry ilə.
    """
    from django.apps import apps as django_apps

    profile_model = django_apps.get_model("accounts", "UserProfile")
    profile = profile_model.objects.filter(user_id=record.student_id).first()
    if profile is None:
        return
    states = profile_model.AccessState
    if to_status in (AcademicStatus.EXPELLED, AcademicStatus.GRADUATED):
        target = states.ARCHIVED
    elif to_status == AcademicStatus.ENROLLED and profile.access_state == states.ARCHIVED:
        target = states.ACTIVE
    else:
        return
    if profile.access_state != target:
        profile.access_state = target
        profile.save(update_fields=["access_state"])


def validate(record, *, kind, new_group=None, new_program=None, new_form=None, effective_until=None) -> MovementRule:
    """Keçidin qanuniliyini yoxlayır — HEÇ NƏ YAZMIR (ön baxış üçün də)."""
    rule = rule_for(kind)
    if record.status not in rule.from_statuses:
        raise MovementError(
            "illegal_transition",
            "«%s» əmri «%s» statusundan verilə bilməz."
            % (str(status_catalog.label("student_movement", rule.kind)), _status_label(record.status)),
            status=409,
        )
    if rule.requires_group and new_group is None:
        raise MovementError("target_group_required", "Hədəf qrup seçilməlidir.")
    if new_group is not None and record.group_id and new_group.pk == record.group_id:
        # «229K → 229K» boş hərəkəti tarixçəyə yazılırdı (QA 2026-09-05 STUDENT-MGMT-06).
        raise MovementError("same_group", "Tələbə onsuz da bu qrupdadır.", status=409)
    if rule.requires_program and new_program is None:
        raise MovementError("target_program_required", "Hədəf ixtisas seçilməlidir.")
    if rule.requires_form and not new_form:
        raise MovementError("target_form_required", "Yeni təhsil forması seçilməlidir.")
    if rule.requires_until and effective_until is None:
        # Kod aktor qatı ilə EYNİDİR (`movements.parse_date` sahə adından qurur),
        # yəni UI eyni açarı iki fərqli mesajla görmür.
        raise MovementError("effective_until_required", "Akademik məzuniyyətin bitmə tarixi məcburidir.")
    if effective_until is not None and effective_until < timezone.localdate():
        # Keçmiş bitmə tarixi tələbəni dərhal «bitmiş» məzuniyyətdə qoyurdu (STUDENT-MGMT-07).
        raise MovementError("effective_until_past", "Akademik məzuniyyətin bitmə tarixi keçmişdə ola bilməz.")
    return rule


@transaction.atomic
def create_movement(
    *,
    record,
    kind: str,
    order_number: str,
    order_date,
    reason: str,
    actor,
    period=None,
    new_group=None,
    new_program=None,
    new_form: str = "",
    effective_until=None,
    document=None,
) -> StudentMovement:
    """Hərəkəti tətbiq edir və ledger sətrini yazır (bir tranzaksiyada).

    ⚠️ Sətir ƏVVƏLCƏ deyil, SONRA yazılır: domen dəyişikliyi uğursuz olarsa
    tarixçədə «olmuş» kimi görünən əmr qalmamalıdır. İkisi eyni atomik blokdadır.
    """
    reason = normalize_reason(reason)
    order_number = normalize_order_number(order_number)
    if order_date is None:
        raise MovementError("order_date_required", "Əmrin tarixi məcburidir.")

    record = (
        StudentAcademicRecord.objects.select_for_update(of=("self",))
        .select_related("organization", "student", "program", "group", "curriculum")
        .get(pk=record.pk, organization_id=record.organization_id)
    )
    rule = validate(
        record,
        kind=kind,
        new_group=new_group,
        new_program=new_program,
        new_form=new_form,
        effective_until=effective_until,
    )

    from_group = record.group
    from_program = record.program
    from_status = record.status
    from_parts = [_group_label(from_group)]
    to_parts: list = []

    if rule.kind == MovementKind.PROGRAM_TRANSFER:
        from_parts = [_program_label(from_program)]
        _apply_program(record, new_program=new_program)
        to_parts = [_program_label(new_program)]
        if new_group is not None:
            _apply_group(record, new_group=new_group, period=period, actor=actor, reason=reason)
            to_parts.append(_group_label(new_group))
    elif rule.kind == MovementKind.FORM_CHANGE:
        from_parts = [str(record.get_education_form_display()), _group_label(from_group)]
        _apply_form(record, new_form=new_form)
        to_parts = [str(record.get_education_form_display())]
        if new_group is not None:
            _apply_group(record, new_group=new_group, period=period, actor=actor, reason=reason)
            to_parts.append(_group_label(new_group))
        else:
            to_parts.append(_group_label(from_group))
    elif rule.kind in (MovementKind.GROUP_TRANSFER, MovementKind.REINSTATEMENT):
        if rule.to_status is not None:
            _apply_status(record, to_status=rule.to_status, actor=actor, reason=reason)
            from_parts = [_status_label(from_status)]
        _apply_group(record, new_group=new_group, period=period, actor=actor, reason=reason)
        to_parts = [_group_label(new_group)]
    else:
        # Akademik məzuniyyət / xaric etmə — yalnız status dəyişir.
        from_parts = [_status_label(from_status)]
        _apply_status(record, to_status=rule.to_status, actor=actor, reason=reason)
        to_parts = [_status_label(record.status)]
        if rule.kind == MovementKind.ACADEMIC_LEAVE and effective_until is not None:
            to_parts.append(str(effective_until))

    movement = StudentMovement(
        organization=record.organization,
        record=record,
        kind=rule.kind,
        order_number=order_number,
        order_date=order_date,
        reason=reason,
        from_group=from_group,
        to_group=new_group if new_group is not None else from_group,
        from_program=from_program,
        to_program=new_program if new_program is not None else from_program,
        from_status=from_status,
        to_status=record.status,
        # Etiketlər DONDURULUR — qrup/ixtisas sonradan adını dəyişsə də əmr
        # öz mətnini saxlayır (§8/5 tarixçə səssizcə yenilənmir).
        from_label=" · ".join(part for part in from_parts if part)[:255],
        to_label=" · ".join(part for part in to_parts if part)[:255],
        effective_until=effective_until,
        actor=actor if getattr(actor, "pk", None) else None,
        actor_name=str(getattr(actor, "get_full_name", lambda: "")() or getattr(actor, "username", "") or "")[:200],
    )
    if document is not None:
        movement.document = document
    movement.full_clean(validate_unique=False, validate_constraints=False)
    movement.save()
    return movement


def movements_for(record):
    """Bir tələbənin hərəkət tarixçəsi (ən yenidən köhnəyə)."""
    return (
        StudentMovement.objects.filter(organization_id=record.organization_id, record=record)
        .select_related("from_group", "to_group", "from_program", "to_program", "actor")
        .order_by("-order_date", "-created_at")
    )


__all__ = [
    "ORDER_NUMBER_MAX_LENGTH",
    "REASON_MAX_LENGTH",
    "RULES",
    "MovementError",
    "MovementRule",
    "create_movement",
    "movements_for",
    "normalize_order_number",
    "normalize_reason",
    "rule_for",
    "validate",
]
