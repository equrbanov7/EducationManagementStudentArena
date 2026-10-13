#!/usr/bin/env python3
"""EMSArena i18n — «Starosta» (2026-10-13 (gecə)).

Əlavə olunan mətnlər:
  * `accounts.group_lead` — qrup reyestrində «Starosta təyin et / dəyiş / götür» (dialoq, xana, xidmət mesajları,
    bildirişlər, ümumi rol axınlarının rədd mesajı);
  * `accounts.my_group` — «Starosta» bölməsinin yeni tab-ları (fənlər, seçmə, birləşmiş dərslər, cədvəl,
    imtahanlar, elanlar) və boş vəziyyətləri;
  * `profile.sidebar` / `accounts.groups` — «Starosta» menyu adı və reyestr sütunu.

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir. Sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_starosta_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

LEAD = "accounts.group_lead"
MG = "accounts.my_group"


def t(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


ENTRIES = {
    "profile.sidebar": {
        "Starosta": t("Group lead", "Староста", "Sınıf temsilcisi"),
    },
    "accounts.groups": {
        "Starosta": t("Group lead", "Староста", "Sınıf temsilcisi"),
    },
    LEAD: {
        "Starosta": t("Group lead", "Староста", "Sınıf temsilcisi"),
        "Qrup tapılmadı və ya arxivdədir.": t(
            "Group not found or archived.", "Группа не найдена или в архиве.", "Grup bulunamadı veya arşivde."
        ),
        "«Baş tələbə» (lead_student) rolu bu təşkilatda yoxdur — standart rollar yüklənməlidir.": t(
            "The «Lead student» (lead_student) role does not exist in this organization — load the default roles.",
            "Роль «Староста» (lead_student) отсутствует в этой организации — загрузите стандартные роли.",
            "Bu kurumda «Sınıf temsilcisi» (lead_student) rolü yok — varsayılan roller yüklenmelidir.",
        ),
        "Starosta yalnız bu qrupun qeydiyyatlı tələbəsi ola bilər.": t(
            "Only an enrolled student of this group can be the group lead.",
            "Старостой может быть только зачисленный студент этой группы.",
            "Sınıf temsilcisi yalnızca bu grubun kayıtlı öğrencisi olabilir.",
        ),
        "Özünüzü starosta təyin edə bilməzsiniz.": t(
            "You cannot appoint yourself as group lead.",
            "Нельзя назначить старостой самого себя.",
            "Kendinizi sınıf temsilcisi olarak atayamazsınız.",
        ),
        "%(name)s artıq bu qrupun starostasıdır.": t(
            "%(name)s is already the lead of this group.",
            "%(name)s уже является старостой этой группы.",
            "%(name)s zaten bu grubun sınıf temsilcisi.",
        ),
        "Starosta vəzifəniz başa çatdı": t(
            "Your group lead role has ended",
            "Ваши полномочия старосты завершены",
            "Sınıf temsilciliği göreviniz sona erdi",
        ),
        "«%(group)s» qrupunun starostası artıq %(name)s-dir.": t(
            "The lead of group «%(group)s» is now %(name)s.",
            "Старостой группы «%(group)s» теперь является %(name)s.",
            "«%(group)s» grubunun sınıf temsilcisi artık %(name)s.",
        ),
        "Siz qrupun starostası təyin olundunuz": t(
            "You have been appointed group lead", "Вы назначены старостой группы", "Grup temsilcisi olarak atandınız"
        ),
        "«%(group)s» qrupunun starostası təyin olundunuz. Kabinetdə «Starosta» bölməsi açıldı: qrupun fənləri, "
        "seçmə fənlər, birləşmiş dərslər, cədvəl, imtahanlar və elanlar.": t(
            "You have been appointed lead of group «%(group)s». A «Group lead» section is now open in your cabinet: "
            "the group's subjects, electives, joint lessons, timetable, exams and announcements.",
            "Вы назначены старостой группы «%(group)s». В кабинете открыт раздел «Староста»: предметы группы, "
            "элективы, объединённые занятия, расписание, экзамены и объявления.",
            "«%(group)s» grubunun temsilcisi olarak atandınız. Kabinette «Sınıf temsilcisi» bölümü açıldı: grubun "
            "dersleri, seçmeli dersler, birleşik dersler, ders programı, sınavlar ve duyurular.",
        ),
        "Bu qrupun starostası yoxdur.": t(
            "This group has no lead.", "У этой группы нет старосты.", "Bu grubun sınıf temsilcisi yok."
        ),
        "«%(group)s» qrupunun starostası vəzifəsindən götürüldünüz.": t(
            "You have been removed as lead of group «%(group)s».",
            "Вы сняты с должности старосты группы «%(group)s».",
            "«%(group)s» grubunun temsilciliğinden alındınız.",
        ),
        "Qrupun starostası": t("Group lead", "Староста группы", "Grup temsilcisi"),
        "Starosta qrupun qeydiyyatlı tələbələrindən seçilir və kabinetində «Starosta» bölməsi açılır: qrupun "
        "fənləri, seçmə fənlər, birləşmiş dərslər, cədvəl, imtahanlar, elanlar.": t(
            "The group lead is chosen from the group's enrolled students and gets a «Group lead» section in the "
            "cabinet: subjects, electives, joint lessons, timetable, exams, announcements.",
            "Староста выбирается из зачисленных студентов группы, в его кабинете открывается раздел «Староста»: "
            "предметы, элективы, объединённые занятия, расписание, экзамены, объявления.",
            "Sınıf temsilcisi grubun kayıtlı öğrencilerinden seçilir ve kabinetinde «Sınıf temsilcisi» bölümü "
            "açılır: dersler, seçmeli dersler, birleşik dersler, program, sınavlar, duyurular.",
        ),
        "Təyin et": t("Appoint", "Назначить", "Ata"),
        "Starostanı götür": t("Remove group lead", "Снять старосту", "Temsilciyi görevden al"),
        "Əməl audit jurnalına yazılır, tələbəyə bildiriş gedir.": t(
            "The action is recorded in the audit log and the student is notified.",
            "Действие записывается в журнал аудита, студент получает уведомление.",
            "İşlem denetim kaydına yazılır, öğrenciye bildirim gider.",
        ),
        "Götür": t("Remove", "Снять", "Görevden al"),
        "qrupda deyil": t("not in group", "не в группе", "grupta değil"),
        "bir neçə starosta": t("several leads", "несколько старост", "birden fazla temsilci"),
        "Qrup": t("Group", "Группа", "Grup"),
        "Hazırkı starosta:": t("Current lead:", "Текущий староста:", "Mevcut temsilci:"),
        "Yeni starosta": t("New group lead", "Новый староста", "Yeni temsilci"),
        "Tələbə adı ilə axtar…": t("Search by student name…", "Поиск по имени студента…", "Öğrenci adıyla ara…"),
        "Uyğun tələbə tapılmadı": t("No matching student", "Студент не найден", "Eşleşen öğrenci bulunamadı"),
        "Tələbə seçin": t("Select a student", "Выберите студента", "Öğrenci seçin"),
        "Yalnız bu qrupun qeydiyyatlı tələbələri. Yeni starosta təyin olunanda əvvəlki avtomatik götürülür; hər "
        "ikisinə bildiriş gedir.": t(
            "Only enrolled students of this group. Appointing a new lead removes the previous one automatically; "
            "both are notified.",
            "Только зачисленные студенты этой группы. При назначении нового старосты прежний снимается "
            "автоматически; оба получают уведомление.",
            "Yalnızca bu grubun kayıtlı öğrencileri. Yeni temsilci atanınca önceki otomatik olarak görevden alınır; "
            "ikisine de bildirim gider.",
        ),
        "Qeyd (istəyə bağlı)": t("Note (optional)", "Примечание (необязательно)", "Not (isteğe bağlı)"),
        "Məs.: qrup yığıncağının qərarı ilə": t(
            "E.g.: by decision of the group meeting",
            "Напр.: по решению собрания группы",
            "Örn.: grup toplantısı kararıyla",
        ),
        "Tələbə qrupda qalır, yalnız starostalıq və «Starosta» bölməsi bağlanır. Sonra yeni starosta təyin edə "
        "bilərsiniz.": t(
            "The student stays in the group; only the lead role and the «Group lead» section are closed. You can "
            "appoint a new lead afterwards.",
            "Студент остаётся в группе; закрываются только полномочия старосты и раздел «Староста». Затем можно "
            "назначить нового старосту.",
            "Öğrenci grupta kalır; yalnızca temsilcilik ve «Sınıf temsilcisi» bölümü kapanır. Ardından yeni "
            "temsilci atayabilirsiniz.",
        ),
        "Starosta təyin olunmayıb": t("No group lead appointed", "Староста не назначен", "Temsilci atanmadı"),
        "Bu qrupun qeydiyyatlı tələbəsi deyil — bölmə ona açılmır. Yenisini təyin edin.": t(
            "Not an enrolled student of this group — the section is closed for them. Appoint a new lead.",
            "Не является зачисленным студентом группы — раздел для него закрыт. Назначьте нового старосту.",
            "Bu grubun kayıtlı öğrencisi değil — bölüm ona kapalı. Yeni temsilci atayın.",
        ),
        "Qrupda bir neçə aktiv starosta var — birini təyin edin, digərləri avtomatik götürüləcək.": t(
            "The group has several active leads — appoint one, the others will be removed automatically.",
            "В группе несколько активных старост — назначьте одного, остальные будут сняты автоматически.",
            "Grupta birden fazla aktif temsilci var — birini atayın, diğerleri otomatik görevden alınacak.",
        ),
        "Starosta təyin et": t("Appoint group lead", "Назначить старосту", "Temsilci ata"),
        "Starostanı dəyiş": t("Change group lead", "Сменить старосту", "Temsilciyi değiştir"),
        "Aktiv təşkilat tapılmadı.": t(
            "Active organization not found.", "Активная организация не найдена.", "Aktif kurum bulunamadı."
        ),
        "Starosta təyin etmək üçün `unit.group_manage` və ya `role.assign` səlahiyyəti lazımdır.": t(
            "Appointing a group lead requires the `unit.group_manage` or `role.assign` permission.",
            "Для назначения старосты нужно право `unit.group_manage` или `role.assign`.",
            "Temsilci atamak için `unit.group_manage` veya `role.assign` yetkisi gerekir.",
        ),
        "Qrup tapılmadı və ya əhatənizdə deyil.": t(
            "Group not found or outside your scope.",
            "Группа не найдена или вне вашей области.",
            "Grup bulunamadı veya kapsamınızda değil.",
        ),
        "«%(group)s» qrupunun starostası dəyişdi: %(old)s → %(new)s.": t(
            "Lead of group «%(group)s» changed: %(old)s → %(new)s.",
            "Староста группы «%(group)s» сменён: %(old)s → %(new)s.",
            "«%(group)s» grubunun temsilcisi değişti: %(old)s → %(new)s.",
        ),
        "%(name)s «%(group)s» qrupunun starostası təyin edildi.": t(
            "%(name)s appointed lead of group «%(group)s».",
            "%(name)s назначен(а) старостой группы «%(group)s».",
            "%(name)s, «%(group)s» grubunun temsilcisi olarak atandı.",
        ),
        "%(name)s «%(group)s» qrupunun starostası vəzifəsindən götürüldü.": t(
            "%(name)s removed as lead of group «%(group)s».",
            "%(name)s снят(а) с должности старосты группы «%(group)s».",
            "%(name)s, «%(group)s» grubunun temsilciliğinden alındı.",
        ),
        "Naməlum əməl.": t("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
        "Starosta «Qruplar» reyestrindən təyin olunur: qrupun tələbələri → «Starosta təyin et».": t(
            "Group leads are appointed in the «Groups» registry: group students → «Appoint group lead».",
            "Староста назначается в реестре «Группы»: студенты группы → «Назначить старосту».",
            "Temsilci «Gruplar» kaydından atanır: grubun öğrencileri → «Temsilci ata».",
        ),
    },
    MG: {
        "Siz bu qrupun starostasısınız: qrupun fənləri, seçmə fənlər, başqa qruplarla birləşmiş dərslər, cədvəl, "
        "imtahanlar və elanlar burada bir yerdədir. Qrup yoldaşlarının balı və davamiyyəti göstərilmir — davamiyyət "
        "yalnız özünüzə aiddir.": t(
            "You are this group's lead: the group's subjects, electives, lessons joint with other groups, timetable, "
            "exams and announcements are all here. Classmates' grades and attendance are not shown — attendance is "
            "only your own.",
            "Вы староста этой группы: предметы группы, элективы, занятия, объединённые с другими группами, "
            "расписание, экзамены и объявления собраны здесь. Оценки и посещаемость одногруппников не "
            "показываются — посещаемость только ваша.",
            "Bu grubun temsilcisisiniz: grubun dersleri, seçmeli dersler, diğer gruplarla birleşik dersler, "
            "program, sınavlar ve duyurular burada. Sınıf arkadaşlarının notları ve devamı gösterilmez — devam "
            "yalnızca size aittir.",
        ),
        "Seçmə fənn": t("Elective", "Электив", "Seçmeli ders"),
        "Birləşmiş dərs": t("Joint lesson", "Объединённое занятие", "Birleşik ders"),
        "Yaxın imtahan": t("Upcoming exam", "Ближайший экзамен", "Yaklaşan sınav"),
        "Starosta bölmələri": t("Group lead sections", "Разделы старосты", "Temsilci bölümleri"),
        "Fənlər": t("Subjects", "Предметы", "Dersler"),
        "Seçmə fənlər": t("Electives", "Элективы", "Seçmeli dersler"),
        "Birləşmiş dərslər": t("Joint lessons", "Объединённые занятия", "Birleşik dersler"),
        "Cədvəl": t("Timetable", "Расписание", "Ders programı"),
        "İmtahanlar": t("Exams", "Экзамены", "Sınavlar"),
        "Elanlar": t("Announcements", "Объявления", "Duyurular"),
        "Davamiyyətim": t("My attendance", "Моя посещаемость", "Devamım"),
        "Bu dövr üçün qrupun fənni hələ açılmayıb.": t(
            "No subjects have been opened for the group this term yet.",
            "Для группы в этом периоде предметы ещё не открыты.",
            "Bu dönem için grubun dersi henüz açılmadı.",
        ),
        "Növ": t("Type", "Тип", "Tür"),
        "Müəllim": t("Teacher", "Преподаватель", "Öğretmen"),
        "Kimlərlə": t("Together with", "Вместе с", "Kimlerle"),
        "Qrupdan": t("From group", "Из группы", "Gruptan"),
        "seçmə": t("elective", "электив", "seçmeli"),
        "məcburi": t("mandatory", "обязательный", "zorunlu"),
        "yalnız öz qrupu": t("own group only", "только своя группа", "yalnızca kendi grubu"),
        "hamısı": t("all", "все", "hepsi"),
        "Bu dövrdə qrupun seçmə fənni yoxdur.": t(
            "The group has no electives this term.",
            "У группы в этом периоде нет элективов.",
            "Grubun bu dönemde seçmeli dersi yok.",
        ),
        "Hər seçmə fənni qrupdan kimin götürdüyü — yalnız adlar (bal və davamiyyət göstərilmir).": t(
            "Who in the group takes each elective — names only (grades and attendance are not shown).",
            "Кто из группы выбрал каждый электив — только имена (оценки и посещаемость не показываются).",
            "Her seçmeli dersi gruptan kimin aldığı — yalnızca adlar (not ve devam gösterilmez).",
        ),
        "siz də": t("you too", "и вы", "siz de"),
        "bütün qrup": t("whole group", "вся группа", "tüm grup"),
        "Götürənlər": t("Taken by", "Выбрали", "Alanlar"),
        "Qrup başqa qruplarla birləşmiş dərsdə oxumur və alt qruplara bölünməyib.": t(
            "The group has no lessons joint with other groups and is not split into subgroups.",
            "У группы нет занятий, объединённых с другими группами, и она не разделена на подгруппы.",
            "Grubun diğer gruplarla birleşik dersi yok ve alt gruplara ayrılmamış.",
        ),
        "Bu fənlərdə qrupunuz başqa qrup(lar)la birlikdə oxuyur: ya dərs başqa qrupun jurnalındadır, ya da jurnala "
        "başqa qrupdan tələbə əlavə olunub.": t(
            "In these subjects your group studies together with other group(s): either the lesson is in another "
            "group's journal, or students from another group were added to the journal.",
            "По этим предметам ваша группа занимается вместе с другими: либо занятие в журнале другой группы, "
            "либо в журнал добавлены студенты другой группы.",
            "Bu derslerde grubunuz başka grup(lar)la birlikte okuyor: ya ders başka grubun yoklama defterinde, ya "
            "da deftere başka gruptan öğrenci eklendi.",
        ),
        "Jurnal: öz qrupunuz": t("Journal: your group", "Журнал: ваша группа", "Defter: kendi grubunuz"),
        "Qrupdan gedənlər": t("Attending from the group", "Посещают из группы", "Gruptan katılanlar"),
        "Alt qruplar": t("Subgroups", "Подгруппы", "Alt gruplar"),
        "Tələbələr": t("Students", "Студенты", "Öğrenciler"),
        "Qrupun dərs cədvəli hələ dərc olunmayıb.": t(
            "The group's timetable has not been published yet.",
            "Расписание группы ещё не опубликовано.",
            "Grubun ders programı henüz yayımlanmadı.",
        ),
        "Yaxın 90 gündə qrupa təyin olunmuş imtahan yoxdur.": t(
            "No exams assigned to the group in the next 90 days.",
            "В ближайшие 90 дней экзаменов для группы нет.",
            "Önümüzdeki 90 günde gruba atanmış sınav yok.",
        ),
        "Qrupa, ixtisasa və ya fakültəyə ünvanlanmış aktiv elan yoxdur.": t(
            "No active announcements addressed to the group, specialty or faculty.",
            "Нет активных объявлений для группы, специальности или факультета.",
            "Gruba, bölüme veya fakülteye yönelik aktif duyuru yok.",
        ),
        "Bütün elanlar": t("All announcements", "Все объявления", "Tüm duyurular"),
        "%(group)s qrupunun cari dövr fənləri": t(
            "Current term subjects of group %(group)s",
            "Предметы группы %(group)s в текущем периоде",
            "%(group)s grubunun bu dönemki dersleri",
        ),
        "%(n)s / %(total)s tələbə": t(
            "%(n)s / %(total)s students", "%(n)s / %(total)s студентов", "%(n)s / %(total)s öğrenci"
        ),
        "birgə: %(groups)s": t("joint: %(groups)s", "вместе: %(groups)s", "birlikte: %(groups)s"),
        "Birgə qruplar: %(groups)s": t(
            "Joint groups: %(groups)s", "Совместные группы: %(groups)s", "Birlikte gruplar: %(groups)s"
        ),
        "Jurnal: %(journal)s": t("Journal: %(journal)s", "Журнал: %(journal)s", "Defter: %(journal)s"),
        "Qrupunuz «%(parent)s» qrupunun alt qrupudur — ümumi dərslər ana qrupun jurnalında keçə bilər.": t(
            "Your group is a subgroup of «%(parent)s» — shared lessons may be held in the parent group's journal.",
            "Ваша группа — подгруппа «%(parent)s»; общие занятия могут вестись в журнале основной группы.",
            "Grubunuz «%(parent)s» grubunun alt grubudur — ortak dersler ana grubun defterinde olabilir.",
        ),
        "%(n)s tələbə": t("%(n)s students", "%(n)s студентов", "%(n)s öğrenci"),
        "qrupdan %(n)s tələbə": t(
            "%(n)s students from the group", "%(n)s студентов из группы", "gruptan %(n)s öğrenci"
        ),
        "Son tarix: %(date)s": t("Deadline: %(date)s", "Срок: %(date)s", "Son tarih: %(date)s"),
    },
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
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
