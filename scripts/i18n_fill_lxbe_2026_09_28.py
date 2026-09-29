#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 canlı viktorina mühərriki (LX-BE).

Əlavə olunan mətnlər:
  * `live_exam.view.message` — yazılı cavab (typed answer) ayarlarının yoxlama xətaları;
  * `live_exam.consumer.error` — `answer_retry` (server cavabı saxlaya bilmədi).

Mövcud, lakin MƏNASI SƏHV tərcümələr üstələnir (FORCE) — dörd dildə də başqa
mətnlərlə qarışıb: `rate_limited` («Format: say/müddət…»), `question_not_active`
(«Sualı redaktə et»), `question_not_accepting_answers`, `submission_outside_active_window`.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_lxbe_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

VM = "live_exam.view.message"
CE = "live_exam.consumer.error"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    VM: {
        "typed_questions_invalid": {
            "az": "Yazılı cavab ayarları yanlış formatdadır.",
            "en": "The typed-answer settings are malformed.",
            "ru": "Настройки письменных ответов имеют неверный формат.",
            "tr": "Yazılı cevap ayarları hatalı biçimde.",
        },
        "typed_question_not_in_exam": {
            "az": "Seçilən sual bu imtahana aid deyil.",
            "en": "The selected question does not belong to this exam.",
            "ru": "Выбранный вопрос не относится к этому экзамену.",
            "tr": "Seçilen soru bu sınava ait değil.",
        },
        "typed_question_not_eligible": {
            "az": (
                "{index}-ci sual yazılı cavab üçün uyğun deyil: yalnız bir düzgün variantı "
                "(≤ 60 simvol) olan və ya qısa cavablı (1–10 sətir) suallar seçilə bilər."
            ),
            "en": (
                "Question {index} cannot be a typed answer: only questions with exactly one correct "
                "option (≤ 60 characters) or a short answer (1–10 lines) are allowed."
            ),
            "ru": (
                "Вопрос {index} нельзя сделать письменным: подходят только вопросы с одним верным "
                "вариантом (≤ 60 символов) или с коротким ответом (1–10 строк)."
            ),
            "tr": (
                "{index}. soru yazılı cevaba uygun değil: yalnızca tek doğru seçeneği (≤ 60 karakter) "
                "olan veya kısa cevaplı (1–10 satır) sorular seçilebilir."
            ),
        },
        "typed_accepted_too_many": {
            "az": "Hər sual üçün ən çox 10 qəbul olunan cavab ola bilər.",
            "en": "A question can have at most 10 accepted answers.",
            "ru": "У вопроса может быть не более 10 допустимых ответов.",
            "tr": "Bir soru için en fazla 10 kabul edilen cevap olabilir.",
        },
        "typed_accepted_too_long": {
            "az": "Qəbul olunan cavab 60 simvoldan uzun ola bilməz.",
            "en": "An accepted answer cannot be longer than 60 characters.",
            "ru": "Допустимый ответ не может быть длиннее 60 символов.",
            "tr": "Kabul edilen cevap 60 karakterden uzun olamaz.",
        },
    },
    CE: {
        "answer_retry": {
            "az": "Cavab saxlanmadı, yenidən göndərin.",
            "en": "Your answer was not saved — please send it again.",
            "ru": "Ответ не сохранён — отправьте его ещё раз.",
            "tr": "Cevabınız kaydedilmedi, lütfen tekrar gönderin.",
        },
        "rate_limited": {
            "az": "Çox tez-tez göndərilir. Bir az gözləyib yenidən cəhd edin.",
            "en": "Too many requests. Please wait a moment and try again.",
            "ru": "Слишком много запросов. Подождите немного и повторите.",
            "tr": "Çok fazla istek. Lütfen biraz bekleyip tekrar deneyin.",
        },
        "question_not_active": {
            "az": "Bu sual artıq aktiv deyil.",
            "en": "This question is no longer active.",
            "ru": "Этот вопрос уже не активен.",
            "tr": "Bu soru artık etkin değil.",
        },
        "question_not_accepting_answers": {
            "az": "Bu sual hazırda cavab qəbul etmir.",
            "en": "This question is not accepting answers right now.",
            "ru": "Сейчас этот вопрос не принимает ответы.",
            "tr": "Bu soru şu anda cevap kabul etmiyor.",
        },
        "submission_outside_active_window": {
            "az": "Cavab vaxtı bitib.",
            "en": "Time is up for this question.",
            "ru": "Время на ответ истекло.",
            "tr": "Bu soru için süre doldu.",
        },
    },
}

# Mövcud olan, amma yanlış mənalı tərcümələr — həmişə üstələnir.
FORCE = {
    (CE, "rate_limited"),
    (CE, "question_not_active"),
    (CE, "question_not_accepting_answers"),
    (CE, "submission_outside_active_window"),
}


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
