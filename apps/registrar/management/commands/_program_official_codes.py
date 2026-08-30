"""``set_program_official_codes`` komandasının DATA cədvəli.

Nə yazılır və nə üçün
---------------------
``Program.official_code`` **rəsmi dövlət ixtisas şifridir** — yalnız göstərmək
üçün, identifikator deyil. ``Program.code`` (daxili ``MYEDU-*`` açarı) bu
faylda **heç vaxt** dəyişdirilmir: köçürmə xətti (``apps/legacy_import``) onu
şəxsiyyət açarı kimi işlədir.

Sübut qaydası
-------------
Buraya YALNIZ düşmən doğrulayıcısının açıq «TƏTBİQ ET» hökmü olan sətirlər
düşür — hər biri **iki müstəqil mənbə** ilə təsdiqlənib. Doğrulayıcının rədd
etdiyi hər şey və dərin sayt axtarışının 21 namizədi ``HELD_BACK`` /
``SITE_SEARCH_CANDIDATES`` siyahılarındadır: onlar **yazılmır**, yalnız
``docs/migration/IXTISAS_KODLARI_SAHIB_QERARI.md`` sənədinə çıxır.

Əvvəlki iki cəhd məhz burada sındı: doğrulayıcının «tətbiq etmə» dediyi
sətirləri yenə də yazdılar. Cədvəli genişləndirən hər kəs əvvəlcə
``apps/registrar/tests/test_program_official_codes.py`` testinə baxsın —
test ``ASSIGNMENTS``-in ölçüsünü və hər sətrin iki mənbəsini kilidləyir.

Mexaniki sağlamlıq qaydası
--------------------------
Köhnə nəsil milli təsnifatda bakalavr şifrləri ``05xxxx``, magistr şifrləri
``06xxxx`` ilə başlayır. ``check_table_health()`` bu qaydanı hər icrada
cədvəlin ÖZÜNƏ tətbiq edir — pozan sətir varsa komanda heç nə yazmadan
dayanır. Məhz bu qayda ``050624`` səhvini tutdu (bax ``WRONG_CODES``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Köhnə nəsil (NK 503/2024-dən əvvəlki) təsnifatda pillə → şifr prefiksi.
LEVEL_PREFIXES: dict[str, str] = {
    "bachelor": "05",
    "master": "06",
}

#: «Təmiz» 6 rəqəmli köhnə nəsil şifr — MyEdu-dan gələn həqiqi dəyər.
CLEAN_CODE_RE = re.compile(r"^0[56]\d{4}$")


@dataclass(frozen=True)
class CodeAssignment:
    """Bir proqrama rəsmi şifr + onu haqlandıran İKİ müstəqil sübut."""

    #: Hədəf sətrin DAXİLİ kodu — yalnız sətri tapmaq üçün, dəyişdirilmir.
    internal_code: str
    #: ``official_code`` sütununa yazılacaq rəsmi dövlət şifri.
    official_code: str
    #: Gözlənilən ad — kor-koranə UPDATE-in qarşısını alır.
    expected_name: str
    degree_level: str
    #: Birinci mənbə: milli təsnifat və ya WCU-nun rəsmi cədvəli.
    source_primary: str
    #: İkinci, MÜSTƏQİL mənbə: saytın kodlu sənədi və ya MyEdu-nun həqiqi kodu.
    source_secondary: str
    note: str = ""


@dataclass(frozen=True)
class WrongCode:
    """Daxili kodu «həqiqi görünən», amma YANLIŞ olan sətir.

    Belə sətrin ``official_code``-u **boş qalır** — əvəzi UYDURULMUR və daxili
    kod rəsmi şifr kimi qəbul edilmir (``--adopt-clean-codes`` da onu keçir).
    """

    internal_code: str
    expected_name: str
    degree_level: str
    reason: str


@dataclass(frozen=True)
class HeldBack:
    """Yazılmayan sətir — sahibin qərarını gözləyir."""

    internal_code: str
    name: str
    reason: str
    proposal: str = ""


@dataclass(frozen=True)
class Candidate:
    """Namizəd şifr — doğrulayıcı «mən tətbiq etmədim» dedi, sahib təsdiqləyir."""

    internal_code: str
    name: str
    degree_level: str
    candidate_code: str
    source: str
    #: 05/06 qaydasını pozduğu BİLİNƏN və qəsdən saxlanan sətir (bax MYEDU-41).
    level_flagged: bool = False
    note: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. TƏTBİQ OLUNAN — doğrulayıcının açıq «TƏTBİQ ET» hökmü (5)
# ─────────────────────────────────────────────────────────────────────────────

ASSIGNMENTS: tuple[CodeAssignment, ...] = (
    CodeAssignment(
        internal_code="050620-M",
        official_code="060631",
        expected_name="Kompüter Mühəndisliyi",
        degree_level="master",
        source_primary="milli magistr təsnifatı: «060631 Kompüter mühəndisliyi»",
        source_secondary="WCU rəsmi 2022/23 magistratura cədvəli + «060631 - Kompüter mühəndisliyi.pdf» tədris planı",
        note="daxili kod 050620 BAKALAVR şifridir, «-M» şəkilçisi köçürmənin uydurmasıdır",
    ),
    CodeAssignment(
        internal_code="060411-M",
        official_code="060411",
        expected_name="Elektron kommersiya",
        degree_level="master",
        source_primary="WCU-nun rəsmi magistratura cədvəli: «060411 Kommersiya / Elektron kommersiya»",
        source_secondary="MyEdu speciality_code = 060411 (mənbə id 60)",
        note="rəsmi şifr artıq düzgündür — yalnız «-M» yer tutucusundan təmizlənir",
    ),
    CodeAssignment(
        internal_code="MYEDU-40",
        official_code="050405",
        expected_name="İqtisadiyyat",
        degree_level="bachelor",
        source_primary="milli bakalavriat təsnifatı: «050405 İqtisadiyyat»",
        source_secondary="wcu.edu.az tədris planı: «050405 İqtisadiyyat 2024 - tədris planı.pdf»",
    ),
    CodeAssignment(
        internal_code="MYEDU-43",
        official_code="050406",
        expected_name="Maliyyə",
        degree_level="bachelor",
        source_primary="milli bakalavriat təsnifatı: «050406 Maliyyə»",
        source_secondary="wcu.edu.az tədris planı: «050406 Maliyyə 2024- tədris planı ingilis.pdf»",
        note="PDF adındakı «ingilis» tədris dili variantıdır — şifri dəyişmir",
    ),
    CodeAssignment(
        internal_code="MYEDU-62",
        official_code="050509",
        expected_name="Kompüter elmləri",
        degree_level="bachelor",
        source_primary="milli bakalavriat təsnifatı: «050509 Kompüter elmləri»",
        source_secondary="wcu.edu.az: «050509 - Kompüter Elmləri.pdf» + «… - QİYABİ.pdf» (2 sənəd)",
        note="MyEdu-nun «37» dəyəri saxtadır; saytın magistr mətnindəki 050509 saytın yazı səhvidir",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# 2. YANLIŞ daxili şifr — rəsmi şifr BOŞ qalır (1)
# ─────────────────────────────────────────────────────────────────────────────

WRONG_CODES: tuple[WrongCode, ...] = (
    WrongCode(
        internal_code="050624",
        expected_name="Cihazqayırma mühəndisliyi",
        degree_level="bachelor",
        reason=(
            "milli bakalavriat təsnifatında «050624 = MƏDƏN MÜHƏNDİSLİYİ»dir. "
            "«Cihazqayırma mühəndisliyi» bakalavriatda ümumiyyətlə yoxdur — yalnız "
            "magistratura «060624». Yəni MyEdu-nun 6-rəqəmli, «həqiqi görünən» dəyəri "
            "korlanmışdır; rəsmi şifr kimi qəbul edilsə tələbəyə BAŞQA ixtisasın şifri "
            "göstərilər. Uydurma əvəz VERİLMİR — official_code boş qalır"
        ),
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# 3. YAZILMIR — doğrulayıcı RƏDD etdi / model qüsuru (8)
# ─────────────────────────────────────────────────────────────────────────────

HELD_BACK: tuple[HeldBack, ...] = (
    HeldBack(
        internal_code="050708-M",
        name="Su Bioehtiyyatları və Akvakultura",
        reason=(
            "doğrulayıcı RƏDD etdi: milli magistr təsnifatında 060709 «Su bioehtiyatları və "
            "AKVABİTKİLƏR»dir («akvakultura» BAKALAVR 050708-in adıdır); hədəfdə bu sahə üçün "
            "İKİ magistr sətri var (050708-M və MYEDU-89-M «Akvabioresurslar»); WCU-nun öz "
            "rəsmi magistratura cədvəlində 060709 ÜMUMİYYƏTLƏ yoxdur"
        ),
        proposal="əvvəlcə qərar: 050708-M və MYEDU-89-M eyni proqramdırmı? sonra təsnifat nəsli",
    ),
    HeldBack(
        internal_code="MYEDU-86-M",
        name="Genetika",
        reason=(
            "doğrulayıcı RƏDD etdi: 060505 «Biologiya» ANA ixtisasının şifridir və HƏM "
            "«Genetika», HƏM «Molekulyar biologiya» ixtisaslaşmasına eyni dərəcədə aiddir — "
            "hansına aid olduğu datadan çıxmır"
        ),
        proposal="«ixtisaslasma» (specialization) sahəsi əlavə et; sonra hər ikisi 060505 ala bilər",
    ),
    HeldBack(
        internal_code="MYEDU-90-M",
        name="Ətraf mühitin mühafizə və bərpa metodları",
        reason=(
            "doğrulayıcı RƏDD etdi: təklif olunan «7005004» YENİ nəsil (NK 503/2024) şifridir "
            "və «Ekologiya» deməkdir; hədəfdəki digər 100 şifr KÖHNƏ nəsildəndir. Bir sütunda "
            "iki təsnifat nəsli tələbəyə yanlış məlumat göstərir"
        ),
        proposal=(
            "əvvəlcə «official_code hansı təsnifat nəslini saxlayır?» qərarı (sənəd §6); "
            "köhnə nəsil seçilsə namizəd 060510 «Ekologiya»dır"
        ),
    ),
    HeldBack(
        internal_code="MYEDU-67",
        name="Davamlı inkişafın idarə edilməsi",
        reason=(
            "doğrulayıcı RƏDD etdi: bu, MyEdu id 58-in DUBLİKAT sətridir (ad hərfi eyni, yalnız "
            "sondakı boşluq fərqlidir; MyEdu şifri «2222» saxtadır) — ayrıca proqram deyil"
        ),
        proposal="050403 sətri ilə BİRLƏŞDİR (tələbə/qrup bağlantılarını köçür), sonra arxivləşdir",
    ),
    HeldBack(
        internal_code="MYEDU-20",
        name="Tarix (Tədris Ingilis Dilində)",
        reason=(
            "doğrulayıcı RƏDD etdi: şifr müstəqil mənbədən deyil, qardaş «Tarix» sətrindən "
            "çıxarılır (MyEdu id 20-də şifr BOŞDUR, sayt İngilis bölməsini ayrıca göstərmir)"
        ),
        proposal="«instruction_language» sahəsi; «050214-EN» şəkilçisi «-M» ilə eyni səhvdir",
    ),
    HeldBack(
        internal_code="MYEDU-15",
        name="Politologiya (Tədris Ingilis Dilində)",
        reason="eyni sinif: tədris dili variantı — şifr yalnız qardaş sətirdən çıxarılır",
        proposal="«instruction_language» sahəsindən sonra 050210 verilə bilər",
    ),
    HeldBack(
        internal_code="MYEDU-17",
        name="Beynəlxalq Münasibətlər (Tədris Ingilis Dilində)",
        reason="eyni sinif: tədris dili variantı — şifr yalnız qardaş sətirdən çıxarılır",
        proposal="«instruction_language» sahəsindən sonra 050201 verilə bilər",
    ),
    HeldBack(
        internal_code="MYEDU-82-M",
        name="Klinik psixologiya (ing)",
        reason="eyni sinif: «Klinik psixologiya» sətrinin tədris dili variantı",
        proposal="«instruction_language» sahəsindən sonra 060209 verilə bilər",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# 4. YAZILMIR — dərin sayt axtarışının 21 namizədi (sahibin təsdiqi lazımdır)
# ─────────────────────────────────────────────────────────────────────────────
#
# Doğrulayıcı bunları hərfən «mən tətbiq etmədim, sahibin təsdiqi üçün» deyə
# qeyd etdi. Əvvəlki iki cəhd məhz bu siyahını yazdı və sındı.

SITE_SEARCH_CANDIDATES: tuple[Candidate, ...] = (
    # ── 4.1 Sayt ∩ milli təsnifat — adlar üst-üstə düşür (12) ────────────────
    Candidate(
        internal_code="050501-63",
        name="Ekologiya Mühəndisliyi",
        degree_level="bachelor",
        candidate_code="050606",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
        note="daxili kod MyEdu-nun 050501 («Biologiya») şifrini İKİ ixtisasa verməsindən doğub",
    ),
    Candidate(
        internal_code="MYEDU-14",
        name="Politologiya",
        degree_level="bachelor",
        candidate_code="050210",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
    ),
    Candidate(
        internal_code="MYEDU-18",
        name="Beynəlxalq münasibətlər",
        degree_level="bachelor",
        candidate_code="050201",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
    ),
    Candidate(
        internal_code="MYEDU-42",
        name="Biznesin idarə edilməsi",
        degree_level="bachelor",
        candidate_code="050402",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
    ),
    Candidate(
        internal_code="MYEDU-44",
        name="Menecment",
        degree_level="bachelor",
        candidate_code="050408",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
    ),
    Candidate(
        internal_code="MYEDU-47",
        name="Marketinq",
        degree_level="bachelor",
        candidate_code="050407",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
    ),
    Candidate(
        internal_code="MYEDU-48",
        name="Mühasibat",
        degree_level="bachelor",
        candidate_code="050409",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
    ),
    Candidate(
        internal_code="MYEDU-49",
        name="Turizm işinin təşkili",
        degree_level="bachelor",
        candidate_code="050810",
        source="milli təsnifat + wcu.edu.az «050810 Turizm işinin təşkili -PTN.pdf»",
        note="Biznes məktəbinin tədris planlarının fayl adında şifr YOXDUR; şifr yalnız PTN sənədindədir",
    ),
    Candidate(
        internal_code="MYEDU-50",
        name="Dövlət və bələdiyyə idarəetməsi",
        degree_level="bachelor",
        candidate_code="050404",
        source="milli bakalavriat təsnifatı + dərin sayt axtarışı (eyni ad)",
    ),
    Candidate(
        internal_code="MYEDU-72-M",
        name="Məhkəmə psixologiyası",
        degree_level="master",
        candidate_code="060209",
        source="milli magistr təsnifatı «060209 Psixologiya» + dərin sayt axtarışı",
        note="060209 dörd psixologiya sətrinə birdən aiddir — official_code unikal olmadığı üçün mümkündür",
    ),
    Candidate(
        internal_code="MYEDU-74-M",
        name="Sosial psixologiya",
        degree_level="master",
        candidate_code="060209",
        source="milli magistr təsnifatı «060209 Psixologiya» + dərin sayt axtarışı",
    ),
    Candidate(
        internal_code="MYEDU-81-M",
        name="Klinik psixologiya",
        degree_level="master",
        candidate_code="060209",
        source="milli magistr təsnifatı «060209 Psixologiya» + dərin sayt axtarışı",
    ),
    # ── 4.2 Tək mənbəli namizədlər (9) ───────────────────────────────────────
    Candidate(
        internal_code="MYEDU-26",
        name="Filologiya (İngilis dili və ədəbiyyatı)",
        degree_level="bachelor",
        candidate_code="050205",
        source="YALNIZ sayt",
    ),
    Candidate(
        internal_code="MYEDU-27",
        name="Tərcümə",
        degree_level="bachelor",
        candidate_code="050215",
        source="YALNIZ sayt",
    ),
    Candidate(
        internal_code="MYEDU-75-M",
        name="Qafqaz xalqlarının tarixi",
        degree_level="master",
        candidate_code="060206",
        source="YALNIZ sayt",
    ),
    Candidate(
        internal_code="MYEDU-83-M",
        name="İqtisadiyyatın tənzimlənməsi",
        degree_level="master",
        candidate_code="060404",
        source="YALNIZ sayt",
    ),
    Candidate(
        internal_code="MYEDU-87-M",
        name="Beynəlxalq turizm",
        degree_level="master",
        candidate_code="060803",
        source="YALNIZ sayt",
    ),
    Candidate(
        internal_code="MYEDU-88-M",
        name="Beynəlxalq münasibətlər və diplomatiya",
        degree_level="master",
        candidate_code="060213",
        source="YALNIZ sayt",
    ),
    Candidate(
        internal_code="MYEDU-53",
        name="Beynəlxalq ticarət və logistika",
        degree_level="bachelor",
        candidate_code="050401",
        source="YALNIZ milli təsnifat (dərin sayt axtarışı bu sətri təsdiqləmədi)",
    ),
    Candidate(
        internal_code="MYEDU-68",
        name="Qida mühəndisliyi",
        degree_level="bachelor",
        candidate_code="050635",
        source="YALNIZ milli təsnifat (dərin sayt axtarışı bu sətri təsdiqləmədi)",
    ),
    Candidate(
        internal_code="MYEDU-41",
        name="Dünya iqtisadiyyatı",
        degree_level="bachelor",
        candidate_code="060401",
        source="YALNIZ milli təsnifat",
        level_flagged=True,
        note=(
            "⚠️ 060401 MAGİSTR şifridir, hədəf sətri isə bakalavr kimi qeyd olunub — "
            "sətrin təhsil pilləsi səhv ola bilər; sahib əvvəlcə pilləni təsdiqləməlidir"
        ),
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. İXTİSAS OLMAYAN sətirlər (8) — şifr verilmir, SİLİNMİR də
# ─────────────────────────────────────────────────────────────────────────────

NON_PROGRAM_ROWS: tuple[HeldBack, ...] = (
    HeldBack(internal_code="MYEDU-61", name="Level", reason="İngilis dili mərkəzinin səviyyə qeydi"),
    HeldBack(internal_code="MYEDU-65", name="aaa", reason="test sətri"),
    HeldBack(internal_code="MYEDU-66", name="Dizayn Məktəbi", reason="fakültə adı, ixtisas deyil"),
    HeldBack(internal_code="MYEDU-36-M", name="Magistratura və doktorantura", reason="struktur bölməsi adı"),
    HeldBack(internal_code="MYEDU-91", name="Lifelong", reason="davamlı təhsil mərkəzi, ixtisas deyil"),
    HeldBack(internal_code="MYEDU-91-M", name="Lifelong", reason="davamlı təhsil mərkəzi (magistr dublikatı)"),
    HeldBack(internal_code="MYEDU-92", name="Kollec", reason="struktur bölməsi, ixtisas deyil"),
    HeldBack(internal_code="MYEDU-101", name="Kollec 2", reason="struktur bölməsi, ixtisas deyil"),
)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Mənbənin (saytın) öz ziddiyyətləri — DÜZƏLDİLMƏYİB, sahibə məlumat
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_CONTRADICTIONS: tuple[str, ...] = (
    "«Molekulyar Biologiya» (magistr): sayt mətnində 050509 yazılıb — o, BAKALAVR «Kompüter "
    "Elmləri»nin şifridir; həmin sətrin PDF-i isə 060505-dir. Saytın YAZI SƏHVİ; şifr verilmədi",
    "050509 / 050615 / 050616 / 050620 / 050706 şifrlərinin hər birində saytda əyani və qiyabi "
    "üçün AYRI PDF, amma EYNİ şifr var — rəsmi şifr tədris formasını AYIRMIR",
    "«Turizm işinin təşkili» (Biznes məktəbi): 5 tədris planının fayl adında şifr YOXDUR "
    "(tt1.pdf, wcu-87.pdf …); şifr yalnız ayrıca «PTN» sənədinin adından oxunur",
)


# ─────────────────────────────────────────────────────────────────────────────
# Plan + cədvəlin öz sağlamlıq yoxlaması
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class WritePlan:
    """Bir icranın planı — nə yazılacaq, nə keçilir, nə bloklayır."""

    pending: list = field(default_factory=list)  # (Program, CodeAssignment)
    adoptions: list = field(default_factory=list)  # (Program, str) — təmiz daxili şifr
    already_done: list = field(default_factory=list)  # CodeAssignment | WrongCode
    missing: list = field(default_factory=list)  # CodeAssignment | WrongCode
    kept_blank: list = field(default_factory=list)  # (Program, WrongCode)
    blocked: list = field(default_factory=list)  # (obyekt, səbəb)


def check_table_health() -> list[str]:
    """Cədvəlin ÖZÜNÜ pillə/prefiks qaydasına tabe et (fail-closed).

    Köhnə nəsil təsnifatda bakalavr ``05xxxx``, magistr ``06xxxx``. Boş siyahı =
    cədvəl təmizdir. ``050624`` tipli səhvi gələcəkdə məhz bu tutur.
    """

    problems: list[str] = []

    for row in ASSIGNMENTS:
        expected = LEVEL_PREFIXES.get(row.degree_level)
        if expected and not row.official_code.startswith(expected):
            problems.append(
                f"ASSIGNMENTS {row.internal_code} → {row.official_code}: «{row.degree_level}» "
                f"üçün şifr «{expected}» ilə başlamalıdır («{row.expected_name}»)"
            )
        if not CLEAN_CODE_RE.match(row.official_code):
            problems.append(
                f"ASSIGNMENTS {row.internal_code} → {row.official_code}: köhnə nəsil şifr "
                f"6 rəqəmli və 05/06 ilə başlayan olmalıdır"
            )
        if not row.source_primary or not row.source_secondary:
            problems.append(f"ASSIGNMENTS {row.internal_code}: İKİ müstəqil mənbə tələb olunur")

    wrong = {row.internal_code for row in WRONG_CODES}
    for row in ASSIGNMENTS:
        if row.official_code in wrong:
            problems.append(f"ASSIGNMENTS {row.internal_code}: «{row.official_code}» YANLIŞ şifrlər siyahısındadır")

    for cand in SITE_SEARCH_CANDIDATES:
        expected = LEVEL_PREFIXES.get(cand.degree_level)
        violates = bool(expected) and not cand.candidate_code.startswith(expected)
        if violates and not cand.level_flagged:
            problems.append(
                f"SITE_SEARCH_CANDIDATES {cand.internal_code} → {cand.candidate_code}: pillə/prefiks "
                f"qaydasını pozur, amma «level_flagged» qeydi yoxdur"
            )

    assigned = {row.internal_code for row in ASSIGNMENTS}
    for group_name, group in (
        ("HELD_BACK", HELD_BACK),
        ("NON_PROGRAM_ROWS", NON_PROGRAM_ROWS),
    ):
        for row in group:
            if row.internal_code in assigned:
                problems.append(f"{group_name} {row.internal_code}: eyni sətir həm yazılır, həm buraxılır")
    for cand in SITE_SEARCH_CANDIDATES:
        if cand.internal_code in assigned:
            problems.append(f"SITE_SEARCH_CANDIDATES {cand.internal_code}: eyni sətir həm yazılır, həm buraxılır")

    return problems


__all__ = [
    "ASSIGNMENTS",
    "CLEAN_CODE_RE",
    "Candidate",
    "CodeAssignment",
    "HELD_BACK",
    "HeldBack",
    "LEVEL_PREFIXES",
    "NON_PROGRAM_ROWS",
    "SITE_SEARCH_CANDIDATES",
    "SOURCE_CONTRADICTIONS",
    "WRONG_CODES",
    "WritePlan",
    "WrongCode",
    "check_table_health",
]
