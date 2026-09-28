#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 audit remediasiyası, A3 iş paketi (apellyasiya, tarixçə, buraxılış).

Əlavə olunan mətnlər:
  * `appeals.service.create.error` / `appeals.service.decision.error` — yoxlanmamış yazılı
    iş (EXA-02) və apellyasiya verilməyən kateqoriya (EXA-07) xətaları;
  * `appeals.template` — «Apellyasiya göndər» səhifəsinin yeni bannerləri;
  * `exams.final_center.error` — zal/PIN/kod yollarında qayıb limiti qapısı (EXA-04, fail-closed);
  * `registrar.journal` — cəhd tarixçəsində apellyasiya sətri (EXA-03).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_a3_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

CE = "appeals.service.create.error"
DE = "appeals.service.decision.error"
TPL = "appeals.template"
FC = "exams.final_center.error"
RJ = "registrar.journal"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    CE: {
        "Bu imtahan növü üzrə apellyasiya verilmir.": {
            "az": "Bu imtahan növü üzrə apellyasiya verilmir.",
            "en": "Appeals are not accepted for this type of exam.",
            "ru": "Апелляция по этому типу экзамена не подаётся.",
            "tr": "Bu sınav türü için itiraz yapılamaz.",
        },
        "İmtahanınız hələ yoxlanılmayıb — apellyasiya nəticə açıqlandıqdan sonra verilə bilər.": {
            "az": "İmtahanınız hələ yoxlanılmayıb — apellyasiya nəticə açıqlandıqdan sonra verilə bilər.",
            "en": "Your exam has not been graded yet — you can appeal once the result is published.",
            "ru": "Ваша работа ещё не проверена — апелляцию можно подать после объявления результата.",
            "tr": "Sınavınız henüz değerlendirilmedi — sonuç açıklandıktan sonra itiraz edebilirsiniz.",
        },
    },
    DE: {
        "İmtahan hələ yoxlanılmayıb — apellyasiyaya yoxlamadan sonra qərar verilə bilər.": {
            "az": "İmtahan hələ yoxlanılmayıb — apellyasiyaya yoxlamadan sonra qərar verilə bilər.",
            "en": "The exam has not been graded yet — the appeal can be decided only after grading.",
            "ru": "Работа ещё не проверена — решение по апелляции можно принять только после проверки.",
            "tr": "Sınav henüz değerlendirilmedi — itiraz ancak değerlendirmeden sonra karara bağlanabilir.",
        },
    },
    TPL: {
        "İmtahanınız hələ yoxlanılmayıb": {
            "az": "İmtahanınız hələ yoxlanılmayıb",
            "en": "Your exam has not been graded yet",
            "ru": "Ваша работа ещё не проверена",
            "tr": "Sınavınız henüz değerlendirilmedi",
        },
        "Apellyasiya işiniz yoxlanıb nəticə açıqlandıqdan sonra %(days)s gün ərzində göndərilə bilər.": {
            "az": "Apellyasiya işiniz yoxlanıb nəticə açıqlandıqdan sonra %(days)s gün ərzində göndərilə bilər.",
            "en": "You can submit an appeal within %(days)s days after your work is graded and the result is published.",
            "ru": "Апелляцию можно подать в течение %(days)s дн. после проверки работы и объявления результата.",
            "tr": "İtiraz, çalışmanız değerlendirilip sonuç açıklandıktan sonra %(days)s gün içinde yapılabilir.",
        },
        "Bu imtahan növü üzrə apellyasiya verilmir": {
            "az": "Bu imtahan növü üzrə apellyasiya verilmir",
            "en": "Appeals are not accepted for this type of exam",
            "ru": "Апелляция по этому типу экзамена не подаётся",
            "tr": "Bu sınav türü için itiraz yapılamaz",
        },
        "Apellyasiya yalnız aralıq (midterm) və yekun (final) imtahanları üzrə verilir.": {
            "az": "Apellyasiya yalnız aralıq (midterm) və yekun (final) imtahanları üzrə verilir.",
            "en": "Appeals can be submitted only for midterm and final exams.",
            "ru": "Апелляция подаётся только по промежуточным (midterm) и итоговым (final) экзаменам.",
            "tr": "İtiraz yalnızca ara sınav (midterm) ve final sınavları için yapılabilir.",
        },
    },
    FC: {
        "İmtahana buraxılış yoxlanıla bilmədi — nəzarətçiyə və ya imtahan mərkəzinə müraciət edin.": {
            "az": "İmtahana buraxılış yoxlanıla bilmədi — nəzarətçiyə və ya imtahan mərkəzinə müraciət edin.",
            "en": "Exam admission could not be verified — please contact the invigilator or the exam centre.",
            "ru": "Не удалось проверить допуск к экзамену — обратитесь к наблюдателю или в экзаменационный центр.",
            "tr": "Sınava kabul doğrulanamadı — gözetmene veya sınav merkezine başvurun.",
        },
        "Qayıb limiti keçildiyi üçün bu imtahana buraxılmırsınız.": {
            "az": "Qayıb limiti keçildiyi üçün bu imtahana buraxılmırsınız.",
            "en": "You are not admitted to this exam because you have exceeded the absence limit.",
            "ru": "Вы не допущены к этому экзамену, так как превышен лимит пропусков.",
            "tr": "Devamsızlık sınırı aşıldığı için bu sınava alınmıyorsunuz.",
        },
    },
    RJ: {
        "Apellyasiya": {"az": "Apellyasiya", "en": "Appeal", "ru": "Апелляция", "tr": "İtiraz"},
        "+%(delta)s bal": {
            "az": "+%(delta)s bal",
            "en": "+%(delta)s pts",
            "ru": "+%(delta)s балл.",
            "tr": "+%(delta)s puan",
        },
    },
}

# Mövcud, amma yanlış tərcümələr — bu paketdə yoxdur.
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
