#!/usr/bin/env python3
"""EMSArena i18n — ixtisas şifrinin İKİ NƏSLİ (cari NK 503/2024 + köhnə), 4 dil.

Azərbaycanda ixtisas təsnifatı 2024-cü ildə dəyişdi, ona görə ``Program``-da
iki rəsmi şifr sütunu var (``official_code`` — cari, ``legacy_official_code`` —
əvvəlki nəsil) və hər ikisi istifadəçiyə göstərilir. Bu skript həmin göstərmə
ilə bağlı yeni sətirləri əlavə edir:

* ``registrar.program`` konteksti — ``official_code_pair``-də köhnə şifri
  işarələyən «köhnə» sözü (``6006004 · köhnə 050624``);
* ``registrar.console`` konteksti — proqram formasının iki şifr sahəsinin
  etiketi və izahı.

⚠️ ``makemessages`` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript
yalnız ƏLAVƏ edir və mövcud girişə TOXUNMUR. İdempotentdir.

İstifadə:  python scripts/i18n_fill_program_code_generations.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

#: ``Program.official_code_pair`` — köhnə nəsil şifrin qarşısındakı söz.
_PROGRAM = {
    "köhnə": {"en": "former", "ru": "прежний", "tr": "eski"},
}

_CONSOLE = {
    "Rəsmi ixtisas şifri (cari)": {
        "en": "Official program code (current)",
        "ru": "Официальный код специальности (действующий)",
        "tr": "Resmî program kodu (güncel)",
    },
    "Rəsmi ixtisas şifri (köhnə)": {
        "en": "Official program code (former)",
        "ru": "Официальный код специальности (прежний)",
        "tr": "Resmî program kodu (eski)",
    },
    "CARİ rəsmi dövlət ixtisas şifri (NK 503/2024) — 7 rəqəm, məsələn 6006004. "
    "İstifadəçilərə ixtisas adının yanında bu şifr göstərilir. İxtisas yeni "
    "təsnifatda ləğv olunubsa boş qalır. Eyni şifr bir neçə ixtisasda təkrarlana bilər.": {
        "en": "The CURRENT official state program code (Cabinet decision 503/2024) — 7 digits, for example "
        "6006004. It is shown to users next to the program name. It stays empty if the program was "
        "abolished in the new classification. The same code may repeat across several programs.",
        "ru": "ДЕЙСТВУЮЩИЙ официальный государственный код специальности (постановление 503/2024) — 7 цифр, "
        "например 6006004. Показывается пользователям рядом с названием специальности. Остаётся пустым, "
        "если специальность упразднена в новой классификации. Один и тот же код может повторяться у "
        "нескольких специальностей.",
        "tr": "GÜNCEL resmî devlet program kodu (503/2024 sayılı karar) — 7 hane, örneğin 6006004. "
        "Kullanıcılara program adının yanında gösterilir. Program yeni sınıflandırmada kaldırıldıysa boş "
        "kalır. Aynı kod birden çok programda tekrarlanabilir.",
    },
    "ƏVVƏLKİ nəsil ixtisas şifri — 050XXX bakalavr, 060XXX magistratura. "
    "Köhnə tələbələrin diplomundakı şifrdir; ixtisas yalnız yeni təsnifatda "
    "varsa boş qalır.": {
        "en": "The FORMER generation program code — 050XXX for bachelor, 060XXX for master. This is the code "
        "printed on earlier students' diplomas; it stays empty if the program exists only in the new "
        "classification.",
        "ru": "Код специальности ПРЕЖНЕГО поколения — 050XXX для бакалавриата, 060XXX для магистратуры. "
        "Именно он указан в дипломах прежних студентов; остаётся пустым, если специальность есть только в "
        "новой классификации.",
        "tr": "ÖNCEKİ nesil program kodu — lisans için 050XXX, yüksek lisans için 060XXX. Eski öğrencilerin "
        "diplomalarında yazan koddur; program yalnızca yeni sınıflandırmada varsa boş kalır.",
    },
}

ENTRIES = {
    "registrar.program": _PROGRAM,
    "registrar.console": _CONSOLE,
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n'
            if probe in text:
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
