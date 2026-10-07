#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-07: müraciət keçidlərinin (``TransitionDenied``) mətnləri.

Kontekst: ``applications.transition`` (``apps/applications/state_machine.py``,
``services/submit.py``, ``services/workflow.py``). Əvvəl mətnlər AZ dilində sərt yazılmışdı —
Elanlardan müraciət (``apps/announcements/services/apply.py``) onları en/ru/tr istifadəçiyə də
olduğu kimi göstərirdi. Kodlar (``TransitionDenied.code``) dəyişməyib.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları `msgfmt` ilə yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_07_applications_transition.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

# (kontekst, az) → (en, ru, tr)
ROWS = {
    "applications.transition": {
        "Naməlum əməl: %(action)s": (
            "Unknown action: %(action)s",
            "Неизвестное действие: %(action)s",
            "Bilinmeyen işlem: %(action)s",
        ),
        "«%(action)s» əməli «%(status)s» statusundan mümkün deyil.": (
            "The “%(action)s” action is not possible from the “%(status)s” status.",
            "Действие «%(action)s» невозможно из статуса «%(status)s».",
            "“%(action)s” işlemi “%(status)s” durumundan yapılamaz.",
        ),
        "Bu əməl üçün mətn məcburidir.": (
            "Text is required for this action.",
            "Для этого действия текст обязателен.",
            "Bu işlem için metin zorunludur.",
        ),
        "Mətn ən azı %(n)s simvol olmalıdır.": (
            "The text must be at least %(n)s characters long.",
            "Текст должен содержать не менее %(n)s символов.",
            "Metin en az %(n)s karakter olmalıdır.",
        ),
        "Müraciət yaratmaq səlahiyyətiniz yoxdur.": (
            "You are not allowed to create applications.",
            "У вас нет права создавать заявки.",
            "Başvuru oluşturma yetkiniz yok.",
        ),
        "Aktiv üzvlüyünüz olmadan müraciət göndərilə bilməz.": (
            "An application cannot be sent without an active membership.",
            "Без активного членства заявку отправить нельзя.",
            "Etkin üyeliğiniz olmadan başvuru gönderilemez.",
        ),
        "Bu müraciət növü sizin üçün açıq deyil.": (
            "This application type is not available to you.",
            "Этот тип заявки вам недоступен.",
            "Bu başvuru türü sizin için açık değil.",
        ),
        "Eyni müraciət az əvvəl göndərilib — siyahıdan onun statusuna baxın.": (
            "The same application was sent a moment ago — check its status in the list.",
            "Такая же заявка была отправлена только что — проверьте её статус в списке.",
            "Aynı başvuru az önce gönderildi — durumunu listeden kontrol edin.",
        ),
        "Seçilmiş şöbə bu təşkilatda aktiv deyil.": (
            "The selected unit is not active in this organization.",
            "Выбранное подразделение не активно в этой организации.",
            "Seçilen birim bu kurumda etkin değil.",
        ),
        "Bu müraciət sizin şöbənizdə deyil.": (
            "This application is not in your unit.",
            "Эта заявка не относится к вашему подразделению.",
            "Bu başvuru sizin biriminizde değil.",
        ),
        "Bu əməli yalnız müraciət sahibi edə bilər.": (
            "Only the applicant can perform this action.",
            "Это действие может выполнить только автор заявки.",
            "Bu işlemi yalnızca başvuru sahibi yapabilir.",
        ),
        "Bu müraciətə qeyd yaza bilməzsiniz.": (
            "You cannot add a note to this application.",
            "Вы не можете добавить примечание к этой заявке.",
            "Bu başvuruya not ekleyemezsiniz.",
        ),
        "Seçilən şəxs bu şöbənin emalçısı deyil.": (
            "The selected person does not handle applications in this unit.",
            "Выбранный сотрудник не обрабатывает заявки этого подразделения.",
            "Seçilen kişi bu birimde başvuruları işleyen biri değil.",
        ),
        "Hədəf şöbə tapılmadı.": (
            "Target unit not found.",
            "Целевое подразделение не найдено.",
            "Hedef birim bulunamadı.",
        ),
        "Hədəf şöbə cari şöbə ilə eyni ola bilməz.": (
            "The target unit cannot be the same as the current unit.",
            "Целевое подразделение не может совпадать с текущим.",
            "Hedef birim mevcut birimle aynı olamaz.",
        ),
    },
}

#: Bu skriptin öz kontekstləri — dəyər həmişə buradakı ilə sinxronlanır.
FORCE = {"applications.transition"}


def _value(lang, az, row):
    return az if lang == "az" else row[LANGS.index(lang) - 1]


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ROWS.items():
        for msgid, row in items.items():
            want = _value(lang, msgid, row)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
            elif entry.msgstr != want and (
                not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete or ctx in FORCE
            ):
                entry.msgstr, entry.obsolete = want, False
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
