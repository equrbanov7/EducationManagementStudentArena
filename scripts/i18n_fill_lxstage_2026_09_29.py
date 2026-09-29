#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-29 canlı oyun: aparıcı (proyektor) ekranı + final səhnəsi (LX-FE-STAGE).

Əlavə olunan mətnlər (hamısı `liveExam/partials/_host_i18n.html` JSON blokunda, JS oxuyur):
  * `live_exam.host_game`     — lobbi, hazır ol / 3-2-1, sual, cavab açılışı, liderlər lövhəsi,
                                cavab fiqurlarının adları, sürətli düymə mətnləri;
  * `live_exam.host_sound`    — proyektordakı səs idarəsi (susdur / səviyyə / fon musiqisi);
  * `live_exam.host_stage`    — final səhnəsi (yerlər, bərabər xal, təkrar, statistika);
  * `live_exam.host_settings` — tənzimləmə çekməcəsinin «Cavab rejimi» bölməsi (çox seçimli bal,
                                yazı səhvlərinə dözüm, yazılı cavablı suallar və variant çipləri);
  * `liveExam.template.session_detail` — sessiya statistikası: CSV ixracı, yazılı cavablar.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_lxstage_2026_09_29.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

G = "live_exam.host_game"
SN = "live_exam.host_sound"
ST = "live_exam.host_stage"
DR = "live_exam.host_settings"
SD = "liveExam.template.session_detail"


