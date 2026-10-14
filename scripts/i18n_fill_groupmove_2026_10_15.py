#!/usr/bin/env python3
"""EMSArena i18n — qrupdan çıxarma / uzaqlaşdırma / «Bərpa et» 2026-10-15.

Sahib: «əmr yazma yerində 20 simvol lazım deyil … çıxardığım birini sonra əlavə
edə bilim». Əlavə olunan mətnlər:
  * `ui.dialog` — `_reason_dialog.html`-in «(istəyə bağlı)» etiketi;
  * `accounts.groups` — qrup çekmecəsinin hərəkət dialoqlarının yeni alt başlıqları
    (tələbə hara düşür), «Bərpa et» dialoqu, çıxmış tələbələr qeydi
    (`_groups_registry.html`, `_group_students_drawer.html`, `_movement_extra_fields.html`);
  * `accounts.student_registry` — reyestr alt başlığı + səbəb ipucu (`_student_registry.html`).

msgid AZ cümlədir → az msgstr = msgid. Şablon `{% trans %}` literalındakı `%` kataloqda
`%%` kimi saxlanır (Django `Variable` onu ikiqatlayır) — ona görə «%%d …».

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir (mövcudluq `polib` ilə yoxlanılır — sarılmış uzun msgid-lər də tanınır).
Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_groupmove_2026_10_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

DIALOG = "ui.dialog"
GROUPS = "accounts.groups"
REGISTRY = "accounts.student_registry"

HINT_AZ = (
    "Rəsmi əsas əmrdir (nömrə + tarix). Səbəb istəyə bağlıdır — boş qalsa audit sətrinə əmrin növü və nömrəsi yazılır."
)
HINT = {
    "en": "The official basis is the order (number + date). The reason is optional — if left empty, "
    "the order type and number are written to the audit record.",
    "ru": "Официальное основание — приказ (номер + дата). Причина необязательна — если оставить пустой, "
    "в журнал аудита записываются тип и номер приказа.",
    "tr": "Resmî dayanak emirdir (numara + tarih). Gerekçe isteğe bağlıdır — boş bırakılırsa denetim kaydına "
    "emrin türü ve numarası yazılır.",
    "de": "Die amtliche Grundlage ist der Erlass (Nummer + Datum). Die Begründung ist optional — bleibt sie leer, "
    "werden Art und Nummer des Erlasses im Audit-Eintrag vermerkt.",
}

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    DIALOG: {
        "(istəyə bağlı)": {"en": "(optional)", "ru": "(необязательно)", "tr": "(isteğe bağlı)", "de": "(optional)"},
    },
    REGISTRY: {
        "Universitetin bütün tələbələri: ixtisas, qrup, kurs, forma, maliyyələşmə və akademik status. "
        "Hərəkət əmr nömrəsi və tarixi ilə yazılır; səbəb istəyə bağlıdır.": {
            "en": "All students of the university: specialty, group, year, form, funding and academic status. "
            "A movement is recorded with the order number and date; the reason is optional.",
            "ru": "Все студенты университета: специальность, группа, курс, форма, финансирование и академический "
            "статус. Движение записывается с номером и датой приказа; причина необязательна.",
            "tr": "Üniversitenin tüm öğrencileri: bölüm, grup, sınıf, öğrenim şekli, finansman ve akademik durum. "
            "Hareket emir numarası ve tarihiyle kaydedilir; gerekçe isteğe bağlıdır.",
            "de": "Alle Studierenden der Universität: Fachrichtung, Gruppe, Studienjahr, Form, Finanzierung und "
            "akademischer Status. Eine Bewegung wird mit Erlassnummer und -datum erfasst; die Begründung ist optional.",
        },
        HINT_AZ: HINT,
    },
    GROUPS: {
        HINT_AZ: HINT,
        "Qrupun tələbələri. Akademik məzuniyyətdə və xaric edilmiş tələbələr də burada qalır (süzgəc) və «Bərpa et» "
        "ilə qrupa qaytarıla bilər. Hər hərəkət əmr nömrəsi və tarixi ilə yazılır; tarixçə silinmir.": {
            "en": "Students of the group. Students on academic leave or expelled also stay here (filter) and can be "
            "returned to the group with «Reinstate». Every movement is recorded with the order number and date; "
            "history is never deleted.",
            "ru": "Студенты группы. Студенты в академическом отпуске и отчисленные тоже остаются здесь (фильтр) и могут "
            "быть возвращены в группу кнопкой «Восстановить». Каждое движение записывается с номером и датой "
            "приказа; история не удаляется.",
            "tr": "Grubun öğrencileri. Akademik izindeki ve kaydı silinen öğrenciler de burada kalır (filtre) ve "
            "«Geri al» ile gruba döndürülebilir. Her hareket emir numarası ve tarihiyle kaydedilir; geçmiş silinmez.",
            "de": "Studierende der Gruppe. Beurlaubte und exmatrikulierte Studierende bleiben ebenfalls hier (Filter) "
            "und können mit «Wiederaufnehmen» in die Gruppe zurückgeholt werden. Jede Bewegung wird mit Erlassnummer "
            "und -datum erfasst; der Verlauf wird nie gelöscht.",
        },
        "Tələbə hədəf qrupa köçürülür: bu qrupun siyahısından çıxır və hədəf qrupun çekmecəsində görünür. Köhnə "
        "qrupdakı jurnal qeydiyyatı tarixçəyə keçir, silinmir. Əmr nömrəsi və tarixi məcburidir.": {
            "en": "The student is transferred to the target group: they leave this group's list and appear in the "
            "target group's drawer. Journal enrolment in the old group moves to history and is not deleted. The order "
            "number and date are required.",
            "ru": "Студент переводится в целевую группу: он исчезает из списка этой группы и появляется в панели "
            "целевой группы. Записи журнала в старой группе переходят в историю и не удаляются. Номер и дата приказа "
            "обязательны.",
            "tr": "Öğrenci hedef gruba nakledilir: bu grubun listesinden çıkar ve hedef grubun panelinde görünür. Eski "
            "gruptaki yoklama defteri kaydı geçmişe aktarılır, silinmez. Emir numarası ve tarihi zorunludur.",
            "de": "Die Studierenden werden in die Zielgruppe versetzt: Sie verschwinden aus der Liste dieser Gruppe "
            "und erscheinen im Bereich der Zielgruppe. Die Journaleinschreibung der alten Gruppe wird Teil des "
            "Verlaufs und nicht gelöscht. Erlassnummer und -datum sind Pflicht.",
        },
        "Status «akademik məzuniyyət» olur: tələbə qrupun aktiv siyahısından və cari semestrin açıq jurnallarından "
        "çıxır (qeydiyyatı dondurulur), girişi açıq qalır. Bu çekmecədə «Məzuniyyətdə» süzgəcində və «Tələbə "
        "reyestri»ndə görünür; «Bərpa et» ilə qrupa qaytarılır. Əmr nömrəsi, tarixi və bitmə tarixi məcburidir.": {
            "en": "The status becomes «academic leave»: the student leaves the group's active list and the open "
            "journals of the current semester (enrolment is suspended); sign-in stays open. They are shown in this "
            "drawer under the «On leave» filter and in the «Student registry»; «Reinstate» returns them to the group. "
            "The order number, date and end date are required.",
            "ru": "Статус становится «академический отпуск»: студент выходит из активного списка группы и открытых "
            "журналов текущего семестра (запись приостанавливается), вход остаётся открытым. Он виден в этой панели "
            "в фильтре «В отпуске» и в «Реестре студентов»; кнопка «Восстановить» возвращает его в группу. Номер, "
            "дата приказа и дата окончания обязательны.",
            "tr": "Durum «akademik izin» olur: öğrenci grubun aktif listesinden ve cari dönemin açık yoklama "
            "defterlerinden çıkar (kaydı dondurulur), girişi açık kalır. Bu panelde «İzinde» filtresinde ve «Öğrenci "
            "sicili»nde görünür; «Geri al» ile gruba döndürülür. Emir numarası, tarihi ve bitiş tarihi zorunludur.",
            "de": "Der Status wird «Urlaubssemester»: Die Studierenden verlassen die aktive Gruppenliste und die "
            "offenen Journale des laufenden Semesters (Einschreibung ruht), die Anmeldung bleibt offen. Sie erscheinen "
            "in diesem Bereich unter dem Filter «Beurlaubt» und im «Studierendenregister»; «Wiederaufnehmen» holt sie "
            "in die Gruppe zurück. Erlassnummer, Datum und Enddatum sind Pflicht.",
        },
        "Status «xaric edilib» olur: tələbə qrupun aktiv siyahısından və cari semestrin açıq jurnallarından çıxır, "
        "hesabının girişi bağlanır. Akademik qeyd və qiymət tarixçəsi silinmir — bu çekmecədə «Xaric edilib» "
        "süzgəcində və «Tələbə reyestri»ndə «Rəsmi status» süzgəci ilə tapılır; «Bərpa et» ilə geri qaytarıla bilər. "
        "Əmr nömrəsi və tarixi məcburidir.": {
            "en": "The status becomes «expelled»: the student leaves the group's active list and the open journals of "
            "the current semester, and the account's sign-in is closed. The academic record and grade history are not "
            "deleted — find them in this drawer under the «Expelled» filter and in the «Student registry» with the "
            "«Official status» filter; «Reinstate» can bring them back. The order number and date are required.",
            "ru": "Статус становится «отчислен»: студент выходит из активного списка группы и открытых журналов "
            "текущего семестра, вход в аккаунт закрывается. Академическая запись и история оценок не удаляются — "
            "его можно найти в этой панели в фильтре «Отчислен» и в «Реестре студентов» по фильтру «Официальный "
            "статус»; кнопка «Восстановить» может вернуть его. Номер и дата приказа обязательны.",
            "tr": "Durum «kaydı silindi» olur: öğrenci grubun aktif listesinden ve cari dönemin açık yoklama "
            "defterlerinden çıkar, hesabın girişi kapatılır. Akademik kayıt ve not geçmişi silinmez — bu panelde "
            "«Kaydı silindi» filtresinde ve «Öğrenci sicili»nde «Resmî durum» filtresiyle bulunur; «Geri al» ile geri "
            "döndürülebilir. Emir numarası ve tarihi zorunludur.",
            "de": "Der Status wird «exmatrikuliert»: Die Studierenden verlassen die aktive Gruppenliste und die offenen "
            "Journale des laufenden Semesters, die Anmeldung des Kontos wird gesperrt. Akademischer Datensatz und "
            "Notenverlauf werden nicht gelöscht — zu finden in diesem Bereich unter dem Filter «Exmatrikuliert» und im "
            "«Studierendenregister» über den Filter «Offizieller Status»; «Wiederaufnehmen» kann sie zurückholen. "
            "Erlassnummer und -datum sind Pflicht.",
        },
        "Tələbəni bərpa et (qrupa qaytar)": {
            "en": "Reinstate the student (return to the group)",
            "ru": "Восстановить студента (вернуть в группу)",
            "tr": "Öğrenciyi geri al (gruba döndür)",
            "de": "Studierende wiederaufnehmen (in die Gruppe zurück)",
        },
        "Status yenidən «qeydiyyatlı» olur və tələbə bu qrupun aktiv siyahısına qayıdır: cari semestrin dondurulmuş "
        "jurnal qeydiyyatları bərpa olunur, bağlanmış giriş yenidən açılır. Əmr nömrəsi və tarixi məcburidir.": {
            "en": "The status becomes «enrolled» again and the student returns to this group's active list: suspended "
            "journal enrolments of the current semester are restored and a closed sign-in is reopened. The order "
            "number and date are required.",
            "ru": "Статус снова становится «зачислен», и студент возвращается в активный список этой группы: "
            "приостановленные записи журналов текущего семестра восстанавливаются, закрытый вход снова открывается. "
            "Номер и дата приказа обязательны.",
            "tr": "Durum yeniden «kayıtlı» olur ve öğrenci bu grubun aktif listesine döner: cari dönemin dondurulmuş "
            "yoklama defteri kayıtları geri yüklenir, kapatılmış giriş yeniden açılır. Emir numarası ve tarihi "
            "zorunludur.",
            "de": "Der Status wird wieder «eingeschrieben» und die Studierenden kehren in die aktive Liste dieser "
            "Gruppe zurück: ruhende Journaleinschreibungen des laufenden Semesters werden wiederhergestellt, eine "
            "gesperrte Anmeldung wird wieder geöffnet. Erlassnummer und -datum sind Pflicht.",
        },
        "Bərpa et": {"en": "Reinstate", "ru": "Восстановить", "tr": "Geri al", "de": "Wiederaufnehmen"},
        "%%d qrupdan çıxıb (məzuniyyət / xaric)": {
            "en": "%%d left the group (leave / expelled)",
            "ru": "%%d вышли из группы (отпуск / отчисление)",
            "tr": "%%d gruptan ayrıldı (izin / kayıt silme)",
            "de": "%%d haben die Gruppe verlassen (Urlaub / Exmatrikulation)",
        },
        "Əmr №": {"en": "Order No.", "ru": "Приказ №", "tr": "Emir No.", "de": "Erlass Nr."},
        "Məzuniyyətdə və xaric edilmiş tələbələr qrupun aktiv siyahısında sayılmır, akademik qeydləri və qiymət "
        "tarixçəsi silinmir. «Bərpa et» əmri ilə bu qrupa qaytarılır; «Tələbə reyestri»ndə «Rəsmi status» süzgəci "
        "ilə də tapılır.": {
            "en": "Students on leave or expelled are not counted in the group's active list; their academic records "
            "and grade history are not deleted. A «Reinstate» order returns them to this group; they can also be "
            "found in the «Student registry» with the «Official status» filter.",
            "ru": "Студенты в отпуске и отчисленные не учитываются в активном списке группы, их академические записи "
            "и история оценок не удаляются. Приказ «Восстановить» возвращает их в эту группу; их также можно найти "
            "в «Реестре студентов» по фильтру «Официальный статус».",
            "tr": "İzindeki ve kaydı silinen öğrenciler grubun aktif listesinde sayılmaz, akademik kayıtları ve not "
            "geçmişi silinmez. «Geri al» emriyle bu gruba döndürülür; «Öğrenci sicili»nde «Resmî durum» filtresiyle "
            "de bulunur.",
            "de": "Beurlaubte und exmatrikulierte Studierende zählen nicht zur aktiven Gruppenliste; ihre akademischen "
            "Datensätze und der Notenverlauf werden nicht gelöscht. Ein «Wiederaufnehmen»-Erlass holt sie in diese "
            "Gruppe zurück; im «Studierendenregister» sind sie auch über den Filter «Offizieller Status» zu finden.",
        },
        "Bu tarixə qədər tələbənin statusu «akademik məzuniyyət» olur; qayıdanda çekmecədəki «Bərpa et» ilə qrupa "
        "qaytarılır.": {
            "en": "Until this date the student's status is «academic leave»; on return, «Reinstate» in the drawer "
            "brings them back to the group.",
            "ru": "До этой даты статус студента — «академический отпуск»; по возвращении кнопка «Восстановить» в "
            "панели возвращает его в группу.",
            "tr": "Bu tarihe kadar öğrencinin durumu «akademik izin» olur; dönüşte paneldeki «Geri al» ile gruba "
            "döndürülür.",
            "de": "Bis zu diesem Datum lautet der Status «Urlaubssemester»; bei Rückkehr holt «Wiederaufnehmen» im "
            "Bereich die Studierenden in die Gruppe zurück.",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
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
