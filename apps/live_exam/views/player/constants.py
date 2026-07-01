"""live_exam player paketi — constants."""

from apps.live_exam.constants import REACTIONS
from apps.live_exam.models import LiveSession

PIN_ENTRY_COPY = {
    "az": {
        "title": "Canlı imtahana qoşul",
        "eyebrow": "EMSArena Live",
        "subtitle": "Müəllimin göstərdiyi PIN-i yaz, sonra adını seçib oyuna daxil ol.",
        "pin_label": "Oyun PIN-i",
        "pin_placeholder": "Məsələn: 3A8K2B94F1",
        "button": "Davam et",
        "hint": "PIN-i ekranda gördüyün kimi daxil et. Növbəti addımda ad və avatar seçəcəksən.",
        "feature_fast": "Saniyələr içində qoşul",
        "feature_device": "Telefon, planşet və kompüterdən işləyir",
        "feature_live": "Canlı nəticə və liderlik cədvəli",
        "card_title": "Hazırsan?",
        "card_subtitle": "Bir URL, bir PIN, hamısı eyni oyunda.",
        "footer_left": "Müəllim ekranında PIN və QR kod görünür.",
        "footer_right": "Daxil olduqdan sonra avatar və ad seçimi gəlir.",
        "loading": "Yoxlanılır...",
        "invalid_pin": "Düzgün PIN daxil et.",
        "session_not_found": "Bu PIN tapılmadı və ya oyun bağlanıb.",
    },
    "en": {
        "title": "Join a live exam",
        "eyebrow": "EMSArena Live",
        "subtitle": "Enter the PIN shown by the teacher, then choose your name and join the game.",
        "pin_label": "Game PIN",
        "pin_placeholder": "Example: 3A8K2B94F1",
        "button": "Continue",
        "hint": "Type the PIN exactly as shown on screen. You will choose your nickname and avatar next.",
        "feature_fast": "Join in seconds",
        "feature_device": "Works on phone, tablet, and desktop",
        "feature_live": "Live results and leaderboard",
        "card_title": "Ready to play?",
        "card_subtitle": "One link, one PIN, everyone in the same session.",
        "footer_left": "The teacher screen shows the PIN and QR code.",
        "footer_right": "After this step, students choose nickname and avatar.",
        "loading": "Checking...",
        "invalid_pin": "Enter a valid PIN.",
        "session_not_found": "This PIN was not found or the session is closed.",
    },
    "ru": {
        "title": "Присоединитесь к живому экзамену",
        "eyebrow": "EMSArena Live",
        "subtitle": "Введите PIN, который показал преподаватель, затем выберите имя и войдите в игру.",
        "pin_label": "PIN игры",
        "pin_placeholder": "Например: 3A8K2B94F1",
        "button": "Продолжить",
        "hint": "Введите PIN точно как на экране. На следующем шаге вы выберете ник и аватар.",
        "feature_fast": "Подключение за несколько секунд",
        "feature_device": "Работает на телефоне, планшете и компьютере",
        "feature_live": "Живые результаты и таблица лидеров",
        "card_title": "Готовы?",
        "card_subtitle": "Одна ссылка, один PIN, одна общая сессия.",
        "footer_left": "На экране преподавателя видны PIN и QR-код.",
        "footer_right": "После этого шага ученик выбирает ник и аватар.",
        "loading": "Проверяем...",
        "invalid_pin": "Введите действительный PIN.",
        "session_not_found": "Такой PIN не найден или сессия уже закрыта.",
    },
    "tr": {
        "title": "Canlı sınava katıl",
        "eyebrow": "EMSArena Live",
        "subtitle": "Öğretmenin gösterdiği PIN kodunu gir, sonra adını seçip oyuna katıl.",
        "pin_label": "Oyun PIN'i",
        "pin_placeholder": "Örnek: 3A8K2B94F1",
        "button": "Devam et",
        "hint": "PIN kodunu ekrandaki gibi gir. Sonraki adımda rumuz ve avatar seçeceksin.",
        "feature_fast": "Saniyeler içinde katıl",
        "feature_device": "Telefon, tablet ve bilgisayarda çalışır",
        "feature_live": "Canlı sonuç ve lider tablosu",
        "card_title": "Hazır mısın?",
        "card_subtitle": "Tek link, tek PIN, herkes aynı oturumda.",
        "footer_left": "Öğretmen ekranında PIN ve QR kod görünür.",
        "footer_right": "Bu adımdan sonra öğrenci ad ve avatar seçer.",
        "loading": "Kontrol ediliyor...",
        "invalid_pin": "Geçerli bir PIN gir.",
        "session_not_found": "Bu PIN bulunamadı veya oturum kapanmış.",
    },
}


