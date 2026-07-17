#!/usr/bin/env python3
"""EMSArena i18n — «İmtahan şansı ver» (ikinci şans) + yaratma icazəsi. İdempotent.

2026-07: imtahan mərkəzinin yeni «exam-chance» SPA bölməsi (form + son şanslar
cədvəli), second_chance servis/bildiriş mətnləri, midterm/final yaratma
məhdudiyyəti xətası və yenilənmiş session_detail qeydi 4 dildə doldurulur.

İstifadə:  python scripts/i18n_fill_exam_chance.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CH_CTX = "accounts.exam_chance"

ENTRIES = {
    "profile.section": {
        "İmtahan şansı ver": {
            "en": "Grant exam retake",
            "ru": "Дать шанс на экзамен",
            "tr": "Sınav hakkı ver",
        },
    },
    CH_CTX: {
        "İmtahan şansı ver": {
            "en": "Grant exam retake",
            "ru": "Дать шанс на экзамен",
            "tr": "Sınav hakkı ver",
        },
        "Seçilmiş final/kollokvium imtahanı üzrə tələbəyə və ya bütöv qrupa yenidən cəhd hüququ verin. Sistem avtomatik yeni giriş PIN-i yaradır, finalın köhnə girişini yenidən açır və imtahan tələbənin təyin olunmuş tapşırıqlarında yenidən görünür.": {
            "en": "Grant a retake for the selected final/midterm exam to a student or a whole group. The system automatically issues a new entry PIN, re-opens the final's entry and the exam reappears in the student's assigned tasks.",
            "ru": "Дайте студенту или целой группе повторную попытку по выбранному финальному/промежуточному экзамену. Система автоматически выдаёт новый PIN, заново открывает вход на финал, и экзамен снова появляется в назначенных заданиях студента.",
            "tr": "Seçilen final/vize sınavı için öğrenciye veya tüm gruba yeniden deneme hakkı verin. Sistem otomatik olarak yeni giriş PIN'i oluşturur, finalin girişini yeniden açar ve sınav öğrencinin atanmış görevlerinde yeniden görünür.",
        },
        "Aktiv təşkilat tapılmadı.": {
            "en": "No active organization found.",
            "ru": "Активная организация не найдена.",
            "tr": "Etkin kuruluş bulunamadı.",
        },
        "Bu təşkilatda hələ final/kollokvium imtahanı yoxdur.": {
            "en": "This organization has no final/midterm exams yet.",
            "ru": "В этой организации пока нет финальных/промежуточных экзаменов.",
            "tr": "Bu kuruluşta henüz final/vize sınavı yok.",
        },
        "Yenidən cəhd hüququ": {
            "en": "Retake permission",
            "ru": "Право на повторную попытку",
            "tr": "Yeniden deneme hakkı",
        },
        "İmtahan": {"en": "Exam", "ru": "Экзамен", "tr": "Sınav"},
        "İmtahanı seçin…": {"en": "Select an exam…", "ru": "Выберите экзамен…", "tr": "Sınav seçin…"},
        "Final": {"en": "Final", "ru": "Финал", "tr": "Final"},
        "Kollokvium": {"en": "Midterm", "ru": "Коллоквиум", "tr": "Vize"},
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
        "(bütöv qrupa vermək üçün)": {
            "en": "(to grant to a whole group)",
            "ru": "(чтобы дать всей группе)",
            "tr": "(tüm gruba vermek için)",
        },
        "— Qrup seçilməyib —": {
            "en": "— No group selected —",
            "ru": "— Группа не выбрана —",
            "tr": "— Grup seçilmedi —",
        },
        "Əlavə cəhd sayı": {
            "en": "Extra attempts",
            "ru": "Дополнительные попытки",
            "tr": "Ek deneme sayısı",
        },
        "Adətən 1 — tələbə imtahana bir dəfə də girə bilər.": {
            "en": "Usually 1 — the student can sit the exam once more.",
            "ru": "Обычно 1 — студент сможет сдать экзамен ещё раз.",
            "tr": "Genellikle 1 — öğrenci sınava bir kez daha girebilir.",
        },
        "Tələbələr": {"en": "Students", "ru": "Студенты", "tr": "Öğrenciler"},
        "(istifadəçi adı və ya email — vergül/yeni sətirlə; qrupla birlikdə də olar)": {
            "en": "(username or email — comma/new line; can be combined with a group)",
            "ru": "(имя пользователя или email — через запятую/с новой строки; можно вместе с группой)",
            "tr": "(kullanıcı adı veya e-posta — virgül/yeni satırla; grupla birlikte de olur)",
        },
        "Şans ver": {"en": "Grant retake", "ru": "Дать шанс", "tr": "Hak ver"},
        "Şans veriləndə: cəhd limiti seçilən qədər artır, final/kollokvium üçün YENİ fərdi PIN yaradılır (kabinetdə dərhal görünür), finalın köhnə giriş bileti sıfırlanır və imtahan «Təyin olunmuş tapşırıqlar»da yenidən görünür. Bütün əməliyyat audit jurnalına yazılır.": {
            "en": "When granted: the attempt limit increases by the chosen amount, a NEW personal PIN is issued for final/midterm (immediately visible in the cabinet), the final's old entry ticket is reset and the exam reappears in “Assigned tasks”. The whole operation is written to the audit log.",
            "ru": "При выдаче: лимит попыток увеличивается на выбранное число, для финала/коллоквиума создаётся НОВЫЙ личный PIN (сразу виден в кабинете), старый входной билет финала сбрасывается, и экзамен снова появляется в «Назначенных заданиях». Вся операция записывается в журнал аудита.",
            "tr": "Hak verildiğinde: deneme limiti seçilen kadar artar, final/vize için YENİ kişisel PIN oluşturulur (kabinde hemen görünür), finalin eski giriş bileti sıfırlanır ve sınav «Atanmış görevler»de yeniden görünür. Tüm işlem denetim günlüğüne yazılır.",
        },
        "Son verilən şanslar": {
            "en": "Recently granted retakes",
            "ru": "Недавно выданные шансы",
            "tr": "Son verilen haklar",
        },
        "Tarix": {"en": "Date", "ru": "Дата", "tr": "Tarih"},
        "Tələbə": {"en": "Student", "ru": "Студент", "tr": "Öğrenci"},
        "Cəmi əlavə cəhd": {"en": "Total extra attempts", "ru": "Всего доп. попыток", "tr": "Toplam ek deneme"},
        "Verən": {"en": "Granted by", "ru": "Выдал", "tr": "Veren"},
        "Hələ şans verilməyib.": {
            "en": "No retakes granted yet.",
            "ru": "Шансы пока не выдавались.",
            "tr": "Henüz hak verilmedi.",
        },
        "Bu bölmə yalnız imtahan mərkəzi üçündür.": {
            "en": "This section is only for the exam centre.",
            "ru": "Этот раздел доступен только экзаменационному центру.",
            "tr": "Bu bölüm yalnızca sınav merkezi içindir.",
        },
        "Aktiv təşkilat konteksti tapılmadı.": {
            "en": "No active organization context found.",
            "ru": "Активный контекст организации не найден.",
            "tr": "Etkin kuruluş bağlamı bulunamadı.",
        },
        "İmtahan filtri": {"en": "Exam filter", "ru": "Фильтр экзаменов", "tr": "Sınav filtresi"},
        "Tədris ili": {"en": "Academic year", "ru": "Учебный год", "tr": "Öğretim yılı"},
        "Semestr": {"en": "Semester", "ru": "Семестр", "tr": "Dönem"},
        "Fakültə": {"en": "Faculty", "ru": "Факультет", "tr": "Fakülte"},
        "Kafedra": {"en": "Department", "ru": "Кафедра", "tr": "Bölüm"},
        "Bütün illər": {"en": "All years", "ru": "Все годы", "tr": "Tüm yıllar"},
        "Bütün semestrlər": {"en": "All semesters", "ru": "Все семестры", "tr": "Tüm dönemler"},
        "Bütün fakültələr": {"en": "All faculties", "ru": "Все факультеты", "tr": "Tüm fakülteler"},
        "Bütün kafedralar": {"en": "All departments", "ru": "Все кафедры", "tr": "Tüm bölümler"},
        "İmtahan axtarışı": {"en": "Exam search", "ru": "Поиск экзамена", "tr": "Sınav arama"},
        "İmtahan adı ilə axtar…": {
            "en": "Search by exam title…",
            "ru": "Поиск по названию экзамена…",
            "tr": "Sınav adına göre ara…",
        },
        "Tələbə axtarışı": {"en": "Student search", "ru": "Поиск студента", "tr": "Öğrenci arama"},
        "Qrup, istifadəçi adı və ya ad-soyad…": {
            "en": "Group, username or full name…",
            "ru": "Группа, имя пользователя или ФИО…",
            "tr": "Grup, kullanıcı adı veya ad soyad…",
        },
        "Bu şərtlərə uyğun final/kollokvium imtahanı tapılmadı.": {
            "en": "No final/midterm exams match these filters.",
            "ru": "По заданным условиям финальных/промежуточных экзаменов не найдено.",
            "tr": "Bu koşullara uygun final/vize sınavı bulunamadı.",
        },
        "Axtarış nəticəsi": {"en": "Search results", "ru": "Результаты поиска", "tr": "Arama sonuçları"},
        "işarələdiklərinizə şans veriləcək": {
            "en": "the checked students will receive the retake",
            "ru": "шанс получат отмеченные студенты",
            "tr": "işaretlediğiniz öğrencilere hak verilecek",
        },
        "Nəticə tapılmadı — axtarışı dəyişin.": {
            "en": "No results — change the search.",
            "ru": "Ничего не найдено — измените запрос.",
            "tr": "Sonuç bulunamadı — aramayı değiştirin.",
        },
        "Əlavə tələbələr": {"en": "Additional students", "ru": "Дополнительные студенты", "tr": "Ek öğrenciler"},
        "İmtahan seçin.": {"en": "Select an exam.", "ru": "Выберите экзамен.", "tr": "Sınav seçin."},
        "İstifadəçi tapılmadı və ya bu təşkilatda deyil: %(u)s": {
            "en": "User not found or not in this organization: %(u)s",
            "ru": "Пользователь не найден или не входит в эту организацию: %(u)s",
            "tr": "Kullanıcı bulunamadı veya bu kuruluşta değil: %(u)s",
        },
        "«%(exam)s» üzrə %(n)s tələbəyə +%(extra)s cəhd verildi.": {
            "en": "Granted +%(extra)s attempt(s) to %(n)s student(s) for “%(exam)s”.",
            "ru": "По «%(exam)s» выдано +%(extra)s попыток %(n)s студентам.",
            "tr": "«%(exam)s» için %(n)s öğrenciye +%(extra)s deneme verildi.",
        },
        "Yeni PIN-lər yaradıldı: %(n)s.": {
            "en": "New PINs issued: %(n)s.",
            "ru": "Создано новых PIN: %(n)s.",
            "tr": "Yeni PIN'ler oluşturuldu: %(n)s.",
        },
        "Final girişi yenidən açıldı: %(n)s.": {
            "en": "Final entry re-opened: %(n)s.",
            "ru": "Вход на финал открыт заново: %(n)s.",
            "tr": "Final girişi yeniden açıldı: %(n)s.",
        },
    },
    "exams.second_chance.notification": {
        "İmtahan üçün yenidən şans verildi": {
            "en": "You were granted an exam retake",
            "ru": "Вам дали шанс пересдать экзамен",
            "tr": "Sınav için yeniden hak verildi",
        },
        "«{exam}» imtahanı üzrə sizə yenidən cəhd hüququ verildi. Yeni giriş PIN-iniz kabinetinizdəki tapşırıq kartında görünür.": {
            "en": "You were granted another attempt for the exam “{exam}”. Your new entry PIN is visible on the task card in your cabinet.",
            "ru": "Вам предоставлена повторная попытка по экзамену «{exam}». Новый PIN виден на карточке задания в вашем кабинете.",
            "tr": "«{exam}» sınavı için size yeniden deneme hakkı verildi. Yeni giriş PIN'iniz kabininizdeki görev kartında görünür.",
        },
    },
    "exams.second_chance.error": {
        "Ən azı bir tələbə seçilməlidir.": {
            "en": "Select at least one student.",
            "ru": "Выберите хотя бы одного студента.",
            "tr": "En az bir öğrenci seçilmelidir.",
        },
    },
    "exams.form.exam.error": {
        "secure_exam_category_exam_center_only": {
            "az": "Final və kollokvium imtahanlarını yalnız imtahan mərkəzi yarada bilər.",
            "en": "Only the exam centre can create final and midterm exams.",
            "ru": "Финальные и промежуточные экзамены может создавать только экзаменационный центр.",
            "tr": "Final ve vize sınavlarını yalnızca sınav merkezi oluşturabilir.",
        },
    },
    "exams.final_center.session_detail": {
        "Zal oturumu imtahandan asılı deyil. Tələbə fərdi PIN-i ilə qeydli kompüterdən girəndə bu oturuma qoşulur. Nəzarətçi oturumu başladanda hər kəs öz imtahanına başlayır.": {
            "en": "A room sitting is exam-independent. A student joins it by signing in with their personal PIN from a registered computer. When the invigilator starts the sitting, everyone begins their own exam.",
            "ru": "Сессия зала не привязана к экзамену. Студент подключается к ней, войдя со своим личным PIN с зарегистрированного компьютера. Когда наблюдатель запускает сессию, каждый начинает свой экзамен.",
            "tr": "Salon oturumu sınavdan bağımsızdır. Öğrenci kayıtlı bilgisayardan kişisel PIN'iyle girince bu oturuma katılır. Gözetmen oturumu başlattığında herkes kendi sınavına başlar.",
        },
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = translations.get(lang) if lang != "az" else translations.get("az", msgid)
            if msgstr is None:
                msgstr = msgid
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
