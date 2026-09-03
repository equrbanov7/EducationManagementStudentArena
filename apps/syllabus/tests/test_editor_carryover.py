"""QAPI: köçürülmüş sillabusun məzmunu redaktorun İLK AVTOSAXLAMASINDA itmir.

Kontekst
========
Köçürmə borusu məzmunu düzgün yazır.  Müəllim həmin sillabusdan yeni versiya
açıb bir dəfə avtosaxlama edəndə isə üç bölmə boşalırdı.  Kök səbəb serverdə
DEYİLDİ (``save_section`` açar səviyyəsində birləşdirir) — **redaktorun DOM-u
mənbədən DAR idi**, ona görə toplayıcı açarı kəsilmiş halda göndərirdi:

======================  ===========================================  ==============
açar                    kök səbəb                                    canlı miqyas
======================  ===========================================  ==============
``method.methods``      yalnız 8 sabit kataloq çipi render olunurdu   8,260 sillabus
``self.topics``         ``option: ""`` → 0 yuva render olunurdu       8,258 sillabus
``week.rows``           cədvəl həmişə DƏQİQ 16 sətrə normallaşırdı    1,970 sillabus
``week.rows[].practical/note``  sətir sıfırdan qurulurdu             8,220 sillabus
``out.outcomes``        çox sətirli mətn ``<input>``-ə render olunurdu  4,790 sillabus
``self.topics[].title`` eyni sinif — mənbədə U+2028 ayırıcısı var         1 sillabus
``lit.primary``         ``toLines`` abzas boş sətrini atırdı            556 sillabus
======================  ===========================================  ==============

DÖRDÜNCÜ İTKİ SİNFİ — sətir sonunu UDAN element
===============================================
HTML-in «value sanitization algorithm»-i ``<input>``-in dəyərindən CR/LF
simvollarını SİLİR (boşluqla belə əvəz etmir).  Brauzer probe-u: ``<input
value="a\nb">.value === "ab"``, ``<textarea>`` və ``data-*`` atributu isə
``\n``-i (və abzas boş sətrini) saxlayır.  Ona görə çox sətirli dəyər daşıya
bilən HƏR sahə ``<textarea>``-yə çevrildi; ``week.rows[].topic`` ``<input>``
qalır, çünki köçürmə orada ``clean_text`` işlədir (mənbədə 131,056 sətrin heç
birində sətir sonu yoxdur) — və bu fakt `test_editor_shipped_js`-dəki render
qapısı ilə bağlanıb.

Testlərin forması
=================
Yük SÜNİ DEYİL: ``editor_dom`` redaktorun əsl context-ini qurur, əsl şablon
parçalarını render edir və ``syllabus_editor_fields.js``-in seçiciləri ilə
gövdəni toplayır (``<select>``-in brauzer davranışı da daxil).  Şablondan bir
çip/sətir/yuva düşsə, test çökür.

Hər test BİR itki yolunu bağlayır; dördüncüsü ümumi qaydanı qoruyur:
**toplayıcı göndərmədiyi məlumatı silməməlidir.**

⚠️ Bal bölgüsü mövzusuna TOXUNULMUR (sahib bağlı elan edib) — burada yalnız
MƏTN məzmununun qorunması yoxlanılır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SELFWORK_DISALLOWED, SELFWORK_OPTIONS, SectionKey
from apps.syllabus.document import BLOCK_TITLES, build_preview_blocks
from apps.syllabus.models import ChangeKind
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.editor_dom import HOUR_KINDS, collect, render_editor_dom
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
pytestmark = pytest.mark.django_db

PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]

#: Köhnə sistemdən gələn tədris metodları — kataloqda (``TEACHING_METHODS``)
#: HEÇ BİRİ yoxdur, çünki mənbədə bu, nömrələnmiş sərbəst mətndir.
MIGRATED_METHODS = [
    "1. mühazirə\n2. mövzunun müzakirəsi və diskussiya\n3. seminar və kollokvium",
    "video materiallardan və digər əyani vasitələrdən istifadə",
]

#: Köçürülmüş TƏLİM NƏTİCƏLƏRİ — mənbədə (``sillabus_eldeolunacaq_tecrubeler``)
#: bir sətir bütöv nömrələnmiş siyahı ola bilir, yəni dəyər ÇOX SƏTİRLİDİR.
MIGRATED_OUTCOMES = [
    "TN1. alqoritmin mürəkkəbliyini O notasiyası ilə qiymətləndirir\n" "2. məsələyə uyğun verilənlər strukturunu seçir",
    "təhlilin nəticəsini yazılı şəkildə əsaslandırır",
    "komanda işində kod baxışı aparır",
]

#: Köçürülmüş sərbəst iş mövzusu — mənbədə ayırıcı U+2028-dir, təmizləyici
#: (``legacy_text.clean_multiline_text`` → ``splitlines``) onu ``\n``-ə çevirir.
MIGRATED_SELFWORK_TITLE = (
    "Avropanın siyasi birləşmə konsepsiyalarının təkamülü.\n" "İkinci dünya müharibəsindən sonrakı birləşmə layihələri."
)

#: Köçürülmüş ədəbiyyat — ABZAS FASİLƏSİ (boş sətir) qəsdən qoyulub.
MIGRATED_LITERATURE = [
    "1. Kormen T. Alqoritmlərə giriş. MIT Press, 2019\n"
    "2. Sedgewick R. Alqoritmlər. Addison-Wesley, 2011\n"
    "\n"
    "Elektron resurslar:\n"
    "3. Knuth D. The Art of Computer Programming. 1997",
]

#: Köçürülmüş sərbəst iş mövzuları — mənbədə struktur (``option``) anlayışı yoxdur.
MIGRATED_TOPICS = [
    "Verilənlər strukturlarının müqayisəli təhlili",
    "Alqoritmin mürəkkəbliyinin hesablanması",
    "Qrafların gəzişmə üsulları",
    "Sıralama alqoritmlərinin tətbiqi",
    "Axtarış ağaclarının balanslaşdırılması",
    "Dinamik proqramlaşdırma məsələləri",
    "Layihə: kiçik kitabxana sistemi",
]


def _migrated_week_rows(count: int) -> list:
    """Mənbə formatındakı həftə sətirləri — ``practical`` və ``note`` DAXİL.

    Saat dəyərləri qəsdən redaktorun sabit seçim siyahısından (0–4) BÖYÜKDÜR:
    əvvəllər `<select>` belə dəyəri itirir, brauzer birinci variantı (0)
    göstərirdi və autosave saatı sıfırlayırdı.
    """
    return [
        {
            "topic": f'{index + 1}. mövzu — alqoritmlərin "böyük O" qiymətləndirilməsi',
            "lecture": 6,
            "seminar": 2,
            "lab": 0,
            "outcome": "",
            "practical": 2,
            "note": f"mənbə qeydi #{index + 1}",
        }
        for index in range(count)
    ]


#: Boş `self` bölməsi — struktur seçilməmiş köçürülmüş sillabus.
BLANK_SELF = {"option": "", "topics": [], "archived": []}


@pytest.fixture()
def world():
    org = make_org("carryover-org")
    teacher = User.objects.create_user("carryover_teacher", "carryover@x.test", "pw")
    stack = make_academic_stack(org, code="CAR101")
    activate_member(org, teacher, "teacher", permissions=PERMS)
    make_offering(org, stack, teacher)
    return {"org": org, "teacher": teacher, "stack": stack}


def _migrated_draft(world, section_data):
    """Köçürülmüş (APPROVED) versiya → müəllimin açdığı yeni QARALAMA."""
    actor = services.resolve_actor(world["teacher"], world["org"])
    syllabus, _ = services.import_migrated_version(
        organization=world["org"],
        subject=world["stack"]["subject"],
        approved_at=timezone.now(),
        author=world["teacher"],
        chair_unit=world["stack"]["chair"],
        plan_hours=dict(PLAN_HOURS),
        section_data=section_data,
    )
    version = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    return actor, version


def _autosave(world, version, actor, section_id):
    """Redaktoru render edir, DOM-dan gövdəni toplayır və `save_section` çağırır.

    Yəni müəllimin bölmədə etdiyi İLK avtosaxlama — heç nəyə toxunmadan.
    """
    root, _se = render_editor_dom(user=world["teacher"], organization=world["org"], version=version, step=section_id)
    payload = collect(root, section_id)
    services.save_section(version=version, section_id=section_id, data=payload, actor=actor, request=None)
    return payload, services.section_data_map(version)[section_id]


def _preview(version) -> dict:
    blocks = build_preview_blocks(services.section_data_map(version))
    return {str(block["title"]): block["body"] for block in blocks}


# ── 1. `method.methods` — kataloqda olmayan metod itmir ────────────────────
def test_migrated_teaching_methods_survive_first_autosave(world):
    actor, version = _migrated_draft(
        world, {SectionKey.METHOD.value: {"methods": list(MIGRATED_METHODS), "note": "hər həftə tətbiq olunur"}}
    )
    before = services.section_data_map(version)[SectionKey.METHOD.value]
    assert before["methods"] == MIGRATED_METHODS

    payload, after = _autosave(world, version, actor, SectionKey.METHOD.value)

    # Toplayıcı artıq kataloqdankənar çipləri DƏ görür (əvvəl `methods: []` idi).
    assert payload["methods"] == MIGRATED_METHODS
    assert after["methods"] == MIGRATED_METHODS
    assert after["note"] == "hər həftə tətbiq olunur"
    # Tələbənin gördüyü blok da boşalmır.
    assert MIGRATED_METHODS[1] in _preview(version)[str(BLOCK_TITLES["methods"])]


def test_teacher_can_still_drop_a_migrated_method_explicitly(world):
    """Silmə niyyəti YOX OLMUR: çip `is-on`-dan çıxarılanda metod yazılmır."""
    actor, version = _migrated_draft(world, {SectionKey.METHOD.value: {"methods": list(MIGRATED_METHODS)}})
    root, _se = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.METHOD.value
    )
    # «Siyahıdan çıxar» düyməsinin brauzerdəki nəticəsi: çipdən `is-on` düşür.
    chip = root.xpath("//*[@data-syl-method-custom]")[0]
    chip.set("class", (chip.get("class") or "").replace("is-on", "").strip())

    payload = collect(root, SectionKey.METHOD.value)
    services.save_section(version=version, section_id=SectionKey.METHOD.value, data=payload, actor=actor, request=None)
    after = services.section_data_map(version)[SectionKey.METHOD.value]
    assert after["methods"] == MIGRATED_METHODS[1:]


# ── 2. `self.topics` — variant seçilməyəndə mövzular itmir ─────────────────
def test_migrated_selfwork_topics_survive_first_autosave(world):
    actor, version = _migrated_draft(
        world,
        {
            SectionKey.SELF.value: {
                "option": "",
                "topics": [{"title": title} for title in MIGRATED_TOPICS],
                "archived": [],
            }
        },
    )
    payload, after = _autosave(world, version, actor, SectionKey.SELF.value)

    # Əvvəl: 0 yuva render olunurdu → `topics: []`.
    assert [row["title"] for row in payload["topics"]] == MIGRATED_TOPICS
    assert [row["title"] for row in after["topics"]] == MIGRATED_TOPICS
    assert after["option"] == ""
    assert MIGRATED_TOPICS[-1] in _preview(version)[str(BLOCK_TITLES["selfwork"])]


def test_selfwork_topics_survive_after_the_teacher_picks_a_structure(world):
    """Variant seçmək ARTIQ mövzuları səssizcə silmir — onlar yuva kimi qalır."""
    actor, version = _migrated_draft(
        world,
        {
            SectionKey.SELF.value: {
                "option": "",
                "topics": [{"title": title} for title in MIGRATED_TOPICS],
                "archived": [],
            }
        },
    )
    services.save_section(
        version=version,
        section_id=SectionKey.SELF.value,
        data={"option": "2x5", "topics": [{"title": title} for title in MIGRATED_TOPICS], "archived": []},
        actor=actor,
        request=None,
    )
    # Redaktor bölməni yenidən yükləyir (`STRUCTURAL`), sonra növbəti avtosaxlama.
    payload, after = _autosave(world, version, actor, SectionKey.SELF.value)
    assert payload["option"] == "2x5"
    assert [row["title"] for row in after["topics"]] == MIGRATED_TOPICS


# ── 3. `week.rows` — 16-dan uzun cədvəl və sətir açarları itmir ────────────
def test_migrated_week_rows_and_row_keys_survive_first_autosave(world):
    source_rows = _migrated_week_rows(23)
    actor, version = _migrated_draft(world, {SectionKey.WEEK.value: {"rows": source_rows}})

    payload, after = _autosave(world, version, actor, SectionKey.WEEK.value)

    # (a) sətir sayı kəsilmir — əvvəl 23 → 16 idi.
    assert len(payload["rows"]) == 23
    assert len(after["rows"]) == 23
    # (b) mövzu mətni (dırnaqlar daxil) olduğu kimi qayıdır.
    assert [row["topic"] for row in after["rows"]] == [row["topic"] for row in source_rows]
    # (c) saat dəyəri seçim siyahısından böyük olsa da sıfırlanmır.
    assert {row["lecture"] for row in after["rows"]} == {6}
    assert {row["seminar"] for row in after["rows"]} == {2}
    # (d) redaktorda İNPUTU OLMAYAN açarlar (`practical`, `note`) hər sətirdə qalır.
    assert [row["practical"] for row in after["rows"]] == [2] * 23
    assert [row["note"] for row in after["rows"]] == [row["note"] for row in source_rows]


def test_short_week_table_is_still_padded_to_sixteen_rows(world):
    """Qısa cədvəl üçün davranış DƏYİŞMİR: plan 16 həftədir, boş sətirlər qalır."""
    actor, version = _migrated_draft(world, {SectionKey.WEEK.value: {"rows": _migrated_week_rows(4)}})
    payload, after = _autosave(world, version, actor, SectionKey.WEEK.value)
    assert len(payload["rows"]) == 16
    assert len([row for row in after["rows"] if row["topic"]]) == 4


# ── 4. Ümumi qayda: göndərilməyən sahə silinmir (gələcək açarlar da) ───────
def test_unknown_future_row_key_is_carried_back_untouched(world):
    """Sxemə SONRA əlavə olunan sətir açarı da avtomatik qorunmalıdır.

    Bu, üç itkinin ORTAQ sinif səhvidir: toplayıcı sətri sıfırdan qururdu.
    İndi sətir `data-extra` (mənbənin qorunan açarları) üzərində qurulur, ona
    görə redaktorun tanımadığı açar üçün heç bir kod dəyişikliyi lazım deyil.
    """
    rows = _migrated_week_rows(2)
    rows[0]["gelecek_sahe"] = {"nested": [1, 2, 3]}
    actor, version = _migrated_draft(world, {SectionKey.WEEK.value: {"rows": rows}})

    _payload, after = _autosave(world, version, actor, SectionKey.WEEK.value)
    assert after["rows"][0]["gelecek_sahe"] == {"nested": [1, 2, 3]}


# ── 5. `out.outcomes` — sətir sonu itmir (ƏN BÖYÜK itki yolu) ──────────────
def test_migrated_multiline_outcomes_survive_first_autosave(world):
    """4,790 sillabusun təlim nəticəsi ÇOX SƏTİRLİDİR — `<input>` onu udurdu.

    Nəticə tələbənin ekranında görünürdü: «…qiymətləndirir\\n2. …seçir» →
    «…qiymətləndirir2. …seçir», yəni SÖZLƏR YAPIŞIRDI.  Tetikleyici ən adi
    əməldir: nəticə sahəsinə toxunmaq və ya «Təlim nəticəsi əlavə et».
    """
    actor, version = _migrated_draft(world, {SectionKey.OUT.value: {"outcomes": list(MIGRATED_OUTCOMES)}})

    payload, after = _autosave(world, version, actor, SectionKey.OUT.value)

    assert payload["outcomes"] == MIGRATED_OUTCOMES
    assert after["outcomes"] == MIGRATED_OUTCOMES
    # Sinfin ÖZ simptomu: sətir sonu düşəndə sözlər yapışırdı.
    assert "qiymətləndirir2." not in after["outcomes"][0]
    assert MIGRATED_OUTCOMES[0] in _preview(version)[str(BLOCK_TITLES["outcomes"])]


def test_outcome_count_is_unchanged_so_week_row_tn_references_hold(world):
    """Nəticələri sətirlərə BÖLMƏK olmazdı — TN nömrələri sürüşərdi.

    ``week.rows[].outcome`` «TN2» kimi ETİKETƏ istinad edir; çox sətirli bir
    nəticəni iki sahəyə bölmək TN3-ü TN4 edərdi, yəni köçürülmüş datanın
    strukturunu DƏYİŞƏRDİ.  Ona görə `<textarea>` seçildi, «sətir başına bir
    sahə» yox.
    """
    actor, version = _migrated_draft(
        world,
        {
            SectionKey.OUT.value: {"outcomes": list(MIGRATED_OUTCOMES)},
            SectionKey.WEEK.value: {"rows": [{"topic": "birinci mövzu", "outcome": "TN3"}]},
        },
    )
    payload, after = _autosave(world, version, actor, SectionKey.OUT.value)
    assert len(payload["outcomes"]) == len(MIGRATED_OUTCOMES) == 3

    _week_payload, week_after = _autosave(world, version, actor, SectionKey.WEEK.value)
    assert week_after["rows"][0]["outcome"] == "TN3"
    assert after["outcomes"][2] == MIGRATED_OUTCOMES[2]


# ── 6. `self.topics[].title` — eyni sinif, mənbədə U+2028 ──────────────────
def test_migrated_selfwork_title_line_break_survives_first_autosave(world):
    """Xam sütunda ``[\\r\\n]`` YOXDUR, buna baxmayaraq itki VAR.

    Ayırıcı U+2028-dir; ``clean_multiline_text`` ``splitlines()`` işlədir və
    onu ``\\n``-ə çevirir, yəni SAXLANILAN dəyər çox sətirlidir.  Bu sinfi xam
    sütun üzərində regexp ilə saymaq olmur — məhz ona görə əvvəlki turlarda
    «təhlükəsiz» sayılmışdı.
    """
    actor, version = _migrated_draft(
        world,
        {SectionKey.SELF.value: {"option": "", "topics": [{"title": MIGRATED_SELFWORK_TITLE}], "archived": []}},
    )
    payload, after = _autosave(world, version, actor, SectionKey.SELF.value)

    assert payload["topics"][0]["title"] == MIGRATED_SELFWORK_TITLE
    assert after["topics"][0]["title"] == MIGRATED_SELFWORK_TITLE
    assert "təkamülü.İkinci" not in after["topics"][0]["title"]


# ── 7. `lit.primary` — abzas fasiləsi itmir ────────────────────────────────
def test_migrated_literature_paragraph_break_survives_first_autosave(world):
    """``toLines`` hər boş sətri atırdı; ``_prose_lines`` isə onu QƏSDƏN saxlayır.

    İki qol arasındakı bu ziddiyyət 556 sillabusda abzas fasiləsini müəllimin
    ilk avtosaxlamasında silirdi.
    """
    actor, version = _migrated_draft(world, {SectionKey.LIT.value: {"primary": list(MIGRATED_LITERATURE)}})

    payload, after = _autosave(world, version, actor, SectionKey.LIT.value)

    assert "" in payload["primary"], "abzas fasiləsi toplayıcıda itdi"
    assert after["primary"] == [
        "1. Kormen T. Alqoritmlərə giriş. MIT Press, 2019",
        "2. Sedgewick R. Alqoritmlər. Addison-Wesley, 2011",
        "",
        "Elektron resurslar:",
        "3. Knuth D. The Art of Computer Programming. 1997",
    ]
    # Oxucuya da çatır: sənəddə abzas boşluğu qalır.
    assert "\n\nElektron resurslar:" in _preview(version)[str(BLOCK_TITLES["literature"])]
    # Baş/son boş sətirlər (köhnə redaktorun `\r\n\r\n\r\n` doldurması) qalmır.
    assert after["primary"][0] and after["primary"][-1]


def test_second_autosave_of_literature_is_idempotent(world):
    """Resept idempotentdir: öz nəticəsini yenidən emal etmək dəyişiklik vermir."""
    actor, version = _migrated_draft(world, {SectionKey.LIT.value: {"primary": list(MIGRATED_LITERATURE)}})
    _first, after_one = _autosave(world, version, actor, SectionKey.LIT.value)
    _second, after_two = _autosave(world, version, actor, SectionKey.LIT.value)
    assert after_two["primary"] == after_one["primary"]


# ── 8. Xəbərdarlıq banneri İCRA EDİLƏ BİLƏN olmalıdır ─────────────────────
def _blank_week_row(tr) -> None:
    """Müəllimin brauzerdə etdiyi əməl: mövzunu və saatları boşaltmaq."""
    for node in tr.xpath(".//*[@data-week='topic']"):
        node.set("value", "")
    for kind in HOUR_KINDS:
        for select in tr.xpath(f".//*[@data-week='{kind}']"):
            for option in select.xpath(".//option"):
                if (option.get("value") or "") in ("", "0"):
                    option.set("selected", "selected")
                else:
                    option.attrib.pop("selected", None)


def _plain_week_rows(count: int) -> list:
    """`practical`/`note` DAŞIMAYAN sətirlər — boşaldıla bilən quyruq."""
    return [
        {"topic": f"{index + 1}. mövzu", "lecture": 2, "seminar": 0, "lab": 0, "outcome": ""} for index in range(count)
    ]


def test_emptied_extra_week_rows_leave_the_table_on_the_next_render(world):
    """Banner müəllimə «boşaldın» deyirdi, boşaltmaq isə HEÇ NƏYİ dəyişmirdi.

    Say ``len(raw)``-dan çıxdığı üçün boşaldılmış sətir siyahıdan DÜŞMÜRDÜ
    (23 → 23).  Nəticə: göstəriş icra edilə bilmir, banner ~1,970 sillabusda
    ƏBƏDİ qalır.  İndi yalnız QUYRUQdakı tam boş sətirlər render siyahısından
    çıxır — həm də yalnız müəllimin AÇIQ əməlindən sonra.
    """
    actor, version = _migrated_draft(world, {SectionKey.WEEK.value: {"rows": _plain_week_rows(23)}})
    _root, before = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    assert before["week_extra_count"] == 7
    assert len(before["week_rows"]) == 23

    root, _se = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    for tr in root.xpath("//*[@data-syl-week-row]"):
        if "syl-weeks__row--extra" in (tr.get("class") or ""):
            _blank_week_row(tr)
    payload = collect(root, SectionKey.WEEK.value)
    services.save_section(version=version, section_id=SectionKey.WEEK.value, data=payload, actor=actor, request=None)

    _root2, after = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    assert after["week_extra_count"] == 0, "banner müəllimin əməlindən sonra da qalır"
    assert len(after["week_rows"]) == 16
    # İlk 16 həftənin mövzusu TOXUNULMAZ qalır.
    assert after["week_rows"][15]["topic"] == "16. mövzu"


def test_a_blank_week_row_in_the_middle_keeps_its_position(world):
    """Yalnız QUYRUQ kəsilir — ortadakı boş sətir nömrələməni sürüşdürməməlidir."""
    rows = _plain_week_rows(20)
    rows[17] = {"topic": "", "lecture": 0, "seminar": 0, "lab": 0, "outcome": ""}
    _actor, version = _migrated_draft(world, {SectionKey.WEEK.value: {"rows": rows}})

    _root, se = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    assert len(se["week_rows"]) == 20
    assert se["week_rows"][17]["topic"] == ""
    assert se["week_rows"][19]["topic"] == "20. mövzu"


def test_a_week_row_holding_a_hidden_carried_value_is_not_dropped(world):
    """`practical`/`note` daşıyan sətir «boş» DEYİL — quyruqdan düşmür.

    Məhz buna görə həmin dəyərlər artıq GÖRÜNÜR (`extra_note`): əks halda
    müəllim sətri boşaldıb «niyə getmir?» deyərdi.
    """
    rows = _plain_week_rows(17)
    rows[16] = {"topic": "", "lecture": 0, "seminar": 0, "lab": 0, "outcome": "", "practical": 2}
    _actor, version = _migrated_draft(world, {SectionKey.WEEK.value: {"rows": rows}})

    _root, se = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    assert len(se["week_rows"]) == 17
    assert "2" in se["week_rows"][16]["extra_note"]


def test_emptied_extra_selfwork_slots_leave_the_panel_on_the_next_render(world):
    """Eyni qayda sərbəst iş yuvalarında (~8,258 sillabus)."""
    actor, version = _migrated_draft(
        world,
        {
            SectionKey.SELF.value: {
                "option": "",
                "topics": [{"title": title} for title in MIGRATED_TOPICS],
                "archived": [],
            }
        },
    )
    root, before = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.SELF.value
    )
    assert before["selfwork"]["extra_count"] == len(MIGRATED_TOPICS)

    for slot in root.xpath("//*[@data-syl-slot]"):
        for node in slot.xpath(".//*[@data-selfwork-title]"):
            node.text = ""
    payload = collect(root, SectionKey.SELF.value)
    services.save_section(version=version, section_id=SectionKey.SELF.value, data=payload, actor=actor, request=None)

    _root2, after = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.SELF.value
    )
    assert after["selfwork"]["slots"] == []
    assert after["selfwork"]["extra_count"] == 0


# ── 9. Arxiv sətri də ORTAQ qaydaya tabedir ───────────────────────────────
def test_a_disallowed_selfwork_option_can_never_be_stored(world):
    """«Sonuncu latent itki yolu» — ÖLÇÜLDÜ, itki yolu DEYİL.

    Baxış belə oxunur: ``SELFWORK_DISALLOWED`` variantları render-də həmişə
    ``active: False``-dır, yəni siyasətə uyğun gəlməyən variant saxlanılsaydı
    heç bir çip ``is-on`` olmaz, ``collectSelf`` ``option: ""`` göndərib dəyəri
    səssizcə silərdi.

    Əslində belə dəyər HEÇ VAXT yarana bilmir: ``drafts.save_section``
    ``self.option_not_allowed`` ilə rədd edir.  Yəni render qərarı DOĞRUDUR —
    çipi ``is-on`` etmək bölmənin hər avtosaxlamasını çökdürərdi (silmə yox,
    tam blok).  Bu test həmin səbəbi BƏRKİDİR: server qapısı götürülsə,
    ``editor_panels`` qərarına yenidən baxılmalıdır.
    """
    disallowed = next(iter(SELFWORK_DISALLOWED))
    assert disallowed not in SELFWORK_OPTIONS
    actor, version = _migrated_draft(world, {SectionKey.SELF.value: dict(BLANK_SELF)})
    with pytest.raises(TransitionDenied) as excinfo:
        services.save_section(
            version=version,
            section_id=SectionKey.SELF.value,
            data={"option": disallowed, "topics": [], "archived": []},
            actor=actor,
            request=None,
        )
    assert excinfo.value.code == "self.option_not_allowed"


def test_archived_rows_carry_unknown_keys_back_untouched(world):
    """`collectSelf` arxivi sıfırdan qururdu — naxış pozuq idi (bu gün 0 təsir).

    Bu gün köçürmə ``archived: []`` yazır, yəni itki YOXDUR; naxışı pozmaq isə
    məhz həmin sinif səhvini gələcəyə buraxmaq deməkdir.
    """
    actor, version = _migrated_draft(
        world,
        {
            SectionKey.SELF.value: {
                "option": "",
                "topics": [{"title": "aktiv mövzu"}],
                "archived": [{"title": "köhnə tapşırıq", "note": "3 qiymət", "gelecek_sahe": {"nested": [1]}}],
            }
        },
    )
    payload, after = _autosave(world, version, actor, SectionKey.SELF.value)
    assert payload["archived"][0]["gelecek_sahe"] == {"nested": [1]}
    assert after["archived"][0]["title"] == "köhnə tapşırıq"
    assert after["archived"][0]["gelecek_sahe"] == {"nested": [1]}
