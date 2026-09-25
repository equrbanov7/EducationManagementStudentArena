#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: kabinetin «Ana səhifə»si (tələbə/müəllim kartları).

Fənn-fənn davamiyyət («qayıb X / icazə Y saat», status çipləri, limit qaydası),
«Cari ballar» (giriş balı + Midterm), «Bu gün / növbəti dərslər», müəllimin
«Jurnallarım» və «Midterm — bal yazma» kartları, İmtahan Mərkəzinin «Midterm
pəncərəsi», «Müraciətlər» (açıq + cavabınızı gözləyən).

⚠️ ``accounts.dashboard`` sətirlərinin bir hissəsi Python-da DƏYİŞƏN kontekstlə
(``_CTX``) qurulur — ``makemessages`` onları tapmır, ona görə HAMISI buradadır.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_dashboard_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
C = "accounts.dashboard"

STRINGS = {
    # ── Başlıq / həftə ──────────────────────────────────────────────────────
    (C, "üst həftə"): ("upper week", "верхняя неделя", "üst hafta"),
    (C, "alt həftə"): ("lower week", "нижняя неделя", "alt hafta"),
    # ── Bu gün / növbəti dərslər ────────────────────────────────────────────
    (C, "Bu gün / növbəti dərslərim"): (
        "My classes — today / next",
        "Мои занятия — сегодня / следующие",
        "Derslerim — bugün / sıradaki",
    ),
    (C, "Bu gün · %(day)s"): ("Today · %(day)s", "Сегодня · %(day)s", "Bugün · %(day)s"),
    (C, "Növbəti dərs günü · %(day)s"): (
        "Next class day · %(day)s",
        "Следующий учебный день · %(day)s",
        "Sonraki ders günü · %(day)s",
    ),
    (C, "bu gün"): ("today", "сегодня", "bugün"),
    (C, "indi gedir"): ("in progress", "идёт сейчас", "şu an sürüyor"),
    (C, "indi"): ("now", "сейчас", "şimdi"),
    (C, "aud. %(room)s"): ("room %(room)s", "ауд. %(room)s", "derslik %(room)s"),
    (C, "Bu semestrdə qarşıda dərs qalmayıb."): (
        "No upcoming classes remain this semester.",
        "До конца семестра занятий больше нет.",
        "Bu dönemde kalan ders yok.",
    ),
    (C, "Bu günün dərsləri bitib, bu semestrdə qarşıda dərs qalmayıb."): (
        "Today's classes are over and no classes remain this semester.",
        "Сегодняшние занятия закончились, и до конца семестра занятий больше нет.",
        "Bugünün dersleri bitti ve bu dönemde kalan ders yok.",
    ),
    (C, "Bu semestr üçün qrupunuzun dərs cədvəli hələ qurulmayıb — cədvəl dərc olunanda burada görünəcək."): (
        "Your group's timetable for this semester has not been set up yet — it will appear here once published.",
        "Расписание вашей группы на этот семестр ещё не составлено — оно появится здесь после публикации.",
        "Grubunuzun bu dönemki ders programı henüz hazırlanmadı — yayımlandığında burada görünecek.",
    ),
    (C, "Bu semestr üçün cədvəldə dərsiniz yoxdur."): (
        "You have no classes in the timetable this semester.",
        "В расписании этого семестра у вас нет занятий.",
        "Bu dönem ders programında dersiniz yok.",
    ),
    # ── Davamiyyət — fənlər üzrə ────────────────────────────────────────────
    (C, "Davamiyyət — fənlər üzrə"): ("Attendance by subject", "Посещаемость по предметам", "Derslere göre devam"),
    (C, "Limit hər fənn üzrə ayrıca hesablanır: fənnin dərs saatlarının %(percent)s%%-i."): (
        "The limit is counted separately for each subject: %(percent)s%% of that subject's class hours.",
        "Лимит считается отдельно по каждому предмету: %(percent)s%% учебных часов предмета.",
        "Sınır her ders için ayrı hesaplanır: dersin saatlerinin %%%(percent)s'i.",
    ),
    (C, "qayıb %(absent)s / icazə %(allowed)s saat"): (
        "absent %(absent)s / allowed %(allowed)s h",
        "пропущено %(absent)s / допустимо %(allowed)s ч",
        "devamsızlık %(absent)s / izin %(allowed)s saat",
    ),
    (C, "qayıb %(absent)s saat · fənnin dərs saatı təyin olunmayıb"): (
        "absent %(absent)s h · the subject's class hours are not set",
        "пропущено %(absent)s ч · учебные часы предмета не заданы",
        "devamsızlık %(absent)s saat · dersin saati tanımlanmamış",
    ),
    (C, "Normal"): ("Normal", "Норма", "Normal"),
    (C, "Limitə yaxın"): ("Near the limit", "Близко к лимиту", "Sınıra yakın"),
    (C, "Limit keçib — imtahana buraxılmır"): (
        "Limit exceeded — not admitted to the exam",
        "Лимит превышен — к экзамену не допущен",
        "Sınır aşıldı — sınava alınmaz",
    ),
    (C, "Limit keçib"): ("Limit exceeded", "Лимит превышен", "Sınır aşıldı"),
    (C, "Köhnə sistemdən"): ("From the old system", "Из старой системы", "Eski sistemden"),
    (C, "Məlumat yoxdur"): ("No data", "Нет данных", "Veri yok"),
    (C, "Qayıb icazə verilən həddin altındadır."): (
        "Absences are below the allowed limit.",
        "Пропуски ниже допустимого лимита.",
        "Devamsızlık izin verilen sınırın altında.",
    ),
    (C, "İcazə verilən qayıbın 75%-i keçilib — davamiyyətə diqqət edin."): (
        "Over 75% of the allowed absence is used — watch your attendance.",
        "Использовано более 75% допустимых пропусков — следите за посещаемостью.",
        "İzin verilen devamsızlığın %75'i aşıldı — devamınıza dikkat edin.",
    ),
    (C, "Qayıb həddi keçilib — bu fəndən yekun imtahana buraxılmırsınız."): (
        "The absence limit is exceeded — you are not admitted to this subject's final exam.",
        "Лимит пропусков превышен — к итоговому экзамену по этому предмету вы не допущены.",
        "Devamsızlık sınırı aşıldı — bu dersin final sınavına alınmıyorsunuz.",
    ),
    (C, "Köhnə sistemdən köçürülmüş bağlı semestr — status yenidən hesablanmır."): (
        "A closed semester migrated from the old system — the status is not recalculated.",
        "Закрытый семестр, перенесённый из старой системы, — статус не пересчитывается.",
        "Eski sistemden aktarılmış kapalı dönem — durum yeniden hesaplanmaz.",
    ),
    (C, "Fənnin dərs saatı təyin olunmayıb — limit hesablana bilmir."): (
        "The subject's class hours are not set — the limit cannot be calculated.",
        "Учебные часы предмета не заданы — лимит невозможно рассчитать.",
        "Dersin saati tanımlanmamış — sınır hesaplanamıyor.",
    ),
    (C, "Qayıb saatı / icazə verilən limit"): (
        "Absence hours / allowed limit",
        "Часы пропусков / допустимый лимит",
        "Devamsızlık saati / izin verilen sınır",
    ),
    (C, "İdmançı istisnası: limit keçilsə də imtahana buraxılırsınız."): (
        "Athlete exemption: you are admitted to the exam even if the limit is exceeded.",
        "Исключение для спортсменов: вы допускаетесь к экзамену даже при превышении лимита.",
        "Sporcu istisnası: sınır aşılsa da sınava alınırsınız.",
    ),
    (C, "Cari tədris dövrü müəyyən edilməyib."): (
        "The current academic period is not defined.",
        "Текущий учебный период не определён.",
        "Güncel eğitim dönemi belirlenmemiş.",
    ),
    (C, "Cari semestrdə fənn qeydiyyatınız yoxdur — sualınız varsa dekanlığa müraciət edin."): (
        "You have no subject enrolments this semester — contact the dean's office if you have questions.",
        "В этом семестре у вас нет записей на предметы — с вопросами обращайтесь в деканат.",
        "Bu dönem ders kaydınız yok — sorunuz varsa dekanlığa başvurun.",
    ),
    (C, "Cəmi"): ("Total", "Всего", "Toplam"),
    (C, "fənn"): ("subjects", "предметов", "ders"),
    # ── Cari ballar — fənlər üzrə ───────────────────────────────────────────
    (C, "Cari ballar — fənlər üzrə"): (
        "Current scores by subject",
        "Текущие баллы по предметам",
        "Derslere göre güncel puanlar",
    ),
    (C, "Giriş balı — imtahana qədər toplanan bal (maks. %(max)s)."): (
        "Entry score — points collected before the exam (max. %(max)s).",
        "Входной балл — баллы, набранные до экзамена (макс. %(max)s).",
        "Giriş puanı — sınava kadar toplanan puan (en çok %(max)s).",
    ),
    (C, "Orta giriş balı"): ("Average entry score", "Средний входной балл", "Ortalama giriş puanı"),
    (C, "fənlər üzrə"): ("across subjects", "по предметам", "dersler genelinde"),
    (C, "fəndə yazılıb"): ("subjects graded", "предметов оценено", "derste girildi"),
    (C, "giriş balı"): ("entry score", "входной балл", "giriş puanı"),
    (C, "Giriş balı"): ("Entry score", "Входной балл", "Giriş puanı"),
    (C, "hələ yazılmayıb"): ("not graded yet", "ещё не выставлен", "henüz girilmedi"),
    (C, "Cari semestrdə bal yazılan fənniniz yoxdur."): (
        "You have no graded subjects this semester.",
        "В этом семестре у вас нет предметов с баллами.",
        "Bu dönem not girilen dersiniz yok.",
    ),
    # ── Müəllim: Jurnallarım ────────────────────────────────────────────────
    (C, "Jurnallarım"): ("My journals", "Мои журналы", "Yoklama defterlerim"),
    (C, "Jurnallara keç"): ("Go to the journals", "Перейти к журналам", "Yoklama defterlerine git"),
    (C, "Cari semestr"): ("Current semester", "Текущий семестр", "Güncel dönem"),
    (C, "jurnal"): ("journals", "журналов", "defter"),
    (C, "cəmi"): ("in total", "всего", "toplam"),
    (C, "%(count)s tələbə"): ("%(count)s students", "студентов: %(count)s", "%(count)s öğrenci"),
    (C, "keçirilib %(held)s / %(plan)s saat"): (
        "held %(held)s / %(plan)s h",
        "проведено %(held)s / %(plan)s ч",
        "yapıldı %(held)s / %(plan)s saat",
    ),
    (C, "keçirilib %(held)s saat"): ("held %(held)s h", "проведено %(held)s ч", "yapıldı %(held)s saat"),
    (C, "Keçirilmiş saat / plan saatı"): (
        "Hours held / planned hours",
        "Проведённые часы / плановые часы",
        "Yapılan saat / planlanan saat",
    ),
    # ── Midterm (aralıq qiymətləndirmə) pəncərəsi ───────────────────────────
    (C, "%(title)s — bal yazma"): ("%(title)s — grade entry", "%(title)s — ввод баллов", "%(title)s — not girişi"),
    (C, "Midterm pəncərəsi"): ("Midterm window", "Окно мидтерма", "Ara sınav penceresi"),
    (C, "Vəziyyət"): ("Status", "Состояние", "Durum"),
    (C, "Son tarix"): ("Deadline", "Крайний срок", "Son tarih"),
    (C, "Açılır"): ("Opens", "Открывается", "Açılış"),
    (C, "Açıqdır"): ("Open", "Открыто", "Açık"),
    (C, "Bağlanıb"): ("Closed", "Закрыто", "Kapandı"),
    (C, "Deaktivdir"): ("Inactive", "Неактивно", "Pasif"),
    (C, "Təyin olunmayıb"): ("Not set", "Не назначено", "Belirlenmedi"),
    (C, "Bal yazmaq açıqdır — son tarix %(date)s."): (
        "Grade entry is open — deadline %(date)s.",
        "Ввод баллов открыт — крайний срок %(date)s.",
        "Not girişi açık — son tarih %(date)s.",
    ),
    (C, "Pəncərə %(opens)s-də açılır, son tarix %(closes)s."): (
        "The window opens on %(opens)s, deadline %(closes)s.",
        "Окно открывается %(opens)s, крайний срок %(closes)s.",
        "Pencere %(opens)s tarihinde açılır, son tarih %(closes)s.",
    ),
    (C, "Pəncərə %(date)s tarixində bağlanıb."): (
        "The window closed on %(date)s.",
        "Окно закрылось %(date)s.",
        "Pencere %(date)s tarihinde kapandı.",
    ),
    (C, "Pəncərə yaradılıb, amma İmtahan Mərkəzi onu hələ aktivləşdirməyib."): (
        "The window has been created but the Exam Centre has not activated it yet.",
        "Окно создано, но Экзаменационный центр ещё не активировал его.",
        "Pencere oluşturuldu, ancak Sınav Merkezi henüz etkinleştirmedi.",
    ),
    (C, "İmtahan Mərkəzi hələ bal yazma pəncərəsini təyin etməyib."): (
        "The Exam Centre has not set the grade entry window yet.",
        "Экзаменационный центр ещё не назначил окно ввода баллов.",
        "Sınav Merkezi not giriş penceresini henüz belirlemedi.",
    ),
    (C, "Bəzi bölmələr üçün müddət uzadılıb — dəqiq tarix jurnaldadır."): (
        "The deadline has been extended for some units — see the journal for the exact date.",
        "Для некоторых подразделений срок продлён — точная дата указана в журнале.",
        "Bazı birimler için süre uzatıldı — kesin tarih yoklama defterinde.",
    ),
    (C, "açıqdır · son tarix %(date)s"): (
        "open · deadline %(date)s",
        "открыто · крайний срок %(date)s",
        "açık · son tarih %(date)s",
    ),
    (C, "%(date)s-də açılır"): ("opens on %(date)s", "открывается %(date)s", "%(date)s tarihinde açılır"),
    (C, "bağlanıb · %(date)s"): ("closed · %(date)s", "закрыто · %(date)s", "kapandı · %(date)s"),
    # ── Müraciətlər ─────────────────────────────────────────────────────────
    (C, "Cavabınızı gözləyən"): ("Awaiting your reply", "Ждут вашего ответа", "Yanıtınızı bekleyen"),
    (C, "müraciətiniz"): ("your applications", "ваших обращений", "başvurunuz"),
    (C, "Sizə gələn"): ("Assigned to you", "Поступило вам", "Size gelen"),
    (C, "açıq müraciət"): ("open applications", "открытых обращений", "açık başvuru"),
    (C, "Açıq müraciətiniz yoxdur — yenisini «Müraciətlər» bölməsindən göndərə bilərsiniz."): (
        "You have no open applications — you can submit a new one in the “Applications” section.",
        "У вас нет открытых обращений — новое можно отправить в разделе «Обращения».",
        "Açık başvurunuz yok — yenisini «Başvurular» bölümünden gönderebilirsiniz.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
