"""«Ana səhifə» — vidjet siyahısının TƏQDİMAT qatı (sıralama + hero KPI).

NİYƏ AYRI MODUL?  ``dashboard_widgets`` / ``dashboard_staff_widgets`` MƏLUMAT
toplayır (rol qapısı + sorğu büdcəsi), bu fayl isə həmin nəticəni EKRANA necə
düzəcəyimizi qərara alır.  İki məsuliyyət ayrı qalanda yeni vidjet əlavə etmək
düzümü, düzümü dəyişmək isə sorğuları qətiyyən narahat etmir.

MÜQAVİLƏ (dəyişdirməzdən əvvəl oxu)
-----------------------------------
* Vidjetin MÖVCUD açarları (``key``, ``title``, ``icon``, ``tone``, ``stats``,
  ``rows``, ``link``, ``empty``, ``is_empty``) TOXUNULMAZDIR — bu modul yalnız
  ƏLAVƏ (törəmə) sahələr yazır:

    variant     "data" | "link" — kartın forması (aşağıda)
    attention   bool — hərəkət gözləyən kart (xəbərdarlıq tonu + boş deyil)
    more_count  int  — siyahıda göstərilməyən sətirlərin sayı («+N daha»)

* Rol qapısı BURADA YOXDUR.  Siyahıya nə düşürsə, artıq ``allowed_sections`` /
  ``capabilities`` süzgəcindən keçib; bu modul heç bir vidjeti ATMIR, yalnız
  sıralayır (gizlətmək = sayğac sızması riskini yenidən açmaq olardı).

«data» və «link» kartları
-------------------------
Rəqəmi və ya sətri OLMAYAN vidjet əslində məlumat kartı deyil — bölməyə KEÇİD
kartıdır (22-ekran dalğasının naviqasiya kartları, «Tələbə əlavəsi (toplu)»,
əhatəsi qurulmamış «Sillabus təsdiqi»…).  Onları böyük boş kart kimi göstərmək
ana səhifəni «sıfırlar divarına» çevirirdi (RİM-də 12-yə qədər belə kart olur),
ona görə şablon onları AYRI, yığcam keçid zolağında verir.
"""

from __future__ import annotations

#: Hero zolağındakı KPI kartlarının sayı — dizayn: «2–4 rəqəm».  Tək kart zolaq
#: kimi oxunmur (və qonşu kartsız müqayisə mənası daşımır), ona görə alt hədd
#: var: bir dənə rəqəm tapılırsa zolaq ÜMUMİYYƏTLƏ göstərilmir — həmin rəqəm
#: onsuz da öz kartında var.
MIN_HERO_TILES = 2
MAX_HERO_TILES = 4

#: Hero-da göstərilə bilən dəyərin maksimum uzunluğu.  Zolaq İRİ RƏQƏM üçündür
#: («12», «09:00», «85%»); uzun mətn 25px-də sətirlərə dağılıb kartı partladır
#: — belə dəyər hero-ya çıxmır, öz kartında qalır.
MAX_HERO_VALUE_LEN = 10

#: «Rəqəm yoxdur» sayılan dəyərlər (``widget()``-dəki ``is_empty`` ilə eyni dil).
_BLANK_VALUES = ("", "0", "0%", "—")

#: Vidjet tonu → KPI kartının tonu.  Hero zolağı «ağ fon + 4px rəngli sol
#: kontur» dilindədir (bax `ems_ui/kpi.css` accent-*): sıx zolaqda tinted fonlar
#: göz yorur, kontur isə xəbərdarlığı yenə də bir baxışda verir.
_HERO_TONE = {
    "warning": "accent-warning",
    "danger": "accent-danger",
    "success": "accent-success",
}


def _is_blank(value) -> bool:
    return str(value or "").strip() in _BLANK_VALUES


