#!/usr/bin/env python3
"""EMSArena i18n — kafedralar arası dərs yükü (sahib 2026-10-25).

«Ştat olaraq bir kafedrada, saat hesabı olaraq başqa kafedrada fənn götürüb»: bölgü seçicisində kənar müəllim,
kafedra profilində «Kənar kafedradan» / «başqa kafedrada: N saat», Kadr analitikası, «Dərs yükü faylı»
önizləməsində «Fənn başqa kafedraya aiddir: X». msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud
msgctxt+msgid toxunulmur); sonra .mo polib ilə yığılır.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WORKLOAD = "accounts.workload"
CHAIR_PROFILE = "accounts.chair_profile"
HR = "accounts.hr_analytics"
LOAD = "accounts.workload_load"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


OTHER_HOURS = t(
    "in other departments: %(hours)s h",
    "на других кафедрах: %(hours)s ч",
    "diğer bölümlerde: %(hours)s saat",
    "an anderen Lehrstühlen: %(hours)s Std.",
)

#: (domain, msgctxt) → {msgid: tərcümələr}; msgctxt=None — kontekstsiz gettext.
ENTRIES = {
    ("django", WORKLOAD): {
        "Müəllim axtar…": t("Search teacher…", "Поиск преподавателя…", "Öğretim üyesi ara…", "Lehrkraft suchen…"),
    },
    ("django", CHAIR_PROFILE): {
        "Kənar kafedradan": t(
            "From another department",
            "С другой кафедры",
            "Başka bölümden",
            "Von einem anderen Lehrstuhl",
        ),
        "Ştat: %(chair)s": t(
            "Staff post: %(chair)s",
            "Штатная кафедра: %(chair)s",
            "Kadro: %(chair)s",
            "Planstelle: %(chair)s",
        ),
        "bu kafedrada": t("in this department", "на этой кафедре", "bu bölümde", "an diesem Lehrstuhl"),
        "başqa kafedrada: %(hours)s saat": OTHER_HOURS,
        "+ %(count)d kənar kafedradan (saathesabı)": t(
            "+ %(count)d from other departments (hourly)",
            "+ %(count)d с других кафедр (почасовая)",
            "+ %(count)d başka bölümden (ders saati ücretli)",
            "+ %(count)d von anderen Lehrstühlen (stundenweise)",
        ),
    },
    ("django", HR): {
        "başqa kafedrada: %(hours)s saat": OTHER_HOURS,
        "O cümlədən başqa kafedrada (saat)": t(
            "Of which in other departments (hours)",
            "В том числе на других кафедрах (ч)",
            "Bunun diğer bölümlerdeki kısmı (saat)",
            "Davon an anderen Lehrstühlen (Std.)",
        ),
    },
    ("django", LOAD): {
        "Yoxlanmadı — sətir başqa kafedranındır": t(
            "Not checked — the line belongs to another department",
            "Не проверялось — строка относится к другой кафедре",
            "Kontrol edilmedi — satır başka bölüme ait",
            "Nicht geprüft — die Zeile gehört zu einem anderen Lehrstuhl",
        ),
        "Fənn başqa kafedraya aiddir: %(chair)s — sətir o kafedranın yükündədir, burada yazılmadı": t(
            "The subject belongs to another department: %(chair)s — the line is in that department's load and "
            "was not written here",
            "Предмет относится к другой кафедре: %(chair)s — строка есть в нагрузке этой кафедры, здесь не " "записана",
            "Ders başka bölüme ait: %(chair)s — satır o bölümün yükünde, buraya yazılmadı",
            "Das Fach gehört zu einem anderen Lehrstuhl: %(chair)s — die Zeile steht in dessen Lehrdeputat und "
            "wurde hier nicht eingetragen",
        ),
        "Fənn başqa kafedraya aiddir: %(chair)s — o kafedranın faylı ilə yüklənməlidir": t(
            "The subject belongs to another department: %(chair)s — it must be uploaded with that department's " "file",
            "Предмет относится к другой кафедре: %(chair)s — его нужно загрузить файлом этой кафедры",
            "Ders başka bölüme ait: %(chair)s — o bölümün dosyasıyla yüklenmelidir",
            "Das Fach gehört zu einem anderen Lehrstuhl: %(chair)s — es muss mit dessen Datei hochgeladen werden",
        ),
        "BAŞQA KAFEDRANIN FƏNNİ": t(
            "OTHER DEPARTMENT'S SUBJECT",
            "ПРЕДМЕТ ДРУГОЙ КАФЕДРЫ",
            "BAŞKA BÖLÜMÜN DERSİ",
            "FACH EINES ANDEREN LEHRSTUHLS",
        ),
        "bu kafedraya yazılmır": t(
            "not written to this department",
            "не записывается на эту кафедру",
            "bu bölüme yazılmaz",
            "wird nicht diesem Lehrstuhl zugeordnet",
        ),
    },
    ("djangojs", None): {
        "kənar, ştat: %(chair)s": t(
            "external, staff post: %(chair)s",
            "внешний, штат: %(chair)s",
            "dış, kadro: %(chair)s",
            "extern, Planstelle: %(chair)s",
        ),
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain):
    path = po_path(lang, domain)
    if not os.path.exists(path):
        print(f"{lang}/{domain}: kataloq yoxdur — keçildi")
        return 0
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for (entry_domain, ctx), messages in ENTRIES.items():
        if entry_domain != domain:
            continue
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            ctx_line = f'msgctxt "{esc(ctx)}"\n' if ctx is not None else ""
            blocks.append(f'{flags}{ctx_line}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")
    return added


def compile_mo(lang, domain):
    path = po_path(lang, domain)
    polib.pofile(path).save_as_mofile(path[:-3] + ".mo")


if __name__ == "__main__":
    for locale in LOCALES:
        for catalog in ("django", "djangojs"):
            if fill(locale, catalog):
                compile_mo(locale, catalog)
