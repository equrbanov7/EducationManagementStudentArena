#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-08 təhlükəsizlik dizaynı (audit 2026-10-07 «Dizayn riskləri»).

Əlavə olunan mətnlər (yalnız 3-cü maddə istifadəçiyə mətn göstərir; WS qapısı bağlanma
kodu ilə, yazılı sualın çatdırılması mövcud mətnlərlə işləyir):

  * ``exams.final_center.device`` — final cəhdinin cihaz bağlantısı: «başqa cihaz» səhifəsi
    və JSON mesajı (``final_device_blocked.html``, ``services/final_center/device_binding.py``),
    nəzarətçi təsdiqi (``views/exam_center/device_change.py``), PIN axtarışı düyməsi
    (``_pin_lookup_body.html`` i18n adası → ``pin_lookup.js``);
  * ``exams.model.final_device.meta`` — ``FinalAttemptDevice`` modelinin adları.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
Locale birləşmə konflikti olsa: «ours» götürülür, sonra bu skript (və digər fill
skriptləri) yenidən işlədilir.
İstifadə:  python scripts/i18n_fill_2026_10_08_security_design.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


def _same(az, en, ru, tr):
    """msgid = AZ mətnin özü."""
    return az, _t(az, en, ru, tr)


DEVICE = "exams.final_center.device"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    DEVICE: dict(
        [
            _same(
                "Bu final imtahanı başqa cihazda davam edir. Cihazı dəyişmək lazımdırsa, nəzarətçidən və ya "
                "imtahan mərkəzindən «cihaz dəyişikliyi» təsdiqi istəyin, sonra səhifəni yeniləyin.",
                "This final exam is continuing on another device. If you need to switch devices, ask the "
                "invigilator or the exam centre for a “device change” approval, then reload the page.",
                "Этот итоговый экзамен продолжается на другом устройстве. Если нужно сменить устройство, "
                "попросите наблюдателя или экзаменационный центр подтвердить «смену устройства», затем "
                "обновите страницу.",
                "Bu final sınavı başka bir cihazda devam ediyor. Cihaz değiştirmeniz gerekiyorsa gözetmenden "
                "veya sınav merkezinden «cihaz değişikliği» onayı isteyin, ardından sayfayı yenileyin.",
            ),
            _same(
                "İmtahan başqa cihazda davam edir",
                "The exam is continuing on another device",
                "Экзамен продолжается на другом устройстве",
                "Sınav başka bir cihazda devam ediyor",
            ),
            _same("Final imtahanı", "Final exam", "Итоговый экзамен", "Final sınavı"),
            _same(
                "Cavablarınız serverdə saxlanılıb — təsdiqdən sonra imtahan qaldığı yerdən davam edəcək.",
                "Your answers are saved on the server — after approval the exam continues where you left off.",
                "Ваши ответы сохранены на сервере — после подтверждения экзамен продолжится с того места, "
                "где вы остановились.",
                "Cevaplarınız sunucuda kayıtlı — onaydan sonra sınav kaldığınız yerden devam eder.",
            ),
            _same("Nəzarətçi təsdiqi", "Invigilator approval", "Подтверждение наблюдателя", "Gözetmen onayı"),
            _same("Səhifəni yenilə", "Reload the page", "Обновить страницу", "Sayfayı yenile"),
            _same(
                "Hər cihaz dəyişikliyi nəzarətçi tərəfindən təsdiqlənir və jurnalda qeyd olunur.",
                "Every device change is approved by an invigilator and recorded in the audit log.",
                "Каждая смена устройства подтверждается наблюдателем и фиксируется в журнале аудита.",
                "Her cihaz değişikliği bir gözetmen tarafından onaylanır ve denetim kaydına işlenir.",
            ),
            _same(
                "Cihaz dəyişikliyini yalnız nəzarətçi və ya imtahan mərkəzi təsdiqləyə bilər.",
                "Only an invigilator or the exam centre can approve a device change.",
                "Смену устройства может подтвердить только наблюдатель или экзаменационный центр.",
                "Cihaz değişikliğini yalnızca gözetmen veya sınav merkezi onaylayabilir.",
            ),
            _same(
                "Tələbənin davam edən final cəhdi yoxdur.",
                "The student has no final attempt in progress.",
                "У студента нет незавершённой попытки итогового экзамена.",
                "Öğrencinin devam eden bir final denemesi yok.",
            ),
            _same(
                "Cihaz dəyişikliyinə icazə verildi — tələbə %(minutes)d dəqiqə ərzində yeni cihazdan davam edə bilər.",
                "Device change approved — the student can continue from a new device within %(minutes)d minutes.",
                "Смена устройства подтверждена — студент может продолжить с нового устройства в течение "
                "%(minutes)d мин.",
                "Cihaz değişikliği onaylandı — öğrenci %(minutes)d dakika içinde yeni bir cihazdan devam edebilir.",
            ),
            _same(
                "Cəhd hələ heç bir cihaza bağlanmayıb — tələbə ilk açdığı cihazdan davam edəcək.",
                "The attempt is not bound to a device yet — the student will continue on the first device that opens it.",
                "Попытка ещё не привязана к устройству — студент продолжит на первом устройстве, с которого её "
                "откроет.",
                "Deneme henüz bir cihaza bağlanmadı — öğrenci onu ilk açtığı cihazdan devam edecek.",
            ),
            _same(
                "Cihaz dəyişikliyinə icazə ver",
                "Approve device change",
                "Разрешить смену устройства",
                "Cihaz değişikliğine izin ver",
            ),
            _same(
                "Cihaz dəyişikliyi təsdiqlənib — tələbə yeni cihazdan daxil olmalıdır",
                "Device change approved — the student should sign in on the new device",
                "Смена устройства подтверждена — студенту нужно войти с нового устройства",
                "Cihaz değişikliği onaylandı — öğrenci yeni cihazdan giriş yapmalı",
            ),
            _same(
                "Təsdiq alınmadı — yenidən cəhd edin.",
                "Approval failed — please try again.",
                "Не удалось подтвердить — попробуйте ещё раз.",
                "Onay alınamadı — lütfen tekrar deneyin.",
            ),
        ]
    ),
    "exams.model.final_device.meta": {
        "singular": _t(
            "Final cəhdinin cihazı",
            "Final attempt device",
            "Устройство попытки итогового экзамена",
            "Final denemesi cihazı",
        ),
        "plural": _t(
            "Final cəhdlərinin cihazları",
            "Final attempt devices",
            "Устройства попыток итогового экзамена",
            "Final denemesi cihazları",
        ),
    },
}


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                flags = ["python-format"] if "%(" in msgid else []
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want, flags=flags))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if stale and entry.msgstr != want:
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
