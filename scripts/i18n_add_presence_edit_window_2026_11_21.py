#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-21: i/e xanasının dəyişmə müddəti (Sistem tənzimləmələri → Elektron jurnal).

Sahib (RİM rəhbəri): «i/e qoyulandan sonra 1 gün ərzində müəllim onu dəyişə bilsin, sonra q/b kimi donsun … hamısını
sistem tənzimləmələrindən idarə edim». ``django`` kataloquna (``core.runtime_settings`` +
``registrar.journal_timing`` + ``registrar.journal``) beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_presence_edit_window_2026_11_21.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_RS = "core.runtime_settings"
_JT = "registrar.journal_timing"
_J = "registrar.journal"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _RS, "i/e xanası müddət bitəndə donur"): (
        "Present marks freeze when their time runs out",
        "Отметка «присутствовал» замораживается по истечении срока",
        "Katıldı işareti süre dolunca kilitlenir",
        "Anwesenheitsvermerk wird nach Ablauf der Frist gesperrt",
    ),
    (
        "django",
        _RS,
        "Yandırılıbsa müəllimin yazdığı i/e aşağıdakı müddət ərzində dəyişir, sonra q/b kimi donur — köhnə sistemdən "
        "köçürülmüş i/e də. Sonra yalnız RİM-in rəsmi düzəlişi. Söndürüləndə i/e dərsin yazma müddəti ərzində həmişə "
        "dəyişir. Boş xanaya yazma qaydası dəyişmir.",
    ): (
        "When on, a present mark written by the teacher can be changed during the period below, then it freezes like an "
        "absence — including present marks migrated from the old system. After that only an official RIM correction. "
        "When off, present marks can always be changed while the lesson is open for entry. The rule for filling empty "
        "cells does not change.",
        "Если включено, отметку «присутствовал», поставленную преподавателем, можно изменить в течение указанного ниже "
        "срока, затем она замораживается, как пропуск, — в том числе перенесённая из старой системы. Дальше только "
        "официальное исправление РИМ. Если выключено, отметку «присутствовал» можно менять всегда, пока занятие открыто "
        "для записи. Правило заполнения пустых ячеек не меняется.",
        "Açıksa öğretmenin yazdığı katıldı işareti aşağıdaki süre içinde değiştirilebilir, sonra devamsızlık gibi "
        "kilitlenir — eski sistemden aktarılanlar da. Sonrasında yalnızca RİM'in resmî düzeltmesi. Kapalıysa katıldı "
        "işareti dersin yazma süresi boyunca her zaman değiştirilebilir. Boş hücreye yazma kuralı değişmez.",
        "Wenn aktiviert, kann ein von der Lehrkraft eingetragener Anwesenheitsvermerk innerhalb der unten genannten Frist "
        "geändert werden und wird danach wie eine Abwesenheit gesperrt — auch aus dem alten System übernommene. Danach "
        "nur noch eine offizielle Korrektur durch das RIM. Wenn deaktiviert, ist der Anwesenheitsvermerk immer änderbar, "
        "solange die Stunde für Einträge offen ist. Die Regel für leere Zellen ändert sich nicht.",
    ),
    ("django", _RS, "i/e-ni dəyişmə müddəti"): (
        "Time to change present marks",
        "Срок изменения отметки «присутствовал»",
        "Katıldı işaretini değiştirme süresi",
        "Frist zum Ändern des Anwesenheitsvermerks",
    ),
    (
        "django",
        _RS,
        "Müəllimin yazdığı i/e İLK yazılışdan bu qədər dəqiqə sonra donur (defolt 1440 dəqiqə = 1 gün). Müddət ərzində "
        "i/e q/b-yə və ya bala dəyişdirilsə, yeni q/b və balın öz müddəti (yuxarıdakı sətir) dəyişiklik anından "
        "başlayır. Yalnız yuxarıdakı açar yandırılıbsa işləyir.",
    ): (
        "A present mark written by the teacher freezes this many minutes after it was FIRST written (default 1440 "
        "minutes = 1 day). If it is changed to an absence or a score within this time, the new absence or score gets "
        "its own time (the row above) from the moment of the change. Works only when the switch above is on.",
        "Отметка «присутствовал», поставленная преподавателем, замораживается через столько минут после ПЕРВОЙ записи "
        "(по умолчанию 1440 минут = 1 день). Если в течение этого срока её заменили на пропуск или балл, у нового "
        "пропуска или балла свой срок (строка выше) с момента изменения. Работает, только если переключатель выше "
        "включён.",
        "Öğretmenin yazdığı katıldı işareti İLK yazılıştan bu kadar dakika sonra kilitlenir (varsayılan 1440 dakika = 1 "
        "gün). Bu süre içinde devamsızlığa veya puana çevrilirse, yeni devamsızlık veya puanın kendi süresi (üstteki "
        "satır) değişiklik anından başlar. Yalnızca üstteki anahtar açıksa çalışır.",
        "Ein von der Lehrkraft eingetragener Anwesenheitsvermerk wird so viele Minuten nach dem ERSTEN Eintrag gesperrt "
        "(Standard 1440 Minuten = 1 Tag). Wird er in dieser Zeit in eine Abwesenheit oder Note geändert, gilt für den "
        "neuen Eintrag ab dem Zeitpunkt der Änderung dessen eigene Frist (Zeile oben). Gilt nur, wenn der Schalter oben "
        "aktiviert ist.",
    ),
    ("django", _RS, "q/b və balı dəyişmə müddəti"): (
        "Time to change absences and scores",
        "Срок изменения пропусков и баллов",
        "Devamsızlık ve puanı değiştirme süresi",
        "Frist zum Ändern von Abwesenheiten und Noten",
    ),
    (
        "django",
        _RS,
        "Müəllimin yazdığı q/b və bal İLK yazılışdan bu qədər dəqiqə sonra donur (defolt 15); sonra yalnız RİM-in "
        "rəsmi düzəlişi. Köçürülmüş q/b və bal həmişə kilidlidir. i/e üçün ayrıca müddət aşağıdakı sətirdədir.",
    ): (
        "Absences and scores written by the teacher freeze this many minutes after they were FIRST written (default "
        "15); after that only an official RIM correction. Migrated absences and scores are always locked. Present marks "
        "have their own time in the row below.",
        "Пропуски и баллы, поставленные преподавателем, замораживаются через столько минут после ПЕРВОЙ записи (по "
        "умолчанию 15); дальше только официальное исправление РИМ. Перенесённые пропуски и баллы всегда закрыты. Для "
        "отметки «присутствовал» отдельный срок — в строке ниже.",
        "Öğretmenin yazdığı devamsızlık ve puan İLK yazılıştan bu kadar dakika sonra kilitlenir (varsayılan 15); "
        "sonrasında yalnızca RİM'in resmî düzeltmesi. Aktarılan devamsızlık ve puanlar her zaman kilitlidir. Katıldı "
        "işaretinin ayrı süresi alttaki satırdadır.",
        "Von der Lehrkraft eingetragene Abwesenheiten und Noten werden so viele Minuten nach dem ERSTEN Eintrag gesperrt "
        "(Standard 15); danach nur noch eine offizielle Korrektur durch das RIM. Übernommene Abwesenheiten und Noten "
        "sind immer gesperrt. Für Anwesenheitsvermerke gilt eine eigene Frist in der Zeile unten.",
    ),
    (
        "django",
        _JT,
        "Bu i/e qeydi yazılandan %(w)s keçib və artıq dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə müraciət edib "
        "təqdimat yazın.",
    ): (
        "%(w)s have passed since this present mark was written, so it can no longer be changed. To change it, apply "
        "to the RIM with a written request.",
        "С момента записи этой отметки «присутствовал» прошло %(w)s, её больше нельзя изменить. Для изменения "
        "обратитесь в РИМ с письменным представлением.",
        "Bu katıldı işareti yazılalı %(w)s geçti ve artık değiştirilemez. Değişiklik için RİM'e başvurup yazılı "
        "talep gönderin.",
        "Seit dieser Anwesenheitsvermerk eingetragen wurde, sind %(w)s vergangen; er kann nicht mehr geändert werden. "
        "Für eine Änderung stellen Sie beim RIM einen schriftlichen Antrag.",
    ),
    ("django", _J, "i/e qeydi %(p)s sonra kilidlənir."): (
        "a present mark is locked %(p)s later.",
        "отметка «присутствовал» закрывается через %(p)s.",
        "katıldı işareti %(p)s sonra kilitlenir.",
        "ein Anwesenheitsvermerk wird %(p)s später gesperrt.",
    ),
}


def main():
    for domain in ("django",):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
                if "%(" in msgid:
                    entry.flags.append("python-format")
                po.append(entry)
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
