#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 PROC: anti-cheat proktorinq qatı + İM monitorunda tələbə kimliyi (sahib).

Əlavə olunan mətnlər:
  * `exams.proctoring.signal`   — evristik siqnal etiketləri (services/supervision/signals.py);
  * `exams.proctoring.monitor`  — İM monitoru JS etiketləri (#fxc-proctor-i18n) + müəllim hesabatı;
  * `exams.proctoring.identity` — imtahan başlığındakı kimlik çipi;
  * `exams.proctoring.form`     — imtahan formasının «Qabaqcıl aşkarlama» bloku;
  * `exams.proctoring.teacher`  — müəllimin cəhd səhifəsindəki proktorinq hesabatı.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_proc_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_SIGNAL = [
    _t(
        "Tərtibatçı alətləri (DevTools) açıq ola bilər",
        "Developer tools (DevTools) may be open",
        "Возможно, открыты инструменты разработчика (DevTools)",
        "Geliştirici araçları (DevTools) açık olabilir",
    ),
    _t(
        "Əlavə monitor qoşulub",
        "An extra monitor is connected",
        "Подключён дополнительный монитор",
        "Ek monitör bağlı",
    ),
    _t(
        "Səhifəyə kənar element əlavə olunub",
        "A foreign element was injected into the page",
        "На страницу добавлен посторонний элемент",
        "Sayfaya yabancı bir öğe eklendi",
    ),
    _t(
        "Brauzer genişlənməsinin pəncərəsi aşkarlandı",
        "A browser-extension frame was detected",
        "Обнаружено окно расширения браузера",
        "Tarayıcı eklentisi penceresi algılandı",
    ),
    _t(
        "Brauzer genişlənməsinin izi aşkarlandı",
        "Traces of a browser extension were detected",
        "Обнаружены следы расширения браузера",
        "Tarayıcı eklentisi izi algılandı",
    ),
    _t(
        "Süni intellekt köməkçisi (genişlənmə) aşkarlandı",
        "AI assistant (extension) detected",
        "Обнаружен ИИ-помощник (расширение)",
        "Yapay zekâ asistanı (eklenti) algılandı",
    ),
    _t(
        "Avtomatlaşdırılmış brauzer (bot)",
        "Automated browser (bot)",
        "Автоматизированный браузер (бот)",
        "Otomatik tarayıcı (bot)",
    ),
    _t(
        "Cavab xanasına yapışdırma cəhdi",
        "Paste attempt into an answer field",
        "Попытка вставки в поле ответа",
        "Cevap alanına yapıştırma girişimi",
    ),
    _t(
        "Cavaba bir anda böyük mətn daxil edildi",
        "A large block of text was inserted into an answer at once",
        "В ответ одним действием вставлен большой текст",
        "Cevaba tek seferde büyük bir metin eklendi",
    ),
    _t(
        "Cavab skriptlə dəyişdirildi",
        "The answer was changed by a script",
        "Ответ изменён скриптом",
        "Cevap bir betik tarafından değiştirildi",
    ),
    _t("Qeyri-adi sürətli yazı", "Unusually fast typing", "Необычно быстрый ввод", "Olağandışı hızlı yazma"),
    _t("Çap cəhdi", "Print attempt", "Попытка печати", "Yazdırma girişimi"),
    _t(
        "Nəzarət siqnalı müvəqqəti kəsilmişdi",
        "The proctoring signal was temporarily lost",
        "Сигнал контроля временно пропадал",
        "Gözetim sinyali geçici olarak kesilmişti",
    ),
]

_MONITOR = [
    _t("Kimlik yoxlaması", "Identity check", "Проверка личности", "Kimlik kontrolü"),
    _t("Şəkil yüklənməyib", "No photo uploaded", "Фото не загружено", "Fotoğraf yüklenmemiş"),
    _t("Qrup", "Group", "Группа", "Grup"),
    _t("Tələbə №", "Student No.", "Студент №", "Öğrenci No."),
    _t("Risk xalı", "Risk score", "Балл риска", "Risk puanı"),
    _t(
        "Risk xalı / şübhə həddi — qayda pozuntuları və siqnalların ciddiliyinin cəmi",
        "Risk score / flag threshold — the summed severity of rule violations and signals",
        "Балл риска / порог подозрения — сумма серьёзности нарушений правил и сигналов",
        "Risk puanı / şüphe eşiği — kural ihlalleri ve sinyallerin önem derecelerinin toplamı",
    ),
    _t("Şübhəli", "Suspicious", "Подозрительно", "Şüpheli"),
    _t("siqnal", "signals", "сигналов", "sinyal"),
    _t("Nəzarət siqnalı kəsilib", "Proctoring signal lost", "Сигнал контроля пропал", "Gözetim sinyali kesildi"),
    _t("Nəzarət siqnalı yoxdur", "No proctoring signal", "Нет сигнала контроля", "Gözetim sinyali yok"),
    _t("Hadisə xronologiyası", "Event timeline", "Хронология событий", "Olay zaman çizelgesi"),
    _t("Qayda", "Rule", "Правило", "Kural"),
    _t("Siqnal", "Signal", "Сигнал", "Sinyal"),
    _t("pozuntu sayılır", "counts as a violation", "считается нарушением", "ihlal sayılır"),
    _t("Hadisə qeydə alınmayıb.", "No events recorded.", "События не зафиксированы.", "Kayıtlı olay yok."),
    _t("Kritik", "Critical", "Критично", "Kritik seviye"),
    _t("Yüksək", "High", "Высокая", "Yüksek seviye"),
    _t("Orta", "Medium", "Средняя", "Orta seviye"),
    _t("Aşağı", "Low", "Низкая", "Düşük seviye"),
    _t("Məlumat", "Info", "Информация", "Bilgi"),
]

_IDENTITY = [
    _t("Qrup", "Group", "Группа", "Grup"),
    _t("Tələbə №", "Student No.", "Студент №", "Öğrenci No."),
]

_FORM = [
    _t(
        "Qabaqcıl aşkarlama (genişlənmə, süni intellekt, DevTools)",
        "Advanced detection (extensions, AI, DevTools)",
        "Расширенное обнаружение (расширения, ИИ, DevTools)",
        "Gelişmiş algılama (eklentiler, yapay zekâ, DevTools)",
    ),
    _t(
        "Bu yoxlamalar tələbəni kilidləmir — yalnız qeyd edir və nəzarətçiyə göstərir. Risk xalı həddə çatanda "
        "cəhd «şübhəli» işarələnir.",
        "These checks never lock the student — they only record and show events to the proctor. When the risk "
        "score reaches the threshold, the attempt is marked “suspicious”.",
        "Эти проверки не блокируют студента — они лишь фиксируют события и показывают их наблюдателю. Когда балл "
        "риска достигает порога, попытка помечается как «подозрительная».",
        "Bu kontroller öğrenciyi kilitlemez — yalnızca kaydeder ve gözetmene gösterir. Risk puanı eşiğe "
        "ulaştığında deneme «şüpheli» olarak işaretlenir.",
    ),
    _t(
        "Süni intellekt köməkçilərinə və brauzer genişlənmələrinə qarşı qoruma (sual mətni seçilmir, kənar "
        "elementlər aşkarlanır)",
        "Protection against AI assistants and browser extensions (question text cannot be selected, injected "
        "elements are detected)",
        "Защита от ИИ-помощников и расширений браузера (текст вопроса нельзя выделить, посторонние элементы "
        "обнаруживаются)",
        "Yapay zekâ asistanlarına ve tarayıcı eklentilerine karşı koruma (soru metni seçilemez, yabancı öğeler "
        "algılanır)",
    ),
    _t(
        "Cavaba kənardan mətn daxil edilməsini aşkarla (yapışdırma, skriptlə yazma, qeyri-adi sürət)",
        "Detect text injected into answers (pasting, script-typed text, unusual speed)",
        "Обнаруживать внешний ввод текста в ответ (вставка, ввод скриптом, необычная скорость)",
        "Cevaba dışarıdan metin eklenmesini algıla (yapıştırma, betikle yazma, olağandışı hız)",
    ),
    _t(
        "Tərtibatçı alətlərinin (DevTools) açılmasını aşkarla",
        "Detect opening of developer tools (DevTools)",
        "Обнаруживать открытие инструментов разработчика (DevTools)",
        "Geliştirici araçlarının (DevTools) açılmasını algıla",
    ),
    _t(
        "Əlavə monitorun qoşulmasını aşkarla (dəstəkləyən brauzerlərdə)",
        "Detect an extra connected monitor (in supporting browsers)",
        "Обнаруживать подключение дополнительного монитора (в поддерживающих браузерах)",
        "Ek monitör bağlanmasını algıla (destekleyen tarayıcılarda)",
    ),
    _t(
        "Şübhə həddi (risk xalı)",
        "Flag threshold (risk score)",
        "Порог подозрения (балл риска)",
        "Şüphe eşiği (risk puanı)",
    ),
]

_TEACHER = [
    _t("Proktorinq hesabatı", "Proctoring report", "Отчёт о прокторинге", "Gözetim raporu"),
    _t("Pozuntu", "Violations", "Нарушения", "İhlal"),
    _t("Risk xalı", "Risk score", "Балл риска", "Risk puanı"),
    _t(
        "Risk xalı qayda pozuntuları və evristik siqnalların ciddiliyinin cəmidir. Yalnız məlumat üçündür — "
        "nəticəyə avtomatik təsir etmir; qərarı müəllim/komissiya verir.",
        "The risk score is the summed severity of rule violations and heuristic signals. It is informational "
        "only — it never changes the result automatically; the teacher/committee decides.",
        "Балл риска — сумма серьёзности нарушений правил и эвристических сигналов. Он носит лишь "
        "информационный характер и не влияет на результат автоматически; решение принимает преподаватель/комиссия.",
        "Risk puanı, kural ihlalleri ve sezgisel sinyallerin önem derecelerinin toplamıdır. Yalnızca bilgi "
        "amaçlıdır — sonucu otomatik olarak etkilemez; kararı öğretmen/komisyon verir.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    "exams.proctoring.signal": {row["az"]: row for row in _SIGNAL},
    "exams.proctoring.monitor": {row["az"]: row for row in _MONITOR},
    "exams.proctoring.identity": {row["az"]: row for row in _IDENTITY},
    "exams.proctoring.form": {row["az"]: row for row in _FORM},
    "exams.proctoring.teacher": {row["az"]: row for row in _TEACHER},
}

FORCE = set()


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
