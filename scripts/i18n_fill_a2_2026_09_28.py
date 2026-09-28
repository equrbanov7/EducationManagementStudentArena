#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 audit remediasiyası, iş paketi A2 (qiymətləndirmə və vaxt).

Əlavə olunan mətnlər:
  * `exams.view.results.message` — EX28-02: bitməmiş cəhdin yoxlanması rədd olunur
    (yoxlama URL-i baxış rejiminə yönləndirir; servis xətası);
  * `exams.template.student_exam_result` — EX28-03: cəhd haqqı qalıbsa cavab açarı
    gizlidir (nəticə səhifəsindəki bildiriş).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_a2_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

RM = "exams.view.results.message"
SR = "exams.template.student_exam_result"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    RM: {
        "attempt_not_finished_view_only": {
            "az": "Tələbə imtahanı hələ bitirməyib — cəhd yalnız baxış rejimində açıldı. "
            "Yoxlama cəhd bitdikdən sonra mümkündür.",
            "en": "The student has not finished the exam yet — the attempt is opened in view-only mode. "
            "Grading is available once the attempt is finished.",
            "ru": "Студент ещё не завершил экзамен — попытка открыта только для просмотра. "
            "Проверка станет доступна после завершения попытки.",
            "tr": "Öğrenci sınavı henüz bitirmedi — deneme yalnızca görüntüleme modunda açıldı. "
            "Değerlendirme deneme bittikten sonra yapılabilir.",
        },
        "attempt_not_finished_cannot_grade": {
            "az": "Cəhd hələ bitməyib — tələbə imtahanı bitirənə qədər qiymətləndirmək olmaz.",
            "en": "The attempt is not finished yet — it cannot be graded until the student finishes the exam.",
            "ru": "Попытка ещё не завершена — её нельзя оценить, пока студент не завершит экзамен.",
            "tr": "Deneme henüz bitmedi — öğrenci sınavı bitirene kadar değerlendirilemez.",
        },
    },
    SR: {
        "notice_answer_key_hidden_attempts_left": {
            "az": "Sizin hələ cəhd haqqınız var — düzgün cavablar son cəhdinizdən və ya imtahan müddəti "
            "bitdikdən sonra göstəriləcək. Bal və cavablarınızın nəticəsi (düz/səhv) artıq görünür.",
            "en": "You still have attempts left — the correct answers will be shown after your last attempt "
            "or when the exam period ends. Your score and whether each answer was right or wrong are shown now.",
            "ru": "У вас ещё остались попытки — правильные ответы будут показаны после последней попытки "
            "или по окончании срока экзамена. Балл и верность ваших ответов видны уже сейчас.",
            "tr": "Hâlâ deneme hakkınız var — doğru cevaplar son denemenizden sonra veya sınav süresi "
            "bittiğinde gösterilecek. Puanınız ve cevaplarınızın doğru/yanlış sonucu şimdiden görünür.",
        },
    },
}

#: Mövcud, lakin səhv tərcüməsi üstələnməli girişlər (bu paketdə yoxdur).
FORCE = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
