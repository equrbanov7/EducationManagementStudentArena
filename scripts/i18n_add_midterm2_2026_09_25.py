#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25 (M2): «Midterm» jurnaldan kənarda.

Sahib qərarı: 3 kollokvium əvəzinə TƏK midterm (20 bal). Bu skript:

* İmtahan Mərkəzinin «Midterm pəncərələri» ekranının (midterm rejimli semestr:
  tək kart, KPI, izah, köhnə K2/K3 pəncərələri) yeni mətnlərini;
* sillabusun «Midterm (aralıq imtahan)» ifadələrini;
* exams tərəfində «Kollekvium» (yazı səhvi) əvəzinə «Midterm» deyən yeni
  msgid-ləri (forma etiketi, yardım mətni, xəta, «İmtahan şansı ver» ekranı)

dörd kataloqa əlavə edir (AZ msgstr = msgid). ``UPDATES`` isə yalnız İKİ mövcud
(msgctxt, msgid) cütünün msgstr-ni dəyişir — imtahan kateqoriyasının «midterm»
etiketi (``exams.model.exam.choice.exam_type_extended`` və ``exams.type.label``);
dəyişən hər dəyər çap olunur. İdempotent.

İstifadə:  python scripts/i18n_add_midterm2_2026_09_25.py
"""

import os
import subprocess
import sys

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_KW = "registrar.kollokvium_window"
_EXCH = "accounts.exam_chance"

#: {(msgctxt, az_msgid): (en, ru, tr)} — YENİ girişlər (mövcuddursa toxunulmur).
STRINGS = {
    # ── Bölmə başlığı (labels.py) ───────────────────────────────────────────
    ("profile.section", "Midterm pəncərələri"): ("Midterm windows", "Окна мидтерма", "Vize pencereleri"),
    # ── POST controller + forma ─────────────────────────────────────────────
    (
        "accounts.kollokvium_windows",
        "Bu pəncərə köhnə kollokvium qaydasından qalıb — midterm semestrində onu yalnız silmək olar.",
    ): (
        "This window is left over from the old colloquium rule — in a midterm semester it can only be deleted.",
        "Это окно осталось от старого правила коллоквиумов — в семестре с мидтермом его можно только удалить.",
        "Bu pencere eski kolokyum kuralından kalmıştır — vize döneminde yalnızca silinebilir.",
    ),
    (
        _KW,
        "Bu semestr midterm rejimindədir: K1/K2/K3 kollokviumları əvəzinə yalnız bir «Midterm» pəncərəsi təyin olunur.",
    ): (
        "This semester follows the midterm rule: instead of the K1/K2/K3 colloquiums only one «Midterm» window is set.",
        "В этом семестре действует правило мидтерма: вместо коллоквиумов K1/K2/K3 задаётся только одно окно «Мидтерм».",
        "Bu dönemde vize kuralı geçerlidir: K1/K2/K3 kolokyumları yerine yalnızca bir «Vize» penceresi belirlenir.",
    ),
    # ── Ekran (_kollokvium_windows_content.html) ────────────────────────────
    (
        _KW,
        "Midterm üçün müəllimlərin %(scale)s bal yaza biləcəyi tarix aralığını təyin edin və aktivləşdirin. "
        "Rəhbər əlavə gün verə bilər.",
    ): (
        "Set and activate the date range in which teachers can enter midterm scores (%(scale)s). "
        "The manager can grant extra days.",
        "Задайте и активируйте диапазон дат, в который преподаватели могут выставлять баллы за мидтерм (%(scale)s). "
        "Руководитель может предоставить дополнительные дни.",
        "Öğretmenlerin vize puanını (%(scale)s) girebileceği tarih aralığını belirleyin ve etkinleştirin. "
        "Yönetici ek gün verebilir.",
    ),
    (_KW, "Vəziyyət"): ("Status", "Статус", "Durum"),
    (_KW, "açılış gününü gözləyir"): ("waiting for the opening day", "ожидает дня открытия", "açılış gününü bekliyor"),
    (_KW, "aktivləşdirmə gözləyir"): ("awaiting activation", "ожидает активации", "etkinleştirme bekliyor"),
    (_KW, "Bal yazma aralığı"): ("Score entry window", "Период выставления баллов", "Puan girişi aralığı"),
    (_KW, "açılış – bağlanış"): ("opening – closing", "открытие – закрытие", "açılış – kapanış"),
    (_KW, "Bal şkalası"): ("Score scale", "Шкала баллов", "Puan ölçeği"),
    (_KW, "müəllim jurnalda yazır"): (
        "the teacher enters it in the journal",
        "преподаватель вносит в журнал",
        "öğretim elemanı jurnala girer",
    ),
    (_KW, "Köhnə qayda: %(rule)s. Tək midterm %(year)s tədris ilindən tətbiq olunur."): (
        "Old rule: %(rule)s. The single midterm applies from the %(year)s academic year.",
        "Старое правило: %(rule)s. Единый мидтерм применяется с %(year)s учебного года.",
        "Eski kural: %(rule)s. Tek vize %(year)s eğitim-öğretim yılından itibaren uygulanır.",
    ),
    (_KW, "Köhnə qaydadan qalmış kollokvium pəncərələri"): (
        "Colloquium windows left over from the old rule",
        "Окна коллоквиумов, оставшиеся от старого правила",
        "Eski kuraldan kalan kolokyum pencereleri",
    ),
    (
        _KW,
        "Bu semestr midterm rejimindədir — aşağıdakı pəncərələr müəllim jurnalında istifadə olunmur. "
        "Qarışıqlıq olmasın deyə onları silin.",
    ): (
        "This semester follows the midterm rule — the windows below are not used in the teachers' journal. "
        "Delete them to avoid confusion.",
        "В этом семестре действует правило мидтерма — окна ниже не используются в журнале преподавателя. "
        "Удалите их, чтобы избежать путаницы.",
        "Bu dönemde vize kuralı geçerlidir — aşağıdaki pencereler öğretim elemanının jurnalında kullanılmaz. "
        "Karışıklık olmaması için silin.",
    ),
    (_KW, "Köhnə pəncərəni sil"): ("Delete the old window", "Удалить старое окно", "Eski pencereyi sil"),
    (_KW, "Bu köhnə kollokvium pəncərəsi (əlavə günləri ilə birlikdə) silinsin?"): (
        "Delete this old colloquium window (together with its extra days)?",
        "Удалить это старое окно коллоквиума (вместе с дополнительными днями)?",
        "Bu eski kolokyum penceresi (ek günleriyle birlikte) silinsin mi?",
    ),
    (_KW, "%(label)s — bal yazma pəncərəsi (%(scale)s bal)"): (
        "%(label)s — score entry window (%(scale)s points)",
        "%(label)s — окно выставления баллов (%(scale)s баллов)",
        "%(label)s — puan girişi penceresi (%(scale)s puan)",
    ),
    (
        _KW,
        "Bu semestrdə 3 kollokvium əvəzinə TƏK midterm keçirilir. Bal yazma vaxtını İmtahan Mərkəzi təyin edir: "
        "pəncərə aktiv və açıq olduqda müəllimlər elektron jurnalda hər tələbəyə %(scale)s bal yazır. "
        "Bağlanış tarixindən sonra (verilmiş əlavə günlər daxil) bal yazmaq kilidlənir.",
    ): (
        "This semester has a SINGLE midterm instead of 3 colloquiums. The Exam Center sets the score entry time: "
        "while the window is active and open, teachers enter %(scale)s points for each student in the electronic "
        "journal. After the closing date (including any extra days granted) score entry is locked.",
        "В этом семестре вместо 3 коллоквиумов проводится ОДИН мидтерм. Время выставления баллов задаёт "
        "Экзаменационный центр: пока окно активно и открыто, преподаватели выставляют каждому студенту %(scale)s "
        "баллов в электронном журнале. После даты закрытия (с учётом предоставленных дополнительных дней) "
        "выставление баллов блокируется.",
        "Bu dönemde 3 kolokyum yerine TEK vize yapılır. Puan girişi zamanını Sınav Merkezi belirler: pencere etkin "
        "ve açık olduğunda öğretim elemanları elektronik jurnalda her öğrenciye %(scale)s puan girer. Kapanış "
        "tarihinden sonra (verilen ek günler dahil) puan girişi kilitlenir.",
    ),
    (_KW, "Bu pəncərəni deaktiv etsəniz, müəllimlər midterm üzrə bal yaza bilməyəcək. Davam edilsin?"): (
        "If you deactivate this window, teachers will not be able to enter midterm scores. Continue?",
        "Если вы деактивируете это окно, преподаватели не смогут выставлять баллы за мидтерм. Продолжить?",
        "Bu pencereyi devre dışı bırakırsanız, öğretmenler vize puanı giremeyecek. Devam edilsin mi?",
    ),
    # ── Sillabus ────────────────────────────────────────────────────────────
    ("syllabus.assessment", "Midterm (aralıq imtahan)"): (
        "Midterm (interim exam)",
        "Мидтерм (промежуточный экзамен)",
        "Vize (ara sınav)",
    ),
    (
        "accounts.syllabus",
        "Bal bölgüsü universitet standartıdır: davamiyyət 10, midterm 20, sərbəst iş 10, seminar/laboratoriya "
        "ədədi ortası 10 (semestr 50) və yekun imtahan 50 — müəllim dəyişmir. Fəaliyyət növü dərs yükündən gəlir.",
    ): (
        "The score split is a university standard: attendance 10, midterm 20, independent work 10, "
        "seminar/laboratory average 10 (semester 50) and final exam 50 — the teacher does not change it. "
        "The activity type comes from the teaching load.",
        "Распределение баллов — стандарт университета: посещаемость 10, мидтерм 20, самостоятельная работа 10, "
        "среднее за семинары/лабораторные 10 (семестр 50) и итоговый экзамен 50 — преподаватель его не меняет. "
        "Вид занятий берётся из нагрузки.",
        "Puan dağılımı üniversite standardıdır: devam 10, vize 20, bağımsız çalışma 10, seminer/laboratuvar "
        "ortalaması 10 (dönem 50) ve final sınavı 50 — öğretim elemanı değiştirmez. Etkinlik türü ders yükünden gelir.",
    ),
    (
        "accounts.syllabus",
        "Semestr balı %(semester)s (davamiyyət + midterm + sərbəst iş + seminar/laboratoriya ədədi ortası), yekun "
        "imtahan 50 — cəmi %(total)s bal. Bölgü universitet standartıdır və dəyişdirilmir.",
    ): (
        "Semester score %(semester)s (attendance + midterm + independent work + seminar/laboratory average), "
        "final exam 50 — total %(total)s points. The split is a university standard and cannot be changed.",
        "Балл за семестр %(semester)s (посещаемость + мидтерм + самостоятельная работа + среднее за "
        "семинары/лабораторные), итоговый экзамен 50 — всего %(total)s баллов. Распределение — стандарт "
        "университета и не меняется.",
        "Dönem puanı %(semester)s (devam + vize + bağımsız çalışma + seminer/laboratuvar ortalaması), final sınavı "
        "50 — toplam %(total)s puan. Dağılım üniversite standardıdır ve değiştirilemez.",
    ),
    # ── Exams: «Kollekvium» (yazı səhvi) deyən açar-msgid-lərin AZ-mətnli əvəzləri ──
    ("exams.form.exam.label", "Kateqoriya (Final / Midterm / Sınaq)"): (
        "Category (Final / Midterm / Quiz)",
        "Категория (Финал / Мидтерм / Квиз)",
        "Kategori (Final / Vize / Quiz)",
    ),
    ("exams.template.create_exam_modal_form", "Yalnız lazım olduqda seç: Sınaq, Midterm və ya Final."): (
        "Choose only when needed: Quiz, Midterm, or Final.",
        "Выбирайте только при необходимости: квиз, мидтерм или финал.",
        "Yalnızca gerektiğinde seçin: Quiz, Vize veya Final.",
    ),
    ("exams.form.exam.error", "Final və midterm imtahanlarını yalnız imtahan mərkəzi yarada bilər."): (
        "Only the exam centre can create final and midterm exams.",
        "Финальные экзамены и мидтермы может создавать только экзаменационный центр.",
        "Final ve vize sınavlarını yalnızca sınav merkezi oluşturabilir.",
    ),
    # ── «İmtahan şansı ver» (_exam_chance_content.html) ─────────────────────
    (_EXCH, "Midterm"): ("Midterm", "Мидтерм", "Vize"),
    (
        _EXCH,
        "Seçilmiş final/midterm imtahanı üzrə tələbəyə və ya bütöv qrupa yenidən cəhd hüququ verin. Sistem avtomatik "
        "yeni giriş PIN-i yaradır, finalın köhnə girişini yenidən açır və imtahan tələbənin təyin olunmuş "
        "tapşırıqlarında yenidən görünür.",
    ): (
        "Grant a retake for the selected final/midterm exam to a student or a whole group. The system automatically "
        "issues a new entry PIN, re-opens the final's entry and the exam reappears in the student's assigned tasks.",
        "Дайте студенту или целой группе повторную попытку по выбранному финалу/мидтерму. Система автоматически "
        "выдаёт новый PIN, заново открывает вход на финал, и экзамен снова появляется в назначенных заданиях "
        "студента.",
        "Seçilen final/vize sınavı için öğrenciye veya tüm gruba yeniden deneme hakkı verin. Sistem otomatik olarak "
        "yeni giriş PIN'i oluşturur, finalin girişini yeniden açar ve sınav öğrencinin atanmış görevlerinde yeniden "
        "görünür.",
    ),
    (_EXCH, "Bu şərtlərə uyğun final/midterm imtahanı tapılmadı."): (
        "No final/midterm exams match these filters.",
        "По заданным условиям финалов/мидтермов не найдено.",
        "Bu koşullara uygun final/vize sınavı bulunamadı.",
    ),
    (
        _EXCH,
        "Şans veriləndə: cəhd limiti seçilən qədər artır, final/midterm üçün YENİ fərdi PIN yaradılır (kabinetdə "
        "dərhal görünür), finalın köhnə giriş bileti sıfırlanır və imtahan «Təyin olunmuş tapşırıqlar»da yenidən "
        "görünür. Bütün əməliyyat audit jurnalına yazılır.",
    ): (
        "When granted: the attempt limit increases by the chosen amount, a NEW personal PIN is issued for "
        "final/midterm (immediately visible in the cabinet), the final's old entry ticket is reset and the exam "
        "reappears in “Assigned tasks”. The whole operation is written to the audit log.",
        "При выдаче: лимит попыток увеличивается на выбранное число, для финала/мидтерма создаётся НОВЫЙ личный PIN "
        "(сразу виден в кабинете), старый входной билет финала сбрасывается, и экзамен снова появляется в "
        "«Назначенных заданиях». Вся операция записывается в журнал аудита.",
        "Hak verildiğinde: deneme limiti seçilen kadar artar, final/vize için YENİ kişisel PIN oluşturulur (kabinde "
        "hemen görünür), finalin eski giriş bileti sıfırlanır ve sınav «Atanmış görevler»de yeniden görünür. Tüm "
        "işlem denetim günlüğüne yazılır.",
    ),
}

#: {(msgctxt, msgid): (az, en, ru, tr)} — MÖVCUD msgstr-lərin yenilənməsi. Brief yalnız bu
#: iki cütə icazə verir: imtahan kateqoriyasının «midterm» etiketi (AZ-da «Kollekvium» idi).
UPDATES = {
    ("exams.model.exam.choice.exam_type_extended", "midterm"): ("Midterm", "Midterm", "Мидтерм", "Vize"),
    ("exams.type.label", "midterm"): ("Midterm", "Midterm", "Мидтерм", "Vize"),
}


def _apply(po, lang):
    existing = {(e.msgctxt, e.msgid): e for e in po if not e.obsolete}
    added = 0
    changed = []
    for (ctx, msgid), (en, ru, tr) in STRINGS.items():
        if (ctx, msgid) in existing:
            continue
        msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
        po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
        added += 1
    index = LOCALES.index(lang)
    for (ctx, msgid), values in UPDATES.items():
        target = values[index]
        entry = existing.get((ctx, msgid))
        if entry is None:
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=target))
            changed.append((ctx, msgid, None, target))
            continue
        if entry.msgstr != target or "fuzzy" in entry.flags:
            changed.append((ctx, msgid, entry.msgstr, target))
            entry.msgstr = target
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
    return added, changed


def main(base=BASE):
    for lang in LOCALES:
        path = os.path.join(base, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        added, changed = _apply(po, lang)
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}, updated {len(changed)}")
        for ctx, msgid, old, new in changed:
            print(f"    [{ctx}] {msgid!r}: {old!r} -> {new!r}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else BASE)