def _more_count(stats, rows) -> int:
    """Siyahıdan kənarda qalan sətir sayı — «+N daha».

    Vidjetin BİRİNCİ rəqəmi konvensiya olaraq həmin siyahının TAM sayıdır
    (növbədə N sillabus, planlanmış N imtahan, əhatədə N qrup…), sətirlər isə
    ``ROW_LIMIT``-ə kəsilir.  Rəqəm tam ədəd deyilsə (status mətni, saat) fərq
    hesablanmır — yanlış «+N» göstərməkdənsə heç nə göstərmək yaxşıdır.
    """
    if not rows or not stats:
        return 0
    try:
        total = int(str(stats[0].get("value", "")).strip())
    except (AttributeError, TypeError, ValueError):
        return 0
    return max(0, total - len(rows))


def _rank(item) -> int:
    """Sıralama açarı — hərəkət gözləyən kart əvvəl, keçid kartı sonda.

    ``sorted`` stabil olduğu üçün eyni rütbədə qurucudakı MƏNALI sıra (şəxsi →
    tədris → idarəetmə) olduğu kimi qalır.
    """
    if item.get("variant") == "link":
        return 3
    if item.get("attention"):
        return 0
    if not item.get("is_empty"):
        return 1
    return 2


def decorate(widgets: list) -> list:
    """Törəmə sahələri yazır və siyahını prioritetə görə sıralayır."""
    for item in widgets:
        stats = item.get("stats") or []
        rows = item.get("rows") or []
        item["variant"] = "data" if (stats or rows) else "link"
        item["attention"] = bool(item.get("tone") in ("warning", "danger") and not item.get("is_empty"))
        item["more_count"] = _more_count(stats, rows)
    return sorted(widgets, key=_rank)


def _headline_stat(stats):
    """Kartın hero-ya çıxa bilən rəqəmi (yoxdursa ``None``).

    YALNIZ BİRİNCİ rəqəmə baxılır: qurucularda konvensiya budur ki, vidjetin
    əsas göstəricisi birinci gəlir (növbədə N sillabus, bu gün N dərs…).  Sonrakı
    rəqəmlərə keçmək cazibədar görünür, amma yanlış cavab verir — məsələn
    «Davamiyyət» kartında qayıb 0 olanda ikinci rəqəm PROQRAMIN LİMİTİdir
    («25%») və hero zolağında sanki tələbənin qayıbı kimi oxunur.

    Üç şərt: dəyər boş/sıfır olmamalı, RƏQƏMLƏ başlamalı (status mətni — «yoxdur»,
    «tapşırıq yoxdur» — zolağa düşməsin) və qısa olmalıdır.
    """
    if not stats:
        return None
    item = stats[0]
    value = str(item.get("value", "")).strip()
    if _is_blank(value) or len(value) > MAX_HERO_VALUE_LEN or not value[:1].isdigit():
        return None
    return item


def hero_tiles(widgets: list) -> list:
    """Rolun ƏN VACİB 2–4 rəqəmi — `ems_ui/_kpi_row.html` müqaviləsində.

    Mənbə sıralanmış vidjet siyahısıdır, yəni «hansı rəqəm vacibdir» sualına
    cavabı `_rank` verir: əvvəl hərəkət gözləyənlər, sonra dolu kartlar.  Ayrıca
    rol cədvəli SAXLANMIR — yeni rol/vidjet əlavə olunanda zolaq özü uyğunlaşır.
    """
    tiles = []
    for item in widgets:
        if item.get("variant") == "link":
            continue
        picked = _headline_stat(item.get("stats") or [])
        if picked is None:
            continue
        note = " · ".join(str(part) for part in (picked.get("label"), picked.get("note")) if str(part or "").strip())
        tiles.append(
            {
                "label": item.get("title"),
                "value": picked.get("value"),
                "note": note,
                "tone": _HERO_TONE.get(item.get("tone") or "", "accent-primary"),
            }
        )
        if len(tiles) >= MAX_HERO_TILES:
            break
    return tiles if len(tiles) >= MIN_HERO_TILES else []


def count_variant(widgets: list, variant: str) -> int:
    """Şablon üçün sayğac (Django şablonunda siyahı süzgəci yoxdur)."""
    return sum(1 for item in widgets if item.get("variant") == variant)


__all__ = [
    "MAX_HERO_TILES",
    "MAX_HERO_VALUE_LEN",
    "MIN_HERO_TILES",
    "count_variant",
    "decorate",
    "hero_tiles",
]
