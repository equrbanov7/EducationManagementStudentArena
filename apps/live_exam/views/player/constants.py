"""live_exam player paketi — constants."""

from apps.live_exam.constants import REACTIONS
from apps.live_exam.models import LiveSession

# 2026-10-08: PIN girişi / «əvvəlki qoşulma» / «ad məşğuldur» mətnləri — texts.py (gettext).


LIVE_JOIN_LIMIT_SCOPE = "live_exam.join"


LIVE_PIN_LIMIT_SCOPE = "live_exam.pin"


# Audit 2026-09-28 EX28-10: cookie-dən ASILI OLMAYAN İP vedrələri. Klient
# ``live_client_id`` cookie-sini hər sorğuda dəyişməklə dar vedrəni sıfırlaya
# bilirdi (atılan oyunçularla variant yoxlaması). Həddlər geniş saxlanılır —
# bir auditoriya adətən eyni NAT İP-si arxasındadır.
LIVE_JOIN_IP_LIMIT_SCOPE = "live_exam.join.ip"


LIVE_PIN_IP_LIMIT_SCOPE = "live_exam.pin.ip"


# Audit 2026-09-28 LXS-05: 90–150 tələbə eyni NAT İP-sindən qoşulur, bəziləri bir
# neçə dəfə yenidən. pin+İP vedrəsi indi YALNIZ yeni oyunçu cəhdlərini sayır və
# ≥ 3 × 150 hərəkətə görə ölçülüb (əvvəl 150/10dəq — reconnect-lər də sayılırdı,
# sinif kilidlənirdi). Ayarlarla eyni default: config/settings/components/admin_ratelimit.py.
LIVE_JOIN_IP_RATE_LIMIT_DEFAULT = "600/10m"


# Yalnız UĞURSUZ PIN axtarışları (brute force «miss» tələb edir); bütün PIN həll
# edən giriş nöqtələri üçün ortaq büdcə. 10 simvollu PIN (31^10) üçün 300/10dəq
# brute force-u praktiki olaraq sıfıra endirir, bir neçə sinfin səhvlərinə isə yer qoyur.
LIVE_PIN_IP_RATE_LIMIT_DEFAULT = "300/10m"


LIVE_REACTION_LIMIT_SCOPE = "live_exam.reaction"


# Audit 2026-09-28 LXS-11: sessiya-səviyyəli reaksiya tavanı — hər reaksiya lobbi
# qrupundakı BÜTÜN soketlərə yayılır (fan-out). Oyunçu başına 3/10s ilə atılan
# oyunçular sərhədsiz yük yaradırdı. ``LIVE_REACTION_SESSION_RATE_LIMIT`` ayarı ilə dəyişir.
LIVE_REACTION_SESSION_LIMIT_SCOPE = "live_exam.reaction.session"


LIVE_REACTION_SESSION_RATE_LIMIT_DEFAULT = "60/10s"


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
