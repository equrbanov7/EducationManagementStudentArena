#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-27: dekanlıq tələbə hərəkəti + bərpada hədəf qrupun seçilməsi.

``django`` kataloquna beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_dean_office_movement_2026_11_27.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_G = "accounts.groups"
_SR = "accounts.student_registry"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_G, "Bərpa olunacağı qrup"): (
        "Group to reinstate into",
        "Группа восстановления",
        "Geri alınacağı grup",
        "Gruppe der Wiederaufnahme",
    ),
    (
        _G,
        "Defolt — tələbənin köhnə qrupu (aktivdirsə). Köhnə qrup arxivdədirsə və ya tələbə başqa qrupa qayıdırsa, "
        "sizin əhatənizdəki aktiv qruplardan birini seçin: tələbə həmin qrupa köçürülür və onun cari semestr "
        "jurnallarına qoşulur.",
    ): (
        "Default — the student's previous group (if active). If the previous group is archived or the student "
        "returns to another group, choose one of the active groups in your scope: the student is moved to it and "
        "joins its current-semester journals.",
        "По умолчанию — прежняя группа студента (если активна). Если прежняя группа в архиве или студент "
        "возвращается в другую группу, выберите одну из активных групп в вашей зоне: студент переводится в неё и "
        "включается в её журналы текущего семестра.",
        "Varsayılan — öğrencinin eski grubu (aktifse). Eski grup arşivdeyse veya öğrenci başka bir gruba dönüyorsa, "
        "yetki alanınızdaki aktif gruplardan birini seçin: öğrenci o gruba aktarılır ve grubun bu dönemki "
        "yoklama defterlerine eklenir.",
        "Standard — die bisherige Gruppe der/des Studierenden (falls aktiv). Ist die bisherige Gruppe archiviert "
        "oder kehrt die/der Studierende in eine andere Gruppe zurück, wählen Sie eine aktive Gruppe in Ihrem "
        "Bereich: die/der Studierende wird dorthin versetzt und in deren Journale des laufenden Semesters "
        "aufgenommen.",
    ),
    (
        _G,
        "Status yenidən «qeydiyyatlı» olur və tələbə seçdiyiniz qrupun aktiv siyahısına qayıdır (defolt — köhnə "
        "qrupu): həmin qrupun cari semestr jurnallarına qoşulur, bağlanmış giriş yenidən açılır. Əmr nömrəsi və "
        "tarixi məcburidir.",
    ): (
        "The status becomes “enrolled” again and the student returns to the active list of the group you choose "
        "(default — the previous group): they join its current-semester journals and a closed login is reopened. "
        "Order number and date are required.",
        "Статус снова становится «зачислен», студент возвращается в активный список выбранной группы (по "
        "умолчанию — прежней): включается в её журналы текущего семестра, закрытый вход снова открывается. Номер и "
        "дата приказа обязательны.",
        "Durum yeniden «kayıtlı» olur ve öğrenci seçtiğiniz grubun aktif listesine döner (varsayılan — eski grubu): "
        "grubun bu dönemki yoklama defterlerine eklenir, kapatılmış giriş yeniden açılır. Karar numarası ve tarihi "
        "zorunludur.",
        "Der Status wird wieder „immatrikuliert“ und die/der Studierende kehrt in die aktive Liste der gewählten "
        "Gruppe zurück (Standard — die bisherige): sie/er wird in deren Journale des laufenden Semesters "
        "aufgenommen, ein gesperrter Zugang wird wieder geöffnet. Anordnungsnummer und -datum sind Pflicht.",
    ),
    (
        _G,
        "Məzuniyyətdə və xaric edilmiş tələbələr qrupun aktiv siyahısında sayılmır, akademik qeydləri və qiymət "
        "tarixçəsi silinmir. «Bərpa et» əmri ilə bu və ya seçdiyiniz başqa aktiv qrupa qaytarılır; «Tələbə "
        "reyestri»ndə «Rəsmi status» süzgəci ilə də tapılır.",
    ): (
        "Students on leave and expelled students are not counted in the group's active list; their academic "
        "records and grade history are not deleted. The “Reinstate” order returns them to this or another active "
        "group you choose; they can also be found in the “Student registry” with the “Official status” filter.",
        "Студенты в академическом отпуске и отчисленные не учитываются в активном списке группы, их академические "
        "записи и история оценок не удаляются. Приказом «Восстановить» они возвращаются в эту или выбранную вами "
        "другую активную группу; в «Реестре студентов» их можно найти фильтром «Официальный статус».",
        "İzindeki ve kaydı silinen öğrenciler grubun aktif listesinde sayılmaz; akademik kayıtları ve not geçmişi "
        "silinmez. «Geri al» kararıyla bu gruba veya seçtiğiniz başka bir aktif gruba döndürülür; «Öğrenci "
        "kaydı»nda «Resmî durum» filtresiyle de bulunur.",
        "Beurlaubte und exmatrikulierte Studierende zählen nicht zur aktiven Liste der Gruppe; ihre akademischen "
        "Datensätze und Notenhistorie werden nicht gelöscht. Mit der Anordnung „Wiederaufnehmen“ kehren sie in "
        "diese oder eine andere gewählte aktive Gruppe zurück; im „Studierendenregister“ findet man sie über den "
        "Filter „Offizieller Status“.",
    ),
    (
        _SR,
        "Bərpa: tələbənin qayıdacağı qrupu seçin. Köhnə qrupu aktivdirsə, o avtomatik seçilir; arxivdədirsə başqa "
        "aktiv qrup seçin — tələbə həmin qrupun cari semestr jurnallarına qoşulur.",
    ): (
        "Reinstatement: choose the group the student returns to. If the previous group is active it is selected "
        "automatically; if it is archived, choose another active group — the student joins its current-semester "
        "journals.",
        "Восстановление: выберите группу, в которую возвращается студент. Если прежняя группа активна, она "
        "выбирается автоматически; если в архиве — выберите другую активную группу: студент включается в её "
        "журналы текущего семестра.",
        "Geri alma: öğrencinin döneceği grubu seçin. Eski grubu aktifse otomatik seçilir; arşivdeyse başka bir "
        "aktif grup seçin — öğrenci o grubun bu dönemki yoklama defterlerine eklenir.",
        "Wiederaufnahme: Wählen Sie die Gruppe, in die die/der Studierende zurückkehrt. Ist die bisherige Gruppe "
        "aktiv, wird sie automatisch gewählt; ist sie archiviert, wählen Sie eine andere aktive Gruppe — die/der "
        "Studierende wird in deren Journale des laufenden Semesters aufgenommen.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        if added:
            po.save(path)
            subprocess.run(["msgfmt", "-o", path[:-2] + "mo", path], check=True)
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
