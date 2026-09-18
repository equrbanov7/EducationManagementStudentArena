"""ATİS qəbulu — ixtisas kodundan hədəf həlli, qəbul sahələri, qrup təklifi.

NİYƏ AYRI MODUL? ``validate.py`` 490/600 sətirdir (SOFT_CAP=600). Burada
ekran 08-in ƏLAVƏ qatı var; mövcud 16 sütunlu idxal müqaviləsi TOXUNULMUR.

İKİ HƏDƏF YOLU (biri digərini əvəz etmir):

1. **Qrup verilib** — köhnə yol: qrup adı/kodu ilə tapılır, ixtisas qrupun
   ``specialty`` əcdadından çıxarılır (``validate._validate_structure``).
2. **Qrup verilməyib, ixtisas kodu verilib** — ATİS yolu: ``Program`` rəsmi
   şifrlə (NK 503 kataloqu, köhnə nəsil şifr də qəbul olunur) tapılır, sonra
   ixtisasın altındakı qruplardan biri AVTOMATİK təklif olunur (dil sektoru +
   boş yer). Operator təklifi ön baxış cədvəlində DƏYİŞƏ bilər; heç bir qrup
   uyğun gəlmirsə sətir «qrup təyin edilməyib» kimi qalır və `student.assign_group`
   icazəsi ilə YENİ qrup yaradıla bilər.

⚠️ AVTOMATİK TƏKLİF SƏSSİZ TƏTBİQ OLUNMUR: ön baxış (`dry-run`) sətirdə hansı
qrupun təklif edildiyini AÇIQ göstərir və tətbiq eyni plan qurucusundan keçir
(«gördüyün nəticə = alacağın nəticə» — ``PHASE1_STUDENT_INTAKE.md`` §3).
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation

from django.utils.translation import pgettext

_CTX = "student_intake"

#: «Dövlət sifarişi» sinonimləri (ATİS ixracında sərbəst mətndir).
_STATE_WORDS = {"dovletsifarisi", "dovlet", "budce", "budcə", "state", "dsi", "pulsuz"}
#: «Ödənişli» sinonimləri.
_PAID_WORDS = {"odenisli", "odenis", "paid", "pullu", "ozunumaliyyelesdirme"}

#: Təhsil formasının sinonimləri → ``registrar.EducationForm`` açarları.
_FORM_ALIASES = {
    "eyani": "full_time",
    "əyani": "full_time",
    "fulltime": "full_time",
    "gunduz": "full_time",
    "qiyabi": "part_time",
    "parttime": "part_time",
    "distant": "distance",
    "distance": "distance",
    "onlayn": "distance",
}


def _text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


#: AZ hərflərinin ASCII qarşılığı — ATİS ixracında eyni söz həm «dövlət
#: sifarişi», həm «Dovlet sifarisi» kimi gələ bilir. Müqayisə açarı hər iki
#: yazılışı eyni sətrə yığır (SAXLANILAN dəyər dəyişmir).
_AZ_FOLD = str.maketrans(
    {
        "ə": "e",
        "ö": "o",
        "ü": "u",
        "ğ": "g",
        "ı": "i",
        "ç": "c",
        "ş": "s",
        "İ": "i",
    }
)


def _key(value: object) -> str:
    folded = _text(value).casefold().translate(_AZ_FOLD)
    return "".join(ch for ch in folded if ch.isalnum())


def parse_score(raw):
    """Qəbul balı — «543,5» / «543.5» / boş. ``(dəyər, tanındı)``."""
    text = _text(raw).replace(",", ".")
    if not text:
        return None, True
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, False
    if not (Decimal("0") <= value <= Decimal("1000")):
        return None, False
    return value, True


def parse_form(raw) -> str:
    """Təhsil forması → enum açarı; tanınmasa boş sətir (default tətbiq olunur)."""
    return _FORM_ALIASES.get(_key(raw), "")


def parse_funding(raw) -> str:
    """Maliyyələşmə → ``state`` / ``paid``; tanınmasa boş sətir.

    ATİS ixracı sərbəst mətn verir («Ödənişli: Öz vəsaiti hesabına») — prefiks
    müqayisəsi ilə tanınır.
    """
    key = _key(raw)
    if not key:
        return ""
    if key in _STATE_WORDS or key.startswith("dovletsifarisi"):
        return "state"
    if key in _PAID_WORDS or key.startswith("odenisli"):
        return "paid"
    return ""


def parse_form_atis(raw) -> str:
    """«Əyani (FULLTIME)» kimi qarışıq yazılış — ilk sözə görə."""
    form = parse_form(raw)
    if form:
        return form
    head = _key(raw)
    for alias, value in _FORM_ALIASES.items():
        if head.startswith(alias):
            return value
    return ""


def parse_admission_status(raw) -> str:
    key = _key(raw)
    if not key:
        return ""
    if key.startswith("mohletle"):
        return "deferred"
    if key.startswith("guzestli"):
        return "privileged"
    if key.startswith("sosialttk"):
        return "social_ttk"
    if key.startswith("standartttk"):
        return "standard_ttk"
    if key.startswith("qebuledildi") or key in {"admitted", "qebul"}:
        return "admitted"
    return ""


def parse_admission_channel(raw) -> str:
    key = _key(raw)
    if not key:
        return ""
    if key.startswith("dim"):
        return "dim"
    if "imtahansiz" in key or key.startswith("imtahandaistiraketmeden"):
        return "exam_free"
    return ""


def parse_tour(raw) -> str:
    key = _key(raw)
    if key in {"firsttour", "1", "i", "itur", "birinci", "first"}:
        return "first"
    if key in {"secondtour", "2", "ii", "iitur", "ikinci", "second"}:
        return "second"
    return ""


def parse_language(raw) -> str:
    """Tədris dili → ``az/en/ru/de`` (`student_groups.normalize_sector` sinonimləri)."""
    from ..student_groups import normalize_sector

    value = normalize_sector(raw)
    return value if value in {"az", "en", "ru", "de"} else ""


def parse_money(raw):
    text = _text(raw).replace(",", ".").replace(" ", "")
    if not text:
        return None, True
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, False
    return (value, True) if Decimal("0") <= value <= Decimal("1000000") else (None, False)


def parse_datetime(raw):
    """«2026-09-08 17:11:20» / «2026-09-08 16:28:42.663000» / «08.09.2026» → aware datetime."""
    from datetime import datetime

    from django.utils import timezone

    if isinstance(raw, datetime):
        return raw if timezone.is_aware(raw) else timezone.make_aware(raw)
    text = _text(raw)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return timezone.make_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def program_by_code(organization, code: str):
    """Rəsmi şifrlə ``Program`` — cari (NK 503) və ya ƏVVƏLKİ nəsil şifr.

    ``core.program_codes.program_code_search_q`` TƏKRAR YAZILMIR: eyni Q
    qurucusu ixtisas reyestrində və axtarışda da işlənir.
    """
    from apps.registrar.models import Program
    from core.program_codes import program_code_search_q

    text = _text(code)
    if not text:
        return None, "missing"
    matches = list(
        Program.objects.filter(organization=organization, is_active=True).filter(program_code_search_q(text))[:2]
    )
    if not matches:
        return None, "missing"
    if len(matches) > 1:
        return None, "ambiguous"
    return matches[0], ""


def disambiguate_program(organization, code: str, *, name: str = "", sector: str = "", specialization: str = ""):
    """Eyni rəsmi şifrli bir neçə proqram (məs. «Tarix» / «Tarix (Tədris İngilis Dilində)»,
    «Dizayn (Qrafik)» / «Dizayn (İnteryer)») — ATİS sətrindəki ixtisas adı, tədris
    dili və ixtisaslaşma ilə seçilir. Seçilə bilməsə ``None`` (operator dəqiqləşdirir).
    """
    from apps.registrar.models import Program
    from core.program_codes import program_code_search_q

    text = _text(code)
    if not text:
        return None
    candidates = list(
        Program.objects.filter(organization=organization, is_active=True).filter(program_code_search_q(text))
    )
    if len(candidates) < 2:
        return candidates[0] if candidates else None
    lang = parse_language(sector)
    english = [p for p in candidates if "ingilis" in _key(p.name) or "english" in _key(p.name)]
    if lang == "en" and len(english) == 1:
        return english[0]
    non_english = [p for p in candidates if p not in english]
    if lang and lang != "en" and len(non_english) == 1:
        return non_english[0]
    spec_key = _key(specialization)
    if spec_key:
        by_spec = [p for p in candidates if spec_key in _key(p.name) or _key(p.name) in spec_key]
        if len(by_spec) == 1:
            return by_spec[0]
    name_key = _key(name)
    if name_key:
        exact = [p for p in candidates if _key(p.name) == name_key]
        if len(exact) == 1:
            return exact[0]
    return None


def specialty_unit_of(program):
    return getattr(program, "specialty_unit", None)


def propose_group_for(organization, program, *, sector: str, taken: dict, admission_year=None):
    """Sətir üçün qrup təklifi.

    ``taken`` — BU FAYLDA artıq təyin edilmiş qrupların sayğacı: eyni qrupa
    tutumundan artıq sətir təklif edilməsin (fayl 300 sətirdirsə, hamısı bir
    qrupa yığılmamalıdır).
    """
    from ..student_groups import group_options, propose_group

    specialty = specialty_unit_of(program)
    if specialty is None:
        return None, []
    rows = group_options(
        organization, specialty, sector=parse_language(sector) or sector, admission_year=admission_year
    )
    for row in rows:
        extra = taken.get(row["id"], 0)
        row["taken"] += extra
        row["free"] = max(row["capacity"] - row["taken"], 0)
        row["is_full"] = row["taken"] >= row["capacity"]
    return propose_group(rows), rows


def enrich(plan, row: dict, context) -> None:
    """Sətrin ATİS sahələrini plana yazır (xəta yaratmır — yalnız xəbərdarlıq).

    Bloklayan xəta YALNIZ struktur həllində olur (``resolve_targets``);
    burada dəyər tanınmasa default tətbiq edilir və operator xəbərdar olunur.
    """
    plan.values["atis_id"] = _text(row.get("atis_id"))[:64]
    plan.values["admission_exam_type"] = _text(row.get("exam_type"))[:64]

    score, ok = parse_score(row.get("admission_score"))
    plan.values["admission_score"] = score
    if not ok:
        plan.warnings.append(pgettext(_CTX, "Qəbul balı tanınmadı — boş saxlanılır."))

    form = parse_form(row.get("education_form"))
    if row.get("education_form") and not form:
        plan.warnings.append(pgettext(_CTX, "Təhsil forması tanınmadı — «əyani» tətbiq olunur."))
    plan.values["education_form"] = form or "full_time"

    funding = parse_funding(row.get("funding"))
    if row.get("funding") and not funding:
        plan.warnings.append(pgettext(_CTX, "Təhsil haqqı sütunu tanınmadı — «ödənişli» tətbiq olunur."))
    plan.values["funding_type"] = funding or "paid"
    if not form and row.get("education_form"):
        plan.values["education_form"] = parse_form_atis(row.get("education_form")) or "full_time"

    # ATİS «Bakalavr» ixracının qalan sütunları (sahibin qərarı 2026-09-19).
    plan.values["admission_status"] = parse_admission_status(row.get("admission_status")) or "admitted"
    if (
        row.get("admission_status")
        and plan.values["admission_status"] == "admitted"
        and not parse_admission_status(row.get("admission_status"))
    ):
        plan.warnings.append(pgettext(_CTX, "Qəbul statusu tanınmadı — «qəbul edildi» tətbiq olunur."))
    plan.values["admission_channel"] = parse_admission_channel(row.get("admission_channel"))
    plan.values["admission_tour"] = parse_tour(row.get("tour"))
    plan.values["instruction_language"] = parse_language(row.get("language_sector"))
    fee, ok = parse_money(row.get("tuition_fee"))
    plan.values["tuition_fee"] = fee
    if not ok:
        plan.warnings.append(pgettext(_CTX, "Təhsil haqqı məbləği tanınmadı — boş saxlanılır."))
    plan.values["applied_at"] = parse_datetime(row.get("applied_at"))
    plan.values["admitted_at"] = next(
        (
            parsed
            for key in ("admitted_at", "admitted_at_2", "admitted_at_3", "admitted_at_4", "admitted_at_5")
            for parsed in [parse_datetime(row.get(key))]
            if parsed is not None
        ),
        None,
    )
    plan.values["admission_note"] = _text(row.get("note"))[:2000]
    plan.values["specialization"] = _text(row.get("specialization"))[:255]
    plan.values["citizenship"] = _text(row.get("citizenship"))[:64]
    plan.values["id_series"] = _text(row.get("id_series"))[:8]
    plan.values["id_number"] = _text(row.get("id_number"))[:32]
    plan.values["address"] = _text(row.get("address"))[:255] or plan.values.get("address", "")
    extra = {
        key: _text(row.get(key))
        for key in (
            "atis_program_id",
            "work_number",
            "global_id",
            "education_base",
            "ielts",
            "foreign_language_exam",
            "education_kind",
            "extra_education_kind",
            "preparation",
            "semester",
            "institution_atis_id",
            "specialty_atis_id",
        )
        if _text(row.get(key))
    }
    plan.values["admission_extra"] = extra


def resolve_atis_targets(plan, row: dict, context) -> bool:
    """QRUP VERİLMƏYƏNDƏ hədəfi ixtisas kodundan həll edir.

    ``True`` — həll olundu (plan ``targets``-i doldu, qrup ``None`` ola bilər);
    ``False`` — bloklayan xəta yazıldı.
    """
    program, code = program_by_code(context.organization, row.get("program_code"))
    if code == "missing":
        # Dizayn 08-in HƏRFİ mesajı (status kataloqu: `unknown_program`).
        plan.fail("unknown_program", pgettext(_CTX, "İxtisas kodu universitetdə tapılmadı"))
        return False
    if code == "ambiguous":
        program = disambiguate_program(
            context.organization,
            row.get("program_code"),
            name=_text(row.get("speciality")),
            sector=_text(row.get("language_sector")),
            specialization=_text(row.get("specialization")),
        )
        if program is None:
            plan.fail(
                "program_code_ambiguous",
                pgettext(_CTX, "Bu şifrlə birdən çox ixtisas var — dəqiqləşdirin: %s") % _text(row.get("program_code")),
            )
            return False

    sector = _text(row.get("language_sector"))
    proposal, options = propose_group_for(
        context.organization,
        program,
        sector=sector,
        taken=context.group_usage,
        admission_year=_text(row.get("admission_year")),
    )
    specialty = specialty_unit_of(program)
    plan.targets["program"] = program
    plan.targets["group"] = None
    plan.targets["group_options"] = options
    plan.targets["specialty"] = specialty
    if specialty is not None:
        from ..student_groups import suggest_group_name

        plan.values["suggested_group_name"] = suggest_group_name(
            context.organization,
            specialty,
            admission_year=_text(row.get("admission_year")),
            sector=sector,
        )
    if proposal is not None:
        from apps.organizations.models import OrgUnit

        unit = OrgUnit.objects.filter(organization=context.organization, pk=proposal["id"]).first()
        plan.targets["group"] = unit
        plan.group_name = proposal["name"]
        context.group_usage[proposal["id"]] = context.group_usage.get(proposal["id"], 0) + 1
        plan.warnings.append(
            pgettext(_CTX, "Qrup avtomatik təklif olundu: %s — tətbiqdən əvvəl dəyişə bilərsiniz.") % proposal["name"]
        )
    else:
        plan.warnings.append(
            pgettext(_CTX, "Uyğun boş qrup tapılmadı — tətbiqdən əvvəl qrup seçin və ya yeni qrup yaradın.")
        )
    return True


__all__ = [
    "disambiguate_program",
    "enrich",
    "parse_admission_channel",
    "parse_admission_status",
    "parse_datetime",
    "parse_form",
    "parse_form_atis",
    "parse_language",
    "parse_money",
    "parse_tour",
    "parse_funding",
    "parse_score",
    "program_by_code",
    "propose_group_for",
    "resolve_atis_targets",
    "specialty_unit_of",
]
