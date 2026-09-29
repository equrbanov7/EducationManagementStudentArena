#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-29 canlı oyun: OYUNÇU (telefon) təcrübəsi (LX-FE-PLAYER).

Əlavə olunan mətnlər:
  * `live_exam.player` — oyun ekranının bütün mətnləri (əvvəl ingiliscə sərt kodlanmışdı:
    «Question», «Get ready», «Correct» və s.), yazılı cavab, çox seçim, nəticə, yer/fərq,
    final (podium, statistika), bağlantı zolağı, səs düyməsi, fiqur adları;
  * `live_exam.wait_room.js` — gözləmə otağı: oyunçu sayı, kilid nişanı, «çıxarıldın» kartı,
    «oyun başlayır», reaksiya soyuması, aksesuar və avatar adları, JS ilə doldurulan şablon mətnləri;
  * `live_exam.join.js` — qoşulma: ad yoxlaması, «başqa avatar», blok kartı, limit sayğacı.

Mövcud, lakin SƏHV/qarışıq dildə olan tərcümələr üstələnir (FORCE): az «Nickname» → «Adın» və s.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_lxplayer_2026_09_29.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    "live_exam.player": {
        "page_title": {"az": "Canlı oyun", "en": "Live game", "ru": "Живая игра", "tr": "Canlı oyun"},
        "announce_answers_open": {
            "az": "Cavab ver! {seconds} saniyə",
            "en": "Answer now! {seconds} seconds",
            "ru": "Отвечай! {seconds} сек.",
            "tr": "Cevapla! {seconds} saniye",
        },
        "announce_question": {
            "az": "Sual {index}: {text}",
            "en": "Question {index}: {text}",
            "ru": "Вопрос {index}: {text}",
            "tr": "Soru {index}: {text}",
        },
        "answer_locked": {
            "az": "Cavabın qəbul edildi!",
            "en": "Answer locked in!",
            "ru": "Ответ принят!",
            "tr": "Cevabın alındı!",
        },
        "answer_sending": {"az": "Göndərilir…", "en": "Sending…", "ru": "Отправляем…", "tr": "Gönderiliyor…"},
        "answers_label": {
            "az": "Cavab variantları",
            "en": "Answer options",
            "ru": "Варианты ответа",
            "tr": "Cevap seçenekleri",
        },
        "collapse_question": {"az": "Qısalt", "en": "Show less", "ru": "Свернуть", "tr": "Daralt"},
        "connecting_game": {
            "az": "Oyuna qoşulur…",
            "en": "Connecting to the game…",
            "ru": "Подключаемся к игре…",
            "tr": "Oyuna bağlanılıyor…",
        },
        "error_send": {
            "az": "Cavab göndərilmədi. Yenidən cəhd et.",
            "en": "Your answer was not sent. Try again.",
            "ru": "Ответ не отправлен. Попробуй ещё раз.",
            "tr": "Cevap gönderilemedi. Tekrar dene.",
        },
        "error_send_offline": {
            "az": "Cavab göndərilmədi — internet bağlantısını yoxla.",
            "en": "Answer not sent — check your internet connection.",
            "ru": "Ответ не отправлен — проверь подключение к интернету.",
            "tr": "Cevap gönderilemedi — internet bağlantını kontrol et.",
        },
        "expand_question": {"az": "Tam oxu", "en": "Read more", "ru": "Читать полностью", "tr": "Devamını oku"},
        "final_keep_going": {
            "az": "Hər oyun səni daha güclü edir — növbəti dəfə podiuma!",
            "en": "Every game makes you stronger — podium next time!",
            "ru": "Каждая игра делает тебя сильнее — в следующий раз на " "пьедестал!",
            "tr": "Her oyun seni daha güçlü yapar — bir dahaki sefere " "podyuma!",
        },
        "final_podium_title": {"az": "Podium", "en": "Podium", "ru": "Пьедестал", "tr": "Podyum"},
        "final_second": {
            "az": "Gümüş medal!",
            "en": "Silver medal!",
            "ru": "Серебряная медаль!",
            "tr": "Gümüş madalya!",
        },
        "final_third": {
            "az": "Bürünc medal!",
            "en": "Bronze medal!",
            "ru": "Бронзовая медаль!",
            "tr": "Bronz madalya!",
        },
        "final_title": {"az": "Oyun bitdi!", "en": "Game over!", "ru": "Игра окончена!", "tr": "Oyun bitti!"},
        "final_well_played": {
            "az": "Əla oyun idi, {name}!",
            "en": "Well played, {name}!",
            "ru": "Отличная игра, {name}!",
            "tr": "Harika oyundu, {name}!",
        },
        "final_winner": {"az": "Qalib sənsən!", "en": "You won!", "ru": "Победа за тобой!", "tr": "Kazanan sensin!"},
        "final_your_place": {"az": "Sənin yerin", "en": "Your place", "ru": "Твоё место", "tr": "Sıralaman"},
        "gap_line": {
            "az": "{name} səndən {gap} xal öndədir",
            "en": "{name} is {gap} pts ahead of you",
            "ru": "{name} опережает тебя на {gap} очк.",
            "tr": "{name} senden {gap} puan önde",
        },
        "gap_tie": {
            "az": "{name} ilə xalın bərabərdir",
            "en": "You're tied with {name}",
            "ru": "У тебя столько же очков, сколько у {name}",
            "tr": "{name} ile puanınız eşit",
        },
        "get_ready_body": {
            "az": "İlk sual gəlir…",
            "en": "The first question is coming…",
            "ru": "Первый вопрос уже близко…",
            "tr": "İlk soru geliyor…",
        },
        "get_ready_title": {"az": "Hazır ol!", "en": "Get ready!", "ru": "Приготовься!", "tr": "Hazır ol!"},
        "intro_hint_main_screen": {
            "az": "Suala böyük ekranda bax",
            "en": "Look at the big screen for the question",
            "ru": "Смотри вопрос на большом экране",
            "tr": "Soruyu büyük ekranda gör",
        },
        "intro_unlocking": {
            "az": "Cavablar {seconds} san sonra açılır",
            "en": "Answers open in {seconds}s",
            "ru": "Ответы откроются через {seconds} с",
            "tr": "Cevaplar {seconds} sn sonra açılıyor",
        },
        "last_question_note": {
            "az": "Bu son sual idi — yekun nəticələr gəlir!",
            "en": "That was the last question — final results are coming!",
            "ru": "Это был последний вопрос — скоро итоги!",
            "tr": "Bu son soruydu — final sonuçları geliyor!",
        },
        "multi_badge": {
            "az": "Bir neçə cavab",
            "en": "Multiple answers",
            "ru": "Несколько ответов",
            "tr": "Birden fazla cevap",
        },
        "multi_counter": {
            "az": "{count}/{max} seçildi",
            "en": "{count}/{max} selected",
            "ru": "Выбрано: {count}/{max}",
            "tr": "{count}/{max} seçildi",
        },
        "multi_hint": {
            "az": "Ən çox {max} cavab seç, sonra «Göndər»",
            "en": "Pick up to {max} answers, then tap “Send”",
            "ru": "Выбери до {max} ответов и нажми «Отправить»",
            "tr": "En fazla {max} cevap seç, sonra “Gönder”e dokun",
        },
        "multi_max_reached": {
            "az": "Ən çox {max} variant seçə bilərsən",
            "en": "You can pick at most {max} options",
            "ru": "Можно выбрать не больше {max} вариантов",
            "tr": "En fazla {max} seçenek seçebilirsin",
        },
        "net_back": {"az": "Yenidən onlayn!", "en": "Back online!", "ru": "Снова в сети!", "tr": "Tekrar çevrimiçi!"},
        "net_offline": {
            "az": "İnternet yoxdur — bağlantı gözlənilir",
            "en": "No internet — waiting for a connection",
            "ru": "Нет интернета — ждём подключения",
            "tr": "İnternet yok — bağlantı bekleniyor",
        },
        "net_reconnecting": {
            "az": "Bağlantı bərpa olunur…",
            "en": "Reconnecting…",
            "ru": "Восстанавливаем соединение…",
            "tr": "Yeniden bağlanılıyor…",
        },
        "next_question_soon": {
            "az": "Növbəti sual tezliklə…",
            "en": "Next question coming up…",
            "ru": "Скоро следующий вопрос…",
            "tr": "Sıradaki soru birazdan…",
        },
        "player_fallback": {"az": "Oyunçu", "en": "Player", "ru": "Игрок", "tr": "Oyuncu"},
        "points_short": {"az": "xal", "en": "pts", "ru": "очк.", "tr": "puan"},
        "question_counter": {
            "az": "Sual {index} / {total}",
            "en": "Question {index} / {total}",
            "ru": "Вопрос {index} / {total}",
            "tr": "Soru {index} / {total}",
        },
        "question_hidden_body": {
            "az": "Sual böyük ekrandadır — oradan oxu",
            "en": "The question is on the big screen — read it there",
            "ru": "Вопрос на большом экране — читай там",
            "tr": "Soru büyük ekranda — oradan oku",
        },
        "question_short": {
            "az": "{index}/{total}",
            "en": "{index}/{total}",
            "ru": "{index}/{total}",
            "tr": "{index}/{total}",
        },
        "rank_aria": {
            "az": "Yerin: {rank}",
            "en": "Your place: {rank}",
            "ru": "Твоё место: {rank}",
            "tr": "Sıran: {rank}",
        },
        "rank_down": {
            "az": "{count} pillə aşağı",
            "en": "down {count}",
            "ru": "на {count} вниз",
            "tr": "{count} basamak aşağı",
        },
        "rank_leader": {
            "az": "Liderdəsən! Belə davam et 👑",
            "en": "You're in the lead! Keep it up 👑",
            "ru": "Ты лидируешь! Так держать 👑",
            "tr": "Liderdesin! Böyle devam 👑",
        },
        "rank_line": {
            "az": "Sən {place} yerdəsən",
            "en": "You're in {place} place",
            "ru": "Твоё место: {place}",
            "tr": "{place} sıradasın",
        },
        "rank_up": {
            "az": "{count} pillə yuxarı",
            "en": "up {count}",
            "ru": "на {count} вверх",
            "tr": "{count} basamak yukarı",
        },
        "rejoin_game": {"az": "Yenidən qoşul", "en": "Join again", "ru": "Войти снова", "tr": "Tekrar katıl"},
        "removed_body": {
            "az": "Oyunçu profilin tapılmadı — müəllim səni çıxarmış və ya oyun " "bağlanmış ola bilər.",
            "en": "Your player profile was not found — the teacher may have " "removed you or the game has closed.",
            "ru": "Профиль игрока не найден — возможно, преподаватель удалил тебя " "или игра закрыта.",
            "tr": "Oyuncu profilin bulunamadı — öğretmen seni çıkarmış ya da oyun " "kapanmış olabilir.",
        },
        "removed_title": {
            "az": "Bu oyunda deyilsən",
            "en": "You're not in this game",
            "ru": "Тебя нет в этой игре",
            "tr": "Bu oyunda değilsin",
        },
        "result_accepted": {
            "az": "Düzgün cavab",
            "en": "Accepted answer",
            "ru": "Правильный ответ",
            "tr": "Doğru cevap",
        },
        "result_correct": {"az": "Düzgün!", "en": "Correct!", "ru": "Верно!", "tr": "Doğru!"},
        "result_correct_answer": {
            "az": "Düzgün cavab",
            "en": "Correct answer",
            "ru": "Правильный ответ",
            "tr": "Doğru cevap",
        },
        "result_correct_answers": {
            "az": "Düzgün cavablar",
            "en": "Correct answers",
            "ru": "Правильные ответы",
            "tr": "Doğru cevaplar",
        },
        "result_missed": {
            "az": "Bu sualı buraxdın",
            "en": "You missed this one",
            "ru": "Этот вопрос пропущен",
            "tr": "Bu soruyu kaçırdın",
        },
        "result_no_answer": {"az": "Cavab verilmədi", "en": "No answer", "ru": "Нет ответа", "tr": "Cevap verilmedi"},
        "result_no_points": {
            "az": "Bu dəfə xal yoxdur",
            "en": "No points this time",
            "ru": "В этот раз без очков",
            "tr": "Bu sefer puan yok",
        },
        "result_partial": {"az": "Qismən düzgün", "en": "Partly correct", "ru": "Частично верно", "tr": "Kısmen doğru"},
        "result_partial_detail": {
            "az": "{correct}/{total} düzgün",
            "en": "{correct}/{total} correct",
            "ru": "{correct}/{total} верно",
            "tr": "{correct}/{total} doğru",
        },
        "result_speed": {"az": "{seconds} san", "en": "{seconds}s", "ru": "{seconds} с", "tr": "{seconds} sn"},
        "result_wrong": {"az": "Səhv cavab", "en": "Incorrect", "ru": "Неверно", "tr": "Yanlış"},
        "result_wrong_picked": {
            "az": "{count} səhv seçim",
            "en": "{count} wrong pick(s)",
            "ru": "неверных: {count}",
            "tr": "{count} yanlış seçim",
        },
        "scoreboard_title": {"az": "Liderlər", "en": "Leaderboard", "ru": "Лидеры", "tr": "Liderler"},
        "sound_turn_off": {"az": "Səsi söndür", "en": "Mute sound", "ru": "Выключить звук", "tr": "Sesi kapat"},
        "sound_turn_on": {"az": "Səsi aç", "en": "Turn sound on", "ru": "Включить звук", "tr": "Sesi aç"},
        "stat_avg_time": {
            "az": "Orta cavab vaxtı",
            "en": "Average answer time",
            "ru": "Среднее время ответа",
            "tr": "Ortalama cevap süresi",
        },
        "stat_best_streak": {"az": "Ən uzun seriya", "en": "Best streak", "ru": "Лучшая серия", "tr": "En uzun seri"},
        "stat_correct": {"az": "Düzgün cavab", "en": "Correct answers", "ru": "Верных ответов", "tr": "Doğru cevap"},
        "streak_label": {
            "az": "{count} ardıcıl düzgün!",
            "en": "{count} in a row!",
            "ru": "{count} подряд!",
            "tr": "Üst üste {count} doğru!",
        },
        "submit_answer": {"az": "Cavabı göndər", "en": "Send answer", "ru": "Отправить ответ", "tr": "Cevabı gönder"},
        "tap_for_sound": {
            "az": "Səs üçün ekrana toxun",
            "en": "Tap the screen to enable sound",
            "ru": "Коснись экрана, чтобы включить звук",
            "tr": "Ses için ekrana dokun",
        },
        "time_up_body": {
            "az": "Bu sualı cavablandırmadın. Növbəti sualda uğurlar!",
            "en": "You didn't answer this one. Good luck on the next!",
            "ru": "На этот вопрос ответа нет. Удачи в следующем!",
            "tr": "Bu soruyu cevaplamadın. Sonrakinde bol şans!",
        },
        "time_up_title": {"az": "Vaxt bitdi!", "en": "Time's up!", "ru": "Время вышло!", "tr": "Süre doldu!"},
        "typed_badge": {"az": "Yazılı cavab", "en": "Typed answer", "ru": "Письменный ответ", "tr": "Yazılı cevap"},
        "typed_empty": {
            "az": "Əvvəlcə cavabını yaz",
            "en": "Type your answer first",
            "ru": "Сначала напиши ответ",
            "tr": "Önce cevabını yaz",
        },
        "typed_label": {"az": "Cavabını yaz", "en": "Type your answer", "ru": "Напиши ответ", "tr": "Cevabını yaz"},
        "typed_placeholder": {
            "az": "Cavabını bura yaz…",
            "en": "Type your answer here…",
            "ru": "Напиши ответ здесь…",
            "tr": "Cevabını buraya yaz…",
        },
        "typed_send": {"az": "Göndər", "en": "Send", "ru": "Отправить", "tr": "Gönder"},
        "wait_msg_1": {
            "az": "Barmaqlarını çarpaz saxla 🤞",
            "en": "Fingers crossed 🤞",
            "ru": "Скрестим пальцы 🤞",
            "tr": "Parmaklar çapraz 🤞",
        },
        "wait_msg_2": {
            "az": "Görək nə olacaq…",
            "en": "Let's see how it goes…",
            "ru": "Посмотрим, что будет…",
            "tr": "Bakalım ne olacak…",
        },
        "wait_msg_3": {"az": "Cəsarətli seçim!", "en": "Bold choice!", "ru": "Смелый выбор!", "tr": "Cesur seçim!"},
        "wait_msg_4": {
            "az": "Digərləri hələ düşünür…",
            "en": "Others are still thinking…",
            "ru": "Остальные ещё думают…",
            "tr": "Diğerleri hâlâ düşünüyor…",
        },
        "wait_msg_5": {
            "az": "Nəticəni birlikdə görəcəyik!",
            "en": "We'll see the result together!",
            "ru": "Скоро узнаем результат!",
            "tr": "Sonucu birlikte göreceğiz!",
        },
        "waiting_for_host": {
            "az": "Müəllimin növbəti addımı gözlənilir…",
            "en": "Waiting for the teacher's next step…",
            "ru": "Ждём следующего шага преподавателя…",
            "tr": "Öğretmenin sonraki adımı bekleniyor…",
        },
        "waiting_title": {"az": "Az qaldı!", "en": "Almost there!", "ru": "Почти начали!", "tr": "Az kaldı!"},
        "you_chose": {"az": "Sənin seçimin", "en": "Your choice", "ru": "Твой выбор", "tr": "Seçimin"},
        "you_label": {"az": "Sən", "en": "You", "ru": "Ты", "tr": "Sen"},
        "your_answer": {
            "az": "Cavabın: «{text}»",
            "en": "Your answer: “{text}”",
            "ru": "Твой ответ: «{text}»",
            "tr": "Cevabın: “{text}”",
        },
        "shape_triangle": {"az": "Üçbucaq", "en": "Triangle", "ru": "Треугольник", "tr": "Üçgen"},
        "shape_diamond": {"az": "Romb", "en": "Diamond", "ru": "Ромб", "tr": "Karo"},
        "shape_circle": {"az": "Dairə", "en": "Circle", "ru": "Круг", "tr": "Daire"},
        "shape_square": {"az": "Kvadrat", "en": "Square", "ru": "Квадрат", "tr": "Kare"},
        "shape_star": {"az": "Ulduz", "en": "Star", "ru": "Звезда", "tr": "Yıldız"},
        "shape_hexagon": {"az": "Altıbucaq", "en": "Hexagon", "ru": "Шестиугольник", "tr": "Altıgen"},
    },
    "live_exam.wait_room.js": {
        "players_count": {
            "az": "{count} oyunçu qoşulub",
            "en": "{count} players joined",
            "ru": "Подключились: {count}",
            "tr": "{count} oyuncu katıldı",
        },
        "players_alone": {
            "az": "Hələlik yalnız sənsən",
            "en": "It's just you so far",
            "ru": "Пока ты один(одна)",
            "tr": "Şimdilik sadece sen varsın",
        },
        "waiting_host_start": {
            "az": "Müəllimin oyunu başlatmasını gözləyirik",
            "en": "Waiting for the teacher to start",
            "ru": "Ждём, пока преподаватель начнёт игру",
            "tr": "Öğretmenin oyunu başlatması bekleniyor",
        },
        "lobby_locked_badge": {
            "az": "Lobbi bağlanıb — oyun tezliklə başlayır",
            "en": "Lobby is locked — the game starts soon",
            "ru": "Лобби закрыто — игра скоро начнётся",
            "tr": "Lobi kilitli — oyun birazdan başlıyor",
        },
        "kicked_title": {
            "az": "Müəllim səni oyundan çıxardı",
            "en": "The teacher removed you from the game",
            "ru": "Преподаватель удалил тебя из игры",
            "tr": "Öğretmen seni oyundan çıkardı",
        },
        "kicked_body": {
            "az": "Bu cihazla bu oyuna yenidən qoşulmaq mümkün deyil. Səhv " "olubsa, müəllimə yaz.",
            "en": "This device can't rejoin this game. If it's a mistake, " "tell your teacher.",
            "ru": "С этого устройства вернуться в игру нельзя. Если это " "ошибка, скажи преподавателю.",
            "tr": "Bu cihazla bu oyuna tekrar katılamazsın. Bir hata varsa " "öğretmenine söyle.",
        },
        "kicked_action": {
            "az": "Başqa PIN daxil et",
            "en": "Enter another PIN",
            "ru": "Ввести другой PIN",
            "tr": "Başka PIN gir",
        },
        "game_starting": {
            "az": "Oyun başlayır!",
            "en": "The game is starting!",
            "ru": "Игра начинается!",
            "tr": "Oyun başlıyor!",
        },
        "nickname_locked_hint": {
            "az": "Lobbi bağlıdır — ad artıq dəyişmir, avatarı " "dəyişə bilərsən.",
            "en": "The lobby is locked — you can't change your name " "now, but you can change your avatar.",
            "ru": "Лобби закрыто — имя менять нельзя, но аватар " "можно.",
            "tr": "Lobi kilitli — adını değiştiremezsin ama " "avatarını değiştirebilirsin.",
        },
        "reaction_sent": {"az": "Göndərildi!", "en": "Sent!", "ru": "Отправлено!", "tr": "Gönderildi!"},
        "reaction_wait": {
            "az": "Bir az gözlə — reaksiyalar çox tez-tezdir",
            "en": "Slow down a little — too many reactions",
            "ru": "Подожди немного — слишком много реакций",
            "tr": "Biraz bekle — çok sık tepki gönderiyorsun",
        },
        "net_reconnecting": {
            "az": "Bağlantı bərpa olunur…",
            "en": "Reconnecting…",
            "ru": "Восстанавливаем соединение…",
            "tr": "Yeniden bağlanılıyor…",
        },
        "net_offline": {
            "az": "İnternet yoxdur — bağlantı gözlənilir",
            "en": "No internet — waiting for a connection",
            "ru": "Нет интернета — ждём подключения",
            "tr": "İnternet yok — bağlantı bekleniyor",
        },
        "net_back": {"az": "Yenidən onlayn!", "en": "Back online!", "ru": "Снова в сети!", "tr": "Tekrar çevrimiçi!"},
        "player_fallback": {"az": "Oyunçu", "en": "Player", "ru": "Игрок", "tr": "Oyuncu"},
        "nickname_counter": {
            "az": "{count}/{max}",
            "en": "{count}/{max}",
            "ru": "{count}/{max}",
            "tr": "{count}/{max}",
        },
        "removed_title": {
            "az": "Bu oyunda deyilsən",
            "en": "You're not in this game",
            "ru": "Тебя нет в этой игре",
            "tr": "Bu oyunda değilsin",
        },
        "rejoin_game": {"az": "Yenidən qoşul", "en": "Join again", "ru": "Войти снова", "tr": "Tekrar katıl"},
        "look_on_screen": {
            "az": "Adını böyük ekranda axtar!",
            "en": "Look for your name on the big screen!",
            "ru": "Найди своё имя на большом экране!",
            "tr": "Adını büyük ekranda ara!",
        },
        "edit_look": {"az": "Görünüşü dəyiş", "en": "Change look", "ru": "Изменить облик", "tr": "Görünümü değiştir"},
        "reactions_hint": {
            "az": "Reaksiya göndər",
            "en": "Send a reaction",
            "ru": "Отправь реакцию",
            "tr": "Tepki gönder",
        },
        "accessory_name_accessory_none": {"az": "Yoxdur", "en": "None", "ru": "Нет", "tr": "Yok"},
        "accessory_name_glasses": {"az": "Eynək", "en": "Glasses", "ru": "Очки", "tr": "Gözlük"},
        "accessory_name_cap": {"az": "Papaq", "en": "Cap", "ru": "Кепка", "tr": "Şapka"},
        "accessory_name_crown": {"az": "Tac", "en": "Crown", "ru": "Корона", "tr": "Taç"},
        "accessory_name_mask": {"az": "Maska", "en": "Mask", "ru": "Маска", "tr": "Maske"},
        "accessory_name_sparkles": {"az": "Parıltı", "en": "Sparkles", "ru": "Блёстки", "tr": "Parıltı"},
        "accessory_name_bowtie": {"az": "Kəpənək qalstuk", "en": "Bow tie", "ru": "Бабочка", "tr": "Papyon"},
        "accessory_name_headphones": {"az": "Qulaqlıq", "en": "Headphones", "ru": "Наушники", "tr": "Kulaklık"},
        "accessory_name_flower": {"az": "Gül", "en": "Flower", "ru": "Цветок", "tr": "Çiçek"},
        "accessory_name_pirate_patch": {
            "az": "Pirat sarğısı",
            "en": "Eye patch",
            "ru": "Пиратская повязка",
            "tr": "Korsan bandı",
        },
        "accessory_name_halo": {"az": "Halə", "en": "Halo", "ru": "Нимб", "tr": "Hale"},
        "avatar_name_avatar_1": {"az": "Tülkü", "en": "Fox", "ru": "Лиса", "tr": "Tilki"},
        "avatar_name_avatar_2": {"az": "Panda", "en": "Panda", "ru": "Панда", "tr": "Panda"},
        "avatar_name_avatar_3": {"az": "Şir", "en": "Lion", "ru": "Лев", "tr": "Aslan"},
        "avatar_name_avatar_4": {"az": "Pələng", "en": "Tiger", "ru": "Тигр", "tr": "Kaplan"},
        "avatar_name_avatar_5": {"az": "Koala", "en": "Koala", "ru": "Коала", "tr": "Koala"},
        "avatar_name_avatar_6": {"az": "Donuz balası", "en": "Piglet", "ru": "Поросёнок", "tr": "Domuz yavrusu"},
        "avatar_name_avatar_7": {"az": "Qurbağa", "en": "Frog", "ru": "Лягушка", "tr": "Kurbağa"},
        "avatar_name_avatar_8": {"az": "Səkkizayaq", "en": "Octopus", "ru": "Осьминог", "tr": "Ahtapot"},
        "avatar_name_avatar_9": {"az": "Meymun", "en": "Monkey", "ru": "Обезьяна", "tr": "Maymun"},
        "avatar_name_avatar_10": {"az": "Təkbuynuz", "en": "Unicorn", "ru": "Единорог", "tr": "Tek boynuzlu at"},
        "avatar_name_avatar_11": {"az": "Dovşan", "en": "Rabbit", "ru": "Кролик", "tr": "Tavşan"},
        "avatar_name_avatar_12": {"az": "Hamster", "en": "Hamster", "ru": "Хомяк", "tr": "Hamster"},
        "avatar_name_avatar_13": {"az": "Canavar", "en": "Wolf", "ru": "Волк", "tr": "Kurt"},
        "avatar_name_avatar_14": {"az": "Ağ ayı", "en": "Polar bear", "ru": "Белый медведь", "tr": "Kutup ayısı"},
        "avatar_name_avatar_15": {"az": "Qırmızı panda", "en": "Red panda", "ru": "Красная панда", "tr": "Kızıl panda"},
        "avatar_name_avatar_16": {
            "az": "Nanə dovşanı",
            "en": "Mint bunny",
            "ru": "Мятный кролик",
            "tr": "Nane tavşanı",
        },
        "nickname_required": {
            "az": "Ad boş ola bilməz.",
            "en": "Nickname cannot be empty.",
            "ru": "Никнейм не может быть пустым.",
            "tr": "Takma ad boş olamaz.",
        },
        "nickname_too_long": {
            "az": "Ad çox uzundur.",
            "en": "Nickname is too long.",
            "ru": "Никнейм слишком длинный.",
            "tr": "Takma ad çok uzun.",
        },
    },
    "live_exam.join.js": {
        "player_label": {"az": "Oyunçu", "en": "Player", "ru": "Игрок", "tr": "Oyuncu"},
        "nickname_required": {
            "az": "Adını yaz.",
            "en": "Enter your nickname.",
            "ru": "Введи никнейм.",
            "tr": "Takma adını yaz.",
        },
        "nickname_too_long": {
            "az": "Ad çox uzundur.",
            "en": "Nickname is too long.",
            "ru": "Никнейм слишком длинный.",
            "tr": "Takma ad çok uzun.",
        },
        "reroll_avatar": {"az": "Başqa avatar", "en": "Another avatar", "ru": "Другой аватар", "tr": "Başka avatar"},
        "join_blocked_title": {
            "az": "Qoşulmaq alınmadı",
            "en": "Couldn't join",
            "ru": "Не удалось подключиться",
            "tr": "Katılamadın",
        },
        "try_again": {"az": "Yenidən yoxla", "en": "Try again", "ru": "Попробовать снова", "tr": "Tekrar dene"},
        "enter_new_pin": {
            "az": "Başqa PIN daxil et",
            "en": "Enter another PIN",
            "ru": "Ввести другой PIN",
            "tr": "Başka PIN gir",
        },
        "rate_limited_wait": {
            "az": "Çox tez-tez cəhd edildi — {seconds} san sonra yenidən " "yoxla.",
            "en": "Too many attempts — try again in {seconds}s.",
            "ru": "Слишком много попыток — повтори через {seconds} с.",
            "tr": "Çok fazla deneme — {seconds} sn sonra tekrar dene.",
        },
    },
    "live_exam.wait_room": {
        "nickname_label": {"az": "Adın", "en": "Nickname", "ru": "Никнейм", "tr": "Takma ad"},
        "nickname_placeholder": {
            "az": "Adını yaz",
            "en": "Enter your nickname",
            "ru": "Введи никнейм",
            "tr": "Takma adını yaz",
        },
    },
}

# Mövcud olan, amma yanlış/qarışıq dildə olan tərcümələr — həmişə üstələnir.
FORCE = {
    ("live_exam.wait_room", "nickname_label"),
    ("live_exam.wait_room", "nickname_placeholder"),
    ("live_exam.wait_room.js", "nickname_required"),
    ("live_exam.wait_room.js", "nickname_too_long"),
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
