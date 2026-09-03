"""Tələbə idxalı — SƏTİR-SƏTİR VALİDASİYA və hədəflərin həlli (quru icra).

Bu modul HEÇ NƏ YAZMIR. O, faylın sətirlərini oxuyub hər biri üçün bir «plan»
qaytarır: yaradılacaq (``create``), ötürüləcək (``skip``) və ya xətalı
(``error``). ``apply.py`` məhz bu planları icra edir — yəni ön baxışda görünən
nəticə ilə tətbiqin nəticəsi EYNİ məntiqdən çıxır (drift olmur).

Qaydalar:

* **FİN** kimliyin açarıdır (``UserProfile.fin`` qlobal unikaldır). Faylda
  təkrarlanan FİN → xəta; bazada mövcud FİN → ötürülür (üzərinə YAZILMIR).
* **Qrup** məcburidir və aktiv təşkilatın ``group`` tipli ``OrgUnit``-i olmalıdır
  (ad və ya kod ilə). Fakültə/ixtisas verilibsə qrupun ƏCDADI olmalıdır — əks
  halda xəta (səhv sətri səssizcə başqa fakültəyə yazmırıq).
* **Proqram** qrupun ``specialty`` əcdadına bağlı ``Program``-dır; yoxdursa
  akademik qeyd yaradıla bilməz → xəta.
* **Kurikulum** (proqram + qəbul ili) tapılmasa TƏTBİQDƏ yaradılır (legacy
  köçürmənin `_bind_curriculum` naxışı) və ön baxışda xəbərdarlıq kimi görünür.
* **E-poçt** boşdursa və ya toqquşursa placeholder yazılır
  (``intake.<fin>@placeholder.invalid``) — hesab yaranır, amma e-poçt heç vaxt
  «təsdiqlənmiş» sayılmır (``email_verified=False``).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import pgettext

from core.constants import OrgUnitType
from core.validators import validate_fin

from ...identity import canonical_identity

_CTX = "student_intake"

User = get_user_model()

#: Placeholder e-poçt domeni — RFC 2606 `.invalid` (heç vaxt marşrutlanmır).
PLACEHOLDER_DOMAIN = "placeholder.invalid"
#: İstifadəçi adı prefiksi (köçürülmüş `myedu.student.<id>` ilə eyni məntiq:
#: mənbəni adından görmək olur, saf rəqəmli username yaranmır).
USERNAME_PREFIX = "st"

_GENDER_MALE = {"kişi", "kisi", "k", "m", "male", "1", "m."}
_GENDER_FEMALE = {"qadın", "qadin", "q", "f", "female", "2", "w"}

_DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y.%m.%d")


@dataclass
class RowPlan:
    """Bir fayl sətrinin planı — ön baxış cədvəlinin və tətbiqin ortaq obyekti."""

    row: int
    status: str = "create"
    code: str = ""
    message: str = ""
    fin: str = ""
    full_name: str = ""
    group_name: str = ""
    username: str = ""
    email: str = ""
    warnings: list = field(default_factory=list)
    values: dict = field(default_factory=dict)
    targets: dict = field(default_factory=dict)

    def fail(self, code: str, message: str) -> "RowPlan":
        self.status = "error"
        self.code = code
        self.message = message
        return self

    def skip(self, code: str, message: str) -> "RowPlan":
        self.status = "skip"
        self.code = code
        self.message = message
        return self

    def as_dict(self) -> dict:
        return {
            "row": self.row,
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "fin": self.fin,
            "full_name": self.full_name,
            "group": self.group_name,
            "username": self.username,
            "email": self.email,
            "warnings": list(self.warnings),
            # Ekran 08 «Qrup təyinatı» addımı üçün: hansı qrup təklif olunub,
            # seçici üçün hansı variantlar var, hansı qəbul dəyərləri oxunub.
            "group_id": str(getattr(self.targets.get("group"), "pk", "") or ""),
            "group_options": list(self.targets.get("group_options") or []),
            "program_label": str(getattr(self.targets.get("program"), "display_label", "") or ""),
            "admission_score": (
                str(self.values.get("admission_score")) if self.values.get("admission_score") is not None else ""
            ),
            "exam_type": self.values.get("admission_exam_type", ""),
            "education_form": self.values.get("education_form", ""),
            "funding_type": self.values.get("funding_type", ""),
            "atis_id": self.values.get("atis_id", ""),
            "specialty_id": str(getattr(self.targets.get("specialty"), "pk", "") or ""),
            "suggested_group_name": self.values.get("suggested_group_name", ""),
        }


def _text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _key(value: object) -> str:
    return _text(value).casefold()


def _parse_date(raw: str):
    text = _text(raw)
    if not text:
        return None, False
    if isinstance(raw, (datetime, date)):  # pragma: no cover — openpyxl str-ə çevirir
        return (raw.date() if isinstance(raw, datetime) else raw), True
    # openpyxl tarixi «2007-05-14 00:00:00» kimi verə bilir.
    text = text.split(" ")[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date(), True
        except ValueError:
            continue
    return None, False


def _parse_gender(raw: str):
    key = _key(raw)
    if not key:
        return "unspecified", True
    if key in _GENDER_MALE:
        return "male", True
    if key in _GENDER_FEMALE:
        return "female", True
    return "unspecified", False


class IntakeContext:
    """Bir faylın emalı üçün paylaşılan həll konteksti (kəşlər + toplu sorğular)."""

    def __init__(self, organization, rows):
        self.organization = organization
        self._units_by_key: dict = {}
        self._programs: dict = {}
        self._curricula: dict = {}
        self._load_units()
        self._load_programs()
        self._load_existing(rows)

    # ── kataloq ────────────────────────────────────────────────────────────
    def _load_units(self):
        from apps.organizations.models import OrgUnit

        for unit in OrgUnit.objects.filter(organization=self.organization, is_active=True).only(
            "id", "name", "code", "unit_type", "path", "parent_id"
        ):
            for raw in (unit.name, unit.code):
                key = _key(raw)
                if key:
                    self._units_by_key.setdefault((unit.unit_type, key), []).append(unit)

    def _load_programs(self):
        from apps.registrar.models import Program

        for program in Program.objects.filter(organization=self.organization, is_active=True).only(
            "id", "specialty_unit_id", "name", "degree_level"
        ):
            if program.specialty_unit_id:
                self._programs.setdefault(str(program.specialty_unit_id), []).append(program)

    def _load_existing(self, rows):
        from ...models import UserProfile

        fins = {_text(row.get("fin")).upper() for row in rows if _text(row.get("fin"))}
        codes = {_text(row.get("student_code")) for row in rows if _text(row.get("student_code"))}
        emails = {_key(row.get("email")) for row in rows if _key(row.get("email"))}

        self.existing_fins = set(
            UserProfile.objects.filter(fin__in=list(fins)).values_list("fin", flat=True) if fins else []
        )
        self.existing_codes = set(
            UserProfile.objects.filter(
                organization=self.organization, institutional_identifier__in=list(codes)
            ).values_list("institutional_identifier", flat=True)
            if codes
            else []
        )
        self.existing_emails = {
            canonical_identity(value)
            for value in (User.objects.filter(email__in=list(emails)).values_list("email", flat=True) if emails else [])
            if value
        }
        # ATİS qəbulu (ekran 08): bu FAYL daxilində qruplara təklif olunan
        # yerlərin sayğacı — 300 sətir eyni qrupa yığılmasın.
        self.group_usage: dict = {}
        # Operatorun ön baxışda seçdiyi qruplar: {sətir nömrəsi: OrgUnit}.
        self.group_overrides: dict = {}
        # İstifadəçi adları sətir-sətir yoxlanılır (namizəd ad sətirdən doğur).
        self.seen_fins: set = set()
        self.seen_emails: set = set()
        self.seen_usernames: set = set()

    # ── həll ───────────────────────────────────────────────────────────────
    def find_unit(self, raw: str, unit_type: str):
        """``(unit, code)`` — code: "" tapıldı, "missing" yoxdur, "ambiguous" çoxdur."""

        key = _key(raw)
        if not key:
            return None, "missing"
        matches = self._units_by_key.get((unit_type, key)) or []
        if not matches:
            return None, "missing"
        if len(matches) > 1:
            return None, "ambiguous"
        return matches[0], ""

    def ancestor_ids(self, unit) -> set:
        """``path`` materiallaşdırılmış yoldan əcdad id-ləri (özü daxil)."""

        parts = [part for part in str(getattr(unit, "path", "") or "").split("/") if part]
        ids = set(parts)
        ids.add(str(unit.pk))
        return ids

    def specialty_for_group(self, group):
        from apps.organizations.models import OrgUnit

        parts = [part for part in str(getattr(group, "path", "") or "").split("/") if part]
        chain = list(
            OrgUnit.objects.filter(organization=self.organization, pk__in=parts).only("id", "unit_type", "name", "path")
        )
        chain.sort(key=lambda unit: len(str(unit.path or "")), reverse=True)
        for unit in chain:
            if unit.unit_type == OrgUnitType.SPECIALTY:
                return unit
        return None

    def program_for_specialty(self, specialty):
        if specialty is None:
            return None
        programs = self._programs.get(str(specialty.pk)) or []
        return programs[0] if len(programs) == 1 else (programs[0] if programs else None)

    def curriculum_for(self, program, admission_year):
        from apps.registrar.models import Curriculum

        cache_key = (str(program.pk), int(admission_year))
        if cache_key not in self._curricula:
            self._curricula[cache_key] = (
                Curriculum.objects.filter(
                    organization=self.organization,
                    program=program,
                    admission_year=admission_year,
                )
                .only("id")
                .first()
            )
        return self._curricula[cache_key]

    def claim_username(self, base: str) -> str:
        candidate = base
        suffix = 1
        while (
            candidate in self.seen_usernames
            or User.objects.filter(username__iexact=candidate).exists()
            or User.objects.filter(email__iexact=candidate).exists()
        ):
            suffix += 1
            candidate = "%s.%d" % (base, suffix)
        self.seen_usernames.add(candidate)
        return candidate


def _validate_identity(plan: RowPlan, row: dict, context: IntakeContext) -> bool:
    fin = _text(row.get("fin")).upper()
    plan.fin = fin
    first_name = _text(row.get("first_name"))
    last_name = _text(row.get("last_name"))
    plan.full_name = " ".join(part for part in (first_name, last_name) if part)

    if not fin:
        plan.fail("fin_required", pgettext(_CTX, "FİN boşdur."))
        return False
    try:
        validate_fin(fin)
    except ValidationError:
        plan.fail("fin_invalid", pgettext(_CTX, "FİN 7 simvolluq [A-Z0-9] formatında olmalıdır."))
        return False
    if not first_name or not last_name:
        plan.fail("name_required", pgettext(_CTX, "Ad və soyad məcburidir."))
        return False
    if fin in context.seen_fins:
        plan.fail("fin_duplicate_in_file", pgettext(_CTX, "Bu FİN faylda təkrarlanır."))
        return False
    context.seen_fins.add(fin)
    if fin in context.existing_fins:
        plan.skip("fin_exists", pgettext(_CTX, "Bu FİN artıq sistemdə var — sətir ötürülür."))
        return False

    plan.values.update(
        {
            "fin": fin,
            "first_name": first_name,
            "last_name": last_name,
            "patronymic": _text(row.get("patronymic")),
            "phone": _text(row.get("phone"))[:20],
        }
    )
    return True


def _validate_structure(plan: RowPlan, row: dict, context: IntakeContext) -> bool:
    group_raw = _text(row.get("group"))
    plan.group_name = group_raw

    override = context.group_overrides.get(plan.row)
    if override is not None:
        # Operator ön baxışda qrupu ƏL İLƏ seçib — avtomatik təklif ləğv olunur.
        return _bind_override(plan, override, context)

    if not group_raw and _text(row.get("program_code")):
        # ATİS yolu: qrup faylda YOXDUR, ixtisas kodu var → hədəf ixtisasdan
        # həll olunur və qrup avtomatik TƏKLİF edilir (bax `admission.py`).
        from . import admission

        return admission.resolve_atis_targets(plan, row, context)

    group, code = context.find_unit(group_raw, OrgUnitType.GROUP)
    if code == "missing":
        plan.fail(
            "group_unknown",
            pgettext(_CTX, "Qrup tapılmadı: %s") % (group_raw or pgettext(_CTX, "(boş)")),
        )
        return False
    if code == "ambiguous":
        plan.fail("group_ambiguous", pgettext(_CTX, "Bu adla birdən çox qrup var — kodla göstərin: %s") % group_raw)
        return False

    ancestors = context.ancestor_ids(group)
    for raw_key, unit_type, error_code, label in (
        ("faculty", OrgUnitType.FACULTY, "faculty_unknown", pgettext(_CTX, "Fakültə")),
        ("speciality", OrgUnitType.SPECIALTY, "speciality_unknown", pgettext(_CTX, "İxtisas")),
    ):
        raw = _text(row.get(raw_key))
        if not raw:
            continue
        unit, unit_code = context.find_unit(raw, unit_type)
        if unit_code:
            plan.fail(error_code, pgettext(_CTX, "%(label)s tapılmadı: %(value)s") % {"label": label, "value": raw})
            return False
        if str(unit.pk) not in ancestors:
            plan.fail(
                error_code,
                pgettext(_CTX, "%(label)s qrupun strukturuna uyğun gəlmir: %(value)s") % {"label": label, "value": raw},
            )
            return False

    specialty = context.specialty_for_group(group)
    program = context.program_for_specialty(specialty)
    if program is None:
        plan.fail(
            "program_missing",
            pgettext(_CTX, "Bu qrupun ixtisas proqramı (Program) tapılmadı — əvvəlcə struktur qurulmalıdır."),
        )
        return False

    degree_raw = _key(row.get("degree_level"))
    if (
        degree_raw
        and degree_raw not in _key(program.degree_level)
        and not _key(program.degree_level).startswith(degree_raw[:3])
    ):
        plan.warnings.append(
            pgettext(_CTX, "Təhsil səviyyəsi proqramla üst-üstə düşmür — proqramın səviyyəsi tətbiq olunur.")
        )

    plan.targets.update({"group": group, "program": program})
    return True


def _bind_override(plan: RowPlan, group, context: IntakeContext) -> bool:
    """Operatorun seçdiyi qrupu plana bağlayır (ixtisas qrupdan çıxarılır)."""
    specialty = context.specialty_for_group(group)
    program = context.program_for_specialty(specialty)
    if program is None:
        plan.fail(
            "program_missing",
            pgettext(_CTX, "Bu qrupun ixtisas proqramı (Program) tapılmadı — əvvəlcə struktur qurulmalıdır."),
        )
        return False
    plan.targets.update({"group": group, "program": program})
    plan.group_name = group.name
    return True


def _validate_academic(plan: RowPlan, row: dict, context: IntakeContext) -> bool:
    raw_year = _text(row.get("admission_year"))
    # Excel «2025» dəyərini «2025.0» kimi verə bilir.
    if raw_year.endswith(".0"):
        raw_year = raw_year[:-2]
    try:
        admission_year = int(raw_year)
    except (TypeError, ValueError):
        plan.fail("admission_year_invalid", pgettext(_CTX, "Qəbul ili rəqəm olmalıdır."))
        return False
    current_year = date.today().year
    if not (1950 <= admission_year <= current_year + 1):
        plan.fail(
            "admission_year_out_of_range",
            pgettext(_CTX, "Qəbul ili 1950–%d aralığında olmalıdır.") % (current_year + 1),
        )
        return False

    birth_date, ok = _parse_date(row.get("birth_date"))
    if not ok:
        plan.fail("birth_date_invalid", pgettext(_CTX, "Doğum tarixi tanınmadı (gg.aa.iiii formatını işlədin)."))
        return False
    if birth_date is not None and not (date(1900, 1, 1) <= birth_date <= date.today()):
        plan.fail("birth_date_out_of_range", pgettext(_CTX, "Doğum tarixi məntiqsizdir."))
        return False

    gender, known = _parse_gender(row.get("gender"))
    if not known:
        plan.warnings.append(pgettext(_CTX, "Cins tanınmadı — «təyin edilməyib» qalır."))

    program = plan.targets["program"]
    curriculum = context.curriculum_for(program, admission_year)
    if curriculum is None:
        plan.warnings.append(pgettext(_CTX, "Bu qəbul ili üçün kurikulum yoxdur — tətbiqdə boş kurikulum yaradılacaq."))

    plan.values.update(
        {
            "admission_year": admission_year,
            "birth_date": birth_date,
            "gender": gender,
            "language_sector": _text(row.get("language_sector")),
        }
    )
    plan.targets["curriculum"] = curriculum
    plan.targets["admission_year"] = admission_year
    return True


def _validate_credentials(plan: RowPlan, row: dict, context: IntakeContext) -> bool:
    code = _text(row.get("student_code"))
    if code and code in context.existing_codes:
        plan.skip("student_code_exists", pgettext(_CTX, "Bu tələbə kodu artıq istifadə olunub — sətir ötürülür."))
        return False
    if code:
        context.existing_codes.add(code)

    base = (
        "%s.%s" % (USERNAME_PREFIX, _key(code).replace(" ", ""))
        if code
        else "%s.fin.%s"
        % (
            USERNAME_PREFIX,
            plan.fin.lower(),
        )
    )
    base = "".join(ch for ch in base if ch.isalnum() or ch in "._-")[:140] or "%s.fin.%s" % (
        USERNAME_PREFIX,
        plan.fin.lower(),
    )
    plan.username = context.claim_username(base)

    email = _text(row.get("email"))
    placeholder = "intake.%s@%s" % (plan.fin.lower(), PLACEHOLDER_DOMAIN)
    if not email:
        plan.email = placeholder
        plan.warnings.append(pgettext(_CTX, "E-poçt yoxdur — placeholder yazılır (ilk girişdə istifadəçi özü yazır)."))
    else:
        try:
            validate_email(email)
        except ValidationError:
            plan.fail("email_invalid", pgettext(_CTX, "E-poçt formatı yanlışdır."))
            return False
        key = canonical_identity(email)
        if key in context.existing_emails or key in context.seen_emails:
            plan.email = placeholder
            plan.warnings.append(pgettext(_CTX, "E-poçt artıq istifadə olunur — placeholder yazılır."))
        else:
            context.seen_emails.add(key)
            plan.email = email
    plan.values["student_code"] = code
    plan.values["email"] = plan.email
    plan.values["username"] = plan.username
    return True


def build_plans(organization, rows, *, group_overrides=None) -> list:
    """Fayl sətirlərini plan siyahısına çevirir — HEÇ NƏ YAZMIR.

    ``group_overrides`` — ``{sətir nömrəsi: qrup id}``: ekran 08-in «Qrup
    təyinatı» addımında operatorun ƏL İLƏ seçdiyi qruplar. Ön baxış və tətbiq
    EYNİ sözlüyü alır, ona görə «gördüyün nəticə = alacağın nəticə» pozulmur.
    """

    context = IntakeContext(organization, rows)
    if group_overrides:
        context.group_overrides = _resolve_overrides(organization, group_overrides)
    plans: list = []
    for row in rows:
        plan = RowPlan(row=int(row.get("_row") or 0))
        if (
            _validate_identity(plan, row, context)
            and _validate_structure(plan, row, context)
            and _validate_academic(plan, row, context)
            and _validate_credentials(plan, row, context)
        ):
            plan.code = "will_create"
            plan.message = pgettext(_CTX, "Yaradılacaq.")
        if plan.status != "error":
            # ATİS sahələri (bal, imtahan növü, forma, maliyyələşmə) — bloklamır.
            from . import admission

            admission.enrich(plan, row, context)
        plans.append(plan)
    return plans


def _resolve_overrides(organization, raw: dict) -> dict:
    """``{sətir: id}`` → ``{sətir: OrgUnit}``; yad tenantın qrupu ATILIR."""
    from apps.organizations.models import OrgUnit

    wanted = {}
    for key, value in (raw or {}).items():
        try:
            wanted[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    if not wanted:
        return {}
    units = {
        str(unit.pk): unit
        for unit in OrgUnit.objects.filter(
            organization=organization,
            unit_type=OrgUnitType.GROUP,
            is_active=True,
            pk__in=list(set(wanted.values())),
        )
    }
    return {row: units[value] for row, value in wanted.items() if value in units}


def summarize(plans) -> dict:
    return {
        "total": len(plans),
        "create": sum(1 for plan in plans if plan.status == "create"),
        "skip": sum(1 for plan in plans if plan.status == "skip"),
        "error": sum(1 for plan in plans if plan.status == "error"),
    }


__all__ = [
    "PLACEHOLDER_DOMAIN",
    "USERNAME_PREFIX",
    "IntakeContext",
    "RowPlan",
    "build_plans",
    "summarize",
]
