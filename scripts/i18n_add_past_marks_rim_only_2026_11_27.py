#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-27: əvvəl yazılmış i/e, q/b və bal yalnız RİM-dədir; profilə baxışda jurnala yazı yoxdur.

``django`` kataloquna beş dildə əlavə edir; AZ msgstr = msgid (açar-üslublu ``action_blocked_journal`` istisna —
onun AZ mətni ayrıca). İdempotent.
İstifadə:  python scripts/i18n_add_past_marks_rim_only_2026_11_27.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_FE = "registrar.journal_full_edit"
_VA = "accounts.view_as"

#: (kontekst, msgid) → (az | None = msgid, en, ru, tr, de)
STRINGS = {
    (
        _FE,
        "Bu dərsdə artıq dəyişdirilə bilməyən q/b, i/e və ya bal var — dərsi silmək, tarixini və ya növünü dəyişmək "
        "olmaz. Dəyişiklik üçün RİM-ə müraciət edib təqdimat yazın.",
    ): (
        None,
        "This lesson already has absences, attendance marks or scores that can no longer be changed — the lesson "
        "cannot be deleted and its date or type cannot be changed. To change it, submit a request to the registrar.",
        "В этом занятии уже есть пропуски, отметки присутствия или баллы, которые больше нельзя изменить — занятие "
        "нельзя удалить, нельзя изменить его дату или тип. Для изменения подайте заявку в отдел учёта.",
        "Bu derste artık değiştirilemeyen devamsızlık, katılım veya puan var — ders silinemez, tarihi veya türü "
        "değiştirilemez. Değişiklik için öğrenci işlerine başvurup dilekçe yazın.",
        "Diese Stunde enthält bereits Fehlzeiten, Anwesenheiten oder Punkte, die nicht mehr geändert werden können — "
        "die Stunde kann weder gelöscht noch in Datum oder Art geändert werden. Stellen Sie dafür einen Antrag beim "
        "Studierendensekretariat.",
    ),
    (
        _FE,
        "Əvvəl yazılmış q/b, i/e və bal bu rejimdə də dəyişmir: q/b və bal yazılandan 15 dəqiqə, i/e 1 gün sonra "
        "donur. Belə qeydi, eləcə də onu daşıyan dərsi silmək və ya növünü dəyişmək yalnız RİM-ə müraciətlə mümkündür.",
    ): (
        None,
        "Absences, attendance and scores written earlier do not change in this mode either: absences and scores "
        "freeze 15 minutes after entry, attendance after 1 day. Changing such an entry, or deleting or re-typing the "
        "lesson that holds it, is only possible through a request to the registrar.",
        "Ранее записанные пропуски, отметки присутствия и баллы в этом режиме тоже не меняются: пропуски и баллы "
        "замораживаются через 15 минут после записи, присутствие — через 1 день. Изменить такую запись, а также "
        "удалить занятие с ней или изменить его тип можно только по заявке в отдел учёта.",
        "Daha önce yazılmış devamsızlık, katılım ve puan bu modda da değişmez: devamsızlık ve puan yazıldıktan 15 "
        "dakika, katılım 1 gün sonra kilitlenir. Böyle bir kaydı değiştirmek, onu taşıyan dersi silmek veya türünü "
        "değiştirmek yalnızca öğrenci işlerine başvuruyla mümkündür.",
        "Früher eingetragene Fehlzeiten, Anwesenheiten und Punkte ändern sich auch in diesem Modus nicht: Fehlzeiten "
        "und Punkte werden 15 Minuten nach dem Eintrag gesperrt, Anwesenheit nach 1 Tag. Einen solchen Eintrag zu "
        "ändern oder die Stunde damit zu löschen bzw. ihre Art zu ändern, ist nur über einen Antrag beim "
        "Studierendensekretariat möglich.",
    ),
    (_VA, "action_blocked_journal"): (
        "Profilə baxış rejimində jurnala (davamiyyət, bal, dərs) yazmaq olmaz. Dəyişikliyi öz hesabınızla edin.",
        "You cannot write to the journal (attendance, scores, lessons) while viewing another profile. Make the "
        "change from your own account.",
        "В режиме просмотра чужого профиля нельзя вносить записи в журнал (посещаемость, баллы, занятия). Внесите "
        "изменение со своей учётной записи.",
        "Profil görüntüleme modunda yoklama defterine (devam, puan, ders) yazılamaz. Değişikliği kendi hesabınızdan "
        "yapın.",
        "Im Profil-Ansichtsmodus kann nicht ins Journal (Anwesenheit, Punkte, Stunden) geschrieben werden. Nehmen Sie "
        "die Änderung über Ihr eigenes Konto vor.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (az, en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": az or msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        if added:
            po.save(path)
            subprocess.run(["msgfmt", "-o", path[:-2] + "mo", path], check=True)
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
