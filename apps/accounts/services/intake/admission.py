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
    """Maliyyələşmə → ``state`` / ``paid``; tanınmasa boş sətir."""
    key = _key(raw)
    if not key:
        return ""
    if key in _STATE_WORDS:
        return "state"
    if key in _PAID_WORDS:
        return "paid"
    return ""


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


def specialty_unit_of(program):
    return getattr(program, "specialty_unit", None)


def propose_group_for(organization, program, *, sector: str, taken: dict):
    """Sətir üçün qrup təklifi.

    ``taken`` — BU FAYLDA artıq təyin edilmiş qrupların sayğacı: eyni qrupa
    tutumundan artıq sətir təklif edilməsin (fayl 300 sətirdirsə, hamısı bir
    qrupa yığılmamalıdır).
    """
    from ..student_groups import group_options, propose_group

    specialty = specialty_unit_of(program)
    if specialty is None:
        return None, []
    rows = group_options(organization, specialty, sector=sector)
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
        plan.fail(
            "program_code_ambiguous",
            pgettext(_CTX, "Bu şifrlə birdən çox ixtisas var — dəqiqləşdirin: %s") % _text(row.get("program_code")),
        )
        return False

    sector = _text(row.get("language_sector"))
    proposal, options = propose_group_for(context.organization, program, sector=sector, taken=context.group_usage)
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
    "enrich",
    "parse_form",
    "parse_funding",
    "parse_score",
    "program_by_code",
    "propose_group_for",
    "resolve_atis_targets",
    "specialty_unit_of",
]
