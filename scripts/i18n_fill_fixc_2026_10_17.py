#!/usr/bin/env python3
"""EMSArena i18n — FIX-C (QA-1 / PERF-2 frontend və UX düzəlişləri) 2026-10-17.

Əlavə olunan mətnlər:
  * `profile.statistics` — «Statistika» bölməsinin (presenter / presenter_org / filters / export) BÜTÜN mətnləri:
    kataloqda yalnız şablon açarları var idi, `pgettext("profile.statistics", …)` cümlələri en/ru/tr/de-də
    tərcüməsiz qalırdı (QA-1 F2);
  * `ui.status` — status kataloqunun (`core/ui/status_catalog.py`) tərcüməsiz etiketləri: «Fənlərim» legend-i
    («İmtahana buraxılır», «Limitə yaxın — buraxılır» …), «Gözləmədə olan cavablar» («Gözləmədə», «Yoxlanır»),
    bölgü / audit / apellyasiya statusları (QA-1 F4);
  * `registrar.journal_room` — dərs modalı: otaq fərqləndirici şəkilçiləri və axtarış mətnləri (QA-1 F5);
  * `registrar.journal_exempt`, `profile.subjects` — «Fəndən azad» tələbə üçün boş-hal mətnləri (QA-1 F6).

(«Mənim dərs yüküm» etiketləri — `workload` kontekstində kataloqda ARTIQ var idi; səhv import anında `str()`
ilə dondurmaqda idi, kod düzəldi — burada əlavə yoxdur, QA-1 F3.)

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq `polib`
ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_fixc_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

STX = "profile.statistics"
UIS = "ui.status"
ROOM = "registrar.journal_room"
JEX = "registrar.journal_exempt"
SUBJ = "profile.subjects"

# ctx → msgid → (en, ru, tr, de). az msgstr = msgid.
_RAW = {
    STX: {
        "%(absent)s saat qayıb / %(hours)s saat": (
            "%(absent)s h absent / %(hours)s h",
            "%(absent)s ч пропущено / %(hours)s ч",
            "%(absent)s saat devamsız / %(hours)s saat",
            "%(absent)s Std. gefehlt / %(hours)s Std.",
        ),
        "%(computers)s kompüter · %(capacity)s yer · %(live)s canlı oturum": (
            "%(computers)s computers · %(capacity)s seats · %(live)s live sessions",
            "%(computers)s компьютеров · %(capacity)s мест · %(live)s активных сессий",
            "%(computers)s bilgisayar · %(capacity)s yer · %(live)s canlı oturum",
            "%(computers)s Computer · %(capacity)s Plätze · %(live)s Live-Sitzungen",
        ),
        "%(groups)s qrup · %(instructors)s müəllim · %(period)s": (
            "%(groups)s groups · %(instructors)s instructors · %(period)s",
            "%(groups)s групп · %(instructors)s преподавателей · %(period)s",
            "%(groups)s grup · %(instructors)s öğretmen · %(period)s",
            "%(groups)s Gruppen · %(instructors)s Lehrende · %(period)s",
        ),
        "%(groups)s qrup · %(students)s tələbə": (
            "%(groups)s groups · %(students)s students",
            "%(groups)s групп · %(students)s студентов",
            "%(groups)s grup · %(students)s öğrenci",
            "%(groups)s Gruppen · %(students)s Studierende",
        ),
        "%(n)s cəhd · orta bal %(avg)s": (
            "%(n)s attempts · average score %(avg)s",
            "%(n)s попыток · средний балл %(avg)s",
            "%(n)s deneme · ortalama puan %(avg)s",
            "%(n)s Versuche · Durchschnitt %(avg)s",
        ),
        "%(n)s davamiyyət qeydi": (
            "%(n)s attendance records",
            "%(n)s записей посещаемости",
            "%(n)s devam kaydı",
            "%(n)s Anwesenheitseinträge",
        ),
        "%(n)s fənn · %(credits)s ECTS · keçid %(passed)s/%(graded)s": (
            "%(n)s subjects · %(credits)s ECTS · passed %(passed)s/%(graded)s",
            "%(n)s предм. · %(credits)s ECTS · сдано %(passed)s/%(graded)s",
            "%(n)s ders · %(credits)s ECTS · geçen %(passed)s/%(graded)s",
            "%(n)s Fächer · %(credits)s ECTS · bestanden %(passed)s/%(graded)s",
        ),
        "%(n)s qiymətləndirilmiş fənn": (
            "%(n)s graded subjects",
            "Оценённых предметов: %(n)s",
            "%(n)s notlandırılmış ders",
            "%(n)s bewertete Fächer",
        ),
        "%(programs)s ixtisas · akademik məzuniyyət %(leave)s": (
            "%(programs)s programs · academic leave %(leave)s",
            "%(programs)s специальностей · академический отпуск %(leave)s",
            "%(programs)s program · akademik izin %(leave)s",
            "%(programs)s Studiengänge · Beurlaubung %(leave)s",
        ),
        "Aktiv": ("Active", "Активно", "Etkin", "Aktiv"),
        "Aktiv akademik qeyd yoxdur.": (
            "No active academic records.",
            "Нет активных академических записей.",
            "Etkin akademik kayıt yok.",
            "Keine aktiven Studienakten.",
        ),
        "Aktiv akademik qeydlər (qeydiyyatlı status).": (
            "Active academic records (enrolled status).",
            "Активные академические записи (статус «зачислен»).",
            "Etkin akademik kayıtlar (kayıtlı durum).",
            "Aktive Studienakten (Status „immatrikuliert“).",
        ),
        "Aktiv imtahan zalı yoxdur.": (
            "No active exam halls.",
            "Нет активных экзаменационных залов.",
            "Etkin sınav salonu yok.",
            "Keine aktiven Prüfungsräume.",
        ),
        "Aktiv istifadəçi": ("Active users", "Активные пользователи", "Etkin kullanıcı", "Aktive Nutzer"),
        "Aktiv tələbə qeydi": (
            "Active student records",
            "Активные записи студентов",
            "Etkin öğrenci kaydı",
            "Aktive Studierendendatensätze",
        ),
        "Aktiv təşkilat": ("Active organizations", "Активные организации", "Etkin kurum", "Aktive Organisationen"),
        "Aktiv təşkilat yoxdur.": (
            "No active organizations.",
            "Нет активных организаций.",
            "Etkin kurum yok.",
            "Keine aktiven Organisationen.",
        ),
        "Aktiv üzvlük yoxdur.": (
            "No active memberships.",
            "Нет активных членств.",
            "Etkin üyelik yok.",
            "Keine aktiven Mitgliedschaften.",
        ),
        "Apellyasiya nəticələri": (
            "Appeal outcomes",
            "Результаты апелляций",
            "İtiraz sonuçları",
            "Ergebnisse der Einsprüche",
        ),
        "Açıq": ("Open", "Открыт", "Açık", "Offen"),
        "Açıq apellyasiya": ("Open appeals", "Открытые апелляции", "Açık itirazlar", "Offene Einsprüche"),
        "Bal": ("Score", "Балл", "Puan", "Punkte"),
        "Baxılır": ("Under review", "Рассматривается", "İnceleniyor", "In Bearbeitung"),
        "Bağlı": ("Closed", "Закрыт", "Kapalı", "Geschlossen"),
        "Bağlı jurnal": ("Closed journals", "Закрытые журналы", "Kapalı yoklama defterleri", "Geschlossene Journale"),
        "Başlanğıc": ("Start", "Начало", "Başlangıç", "Beginn"),
        "Başlanğıc tarixi": ("Start date", "Дата начала", "Başlangıç tarihi", "Startdatum"),
        "Bitib": ("Finished", "Завершён", "Bitti", "Beendet"),
        "Cari dövr üçün proses məlumatı yoxdur.": (
            "No process data for the current period.",
            "Нет данных о процессах за текущий период.",
            "Geçerli dönem için süreç verisi yok.",
            "Keine Prozessdaten für den aktuellen Zeitraum.",
        ),
        "Cari dövrdə sizə təyin olunmuş fənn açılışı yoxdur.": (
            "No course offerings are assigned to you in the current period.",
            "В текущем периоде вам не назначено ни одного открытия предмета.",
            "Geçerli dönemde size atanmış ders açılışı yok.",
            "Im aktuellen Zeitraum sind Ihnen keine Lehrveranstaltungen zugewiesen.",
        ),
        "Cəhd": ("Attempt", "Попытка", "Deneme", "Versuch"),
        "Cəmi": ("Total", "Всего", "Toplam", "Gesamt"),
        "Davamiyyət": ("Attendance", "Посещаемость", "Devam", "Anwesenheit"),
        "Dövrdə %(total)s oturum · bitib %(ended)s · ləğv %(cancelled)s": (
            "%(total)s sessions in the period · finished %(ended)s · cancelled %(cancelled)s",
            "Сессий за период: %(total)s · завершено %(ended)s · отменено %(cancelled)s",
            "Dönemde %(total)s oturum · biten %(ended)s · iptal %(cancelled)s",
            "%(total)s Sitzungen im Zeitraum · beendet %(ended)s · abgebrochen %(cancelled)s",
        ),
        "Dövrdə apellyasiya yoxdur.": (
            "No appeals in the period.",
            "Нет апелляций за период.",
            "Dönemde itiraz yok.",
            "Keine Einsprüche im Zeitraum.",
        ),
        "Dövrdə imtahan yoxdur.": (
            "No exams in the period.",
            "Нет экзаменов за период.",
            "Dönemde sınav yok.",
            "Keine Prüfungen im Zeitraum.",
        ),
        "Dərs yükü bölgüsü": (
            "Teaching load distribution",
            "Распределение учебной нагрузки",
            "Ders yükü dağılımı",
            "Verteilung der Lehrbelastung",
        ),
        "Faiz": ("Percent", "Процент", "Yüzde", "Prozent"),
        "Fənlərim (cari dövr)": (
            "My subjects (current period)",
            "Мои предметы (текущий период)",
            "Derslerim (geçerli dönem)",
            "Meine Fächer (aktueller Zeitraum)",
        ),
        "Fənn": ("Subject", "Предмет", "Ders", "Fach"),
        "Fənn açılışı": ("Course offering", "Открытие предмета", "Ders açılışı", "Lehrveranstaltungsangebot"),
        "Gözləyir": ("Pending", "Ожидает", "Bekliyor", "Ausstehend"),
        "Gözləyən tapşırıq": (
            "Pending assignments",
            "Ожидающие задания",
            "Bekleyen ödevler",
            "Ausstehende Aufgaben",
        ),
        "Hamısı": ("All", "Все", "Tümü", "Alle"),
        "Hələ qiymətləndirilmiş semestr yoxdur.": (
            "No graded semester yet.",
            "Пока нет оценённых семестров.",
            "Henüz notlandırılmış dönem yok.",
            "Noch kein bewertetes Semester.",
        ),
        "Jurnal": ("Journal", "Журнал", "Yoklama defteri", "Journal"),
        "Jurnal bağlama": ("Journal closing", "Закрытие журнала", "Yoklama defteri kapatma", "Journalabschluss"),
        "Keçib": ("Passed", "Сдал", "Geçti", "Bestanden"),
        "Keçid faizi": ("Pass rate", "Процент сдачи", "Geçme oranı", "Bestehensquote"),
        "Keçilmiş fənn": ("Passed subjects", "Сданные предметы", "Geçilmiş dersler", "Bestandene Fächer"),
        "Kompüter": ("Computers", "Компьютеры", "Bilgisayar", "Computer"),
        "Kurs": ("Course", "Курс", "Kurs", "Kurs"),
        "Kurslar": ("Courses", "Курсы", "Kurslar", "Kurse"),
        "Kurslarım": ("My courses", "Мои курсы", "Kurslarım", "Meine Kurse"),
        "Kəsilib": ("Failed", "Не сдал", "Kaldı", "Durchgefallen"),
        "LMS kursları": ("LMS courses", "Курсы LMS", "LMS kursları", "LMS-Kurse"),
        "Müəllif olduğunuz imtahan yoxdur.": (
            "You have not authored any exams.",
            "У вас нет экзаменов, автором которых вы являетесь.",
            "Yazarı olduğunuz sınav yok.",
            "Sie haben keine Prüfungen erstellt.",
        ),
        "Nəticə": ("Result", "Результат", "Sonuç", "Ergebnis"),
        "Nəzarət insidentləri": (
            "Proctoring incidents",
            "Инциденты контроля",
            "Gözetim olayları",
            "Aufsichtsvorfälle",
        ),
        "Orta yekun bal (0–100) və keçid — ən yeni semestr yuxarıda.": (
            "Average final score (0–100) and pass rate — newest semester on top.",
            "Средний итоговый балл (0–100) и сдача — новейший семестр сверху.",
            "Ortalama nihai puan (0–100) ve geçme — en yeni dönem üstte.",
            "Durchschnittliche Endpunktzahl (0–100) und Bestehen — neuestes Semester oben.",
        ),
        "Oturum": ("Session", "Сессия", "Oturum", "Sitzung"),
        "Planlaşdırılıb": ("Scheduled", "Запланирован", "Planlandı", "Geplant"),
        "Proses": ("Process", "Процесс", "Süreç", "Prozess"),
        "Proseslərin gedişi": (
            "Process progress",
            "Ход процессов",
            "Süreçlerin ilerlemesi",
            "Fortschritt der Prozesse",
        ),
        "Qaralama": ("Draft", "Черновик", "Taslak", "Entwurf"),
        "Qrup": ("Group", "Группа", "Grup", "Gruppe"),
        "Qruplar üzrə tələbə": (
            "Students by group",
            "Студенты по группам",
            "Gruplara göre öğrenci",
            "Studierende nach Gruppen",
        ),
        "Qəbul edilib": ("Accepted", "Принята", "Kabul edildi", "Angenommen"),
        "Rədd edilib": ("Rejected", "Отклонена", "Reddedildi", "Abgelehnt"),
        "Semestr üzrə nəticə": (
            "Result by semester",
            "Результат по семестрам",
            "Dönem sonucu",
            "Ergebnis je Semester",
        ),
        "Sillabus təsdiqi": (
            "Syllabus approval",
            "Утверждение силлабуса",
            "Ders izlencesi onayı",
            "Genehmigung des Syllabus",
        ),
        "Son imtahan nəticələri": (
            "Latest exam results",
            "Последние результаты экзаменов",
            "Son sınav sonuçları",
            "Letzte Prüfungsergebnisse",
        ),
        "Son imtahanlar": ("Recent exams", "Последние экзамены", "Son sınavlar", "Letzte Prüfungen"),
        "Son tarix": ("End date", "Дата окончания", "Bitiş tarihi", "Enddatum"),
        "Status": ("Status", "Статус", "Durum", "Status"),
        "Tamamlanıb": ("Completed", "Завершено", "Tamamlandı", "Abgeschlossen"),
        "Tarix": ("Date", "Дата", "Tarih", "Datum"),
        "Toplanmış kredit": ("Credits earned", "Набранные кредиты", "Toplanan kredi", "Erworbene Credits"),
        "Tələbə": ("Student", "Студент", "Öğrenci", "Studierende(r)"),
        "Tələbələr": ("Students", "Студенты", "Öğrenciler", "Studierende"),
        "Təsdiqli sillabus": (
            "Approved syllabi",
            "Утверждённые силлабусы",
            "Onaylı ders izlenceleri",
            "Genehmigte Syllabi",
        ),
        "Təşkilat növləri": ("Organization types", "Типы организаций", "Kurum türleri", "Organisationstypen"),
        "Yekun bal daxil edilib": (
            "Final score entered",
            "Итоговый балл внесён",
            "Nihai puan girildi",
            "Endpunktzahl eingetragen",
        ),
        "Yekunlaşmış imtahan cəhdi yoxdur.": (
            "No completed exam attempts.",
            "Нет завершённых попыток экзамена.",
            "Tamamlanmış sınav denemesi yok.",
            "Keine abgeschlossenen Prüfungsversuche.",
        ),
        "Yer": ("Seats", "Мест", "Yer", "Plätze"),
        "Yoxlama": ("Review", "Проверка", "Kontrol", "Korrektur"),
        "Yoxlama növbəsi": ("Review queue", "Очередь проверки", "Kontrol kuyruğu", "Korrekturwarteschlange"),
        "Yoxlanılıb": ("Reviewed", "Проверено", "Kontrol edildi", "Korrigiert"),
        "Yük bölgüsü tamamlanıb": (
            "Load distribution completed",
            "Распределение нагрузки завершено",
            "Yük dağılımı tamamlandı",
            "Lastverteilung abgeschlossen",
        ),
        "Zal": ("Hall", "Зал", "Salon", "Raum"),
        "aktiv %(running)s · planlaşdırılıb %(scheduled)s": (
            "active %(running)s · scheduled %(scheduled)s",
            "активных %(running)s · запланировано %(scheduled)s",
            "etkin %(running)s · planlanan %(scheduled)s",
            "aktiv %(running)s · geplant %(scheduled)s",
        ),
        "bal": ("pts", "б.", "puan", "Pkt."),
        "bölgü davam edir %(n)s": (
            "distribution in progress %(n)s",
            "распределение идёт: %(n)s",
            "dağılım sürüyor %(n)s",
            "Verteilung läuft %(n)s",
        ),
        "cari dövr": ("current period", "текущий период", "geçerli dönem", "aktueller Zeitraum"),
        "cari dövrün açılışları üzrə": (
            "across the current period's offerings",
            "по открытиям текущего периода",
            "geçerli dönemin açılışlarına göre",
            "über die Angebote des aktuellen Zeitraums",
        ),
        "davam edir: %(n)s ECTS": (
            "in progress: %(n)s ECTS",
            "в процессе: %(n)s ECTS",
            "devam ediyor: %(n)s ECTS",
            "laufend: %(n)s ECTS",
        ),
        "dərc olunmuş / cəmi": (
            "published / total",
            "опубликовано / всего",
            "yayımlanan / toplam",
            "veröffentlicht / gesamt",
        ),
        "dərc olunub %(published)s": (
            "published %(published)s",
            "опубликовано %(published)s",
            "yayımlandı %(published)s",
            "veröffentlicht %(published)s",
        ),
        "dərc olunub %(published)s · tələbə %(students)s": (
            "published %(published)s · students %(students)s",
            "опубликовано %(published)s · студентов %(students)s",
            "yayımlandı %(published)s · öğrenci %(students)s",
            "veröffentlicht %(published)s · Studierende %(students)s",
        ),
        "gecikmiş %(late)s · göndərilmiş %(sent)s": (
            "late %(late)s · submitted %(sent)s",
            "просрочено %(late)s · отправлено %(sent)s",
            "geciken %(late)s · gönderilen %(sent)s",
            "verspätet %(late)s · eingereicht %(sent)s",
        ),
        "imtahan %(exams)s · tapşırıq %(tasks)s": (
            "exams %(exams)s · assignments %(tasks)s",
            "экзамены %(exams)s · задания %(tasks)s",
            "sınav %(exams)s · ödev %(tasks)s",
            "Prüfungen %(exams)s · Aufgaben %(tasks)s",
        ),
        "keçid %(rate)s · orta bal %(avg)s": (
            "pass rate %(rate)s · average score %(avg)s",
            "сдача %(rate)s · средний балл %(avg)s",
            "geçme %(rate)s · ortalama puan %(avg)s",
            "Bestehensquote %(rate)s · Durchschnitt %(avg)s",
        ),
        "kəsilmiş %(failed)s · davam edən %(open)s": (
            "failed %(failed)s · ongoing %(open)s",
            "не сдали %(failed)s · в процессе %(open)s",
            "kalan %(failed)s · devam eden %(open)s",
            "durchgefallen %(failed)s · laufend %(open)s",
        ),
        "müəllim %(n)s": ("instructors %(n)s", "преподавателей %(n)s", "öğretmen %(n)s", "Lehrende %(n)s"),
        "növbəti: %(date)s": ("next: %(date)s", "следующий: %(date)s", "sonraki: %(date)s", "nächster: %(date)s"),
        "orta bal %(avg)s": (
            "average score %(avg)s",
            "средний балл %(avg)s",
            "ortalama puan %(avg)s",
            "Durchschnitt %(avg)s",
        ),
        "planlaşdırılıb %(scheduled)s · aktiv %(running)s · bitib %(finished)s": (
            "scheduled %(scheduled)s · active %(running)s · finished %(finished)s",
            "запланировано %(scheduled)s · активно %(running)s · завершено %(finished)s",
            "planlanan %(scheduled)s · etkin %(running)s · biten %(finished)s",
            "geplant %(scheduled)s · aktiv %(running)s · beendet %(finished)s",
        ),
        "proqram tələbi: %(total)s ECTS": (
            "programme requirement: %(total)s ECTS",
            "требование программы: %(total)s ECTS",
            "program gereksinimi: %(total)s ECTS",
            "Studiengangsvorgabe: %(total)s ECTS",
        ),
        "qəbul %(accepted)s · rədd %(rejected)s": (
            "accepted %(accepted)s · rejected %(rejected)s",
            "принято %(accepted)s · отклонено %(rejected)s",
            "kabul %(accepted)s · red %(rejected)s",
            "angenommen %(accepted)s · abgelehnt %(rejected)s",
        ),
        "tələbə": ("students", "студентов", "öğrenci", "Studierende"),
        "tələbə %(students)s · müəllim %(teachers)s · heyət %(staff)s": (
            "students %(students)s · teachers %(teachers)s · staff %(staff)s",
            "студентов %(students)s · преподавателей %(teachers)s · сотрудников %(staff)s",
            "öğrenci %(students)s · öğretmen %(teachers)s · personel %(staff)s",
            "Studierende %(students)s · Lehrende %(teachers)s · Personal %(staff)s",
        ),
        "təsdiq gözləyir %(pending)s": (
            "awaiting approval %(pending)s",
            "ожидает утверждения %(pending)s",
            "onay bekliyor %(pending)s",
            "wartet auf Genehmigung %(pending)s",
        ),
        "təşkilat": ("organizations", "организаций", "kurum", "Organisationen"),
        "universitet %(n)s": ("universities %(n)s", "университетов %(n)s", "üniversite %(n)s", "Universitäten %(n)s"),
        "yoxlanılıb %(checked)s · növbədə %(queue)s": (
            "reviewed %(checked)s · in queue %(queue)s",
            "проверено %(checked)s · в очереди %(queue)s",
            "kontrol edilen %(checked)s · sırada %(queue)s",
            "korrigiert %(checked)s · in Warteschlange %(queue)s",
        ),
        "yüksək/kritik %(severe)s": (
            "high/critical %(severe)s",
            "высокие/критические %(severe)s",
            "yüksek/kritik %(severe)s",
            "hoch/kritisch %(severe)s",
        ),
        "Üzvlər rol üzrə": ("Members by role", "Участники по ролям", "Üyeler role göre", "Mitglieder nach Rolle"),
        "üzv": ("members", "участников", "üye", "Mitglieder"),
        "üzvlük %(n)s": ("memberships %(n)s", "членств %(n)s", "üyelik %(n)s", "Mitgliedschaften %(n)s"),
        "İmtahan": ("Exam", "Экзамен", "Sınav", "Prüfung"),
        "İmtahan cəhdləri": ("Exam attempts", "Попытки экзаменов", "Sınav denemeleri", "Prüfungsversuche"),
        "İmtahan həyat dövrü": (
            "Exam lifecycle",
            "Жизненный цикл экзаменов",
            "Sınav yaşam döngüsü",
            "Prüfungslebenszyklus",
        ),
        "İmtahan mərkəzi": ("Exam center", "Экзаменационный центр", "Sınav merkezi", "Prüfungszentrum"),
        "İmtahan zalları": ("Exam halls", "Экзаменационные залы", "Sınav salonları", "Prüfungsräume"),
        "İmtahanlarım": ("My exams", "Мои экзамены", "Sınavlarım", "Meine Prüfungen"),
        "İxtisaslar üzrə tələbə": (
            "Students by program",
            "Студенты по специальностям",
            "Programlara göre öğrenci",
            "Studierende nach Studiengang",
        ),
        "əvvəlki semestrə görə %(delta)s bal": (
            "%(delta)s pts vs. previous semester",
            "%(delta)s б. к прошлому семестру",
            "önceki döneme göre %(delta)s puan",
            "%(delta)s Pkt. ggü. Vorsemester",
        ),
        # Təşkilat növü etiketləri (presenter_org._ORG_TYPE_LABELS → t(…) dinamik çağırış)
        "Universitet": ("University", "Университет", "Üniversite", "Universität"),
        "Məktəb": ("School", "Школа", "Okul", "Schule"),
        "Kurs mərkəzi": ("Course center", "Курсовой центр", "Kurs merkezi", "Kurszentrum"),
        "Fərdi": ("Individual", "Индивидуальный", "Bireysel", "Einzelperson"),
    },
    UIS: {
        "Baxılır": ("Under review", "Рассматривается", "İnceleniyor", "In Bearbeitung"),
        "Baxış": ("View", "Просмотр", "Görüntüleme", "Ansicht"),
        "Bölüşdürülüb": ("Distributed", "Распределено", "Dağıtıldı", "Verteilt"),
        "Bölüşdürülür": ("Being distributed", "Распределяется", "Dağıtılıyor", "Wird verteilt"),
        "Düzəliş edilib": ("Amended", "Скорректировано", "Düzeltildi", "Geändert"),
        "Dəyişiklik": ("Change", "Изменение", "Değişiklik", "Änderung"),
        "Giriş": ("Login", "Вход", "Giriş", "Anmeldung"),
        "Gözləmədə": ("Pending", "Ожидает", "Beklemede", "Ausstehend"),
        "Köhnə sistemdən": ("From the old system", "Из старой системы", "Eski sistemden", "Aus dem alten System"),
        "Limitə yaxın — buraxılır": (
            "Near the limit — admitted",
            "Близко к лимиту — допущен",
            "Limite yakın — sınava alınıyor",
            "Nahe am Limit — zugelassen",
        ),
        "Qismən qəbul edildi": (
            "Partially accepted",
            "Принято частично",
            "Kısmen kabul edildi",
            "Teilweise angenommen",
        ),
        "Qəbul edildi": ("Accepted", "Принято", "Kabul edildi", "Angenommen"),
        "Rədd": ("Rejection", "Отклонение", "Ret", "Ablehnung"),
        "Rədd edildi": ("Rejected", "Отклонено", "Reddedildi", "Abgelehnt"),
        "Silinmə": ("Deletion", "Удаление", "Silme", "Löschung"),
        "Status hesablanmır": (
            "Status not calculated",
            "Статус не рассчитывается",
            "Durum hesaplanmıyor",
            "Status wird nicht berechnet",
        ),
        "Tapşırıq yoxdur": ("No task", "Задачи нет", "Görev yok", "Keine Aufgabe"),
        "Təsdiqləmə": ("Approval", "Утверждение", "Onaylama", "Genehmigung"),
        "Yaradılma": ("Creation", "Создание", "Oluşturma", "Erstellung"),
        "Yekun təsdiq gözləyir": (
            "Awaiting final approval",
            "Ожидает окончательного утверждения",
            "Nihai onay bekliyor",
            "Wartet auf endgültige Genehmigung",
        ),
        "Yoxlama sorğusu": ("Verification request", "Запрос на проверку", "Doğrulama isteği", "Prüfanfrage"),
        "Yoxlanır": ("Under review", "Проверяется", "İnceleniyor", "In Prüfung"),
        "Çıxış": ("Logout", "Выход", "Çıkış", "Abmeldung"),
        "İmtahana buraxılmır": (
            "Not admitted to the exam",
            "Не допущен к экзамену",
            "Sınava alınmıyor",
            "Nicht zur Prüfung zugelassen",
        ),
        "İmtahana buraxılır": (
            "Admitted to the exam",
            "Допущен к экзамену",
            "Sınava alınıyor",
            "Zur Prüfung zugelassen",
        ),
        "İxrac": ("Export", "Экспорт", "Dışa aktarma", "Export"),
    },
    ROOM: {
        # Eyni nömrəli otaqları ayırd edən şəkilçilər (lesson_rooms._disambiguation_texts)
        "korpus %(value)s": ("building %(value)s", "корпус %(value)s", "bina %(value)s", "Gebäude %(value)s"),
        "mərtəbə %(value)s": ("floor %(value)s", "этаж %(value)s", "kat %(value)s", "Etage %(value)s"),
        "%(value)s yer": ("%(value)s seats", "%(value)s мест", "%(value)s yer", "%(value)s Plätze"),
        "kod %(value)s": ("code %(value)s", "код %(value)s", "kod %(value)s", "Code %(value)s"),
        "Korpus axtar…": ("Search building…", "Поиск корпуса…", "Bina ara…", "Gebäude suchen…"),
        "Uyğun korpus tapılmadı": (
            "No matching building found",
            "Подходящий корпус не найден",
            "Eşleşen bina bulunamadı",
            "Kein passendes Gebäude gefunden",
        ),
        "Otaq nömrəsi ilə axtar…": (
            "Search by room number…",
            "Поиск по номеру аудитории…",
            "Oda numarasıyla ara…",
            "Nach Raumnummer suchen…",
        ),
        "Uyğun otaq tapılmadı": (
            "No matching room found",
            "Подходящая аудитория не найдена",
            "Eşleşen oda bulunamadı",
            "Kein passender Raum gefunden",
        ),
    },
    JEX: {
        "Bu semestrdə jurnalı aktiv fənniniz yoxdur — qeydiyyatda olduğunuz fənlərdən azad edilmisiniz. "
        "Qrupunuz dəyişmir.": (
            "You have no subjects with an active journal this semester — you are exempted from the subjects you "
            "were registered for. Your group does not change.",
            "В этом семестре у вас нет предметов с активным журналом — вы освобождены от предметов, на которые "
            "были зарегистрированы. Ваша группа не меняется.",
            "Bu dönem etkin yoklama defteri olan dersiniz yok — kayıtlı olduğunuz derslerden muaf tutuldunuz. "
            "Grubunuz değişmez.",
            "In diesem Semester haben Sie keine Fächer mit aktivem Journal — Sie sind von den Fächern befreit, für "
            "die Sie angemeldet waren. Ihre Gruppe ändert sich nicht.",
        ),
    },
    SUBJ: {
        "Bu semestrdə aktiv fənniniz yoxdur.": (
            "You have no active subjects this semester.",
            "В этом семестре у вас нет активных предметов.",
            "Bu dönem etkin dersiniz yok.",
            "In diesem Semester haben Sie keine aktiven Fächer.",
        ),
        "Qeydiyyatda olduğunuz fənlərdən azad edilmisiniz (aşağıda). Qrupunuz dəyişmir; sual yaranarsa dekanlığa "
        "müraciət edin.": (
            "You are exempted from the subjects you were registered for (see below). Your group does not change; "
            "contact the dean's office if you have questions.",
            "Вы освобождены от предметов, на которые были зарегистрированы (см. ниже). Ваша группа не меняется; "
            "при вопросах обратитесь в деканат.",
            "Kayıtlı olduğunuz derslerden muaf tutuldunuz (aşağıda). Grubunuz değişmez; sorunuz olursa dekanlığa "
            "başvurun.",
            "Sie sind von den Fächern befreit, für die Sie angemeldet waren (siehe unten). Ihre Gruppe ändert sich "
            "nicht; bei Fragen wenden Sie sich an das Dekanat.",
        ),
    },
}

# ctx → msgid → {lang: msgstr}
ENTRIES = {
    ctx: {msgid: dict(zip(("en", "ru", "tr", "de"), values, strict=True)) for msgid, values in messages.items()}
    for ctx, messages in _RAW.items()
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
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
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
