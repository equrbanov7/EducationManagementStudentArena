"""RİM «yeni hesab» — SAHƏ-SAHƏ VALİDASİYA (QURU İCRA, heç nə yazmır).

Bu modul toplu idxalın ``validate.py``-sinin TƏK SƏTİRLİK qardaşıdır və qəsdən
onun maşınını işlədir: ``IntakeContext`` qurulur, sonra FİN/kod/e-poçt
toqquşmaları, qrup → ixtisas → proqram → kurikulum zənciri və istifadəçi adının
iddiası MƏHZ toplu axının funksiyaları ilə həll olunur. Səbəb sadədir — «faylda
keçən sətir formada keçmirdi» (və ya əksi) sinfindən drift yaranmasın.

TOPLU AXINDAN QƏSDƏN FƏRQLƏNƏN İKİ NÖQTƏ

* **Mövcud FİN / tələbə kodu**: fayl axınında sətir SƏSSİZCƏ ötürülür
  (``skip``) — 500 sətirlik siyahıda bu düzgün davranışdır. Tək-tək formda
  ötürmək operatoru aldadardı («yaratdım?»), ona görə burada SAHƏ XƏTASIDIR.
* **Xətaların yığılması**: fayl axını ilk xətada sətri dayandırır; form isə
  BÜTÜN sahə xətalarını toplayır ki, operator hamısını bir dəfəyə düzəltsin.

E-poçt toqquşması hər iki axında EYNİDİR: placeholder yazılır + xəbərdarlıq
(hesab yaranır, e-poçt heç vaxt «təsdiqlənmiş» sayılmır).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import pgettext

from core.constants import OrgUnitType
from core.validators import validate_fin

from ...identity import canonical_identity
from ..intake import create as intake_create
from ..intake.validate import (
    MAX_NAME_LENGTH,
    PLACEHOLDER_DOMAIN,
    IntakeContext,
    normalize_text,
    parse_birth_date,
    parse_gender,
)

_CTX = "profile.rim"

#: Formun qəbul etdiyi sahələr (allow-list — naməlum açar atılır).
COMMON_FIELDS = (
    "fin",
    "first_name",
    "last_name",
    "patronymic",
    "birth_date",
    "gender",
    "email",
    "phone",
    "code",
)
STUDENT_FIELDS = ("group", "admission_year")
TEACHER_FIELDS = ("unit",)

#: Müəllim üzvlüyünün scope bölməsi kimi qəbul edilən tiplər.
CHAIR_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)

_PHONE_MAX = 20


@dataclass
class AccountDraft:
    """Bir hesab üçün həll olunmuş plan — ``create_account`` arqumentləri."""

    kind: str
    values: dict = field(default_factory=dict)
    targets: dict = field(default_factory=dict)
    group_name: str = ""
    specialization: str = ""
    scope_unit: object = None
    warnings: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _fail(draft: AccountDraft, name: str, message: str) -> None:
    # İlk mesaj qalır: eyni sahə üçün ikinci yoxlama daha ümumi mətn verə bilər.
    draft.errors.setdefault(name, message)


def _as_row(data: dict) -> dict:
    """Form sahələrini toplu idxalın SƏTİR lüğətinə çevirir (kontekst üçün)."""

    return {
        "fin": normalize_text(data.get("fin")).upper(),
        "student_code": normalize_text(data.get("code")),
        "email": normalize_text(data.get("email")),
    }


def _validate_identity(draft: AccountDraft, data: dict, context: IntakeContext) -> None:
    fin = normalize_text(data.get("fin")).upper()
    first_name = normalize_text(data.get("first_name"))
    last_name = normalize_text(data.get("last_name"))
    patronymic = normalize_text(data.get("patronymic"))

    if not fin:
        _fail(draft, "fin", pgettext(_CTX, "FİN boşdur."))
    else:
        try:
            validate_fin(fin)
        except ValidationError:
            _fail(draft, "fin", pgettext(_CTX, "FİN 7 simvolluq [A-Z0-9] formatında olmalıdır."))
        else:
            if fin in context.existing_fins:
                _fail(draft, "fin", pgettext(_CTX, "Bu FİN artıq sistemdə var — hesab yaradılmadı."))

    if not first_name:
        _fail(draft, "first_name", pgettext(_CTX, "Ad məcburidir."))
    if not last_name:
        _fail(draft, "last_name", pgettext(_CTX, "Soyad məcburidir."))
    for name, value in (("first_name", first_name), ("last_name", last_name), ("patronymic", patronymic)):
        if len(value) > MAX_NAME_LENGTH:
            _fail(
                draft,
                name,
                pgettext(_CTX, "Ən çox %(n)s simvol ola bilər.") % {"n": MAX_NAME_LENGTH},
            )

    draft.values.update(
        {
            "fin": fin,
            "first_name": first_name,
            "last_name": last_name,
            "patronymic": patronymic,
            "phone": normalize_text(data.get("phone"))[:_PHONE_MAX],
        }
    )


def _validate_person(draft: AccountDraft, data: dict) -> None:
    # DOĞUM TARİXİ MƏCBURİDİR — toplu idxalla eyni qayda. `spec.py` sütunu
    # «məcburi» işarələmir, LAKİN `validate._validate_academic` boş tarixi
    # `birth_date_invalid` kimi rədd edir. Formda onu opsional saysaydıq iki
    # səth arasında məhz qaçındığımız drift yaranardı; ona görə burada da
    # məcburidir və şablonda `*` ilə işarələnib. Boş dəyər üçün mesaj
    # AYRIDIR — «format tanınmadı» boş sahə üçün yanıltıcıdır.
    raw = normalize_text(data.get("birth_date"))
    birth_date, ok = parse_birth_date(raw)
    if not raw:
        _fail(draft, "birth_date", pgettext(_CTX, "Doğum tarixi məcburidir."))
    elif not ok:
        _fail(draft, "birth_date", pgettext(_CTX, "Doğum tarixi tanınmadı (gg.aa.iiii formatını işlədin)."))
    elif birth_date is not None and not (date(1900, 1, 1) <= birth_date <= date.today()):
        _fail(draft, "birth_date", pgettext(_CTX, "Doğum tarixi məntiqsizdir."))

    gender, known = parse_gender(data.get("gender"))
    if not known:
        draft.warnings.append(pgettext(_CTX, "Cins tanınmadı — «təyin edilməyib» qalır."))

    draft.values.update({"birth_date": birth_date, "gender": gender})


def _resolve_unit(organization, raw, unit_types):
    from apps.organizations.models import OrgUnit

    value = normalize_text(raw)
    if not value:
        return None
    try:
        return OrgUnit.objects.filter(
            organization=organization,
            pk=value,
            unit_type__in=unit_types,
            is_active=True,
        ).first()
    except (ValidationError, ValueError, TypeError):
        # Qeyri-UUID dəyər `filter(pk=...)`-də ValidationError verir (bax
        # STUDENT-MGMT-01) — sahə xətası kimi göstərilir, 500 deyil.
        return None


def _validate_student_structure(draft: AccountDraft, data: dict, context: IntakeContext) -> None:
    organization = context.organization
    group = _resolve_unit(organization, data.get("group"), (OrgUnitType.GROUP,))
    if group is None:
        _fail(draft, "group", pgettext(_CTX, "Qrup seçilməyib və ya tapılmadı."))
    admission_year = _validate_admission_year(draft, data)

    if group is None or admission_year is None:
        return

    # Qrup → ixtisas → proqram zənciri TOPLU AXININ funksiyaları ilə həll olunur.
    specialty = context.specialty_for_group(group)
    program = context.program_for_specialty(specialty)
    if program is None:
        _fail(
            draft,
            "group",
            pgettext(_CTX, "Bu qrupun ixtisas proqramı (Program) tapılmadı — əvvəlcə struktur qurulmalıdır."),
        )
        return

    curriculum = context.curriculum_for(program, admission_year)
    if curriculum is None:
        draft.warnings.append(
            pgettext(_CTX, "Bu qəbul ili üçün kurikulum yoxdur — hesab yaradılarkən boş kurikulum yaradılacaq.")
        )

    draft.group_name = group.name
    draft.specialization = getattr(program, "name", "") or ""
    draft.targets.update(
        {
            "group": group,
            "program": program,
            "curriculum": curriculum,
            "admission_year": admission_year,
        }
    )
    draft.values.update({"admission_year": admission_year})


def _validate_admission_year(draft: AccountDraft, data: dict):
    raw = normalize_text(data.get("admission_year"))
    if raw.endswith(".0"):
        raw = raw[:-2]
    try:
        year = int(raw)
    except (TypeError, ValueError):
        _fail(draft, "admission_year", pgettext(_CTX, "Qəbul ili rəqəm olmalıdır."))
        return None
    current_year = date.today().year
    if not (1950 <= year <= current_year + 1):
        _fail(
            draft,
            "admission_year",
            pgettext(_CTX, "Qəbul ili 1950–%d aralığında olmalıdır.") % (current_year + 1),
        )
        return None
    return year


def _validate_teacher_structure(draft: AccountDraft, data: dict, context: IntakeContext) -> None:
    raw = normalize_text(data.get("unit"))
    if not raw:
        # Kafedra OPSİONALDIR: org-səviyyə müəllim (kafedrası sonradan təyin
        # olunan) qanuni haldır — `people.set_teacher_role` ilə eyni qayda.
        return
    unit = _resolve_unit(context.organization, raw, CHAIR_UNIT_TYPES)
    if unit is None:
        _fail(draft, "unit", pgettext(_CTX, "Kafedra tapılmadı."))
        return
    draft.scope_unit = unit
    draft.specialization = ""


def _validate_credentials(draft: AccountDraft, data: dict, context: IntakeContext) -> None:
    code = normalize_text(data.get("code"))
    if code and code in context.existing_codes:
        _fail(draft, "code", pgettext(_CTX, "Bu kod artıq istifadə olunub."))

    fin = draft.values.get("fin", "")
    if fin:
        draft.values["username"] = intake_create.claim_username(
            intake_create.username_base(draft.kind, code=code, fin=fin)
        )

    email = normalize_text(data.get("email"))
    placeholder = "intake.%s@%s" % (fin.lower(), PLACEHOLDER_DOMAIN)
    if not email:
        draft.values["email"] = placeholder
        draft.warnings.append(pgettext(_CTX, "E-poçt yoxdur — placeholder yazılır (ilk girişdə istifadəçi özü yazır)."))
    else:
        try:
            validate_email(email)
        except ValidationError:
            _fail(draft, "email", pgettext(_CTX, "E-poçt formatı yanlışdır."))
            draft.values["email"] = placeholder
        else:
            if canonical_identity(email) in context.existing_emails:
                draft.values["email"] = placeholder
                draft.warnings.append(pgettext(_CTX, "E-poçt artıq istifadə olunur — placeholder yazılır."))
            else:
                draft.values["email"] = email

    draft.values["student_code"] = code


def build_draft(organization, kind: str, data: dict) -> AccountDraft:
    """Form sahələrindən ``AccountDraft`` qurur — HEÇ NƏ YAZMIR."""

    draft = AccountDraft(kind=kind)
    if kind not in intake_create.ACCOUNT_KINDS:
        _fail(draft, "kind", pgettext(_CTX, "Naməlum hesab növü."))
        return draft

    context = IntakeContext(organization, [_as_row(data)])
    _validate_identity(draft, data, context)
    _validate_person(draft, data)
    if kind == intake_create.KIND_STUDENT:
        _validate_student_structure(draft, data, context)
    else:
        _validate_teacher_structure(draft, data, context)
    _validate_credentials(draft, data, context)
    return draft


__all__ = [
    "CHAIR_UNIT_TYPES",
    "COMMON_FIELDS",
    "STUDENT_FIELDS",
    "TEACHER_FIELDS",
    "AccountDraft",
    "build_draft",
]
