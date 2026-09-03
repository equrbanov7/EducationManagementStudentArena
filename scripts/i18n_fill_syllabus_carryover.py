#!/usr/bin/env python3
"""EMSArena i18n — sillabus redaktorunun KÖÇÜRÜLMÜŞ MƏZMUN səthi (4 dil). İdempotent.

Redaktor artıq mənbəni olduğu kimi render edir: kataloqda olmayan tədris
metodları, tədris planının 16 həftəsindən uzun cədvəl sətirləri və struktura
sığmayan sərbəst iş mövzuları. Bu sətirlər həmin səthin mətnləridir.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və mövcud girişə TOXUNMUR.
⚠️ Yer tutucular (`%(name)s`) hər dildə EYNİ qalmalıdır — `check_i18n_catalogs`
uyğunsuzluğu runtime `KeyError` riski kimi bloklayır.
⚠️ `Çıxar` / `Geri qaytar` QƏSDƏN işlədilmir: `Geri qaytar` bu kontekstdə artıq
«düzəlişə qaytar» mənasındadır (EN «Return»), `Çıxar` isə kontekstsiz girişlə
toqquşur. Ona görə `Siyahıdan çıxar` / `Bərpa et` seçilib.

İstifadə:  python scripts/i18n_fill_syllabus_carryover.py
"""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_CARRYOVER = {
    # ── Kataloqda olmayan tədris metodları ────────────────────────────────
    "Kataloqda olmayan metodlar": {
        "en": "Methods outside the catalogue",
        "ru": "Методы вне каталога",
        "tr": "Katalog dışı yöntemler",
    },
    "Köhnə sistemdən gəlib — mətn olduğu kimi saxlanılır": {
        "en": "Carried over from the legacy system — the text is kept as it is",
        "ru": "Перенесено из старой системы — текст сохраняется как есть",
        "tr": "Eski sistemden aktarıldı — metin olduğu gibi korunur",
    },
    "Siyahıdan çıxar": {
        "en": "Remove from the list",
        "ru": "Убрать из списка",
        "tr": "Listeden çıkar",
    },
    "Bərpa et": {"en": "Restore", "ru": "Восстановить", "tr": "Geri yükle"},
    # ── Plandan artıq həftə sətirləri ─────────────────────────────────────
    "plandan artıq": {"en": "beyond the plan", "ru": "сверх плана", "tr": "plan dışı"},
    "Köçürülmüş cədvəldə tədris planının %(total)s həftəsindən əlavə %(count)s sətir var. Onlar məzmun "
    "itməsin deyə göstərilir — lazımsız sətirlərin mövzusunu və saatını boşaldın.": {
        "en": "The carried-over table has %(count)s rows beyond the %(total)s weeks of the curriculum plan. They "
        "are shown so that no content is lost — clear the topic and hours of the rows you do not need.",
        "ru": "В перенесённой таблице есть %(count)s строк сверх %(total)s недель учебного плана. Они показаны, "
        "чтобы содержимое не потерялось — очистите тему и часы ненужных строк.",
        "tr": "Aktarılan tabloda öğretim planının %(total)s haftasının dışında %(count)s satır var. İçerik "
        "kaybolmasın diye gösteriliyorlar — gereksiz satırların konusunu ve saatini boşaltın.",
    },
    # ── Strukturdan artıq sərbəst iş mövzuları ────────────────────────────
    "strukturdan artıq": {"en": "beyond the structure", "ru": "сверх структуры", "tr": "yapı dışı"},
    "Seçilmiş struktura sığmayan %(count)s mövzu var. Onlar məzmun itməsin deyə saxlanılır — struktura uyğun "
    "gəlməyənləri boşaldın və ya başqa variant seçin.": {
        "en": "There are %(count)s topics that do not fit the selected structure. They are kept so that no content "
        "is lost — clear the ones that do not fit, or pick another option.",
        "ru": "Есть %(count)s тем, не помещающихся в выбранную структуру. Они сохраняются, чтобы содержимое не "
        "потерялось — очистите лишние или выберите другой вариант.",
        "tr": "Seçilen yapıya sığmayan %(count)s konu var. İçerik kaybolmasın diye korunuyorlar — uymayanları "
        "boşaltın ya da başka bir seçenek belirleyin.",
    },
    "Struktur hələ seçilməyib. Köhnə sistemdən gələn mövzular olduğu kimi saxlanılır — variant seçdikdən sonra "
    "artıq qalanları boşaldın.": {
        "en": "No structure has been selected yet. Topics carried over from the legacy system are kept as they "
        "are — clear the surplus ones after you pick an option.",
        "ru": "Структура ещё не выбрана. Темы, перенесённые из старой системы, сохраняются как есть — очистите "
        "лишние после выбора варианта.",
        "tr": "Yapı henüz seçilmedi. Eski sistemden aktarılan konular olduğu gibi korunur — bir seçenek "
        "belirledikten sonra fazlalıkları boşaltın.",
    },
}