def t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    G: {
        "lobby_join_at": t("Qoşulmaq üçün keçid", "Join at", "Подключайтесь по адресу", "Katılmak için adres"),
        "lobby_pin_label": t("Oyun PIN-i", "Game PIN", "PIN игры", "Oyun PIN'i"),
        "lobby_scan_qr": t(
            "Və ya QR kodu skan edin", "Or scan the QR code", "Или отсканируйте QR-код", "Veya QR kodu tarayın"
        ),
        "lobby_waiting": t(
            "İştirakçılar gözlənilir…", "Waiting for players…", "Ждём участников…", "Katılımcılar bekleniyor…"
        ),
        "lobby_ready": t(
            "Oyun tezliklə başlayır!", "The game starts soon!", "Игра скоро начнётся!", "Oyun birazdan başlıyor!"
        ),
        "lobby_ready_host": t(
            "Hazır olduqda «Başla» düyməsini basın",
            "Press “Start” when everyone is in",
            "Нажмите «Старт», когда все подключатся",
            "Herkes hazır olunca “Başlat”a basın",
        ),
        "lobby_locked": t("Qoşulma bağlanıb", "Joining is locked", "Вход закрыт", "Katılım kapatıldı"),
        "lobby_locked_hint": t(
            "Yeni iştirakçılar qoşula bilməz",
            "New players can't join",
            "Новые участники не могут войти",
            "Yeni katılımcılar katılamaz",
        ),
        "lobby_locked_label": t("Lobbi bağlıdır", "Lobby locked", "Лобби закрыто", "Lobi kilitli"),
        "lobby_players_word": t("iştirakçı", "players", "участников", "katılımcı"),
        "lobby_participants": t(
            "Qoşulan iştirakçılar", "Joined players", "Подключившиеся участники", "Katılan oyuncular"
        ),
        "lobby_empty": t(
            "Hələ heç kim qoşulmayıb — telefonla PIN-i daxil edin",
            "No one has joined yet — enter the PIN on your phone",
            "Пока никто не подключился — введите PIN на телефоне",
            "Henüz kimse katılmadı — telefonunuzdan PIN'i girin",
        ),
        "lobby_more": t("+{count} daha", "+{count} more", "ещё +{count}", "+{count} kişi daha"),
        "lobby_remove_player": t("İştirakçını çıxar", "Remove player", "Удалить участника", "Oyuncuyu çıkar"),
        "game_get_ready": t("Hazır olun!", "Get ready!", "Приготовьтесь!", "Hazır olun!"),
        "game_get_ready_sub": t(
            "{count} sual · telefonunuzu hazır saxlayın",
            "{count} questions · keep your phone ready",
            "Вопросов: {count} · держите телефон наготове",
            "{count} soru · telefonunuzu hazır tutun",
        ),
        "game_countdown_label": t(
            "Raund {value} saniyəyə başlayır",
            "Round starts in {value}",
            "Раунд начнётся через {value}",
            "Tur {value} saniye içinde başlıyor",
        ),
        "game_question_of": t(
            "Sual {index} / {total}",
            "Question {index} of {total}",
            "Вопрос {index} из {total}",
            "Soru {index} / {total}",
        ),
        "game_multi_badge": t(
            "Bir neçə düzgün cavab", "Several correct answers", "Несколько верных ответов", "Birden fazla doğru cevap"
        ),
        "game_multi_pick": t(
            "{count} cavab seçin", "Pick {count} answers", "Выберите ответов: {count}", "{count} cevap seçin"
        ),
        "game_text_badge": t("Yazılı cavab", "Typed answer", "Письменный ответ", "Yazılı cevap"),
        "game_text_prompt": t(
            "Cavabı telefonunuzda yazın",
            "Type your answer on your phone",
            "Введите ответ на телефоне",
            "Cevabınızı telefonunuza yazın",
        ),
        "game_text_placeholder": t("Cavabınızı yazın…", "Type your answer…", "Введите ответ…", "Cevabınızı yazın…"),
        "game_seconds_short": t("san", "sec", "сек", "sn"),
        "game_answers_label": t("cavab", "answers", "ответов", "cevap"),
        "game_all_answered": t("Hamı cavab verdi!", "Everyone answered!", "Все ответили!", "Herkes cevapladı!"),
        "game_time_up": t("Vaxt bitdi!", "Time's up!", "Время вышло!", "Süre doldu!"),
        "game_read_time": t("Sualı oxuyun…", "Read the question…", "Прочитайте вопрос…", "Soruyu okuyun…"),
        "game_correct_answer": t("Düzgün cavab", "Correct answer", "Правильный ответ", "Doğru cevap"),
        "game_correct_answers": t("Düzgün cavablar", "Correct answers", "Правильные ответы", "Doğru cevaplar"),
        "game_correct_summary": t(
            "{correct} / {total} düzgün cavab",
            "{correct} of {total} answered correctly",
            "Верно ответили: {correct} из {total}",
            "{correct} / {total} doğru cevap",
        ),
        "game_no_answers": t(
            "Bu raundda cavab verilmədi",
            "No answers this round",
            "В этом раунде ответов нет",
            "Bu turda cevap verilmedi",
        ),
        "game_partial_credit": t(
            "Qismən bal: hər düzgün seçim bal gətirir",
            "Partial credit: every correct choice scores",
            "Частичные баллы: каждый верный выбор приносит очки",
            "Kısmi puan: her doğru seçim puan kazandırır",
        ),
        "game_strict_credit": t(
            "Bal yalnız bütün düzgün variantlar seçiləndə verilir",
            "Points only when all correct options are chosen",
            "Баллы только если выбраны все верные варианты",
            "Puan yalnızca tüm doğru seçenekler seçildiğinde verilir",
        ),
        "game_fastest": t("Ən sürətli", "Fastest", "Самый быстрый", "En hızlı"),
        "game_accepted_also": t(
            "Qəbul edilən variantlar", "Also accepted", "Также принимается", "Kabul edilen diğer cevaplar"
        ),
        "game_typed_top": t(
            "Ən çox yazılan cavablar", "Most typed answers", "Самые частые ответы", "En çok yazılan cevaplar"
        ),
        "game_leaderboard": t("Liderlər lövhəsi", "Leaderboard", "Таблица лидеров", "Liderlik tablosu"),
        "game_leaderboard_last": t(
            "Son sual bitdi — final səhnəsi gəlir!",
            "That was the last question — the final stage is next!",
            "Это был последний вопрос — впереди финальная сцена!",
            "Son soru bitti — sırada final sahnesi var!",
        ),
        "game_new_entry": t("Yeni", "New", "Новый", "Yeni"),
        "game_streak": t(
            "{count} ardıcıl düzgün", "{count} correct in a row", "{count} верных подряд", "Üst üste {count} doğru"
        ),
        "game_points": t("xal", "pts", "очк.", "puan"),
        "game_correct": t("Düzgün", "Correct", "Верно", "Doğru"),
        "game_wrong": t("Səhv", "Wrong", "Неверно", "Yanlış"),
        "game_close": t("Bağla", "Close", "Закрыть", "Kapat"),
        "game_skip": t("Keç", "Skip", "Пропустить", "Geç"),
        "shape_triangle": t("Üçbucaq", "Triangle", "Треугольник", "Üçgen"),
        "shape_diamond": t("Romb", "Diamond", "Ромб", "Eşkenar dörtgen"),
        "shape_circle": t("Dairə", "Circle", "Круг", "Daire"),
        "shape_square": t("Kvadrat", "Square", "Квадрат", "Kare"),
        "shape_star": t("Ulduz", "Star", "Звезда", "Yıldız"),
        "shape_hexagon": t("Altıbucaq", "Hexagon", "Шестиугольник", "Altıgen"),
    },
    SN: {
        "sound_title": t("Səs", "Sound", "Звук", "Ses"),
        "sound_on": t("Səs açıqdır", "Sound on", "Звук включён", "Ses açık"),
        "sound_off": t("Səs bağlıdır", "Sound off", "Звук выключен", "Ses kapalı"),
        "sound_volume": t("Səs səviyyəsi", "Volume", "Громкость", "Ses düzeyi"),
        "sound_music": t("Fon musiqisi", "Background music", "Фоновая музыка", "Arka plan müziği"),
        "sound_enable": t(
            "Səsi aktivləşdirmək üçün klikləyin",
            "Click to enable sound",
            "Нажмите, чтобы включить звук",
            "Sesi açmak için tıklayın",
        ),
    },
    ST: {
        "stage_title": t("Final nəticələr", "Final results", "Итоги", "Final sonuçları"),
        "stage_subtitle": t(
            "Qalibləri təbrik edirik!",
            "Congratulations to the winners!",
            "Поздравляем победителей!",
            "Kazananları tebrik ederiz!",
        ),
        "stage_place_1": t("1-ci yer", "1st place", "1-е место", "1. sıra"),
        "stage_place_2": t("2-ci yer", "2nd place", "2-е место", "2. sıra"),
        "stage_place_3": t("3-cü yer", "3rd place", "3-е место", "3. sıra"),
        "stage_tie": t("Bərabər xal", "Tied score", "Равный счёт", "Eşit puan"),
        "stage_replay": t("Yenidən göstər", "Replay", "Показать снова", "Tekrar göster"),
        "stage_no_players": t(
            "Bu oyunda iştirakçı olmadı",
            "No one played this game",
            "В этой игре не было участников",
            "Bu oyunda katılımcı yoktu",
        ),
        "stage_more": t("+{count} iştirakçı", "+{count} players", "+{count} участников", "+{count} katılımcı"),
        "stage_audience": t("Digər iştirakçılar", "Other players", "Остальные участники", "Diğer oyuncular"),
        "stage_stats_players": t("iştirakçı", "players", "участников", "katılımcı"),
        "stage_stats_questions": t("sual", "questions", "вопросов", "soru"),
        "stage_stats_accuracy": t("düzgünlük", "accuracy", "точность", "doğruluk"),
        "stage_stats_speed": t("orta cavab", "avg. answer", "средний ответ", "ort. cevap"),
        "stage_correct_count": t(
            "{correct}/{answered} düzgün",
            "{correct}/{answered} correct",
            "верно {correct}/{answered}",
            "{correct}/{answered} doğru",
        ),
        "stage_results": t("Ətraflı nəticələr", "Detailed results", "Подробные результаты", "Ayrıntılı sonuçlar"),
    },
    DR: {
        "answer_mode_title": t("Cavab rejimi", "Answer mode", "Режим ответов", "Cevap modu"),
        "multi_scoring_label": t(
            "Çox seçimli suallarda bal",
            "Scoring for multi-select questions",
            "Баллы за вопросы с несколькими ответами",
            "Çoklu seçimli sorularda puan",
        ),
        "multi_partial": t("Qismən bal", "Partial credit", "Частичные баллы", "Kısmi puan"),
        "multi_partial_help": t(
            "Hər düzgün seçilən variant üçün mütənasib bal verilir.",
            "Each correct option earns a proportional share of the points.",
            "За каждый верный вариант начисляется пропорциональная часть баллов.",
            "Her doğru seçenek için orantılı puan verilir.",
        ),
        "multi_strict": t(
            "Hamısı düzgün olmalıdır", "All must be correct", "Все должны быть верными", "Hepsi doğru olmalı"
        ),
        "multi_strict_help": t(
            "Bal yalnız bütün düzgün variantlar seçiləndə verilir.",
            "Points are awarded only when all correct options are chosen.",
            "Баллы начисляются, только если выбраны все верные варианты.",
            "Puan yalnızca tüm doğru seçenekler seçildiğinde verilir.",
        ),
        "typo_tolerance_label": t(
            "Kiçik yazı səhvlərini qəbul et",
            "Accept small typos",
            "Принимать мелкие опечатки",
            "Küçük yazım hatalarını kabul et",
        ),
        "typo_tolerance_help": t(
            "Yazılı cavablarda 1–2 hərflik səhv, böyük/kiçik hərf və artıq boşluqlar nəzərə alınmır.",
            "In typed answers, 1–2 letter mistakes, letter case and extra spaces are ignored.",
            "В письменных ответах не учитываются ошибки в 1–2 буквы, регистр и лишние пробелы.",
            "Yazılı cevaplarda 1–2 harflik hata, büyük/küçük harf ve fazla boşluklar dikkate alınmaz.",
        ),
        "typed_list_title": t("Yazılı cavab", "Typed answer", "Письменный ответ", "Yazılı cevap"),
        "typed_list_help": t(
            "Uyğun suallarda variantlar əvəzinə tələbə cavabı özü yazır.",
            "For suitable questions, students type the answer instead of choosing an option.",
            "В подходящих вопросах студенты вводят ответ сами вместо выбора варианта.",
            "Uygun sorularda öğrenciler seçenek yerine cevabı kendileri yazar.",
        ),
        "typed_toggle": t("Yazılı cavab", "Typed answer", "Письменный ответ", "Yazılı cevap"),
        "typed_accepted": t("Qəbul edilən cavablar", "Accepted answers", "Принимаемые ответы", "Kabul edilen cevaplar"),
        "typed_add_placeholder": t(
            "Variant əlavə et və Enter bas",
            "Add a variant and press Enter",
            "Добавьте вариант и нажмите Enter",
            "Bir cevap ekleyip Enter'a basın",
        ),
        "typed_not_eligible": t("Yalnız variantlı", "Choice only", "Только варианты", "Yalnızca seçenekli"),
        "typed_limit": t(
            "Ən çox 10 variant, hər biri 1–60 simvol.",
            "Up to 10 variants, 1–60 characters each.",
            "До 10 вариантов, по 1–60 символов.",
            "En fazla 10 cevap, her biri 1–60 karakter.",
        ),
        "typed_locked": t(
            "Oyun başlayandan sonra dəyişmək olmur",
            "Can't be changed after the game starts",
            "Нельзя изменить после начала игры",
            "Oyun başladıktan sonra değiştirilemez",
        ),
        "typed_empty": t(
            "Ən azı bir qəbul edilən cavab yazın",
            "Enter at least one accepted answer",
            "Введите хотя бы один принимаемый ответ",
            "En az bir kabul edilen cevap yazın",
        ),
        "chip_remove": t("Sil", "Remove", "Удалить", "Kaldır"),
        "saved_label": t("Yadda saxlanıldı", "Saved", "Сохранено", "Kaydedildi"),
        "save_error": t("Yadda saxlanılmadı", "Couldn't save", "Не удалось сохранить", "Kaydedilemedi"),
    },
    SD: {
        "export_csv": t("CSV-yə ixrac", "Export CSV", "Экспорт в CSV", "CSV olarak dışa aktar"),
        "typed_answers_heading": t("Yazılı cavablar", "Typed answers", "Письменные ответы", "Yazılı cevaplar"),
    },
}

# Mövcud, lakin SƏHV tərcümələri üstələmək üçün (bu paketdə yoxdur).
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
