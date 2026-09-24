#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: 3 kollokvium → TƏK 20 ballıq «Midterm» (2026/2027-dən), jurnal tərəfi.

Registrar: rejim təsviri (``interim_assessment``), müəllim tabı (``_jd_kollokvium.html``),
jurnal tab adı/lent, «Yekun» cədvəli, tələbə jurnal görünüşü, düzəliş modalı, bal-yazma
mesajları və bildirişlər. Keçmiş dövrlərin kollokvium mətnləri olduğu kimi qalır.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_midterm_journal_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

J = "registrar.journal"
STRINGS = {
    # ── apps/registrar/interim_assessment.py ─────────────────────────────────
    ("registrar.interim", "Kollokvium"): ("Colloquium", "Коллоквиум", "Kolokyum"),
    ("registrar.interim", "Midterm"): ("Midterm", "Мидтерм", "Vize"),
    ("registrar.interim", "3 kollokvium (hər biri 0–10 bal)"): (
        "3 colloquiums (0–10 points each)",
        "3 коллоквиума (по 0–10 баллов)",
        "3 kolokyum (her biri 0–10 puan)",
    ),
    ("registrar.interim", "Midterm — aralıq imtahan (0–20 bal)"): (
        "Midterm — mid-semester exam (0–20 points)",
        "Мидтерм — промежуточный экзамен (0–20 баллов)",
        "Vize — ara sınav (0–20 puan)",
    ),
    # ── apps/registrar/journal_actions.py (kontekstsiz gettext) ──────────────
    (None, "%(title)s bal-yazma pəncərəsi açıq deyil — İmtahan Mərkəzi aralığı aktivləşdirməlidir."): (
        "The %(title)s score-entry window is not open — the Exam Centre has to activate the interval.",
        "Окно ввода баллов «%(title)s» не открыто — его должен активировать Экзаменационный центр.",
        "%(title)s puan giriş penceresi açık değil — Sınav Merkezi aralığı etkinleştirmelidir.",
    ),
    (None, "Pəncərəsi bağlı olan sütunların balı yazılmadı."): (
        "Scores in columns whose window is closed were not saved.",
        "Баллы в столбцах с закрытым окном не сохранены.",
        "Penceresi kapalı sütunların puanları kaydedilmedi.",
    ),
    (None, "%(title)s balları yadda saxlanıldı (%(n)s xana)."): (
        "%(title)s scores saved (%(n)s cells).",
        "Баллы «%(title)s» сохранены (ячеек: %(n)s).",
        "%(title)s puanları kaydedildi (%(n)s hücre).",
    ),
    # ── apps/registrar/kollokvium_notifications.py ───────────────────────────
    ("registrar.kollokvium_notify", "Kollokvium K%(n)s"): ("Colloquium K%(n)s", "Коллоквиум K%(n)s", "Kolokyum K%(n)s"),
    ("registrar.kollokvium_notify", "%(name)s bal-yazma pəncərəsi açıldı: %(opens)s–%(closes)s"): (
        "%(name)s score-entry window opened: %(opens)s–%(closes)s",
        "Окно ввода баллов «%(name)s» открыто: %(opens)s–%(closes)s",
        "%(name)s puan giriş penceresi açıldı: %(opens)s–%(closes)s",
    ),
    ("registrar.kollokvium_notify", "%(name)s bal-yazma pəncərəsi bağlandı"): (
        "%(name)s score-entry window closed",
        "Окно ввода баллов «%(name)s» закрыто",
        "%(name)s puan giriş penceresi kapandı",
    ),
    ("registrar.kollokvium_notify", "%(name)s bal-yazma pəncərəsinin tarixi dəyişdi: %(opens)s–%(closes)s"): (
        "%(name)s score-entry window dates changed: %(opens)s–%(closes)s",
        "Даты окна ввода баллов «%(name)s» изменены: %(opens)s–%(closes)s",
        "%(name)s puan giriş penceresinin tarihleri değişti: %(opens)s–%(closes)s",
    ),
    # ── apps/registrar/journal_notifications.py ──────────────────────────────
    ("registrar.notify", "Kollokvium"): ("Colloquium", "Коллоквиум", "Kolokyum"),
    ("registrar.notify", "%(label)s balı yazıldı: %(score)s"): (
        "%(label)s score recorded: %(score)s",
        "Выставлен балл «%(label)s»: %(score)s",
        "%(label)s puanı girildi: %(score)s",
    ),
    # ── Jurnal şablonları ────────────────────────────────────────────────────
    (J, "Midterm"): ("Midterm", "Мидтерм", "Vize"),
    (J, "MIDTERM"): ("MIDTERM", "МИДТЕРМ", "VİZE"),
    (J, "şkala 0–20"): ("scale 0–20", "шкала 0–20", "ölçek 0–20"),
    (J, "Köhnə qeyd"): ("Legacy entry", "Старая запись", "Eski kayıt"),
    (J, "aralıq imtahan balı"): ("mid-semester exam score", "балл промежуточного экзамена", "ara sınav puanı"),
    (J, "hələ yazılmayıb"): ("not recorded yet", "ещё не выставлен", "henüz girilmedi"),
    (
        J,
        "Midterm — aralıq imtahandır, 0–20 bal. Bal-yazma aralığını İmtahan Mərkəzi təyin edir. Pəncərə açıq "
        "olduqca balı sərbəst yaza/dəyişə bilərsiniz; bağlanandan sonra kilidlənir. Boş buraxılan bal 0 sayılır.",
    ): (
        "The midterm is the mid-semester exam, 0–20 points. The Exam Centre sets the score-entry interval. While "
        "the window is open you can enter or change scores freely; once it closes they are locked. An empty score "
        "counts as 0.",
        "Мидтерм — промежуточный экзамен, 0–20 баллов. Интервал ввода баллов устанавливает Экзаменационный центр. "
        "Пока окно открыто, баллы можно свободно вводить и менять; после закрытия они блокируются. Пустой балл "
        "считается 0.",
        "Vize ara sınavdır, 0–20 puan. Puan giriş aralığını Sınav Merkezi belirler. Pencere açıkken puanı serbestçe "
        "girebilir/değiştirebilirsiniz; kapandıktan sonra kilitlenir. Boş bırakılan puan 0 sayılır.",
    ),
    (
        J,
        "Hazırda açıq Midterm pəncərəsi yoxdur — bal yazmaq üçün İmtahan Mərkəzinin aralığı aktivləşdirməsini "
        "gözləyin.",
    ): (
        "There is no open midterm window at the moment — to enter scores, wait for the Exam Centre to activate "
        "the interval.",
        "Сейчас нет открытого окна мидтерма — чтобы ввести баллы, дождитесь, пока Экзаменационный центр "
        "активирует интервал.",
        "Şu anda açık vize penceresi yok — puan girmek için Sınav Merkezinin aralığı etkinleştirmesini bekleyin.",
    ),
    (
        J,
        "İmtahana qədər bal — jurnalın kanonik giriş balıdır (dərs balları + midterm + sərbəst iş, tavan",
    ): (
        "Pre-exam score is the journal's canonical entry score (lesson scores + midterm + independent work, cap",
        "Балл до экзамена — канонический входной балл журнала (баллы занятий + мидтерм + самостоятельная "
        "работа, предел",
        "Sınav öncesi puan, derginin kanonik giriş puanıdır (ders puanları + vize + serbest çalışma, tavan",
    ),
    # ── Düzəliş modalı ───────────────────────────────────────────────────────
    ("registrar.correction", "Yeni bal"): ("New score", "Новый балл", "Yeni puan"),
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
