#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: sərbəst iş BAL strukturu (1 × 10 / 2 × 5 / 10 × 1).

Jurnalın «Sərbəst iş» tabı (struktur zolağı, bal seçimi, «Fənn qovluğu» nişanı,
uyğunsuzluq izahı), sənədli düzəliş modalının bal sahəsi, tələbə görünüşü və
«Fənn qovluğu» → jurnal hook-unun mesajları (``apps.registrar.selfwork_hook``).
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_swpoints_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_SW = "registrar.selfwork"
_HOOK = "registrar.selfwork_hook"

STRINGS = {
    # ── Model seçimləri (SelfWorkSource) ─────────────────────────────────────
    (_SW, "Jurnal"): ("Journal", "Журнал", "Yoklama defteri"),
    (_SW, "Fənn qovluğu"): ("Subject folder", "Папка предмета", "Ders klasörü"),
    # ── Struktur uyğunsuzluğu (selfwork_structure.mismatch_message) ──────────
    (
        _SW,
        "Sillabus sərbəst işi %(label)s bal kimi tələb edir, jurnalda isə %(topics)s köhnə çeklist mövzusu "
        "var və onların bəzisinə artıq bal yazılıb. Qiymət yazılmış mövzular avtomatik çevrilmir — "
        "tələbələrin balı dəyişərdi. Strukturu dəyişmək üçün RİM ilə sənədli düzəliş edin.",
    ): (
        "The syllabus defines independent work as %(label)s points, but the journal has %(topics)s legacy "
        "checklist topics and some of them are already graded. Graded topics are not converted automatically — "
        "students' scores would change. Use a documented correction with the registrar to change the structure.",
        "Силлабус задаёт самостоятельную работу как %(label)s баллов, а в журнале %(topics)s старых тем-чеклистов, "
        "и часть из них уже оценена. Оценённые темы не конвертируются автоматически — баллы студентов изменились бы. "
        "Для изменения структуры оформите документальную корректировку через регистратуру.",
        "İzlence bağımsız çalışmayı %(label)s puan olarak tanımlıyor, ancak defterde %(topics)s eski kontrol listesi "
        "konusu var ve bazıları zaten puanlanmış. Puanlanmış konular otomatik dönüştürülmez — öğrencilerin puanı "
        "değişirdi. Yapıyı değiştirmek için öğrenci işleri ile belgeli düzeltme yapın.",
    ),
    (
        _SW,
        "Sillabus sərbəst işi %(label)s bal kimi tələb edir, jurnalda isə %(topics)s mövzu var. "
        "Mövzular silinmir — artıq (qiymətsiz) mövzuları özünüz silin, struktur sonra tətbiq olunacaq.",
    ): (
        "The syllabus defines independent work as %(label)s points, but the journal has %(topics)s topics. "
        "Topics are never deleted automatically — delete the extra (ungraded) topics yourself and the structure "
        "will be applied afterwards.",
        "Силлабус задаёт самостоятельную работу как %(label)s баллов, а в журнале %(topics)s тем. Темы не удаляются "
        "автоматически — удалите лишние (неоценённые) темы сами, после этого структура будет применена.",
        "İzlence bağımsız çalışmayı %(label)s puan olarak tanımlıyor, ancak defterde %(topics)s konu var. "
        "Konular otomatik silinmez — fazla (puanlanmamış) konuları kendiniz silin, yapı ardından uygulanacaktır.",
    ),
    (
        _SW,
        "Jurnaldakı sərbəst iş strukturu sillabusdakından (%(label)s) fərqlidir. Qiymət yazılmış slotlar "
        "avtomatik dəyişdirilmir və mövzular silinmir — artıq (qiymətsiz) mövzuları silin, struktur sonra "
        "tətbiq olunacaq.",
    ): (
        "The independent-work structure in the journal differs from the syllabus (%(label)s). Graded slots are not "
        "changed automatically and topics are never deleted — delete the extra (ungraded) topics and the structure "
        "will be applied afterwards.",
        "Структура самостоятельной работы в журнале отличается от силлабуса (%(label)s). Оценённые слоты не "
        "меняются автоматически, темы не удаляются — удалите лишние (неоценённые) темы, после этого структура "
        "будет применена.",
        "Defterdeki bağımsız çalışma yapısı izlencedekinden (%(label)s) farklı. Puanlanmış bölümler otomatik "
        "değiştirilmez ve konular silinmez — fazla (puanlanmamış) konuları silin, yapı ardından uygulanacaktır.",
    ),
    (
        _SW,
        "Jurnaldakı sərbəst iş mövzuları sillabusun strukturu ilə uyğun deyil (köhnə və strukturlu mövzular "
        "qarışıqdır). Qiymət yazılmış mövzular avtomatik dəyişdirilmir.",
    ): (
        "The independent-work topics in the journal do not match the syllabus structure (legacy and structured "
        "topics are mixed). Graded topics are not changed automatically.",
        "Темы самостоятельной работы в журнале не соответствуют структуре силлабуса (старые и структурированные "
        "темы смешаны). Оценённые темы не меняются автоматически.",
        "Defterdeki bağımsız çalışma konuları izlencenin yapısıyla uyumlu değil (eski ve yapılandırılmış konular "
        "karışık). Puanlanmış konular otomatik değiştirilmez.",
    ),
    # ── Lövhə əməliyyatları (journal_actions.selfwork_action) ─────────────────
    (_SW, "Sərbəst iş strukturu sillabusdan quruldu: %(label)s bal."): (
        "The independent-work structure was built from the syllabus: %(label)s points.",
        "Структура самостоятельной работы построена по силлабусу: %(label)s баллов.",
        "Bağımsız çalışma yapısı izlenceden oluşturuldu: %(label)s puan.",
    ),
    (_SW, "Təsdiqlənmiş sillabusda sərbəst iş strukturu yoxdur."): (
        "The approved syllabus has no independent-work structure.",
        "В утверждённом силлабусе нет структуры самостоятельной работы.",
        "Onaylı izlencede bağımsız çalışma yapısı yok.",
    ),
    (_SW, "Sərbəst iş strukturu artıq qurulub."): (
        "The independent-work structure is already in place.",
        "Структура самостоятельной работы уже построена.",
        "Bağımsız çalışma yapısı zaten kurulu.",
    ),
    (
        _SW,
        "Mövzu silinmədi — ona «Fənn qovluğu»ndan bal yazılıb (dəyişiklik yalnız sənədli düzəlişlə).",
    ): (
        "The topic was not deleted — it holds scores from the subject folder (only a documented correction can "
        "change them).",
        "Тема не удалена — в ней есть баллы из «Папки предмета» (изменить можно только документальной "
        "корректировкой).",
        "Konu silinmedi — ders klasöründen gelen puanlar var (yalnızca belgeli düzeltme ile değiştirilebilir).",
    ),
    (
        _SW,
        "Bəzi xanalar dəyişilmədi — geri alma pəncərəsi bitib, bal fənn qovluğundandır və ya bal etibarsızdır.",
    ): (
        "Some cells were not changed — the undo window has passed, the score comes from the subject folder, or the "
        "score is invalid.",
        "Некоторые ячейки не изменены — окно отмены истекло, балл получен из «Папки предмета» или балл " "недопустим.",
        "Bazı hücreler değiştirilmedi — geri alma süresi doldu, puan ders klasöründen geliyor ya da puan geçersiz.",
    ),
    # ── Sənədli düzəliş (item_corrections) ────────────────────────────────────
    (_SW, "Sərbəst iş üçün düzgün bal daxil edin."): (
        "Enter a valid self-work score.",
        "Введите допустимый балл за самостоятельную работу.",
        "Geçerli bir bağımsız çalışma puanı girin.",
    ),
    (_SW, "Bal 0-dan böyük və ən çoxu %(max)s olmalıdır."): (
        "The score must be above 0 and at most %(max)s.",
        "Балл должен быть больше 0 и не больше %(max)s.",
        "Puan 0'dan büyük ve en fazla %(max)s olmalıdır.",
    ),
    (_SW, "Yeni bal (sərbəst iş)"): (
        "New score (independent work)",
        "Новый балл (сам. работа)",
        "Yeni puan (bağımsız çalışma)",
    ),
    (_SW, "Boş saxlasanız bal silinir («—»). 0 yazılmır."): (
        "Leave it empty to remove the score (“—”). A 0 is never recorded.",
        "Оставьте пустым, чтобы удалить балл («—»). Ноль не записывается.",
        "Boş bırakırsanız puan silinir (“—”). 0 yazılmaz.",
    ),
    # ── Lövhə şablonu (_jd_selfwork.html) ─────────────────────────────────────
    (_SW, "%(label)s bal"): ("%(label)s points", "%(label)s баллов", "%(label)s puan"),
    (_SW, "sillabus"): ("syllabus", "силлабус", "izlence"),
    (_SW, "jurnal"): ("journal", "журнал", "defter"),
    (_SW, "Çeklist: hər mövzu 1 bal"): (
        "Checklist: 1 point per topic",
        "Чек-лист: 1 балл за тему",
        "Kontrol listesi: konu başına 1 puan",
    ),
    (_SW, "Cəmi maksimum %(max)s bal"): (
        "Maximum %(max)s points in total",
        "Всего максимум %(max)s баллов",
        "Toplam en fazla %(max)s puan",
    ),
    (_SW, "— bal fənn qovluğundan yazılıb, burada yalnız baxış"): (
        "— score recorded from the subject folder, read-only here",
        "— балл записан из «Папки предмета», здесь только просмотр",
        "— puan ders klasöründen yazıldı, burada yalnızca görüntüleme",
    ),
    (
        _SW,
        "Təsdiqlənmiş sillabus sərbəst işi %(label)s bal kimi müəyyən edir — struktur hələ jurnala tətbiq olunmayıb.",
    ): (
        "The approved syllabus defines independent work as %(label)s points — the structure has not been applied to "
        "the journal yet.",
        "Утверждённый силлабус задаёт самостоятельную работу как %(label)s баллов — структура ещё не применена к "
        "журналу.",
        "Onaylı izlence bağımsız çalışmayı %(label)s puan olarak tanımlıyor — yapı henüz deftere uygulanmadı.",
    ),
    (_SW, "Strukturu tətbiq et"): ("Apply the structure", "Применить структуру", "Yapıyı uygula"),
    (_SW, "%(n)s bal"): ("%(n)s pts", "%(n)s балл.", "%(n)s puan"),
    (_SW, "Sərbəst iş %(n)s"): ("Independent work %(n)s", "Сам. работа %(n)s", "Bağımsız çalışma %(n)s"),
    (_SW, "Struktur hələ jurnala tətbiq olunmayıb"): (
        "The structure has not been applied to the journal yet",
        "Структура ещё не применена к журналу",
        "Yapı henüz deftere uygulanmadı",
    ),
    (_SW, "Fənn qovluğundan yazılıb: %(at)s · %(by)s. Dəyişiklik yalnız sənədli düzəlişlə."): (
        "Recorded from the subject folder: %(at)s · %(by)s. Only a documented correction can change it.",
        "Записано из «Папки предмета»: %(at)s · %(by)s. Изменить можно только документальной корректировкой.",
        "Ders klasöründen yazıldı: %(at)s · %(by)s. Yalnızca belgeli düzeltme ile değiştirilebilir.",
    ),
    (_SW, "Sərbəst iş %(n)s — bal (maksimum %(max)s)"): (
        "Independent work %(n)s — score (maximum %(max)s)",
        "Сам. работа %(n)s — балл (максимум %(max)s)",
        "Bağımsız çalışma %(n)s — puan (en fazla %(max)s)",
    ),
    (
        _SW,
        "Bal strukturu %(label)s: hər sərbəst iş öz maksimum balı ilə qiymətləndirilir, cəmi maksimum %(max)s bal. "
        "«—» — bal yazılmayıb (0 yazılmır: iş bəyənilmirsə fənn qovluğunda rəy yazılıb geri qaytarılır).",
    ): (
        "Point structure %(label)s: each independent work is graded up to its own maximum, %(max)s points in total. "
        "“—” means no score yet (a 0 is never recorded: unsatisfactory work is returned with feedback in the subject "
        "folder).",
        "Структура баллов %(label)s: каждая самостоятельная работа оценивается до своего максимума, всего максимум "
        "%(max)s баллов. «—» — балл не выставлен (ноль не ставится: неудовлетворительная работа возвращается с "
        "отзывом в «Папке предмета»).",
        "Puan yapısı %(label)s: her bağımsız çalışma kendi en yüksek puanıyla değerlendirilir, toplam en fazla "
        "%(max)s puan. “—” — puan yazılmadı (0 yazılmaz: beğenilmeyen çalışma ders klasöründe geri bildirimle iade "
        "edilir).",
    ),
    # ── Tələbə görünüşü (_journal_student_content.html) ───────────────────────
    (_SW, "Bal fənn qovluğunda müəllimin qiymətləndirməsindən jurnala yazılıb"): (
        "The score was recorded to the journal from the teacher's grading in the subject folder",
        "Балл записан в журнал из оценки преподавателя в «Папке предмета»",
        "Puan, ders klasöründeki öğretmen değerlendirmesinden deftere yazıldı",
    ),
    # ── «Fənn qovluğu» hook mesajları (selfwork_hook) ─────────────────────────
    (_HOOK, "Sərbəst iş %(n)s"): ("Independent work %(n)s", "Сам. работа %(n)s", "Bağımsız çalışma %(n)s"),
    (_HOOK, "Jurnala yazıldı: %(slot)s · %(points)s/%(max)s (cəmi %(total)s/%(max_total)s)"): (
        "Recorded in the journal: %(slot)s · %(points)s/%(max)s (total %(total)s/%(max_total)s)",
        "Записано в журнал: %(slot)s · %(points)s/%(max)s (всего %(total)s/%(max_total)s)",
        "Deftere yazıldı: %(slot)s · %(points)s/%(max)s (toplam %(total)s/%(max_total)s)",
    ),
    (_HOOK, "Jurnalda artıq yazılıb: %(slot)s · %(points)s/%(max)s (cəmi %(total)s/%(max_total)s)"): (
        "Already recorded in the journal: %(slot)s · %(points)s/%(max)s (total %(total)s/%(max_total)s)",
        "Уже записано в журнале: %(slot)s · %(points)s/%(max)s (всего %(total)s/%(max_total)s)",
        "Defterde zaten yazılı: %(slot)s · %(points)s/%(max)s (toplam %(total)s/%(max_total)s)",
    ),
    (_HOOK, "Jurnal kilidlidir — bal yazılmadı. Dəyişiklik yalnız sənədli düzəlişlə mümkündür."): (
        "The journal is locked — the score was not recorded. Only a documented correction can change it.",
        "Журнал закрыт — балл не записан. Изменение возможно только документальной корректировкой.",
        "Defter kilitli — puan yazılmadı. Değişiklik yalnızca belgeli düzeltme ile mümkündür.",
    ),
    (_HOOK, "Tələbə bu jurnalda aktiv qeydiyyatda deyil — bal yazılmadı."): (
        "The student is not actively enrolled in this journal — the score was not recorded.",
        "Студент не имеет активной записи в этом журнале — балл не записан.",
        "Öğrenci bu defterde aktif kayıtlı değil — puan yazılmadı.",
    ),
    (_HOOK, "Bal 0-dan böyük və %(max)s-dən çox olmamalıdır (ən çoxu bir onluq) — bal yazılmadı."): (
        "The score must be above 0 and not more than %(max)s (at most one decimal) — the score was not recorded.",
        "Балл должен быть больше 0 и не больше %(max)s (не более одного знака после запятой) — балл не записан.",
        "Puan 0'dan büyük ve %(max)s'den fazla olmamalı (en fazla bir ondalık) — puan yazılmadı.",
    ),
    (
        _HOOK,
        "Bal şkalası uyğun gəlmir: jurnalda %(slot)s maksimum %(journal)s baldır, fənn qovluğunda isə %(folder)s. "
        "Sillabusun sərbəst iş strukturunu yoxlayın.",
    ): (
        "The score scale does not match: in the journal %(slot)s is worth at most %(journal)s points, in the subject "
        "folder %(folder)s. Check the syllabus independent-work structure.",
        "Шкала баллов не совпадает: в журнале %(slot)s — максимум %(journal)s баллов, в «Папке предмета» — "
        "%(folder)s. Проверьте структуру самостоятельной работы в силлабусе.",
        "Puan ölçeği uyuşmuyor: defterde %(slot)s en fazla %(journal)s puan, ders klasöründe ise %(folder)s. "
        "İzlencenin bağımsız çalışma yapısını kontrol edin.",
    ),
    (
        _HOOK,
        "Bu sərbəst iş üçün bal artıq yazılıb (%(slot)s · %(current)s/%(max)s) — ikinci dəfə bal verilmir. "
        "Dəyişiklik yalnız jurnalda sənədli düzəlişlə mümkündür.",
    ): (
        "A score is already recorded for this independent work (%(slot)s · %(current)s/%(max)s) — no second award. "
        "Only a documented correction in the journal can change it.",
        "За эту самостоятельную работу балл уже выставлен (%(slot)s · %(current)s/%(max)s) — повторно балл не "
        "ставится. Изменение возможно только документальной корректировкой в журнале.",
        "Bu bağımsız çalışma için puan zaten yazılmış (%(slot)s · %(current)s/%(max)s) — ikinci kez puan "
        "verilmez. Değişiklik yalnızca defterde belgeli düzeltme ile mümkündür.",
    ),
    (_HOOK, "%(slot)s üzrə bu bal jurnalda sənədli düzəlişlə dəyişdirilib — yenidən yazılmır."): (
        "This score for %(slot)s was changed in the journal by a documented correction — it is not re-recorded.",
        "Этот балл по %(slot)s изменён в журнале документальной корректировкой — повторно не записывается.",
        "%(slot)s için bu puan defterde belgeli düzeltme ile değiştirildi — yeniden yazılmaz.",
    ),
    (_HOOK, "Sərbəst iş cəmi %(max_total)s baldan çox ola bilməz (jurnalda artıq %(total)s bal var)."): (
        "Independent work cannot exceed %(max_total)s points in total (the journal already has %(total)s).",
        "Сумма за самостоятельную работу не может превышать %(max_total)s баллов (в журнале уже %(total)s).",
        "Bağımsız çalışma toplamı %(max_total)s puanı aşamaz (defterde zaten %(total)s puan var).",
    ),
    (_HOOK, "Jurnalın sərbəst iş strukturunda «%(slot)s» yoxdur (%(label)s)."): (
        "The journal's independent-work structure has no “%(slot)s” (%(label)s).",
        "В структуре самостоятельной работы журнала нет «%(slot)s» (%(label)s).",
        "Defterin bağımsız çalışma yapısında “%(slot)s” yok (%(label)s).",
    ),
    (
        _HOOK,
        "Jurnalda sərbəst iş strukturu yoxdur: bu açılışın təsdiqlənmiş sillabusunda sərbəst iş strukturu "
        "(1 × 10 / 2 × 5 / 10 × 1) tapılmadı.",
    ): (
        "The journal has no independent-work structure: no structure (1 × 10 / 2 × 5 / 10 × 1) was found in the "
        "approved syllabus of this course offering.",
        "В журнале нет структуры самостоятельной работы: в утверждённом силлабусе этого курса структура "
        "(1 × 10 / 2 × 5 / 10 × 1) не найдена.",
        "Defterde bağımsız çalışma yapısı yok: bu dersin onaylı izlencesinde yapı (1 × 10 / 2 × 5 / 10 × 1) "
        "bulunamadı.",
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