JOIN_RESUME_COPY = {
    "az": {
        "notice_title": "Əvvəlki qoşulma tapıldı",
        "notice_body": "{nickname} adı ilə bu oyuna artıq daxil olmusan.",
        "notice_hint": "İstəsən həmin oyunçu ilə davam et, istəsən yeni ad və avatarla yenidən qoşul.",
        "continue_button": "{nickname} kimi davam et",
        "modal_title": "Əvvəlki adla davam etmək istəyirsən?",
        "modal_body": "Bu PIN üçün aktiv oyunçu profilin var. Həmin profil ilə gözləmə otağına qayıda və ya yeni ad/avatar seçib yenidən daxil ola bilərsən.",
        "restart_button": "Yenidən daxil ol",
        "close_button": "Bağla",
    },
    "en": {
        "notice_title": "Previous join found",
        "notice_body": "You already joined this game as {nickname}.",
        "notice_hint": "Continue with that player or join again with a new nickname and avatar.",
        "continue_button": "Continue as {nickname}",
        "modal_title": "Continue with your previous name?",
        "modal_body": "You already have an active player profile for this PIN. You can jump back into the waiting room or join again with a new nickname and avatar.",
        "restart_button": "Join again",
        "close_button": "Close",
    },
    "ru": {
        "notice_title": "Найдено предыдущее подключение",
        "notice_body": "Вы уже вошли в эту игру как {nickname}.",
        "notice_hint": "Можно продолжить с этим игроком или войти заново с новым именем и аватаром.",
        "continue_button": "Продолжить как {nickname}",
        "modal_title": "Продолжить с прежним именем?",
        "modal_body": "Для этого PIN уже есть активный профиль игрока. Вы можете вернуться в комнату ожидания или войти заново с новым именем и аватаром.",
        "restart_button": "Войти заново",
        "close_button": "Закрыть",
    },
    "tr": {
        "notice_title": "Önceki katılım bulundu",
        "notice_body": "Bu oyuna zaten {nickname} adıyla katıldın.",
        "notice_hint": "İstersen aynı oyuncuyla devam et, istersen yeni rumuz ve avatarla tekrar katıl.",
        "continue_button": "{nickname} olarak devam et",
        "modal_title": "Önceki adınla devam etmek ister misin?",
        "modal_body": "Bu PIN için aktif bir oyuncu profilin var. Bekleme odasına geri dönebilir ya da yeni rumuz ve avatarla yeniden katılabilirsin.",
        "restart_button": "Yeniden katıl",
        "close_button": "Kapat",
    },
}


NICKNAME_CONFLICT_COPY = {
    "az": "Bu ad artıq istifadə olunur. Başqa ad seç.",
    "en": "This nickname is already in use. Choose another one.",
    "ru": "Этот ник уже используется. Выберите другой.",
    "tr": "Bu rumuz zaten kullanılıyor. Başka bir ad seç.",
}


LIVE_JOIN_LIMIT_SCOPE = "live_exam.join"


LIVE_PIN_LIMIT_SCOPE = "live_exam.pin"


LIVE_REACTION_LIMIT_SCOPE = "live_exam.reaction"


LIVE_RATE_LIMIT_MESSAGE = "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."


REACTION_EMOJI = dict(REACTIONS)


_AMBIGUOUS_PIN_GLYPHS = {
    "0": ("0", "O"),
    "O": ("0", "O"),
    "1": ("1", "I", "L"),
    "I": ("1", "I", "L"),
    "L": ("1", "I", "L"),
}


_MAX_AMBIGUOUS_PIN_CANDIDATES = 64


_JOINABLE_SESSION_STATES = (
    LiveSession.STATE_LOBBY,
    LiveSession.STATE_QUESTION,
    LiveSession.STATE_REVEAL,
)