#: ── GİZLİ (DOM-un idarə etmədiyi) açarların GÖRÜNƏN səthi ────────────────
#: `carry_over()` `practical` / `note` dəyərini `data-extra`-da saxlayır, amma
#: onu tamamilə GÖRÜNMƏZ edirdi: müəllim sətri boşaldıb «sildim» sanırdı.
#: `carried_note()` indi həmin açarları insan adı ilə göstərir — etiketlər
#: burada tərcümə olunur (`CARRIED_LABELS`).
_CARRIED_KEYS = {
    "praktiki saat": {"en": "practical hours", "ru": "практические часы", "tr": "uygulama saati"},
    "mənbə qeydi": {"en": "source note", "ru": "заметка источника", "tr": "kaynak notu"},
    "Köhnə sistemdən saxlanılır:": {
        "en": "Kept from the legacy system:",
        "ru": "Сохраняется из старой системы:",
        "tr": "Eski sistemden korunuyor:",
    },
    "Köhnə sistemdən gəlir və olduğu kimi saxlanılır": {
        "en": "Comes from the legacy system and is kept as it is",
        "ru": "Перенесено из старой системы и сохраняется как есть",
        "tr": "Eski sistemden gelir ve olduğu gibi korunur",
    },
}

ENTRIES = {"accounts.syllabus": {**_CARRYOVER, **_CARRIED_KEYS}}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


#: Kataloqdakı BÜTÜN (msgctxt, msgid) cütləri.
#:
#: ⚠️ Sadə `f'msgctxt "…"\nmsgid "…"' in text` yoxlaması YANLIŞDIR: `msgmerge`
#: uzun mətni `msgid ""` + davam sətirləri kimi yazır, tək sətirlik probe onu
#: GÖRMÜR və skript DUBLİKAT əlavə edir — `msgfmt` isə «duplicate message
#: definition» ilə çökür (ölçülüb: 8 giriş × 4 dil).  Ona görə burada .po
#: sətir davamları birləşdirilir və müqayisə DƏYƏR üzərində aparılır.
def existing_ids(text):
    found, ctx, key, buf = set(), None, None, []

    def flush():
        if key == "msgid" and ctx is not None:
            found.add((ctx, "".join(buf)))

    for line in text.split("\n"):
        line = line.strip()
        head = re.match(r'^(msgctxt|msgid|msgid_plural|msgstr)(?:\[\d+\])?\s+"(.*)"$', line)
        if head:
            flush()
            name, value = head.group(1), unesc(head.group(2))
            if name == "msgctxt":
                ctx, key, buf = value, "msgctxt", [value]
            elif name == "msgid":
                key, buf = "msgid", [value]
            else:
                key, buf = name, [value]
                if name == "msgid_plural":
                    pass
            continue
        cont = re.match(r'^"(.*)"$', line)
        if cont and key:
            buf.append(unesc(cont.group(1)))
            continue
        flush()
        if not line or line.startswith("#"):
            if not line:
                ctx = None
            key, buf = None, []
    flush()
    return found


def unesc(value):
    return value.replace('\\"', '"').replace("\\\\", "\\")


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    present = existing_ids(text)
    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in present:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
