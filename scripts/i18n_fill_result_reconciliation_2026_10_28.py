"""Tələbənin bal dəqiqləşdirmə məlumatı — beş dildə, idempotent kataloq əlavəsi."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parent.parent
CONTEXT = "accounts.grades_notice"
ENTRIES = {
    "Ballarınız haqqında məlumat": {
        "en": "Information about your grades",
        "ru": "Информация о ваших баллах",
        "tr": "Notlarınız hakkında bilgi",
        "de": "Informationen zu Ihren Noten",
    },
    "Köçürülmüş ballarda mümkün uyğunsuzluqlar İmtahan Mərkəzi ilə dəqiqləşdirilir və təsdiqlənən səhvlər düzəldilir. "
    "Fərq görsəniz, narahat olmayın: fənni və semestri qeyd edərək İmtahan Mərkəzinə müraciət edin.": {
        "en": "Possible discrepancies in transferred grades are being checked with the Examination Centre, "
        "and confirmed errors are being corrected. If you notice a difference, do not worry: "
        "contact the Examination Centre and specify the subject and semester.",
        "ru": "Возможные расхождения в перенесённых баллах уточняются с Экзаменационным центром, "
        "а подтверждённые ошибки исправляются. Если заметите различие, не беспокойтесь: "
        "обратитесь в Экзаменационный центр, указав предмет и семестр.",
        "tr": "Aktarılan notlardaki olası tutarsızlıklar Sınav Merkezi ile kontrol edilmekte ve doğrulanan "
        "hatalar düzeltilmektedir. Bir fark görürseniz endişelenmeyin: "
        "dersi ve dönemi belirterek Sınav Merkezine başvurun.",
        "de": "Mögliche Unstimmigkeiten bei übertragenen Noten werden mit dem Prüfungszentrum geklärt, "
        "und bestätigte Fehler werden korrigiert. Falls Sie eine Abweichung bemerken, bleiben Sie unbesorgt: "
        "Wenden Sie sich unter Angabe des Fachs und Semesters an das Prüfungszentrum.",
    },
}


def quote(text):
    return json.dumps(text, ensure_ascii=False)


def fill(language):
    path = BASE / "locale" / language / "LC_MESSAGES" / "django.po"
    catalog = polib.pofile(path)
    additions = []
    for message, translations in ENTRIES.items():
        if catalog.find(message, msgctxt=CONTEXT) is None:
            translation = message if language == "az" else translations[language]
            additions.append(f"msgctxt {quote(CONTEXT)}\nmsgid {quote(message)}\nmsgstr {quote(translation)}\n")
    if additions:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "\n".join(additions))
    polib.pofile(path).save_as_mofile(str(path.with_suffix(".mo")))
    print(f"{language}: +{len(additions)} entries")


if __name__ == "__main__":
    for language in ("az", "en", "ru", "tr", "de"):
        fill(language)
