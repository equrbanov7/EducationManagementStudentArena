"""Qapı testi: şablonlarda XAM native ``<select>`` qalmasın (sahib, 2026-09-09).

Layihə qaydası: hər açılan siyahı `bootstrap-single-select` komponenti ilə
göndərilir::

    <div class="bootstrap-single-select bootstrap-single-select--ems">
      <select class="… bootstrap-single-select__native" data-bootstrap-select …>

`static/js/bootstrap_select.js` qlobal yüklənir (`templates/base.html`) və
`DOMContentLoaded` + `profile:section:loaded` hadisələrində avtomatik qoşulur.
Bu test yeni ekranın xam `<select>` ilə gəlməsini dayandırır.

STRUKTUR İSTİSNALARI (siyahıya salınmır — qaydanın ÖZÜ belədir)
--------------------------------------------------------------
* ``multiple`` seçicilər — komponent TƏK dəyərlidir (`select.value = …`),
  çoxseçimli elementi qoşsaq ilk klikdə bütün seçimlər itərdi. Onlar üçün
  stilli çoxseçim var (2026-10-16): `static/js/ems_multi_select.js`
  (`data-ems-multi-select`) — bunu ayrıca test (aşağıda) məcbur edir. Server-dən
  gələn ÇOX UZUN siyahılar üçün `EMSSearchableSelect` (axtarış ENDPOINT-i ilə).
* GÖRÜNMƏYƏN «güzgü» seçicilər — `hidden`, `aria-hidden="true"` və ya
  `d-none` daşıyanlar. Bunlar istifadəçiyə göstərilmir; öz görünən idarəsi
  (seqment düymələri, axtarış paneli) var, native element yalnız formanın /
  deep-link-in müqaviləsini saxlayır.

Hər iki halda element İSTİFADƏÇİYƏ native select kimi GÖRÜNMÜR, ona görə
«xam select göndərmə» qaydası pozulmur.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parents[3]

#: Django `{% comment %}` blokları və HTML şərhləri — sayılmır. Şərhdə qayda
#: barədə yazan `<select>` sözü (məs. `_head_field.html`) yalançı siqnal idi.
DJANGO_COMMENT_RE = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
SELECT_TAG_RE = re.compile(r"<select\b[^>]*>", re.DOTALL)

#: Hələ çevrilməmiş şablonlar. BURAYA YENİ SƏTİR ƏLAVƏ ETMƏK OLMAZ — siyahı
#: yalnız qısalır. Hər sətrin yanında SƏBƏB və planlanan addım yazılır.
PENDING_CONVERSION = {
    # (boşdur — 2026-09-09-da RİM yaratma dialoqları da çevrildi)
}


def _template_roots():
    roots = sorted((BASE_DIR / "apps").glob("*/templates"))
    shared = BASE_DIR / "templates"
    if shared.is_dir():
        roots.append(shared)
    return roots


def _strip_comments(source):
    return HTML_COMMENT_RE.sub("", DJANGO_COMMENT_RE.sub("", source))


#: Boolean atribut (`multiple`, `hidden`) — dəyəri olan `data-hidden="1"` kimi
#: atributlarla qarışmasın deyə həm əvvəl, həm sonra sərhəd tələb olunur.
def _has_boolean_attr(tag, name):
    return bool(re.search(r"(?:^|\s)" + name + r'(?=[\s>/]|="' + name + r'")', tag))


def _is_hidden_mirror(tag):
    """İstifadəçiyə göstərilməyən «güzgü» seçici (öz atributu ilə)."""
    if _has_boolean_attr(tag, "hidden"):
        return True
    if 'aria-hidden="true"' in tag:
        return True
    return bool(re.search(r'class="[^"]*\bd-none\b', tag))


def _is_structurally_exempt(tag):
    """Qoşulması MÜMKÜN olmayan / görünməyən seçicilər (bax modul docstring-i)."""
    if _has_boolean_attr(tag, "multiple"):
        return True
    return _is_hidden_mirror(tag)


#: Gizli sarğı: `<div class="… d-none …">` açılıb, seçiciyə qədər bağlanmayıb.
HIDDEN_WRAPPER_RE = re.compile(r'<div\b[^>]*class="[^"]*\bd-none\b[^"]*"[^>]*>')


def _inside_hidden_wrapper(head):
    tail = head[-1500:]
    opened = list(HIDDEN_WRAPPER_RE.finditer(tail))
    return bool(opened) and "</div>" not in tail[opened[-1].end() :]


def _bare_selects():
    """(nisbi yol, sətir, teq) — `data-bootstrap-select` daşımayan seçicilər."""
    found = []
    for root in _template_roots():
        for path in sorted(root.rglob("*.html")):
            source = _strip_comments(path.read_text(encoding="utf-8"))
            for match in SELECT_TAG_RE.finditer(source):
                tag = " ".join(match.group(0).split())
                # `data-bootstrap-select-lazy` (2026-09-14): server hazır toggle
                # render edir, komponent ilk fokus/klikdə qoşulur (kağız bal
                # cədvəli — 200 seçici) — eyni komponent, tənbəl qoşulma.
                if "data-bootstrap-select" in tag or _is_structurally_exempt(tag):
                    continue
                relative = path.relative_to(BASE_DIR).as_posix()
                found.append((relative, source[: match.start()].count("\n") + 1, tag))
    return found


class NoNativeSelectsTest(SimpleTestCase):
    def test_templates_ship_no_bare_native_select(self):
        offenders = [item for item in _bare_selects() if item[0] not in PENDING_CONVERSION]
        detail = "\n".join(f"  {path}:{line}: {tag[:110]}" for path, line, tag in offenders)
        self.assertEqual(
            offenders,
            [],
            "Xam native <select> aşkarlandı — `bootstrap-single-select` sarğısı və "
            "`data-bootstrap-select` atributu əlavə edin "
            "(çoxseçimli/gizli güzgü elementlərdə qayda tətbiq olunmur):\n" + detail,
        )

    def test_pending_list_has_no_stale_entries(self):
        """Çevrilmiş şablon siyahıda qalmasın — siyahı yalnız qısalmalıdır."""
        still_bare = {path for path, _, _ in _bare_selects()}
        stale = sorted(set(PENDING_CONVERSION) - still_bare)
        self.assertEqual(
            stale,
            [],
            "PENDING_CONVERSION köhnəlib — bu şablonlar artıq təmizdir, sətirləri silin: " + ", ".join(stale),
        )

    def test_enhanced_selects_carry_the_wrapper_and_native_class(self):
        """Qoşulmanın İKİ şərti markup-dadır — ikisi də yoxlanılır.

        1. `.bootstrap-single-select` SARĞISI — enhancer `select.closest()` ilə
           onu axtarır, tapmasa heç nə etmir və ekranda xam select qalır.
        2. `.bootstrap-single-select__native` KLASSI — native elementi gizlədən
           qayda `.bootstrap-single-select__native.is-enhanced`-dir; klass
           olmasa select stilli düymənin YANINDA görünməyə davam edir.

        Hər iki nasazlıq `_schedule_content.html` və `_jd_coursework.html`-də
        real olaraq baş vermişdi (2026-09-09 auditi).
        """
        broken = []
        for root in _template_roots():
            for path in sorted(root.rglob("*.html")):
                source = _strip_comments(path.read_text(encoding="utf-8"))
                for match in SELECT_TAG_RE.finditer(source):
                    tag = match.group(0)
                    if "data-bootstrap-select" not in tag:
                        continue
                    head = source[: match.start()]
                    reference = f"{path.relative_to(BASE_DIR).as_posix()}:{head.count(chr(10)) + 1}"
                    # Sarğı eyni şablonda AÇILMALIDIR (partial-lar öz sarğısını
                    # daşıyır) — seçicidən dərhal əvvəlki mətndə gözlənilir.
                    if "bootstrap-single-select" not in head[-600:]:
                        broken.append(f"{reference} (sarğı yoxdur)")
                    elif "bootstrap-single-select__native" not in tag:
                        broken.append(f"{reference} (__native klassı yoxdur)")
        self.assertEqual(
            broken,
            [],
            "`data-bootstrap-select` seçicisi düzgün bəzədilməyib: " + ", ".join(broken),
        )

    def test_multiple_selects_use_the_multi_select_component(self):
        """2026-10-16: görünən ``<select multiple>`` stilli çoxseçimlə (`data-ems-multi-select`) gəlir.

        İstisna yalnız GİZLİ güzgülərdir (öz atributu və ya dərhal əhatə edən `d-none` sarğısı) —
        onların görünən idarəsi başqa komponentdir (məs. imtahan dialoqunun axtarışlı siyahısı).
        """
        bare = []
        for root in _template_roots():
            for path in sorted(root.rglob("*.html")):
                source = _strip_comments(path.read_text(encoding="utf-8"))
                for match in SELECT_TAG_RE.finditer(source):
                    tag = " ".join(match.group(0).split())
                    if not _has_boolean_attr(tag, "multiple") or "data-ems-multi-select" in tag:
                        continue
                    head = source[: match.start()]
                    if _is_hidden_mirror(tag) or _inside_hidden_wrapper(head):
                        continue
                    bare.append(f"{path.relative_to(BASE_DIR).as_posix()}:{head.count(chr(10)) + 1}")
        self.assertEqual(
            bare,
            [],
            "Xam native <select multiple> — `data-ems-multi-select` əlavə edin "
            "(static/js/ems_multi_select.js): " + ", ".join(bare),
        )
