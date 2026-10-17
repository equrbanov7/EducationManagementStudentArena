"""«Sistem tənzimləmələri» — işləmə vaxtı dəyişən limitlər (sahib 2026-10-03).

Sahib: «yalnız RİM rəhbərində olsun, settings kimi yer — hər şeyin limitlərini bir dəfəlik oradan artırıb
azaltmaq: AI modeli, OTP etibarlılıq dəqiqəsi, müəllimin jurnalı yazma dəqiqəsi, q/b dəyişmə müddəti…».

QAYDA: ``get(key)`` əvvəl bazadakı dəyişikliyə (``accounts.RuntimeSetting``), yoxdursa mühitin / kodun
DEFOLTUNA baxır — sətir olmayanda davranış əvvəlki kimidir. Yararsız saxlanmış dəyər heç vaxt tətbiq olunmur
(defolta düşür). Keş: proses daxili ``LOCAL_TTL`` saniyə + paylaşılan Redis açarı; yazıda hər ikisi silinir,
digər replikalar ən gec ``LOCAL_TTL`` saniyəyə yeni dəyəri görür. Testlərdə ``RUNTIME_SETTINGS_ENABLED=False``
(bazaya sorğu yoxdur — sorğu büdcəsi testləri pozulmur); xüsusiyyət testləri onu açır.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable

from django.conf import settings
from django.utils.translation import pgettext_lazy

logger = logging.getLogger(__name__)

_CTX = "core.runtime_settings"
CACHE_KEY = "emsarena:core:runtime_settings:v1"
CACHE_TTL = 300
LOCAL_TTL = 10

_local: dict = {"data": None, "expires": 0.0}


def _setting(name: str, fallback):
    return lambda: getattr(settings, name, fallback)


@dataclass(frozen=True)
class Spec:
    key: str
    group: str
    kind: str  # "int" | "decimal" | "rate" | "choice" | "bool"
    default: Callable[[], Any]
    label: Any
    help: Any = ""
    unit: Any = ""
    min: int | float = 0
    max: int | float = 0
    choices: Callable[[], list] | None = field(default=None, compare=False)
    #: Köhnəlmiş açar: «Sistem tənzimləmələri»ndə göstərilmir və saxlanmır, amma bazadakı dəyəri
    #: oxu nöqtəsində FALLBACK kimi tanınır (məs. ``journal.*_hours`` → ``journal.*_minutes``, 2026-10-15).
    hidden: bool = False
    #: Bu açarın əvəz etdiyi köhnə açar — yeni dəyər yazılanda / sıfırlananda köhnə sətir silinir
    #: (sıfırlanmış dəqiqə açarının arxasından köhnə saat dəyəri «dirilməsin»).
    legacy_key: str = ""


def _ai_model_choices() -> list:
    return [
        ("", pgettext_lazy(_CTX, "Avtomatik (cari tənzimləmə)")),
        ("gemini-3.8-flash", "gemini-3.8-flash"),
        ("gemini-3.5-flash-lite", "gemini-3.5-flash-lite"),
        ("gemini-flash-latest", "gemini-flash-latest"),
        ("gemini-pro-latest", "gemini-pro-latest"),
    ]


GROUPS = (
    ("academic", pgettext_lazy(_CTX, "Akademik qaydalar")),
    ("workload", pgettext_lazy(_CTX, "Dərs yükü norması və ştat")),
    ("login", pgettext_lazy(_CTX, "Giriş və parol cəhdləri")),
    ("otp", pgettext_lazy(_CTX, "E-poçt kodu (OTP)")),
    ("session", pgettext_lazy(_CTX, "Sessiya")),
    ("journal", pgettext_lazy(_CTX, "Elektron jurnal")),
    ("ai", pgettext_lazy(_CTX, "Süni intellekt")),
    ("exam", pgettext_lazy(_CTX, "İmtahanlar")),
    ("profile", pgettext_lazy(_CTX, "Məcburi profil məlumatları")),
)

_RATE_HELP = pgettext_lazy(_CTX, "Pəncərə ərzində icazə verilən say; keçəndə istifadəçi gözləməli olur.")

SPECS: dict[str, Spec] = {
    spec.key: spec
    for spec in (
        # ── Akademik qaydalar (sahib 2026-10-10 «Yeni qayda var») ─────────────────────────────────
        # Defolt = YENİ qayda; sətir yazılanda köhnəyə qayıtmaq olur. Mühit/test dəyişəni ilə də
        # (``ACADEMIC_*``) defolt dəyişə bilər — testlər ``override_settings`` ilə köhnə qaydanı yoxlayır.
        # Oxu nöqtəsi YALNIZ ``core.academic_rules`` — çağıranlar açarı birbaşa oxumur.
        Spec(
            "academic.selfwork_enabled", "academic", "bool", _setting("ACADEMIC_SELFWORK_ENABLED", False),
            pgettext_lazy(_CTX, "Sərbəst iş (10 bal)"),
            pgettext_lazy(
                _CTX,
                "Söndürülüdə sərbəst iş jurnalda, sillabusda, fənn qovluğunda və kabinetdə görünmür, onun 10 balı "
                "midterm-ə keçir (midterm 30). Yandırılanda əvvəlki qayda: midterm 20 + sərbəst iş 10. "
                "Yalnız 2026/2027 və sonrakı semestrlərə aiddir; köhnə semestrlərin qiymətləri dəyişmir.",
            ),
        ),
        Spec(
            "academic.activity_split", "academic", "bool", _setting("ACADEMIC_ACTIVITY_SPLIT", True),
            pgettext_lazy(_CTX, "Seminar və laboratoriya ayrıca (5 + 5 bal)"),
            pgettext_lazy(
                _CTX,
                "Fəndə həm seminar, həm laboratoriya varsa fəallıq balı: seminar ballarının ortası 5 + laboratoriya "
                "ballarının ortası 5. Yalnız biri varsa 10 bal onun ortasından. Söndürülüdə bütün seminar və "
                "laboratoriya balları birgə ortalanır.",
            ),
        ),
        Spec(
            "academic.coursework_enabled", "academic", "bool", _setting("ACADEMIC_COURSEWORK_ENABLED", False),
            pgettext_lazy(_CTX, "Kurs işi (jurnalda)"),
            pgettext_lazy(
                _CTX,
                "Söndürülüdə jurnalda «Kurs işi» tabı, addımı və düzəlişi görünmür, tələbə öz jurnalında da görmür. "
                "Kurs işi balı imtahana qədər bala daxil deyil — hesablamalar dəyişmir. Yalnız 2026/2027 və sonrakı "
                "semestrlərə aiddir; köhnə semestrlərdə və mövcud datada heç nə silinmir.",
            ),
        ),
        Spec(
            "syllabus.hours_from_load", "academic", "bool", _setting("SYLLABUS_HOURS_FROM_LOAD", True),
            pgettext_lazy(_CTX, "Sillabus dərs saatları yükdən"),
            pgettext_lazy(
                _CTX,
                "Yanılıda sillabusun mühazirə/seminar/laboratoriya saatları kafedranın paylanmış yükündən gəlir və "
                "müəllim dəyişə bilmir; yükdə olmayan dərs növü (məs. lab yoxdursa) həftəlik planda görünmür və ona "
                "saat yazılmır. Yükdə sətir yoxdursa müəllim saatı özü seçir. Söndürülüdə əvvəlki qayda: əvvəl "
                "təsdiqlənmiş tədris planı, sonra yük; artıq növlər də göstərilir.",
            ),
        ),
        # ── Dərs yükü norması və ştat (sahib 2026-10-14) ─────────────────────────────────────────
        # Oxu nöqtəsi YALNIZ ``apps.workload.services.norms`` — çağıranlar açarı birbaşa oxumur.
        # Qayda: inzibati vəzifəli → «inzibati» norma; 0,5 ştat → «0,5 ştat» norma; 1 ştat və profil yoxdursa →
        # «1 ştat» norma; digər paylar (0,25 / 0,75 / 1,25 / 1,5) → «1 ştat» norma × ştat payı.
        Spec(
            "workload.norm_hours_full", "workload", "int", lambda: 500,
            pgettext_lazy(_CTX, "İllik norma — 1 ştat"),
            pgettext_lazy(
                _CTX,
                "NK №215: bir ştat üzrə illik dərs yükü norması. 0,25 / 0,75 / 1,25 / 1,5 ştat üçün norma bu "
                "dəyərin ştat payına hasilidir (məs. 0,75 ştat → 0,75 × norma). Yük profili olmayan müəllimə də bu "
                "norma tətbiq olunur.",
            ),
            pgettext_lazy(_CTX, "saat"), min=100, max=1500,
        ),
        Spec(
            "workload.norm_hours_half", "workload", "int", lambda: 250,
            pgettext_lazy(_CTX, "İllik norma — 0,5 ştat"),
            pgettext_lazy(
                _CTX,
                "Yarım ştatda işləyən müəllimin illik norması — 1 ştat normasından avtomatik hesablanmır, ayrıca "
                "qeyd olunur.",
            ),
            pgettext_lazy(_CTX, "saat"), min=50, max=1000,
        ),
        Spec(
            "workload.norm_hours_admin", "workload", "int", lambda: 500,
            pgettext_lazy(_CTX, "İllik norma — inzibati vəzifəli müəllim"),
            pgettext_lazy(
                _CTX,
                "Dərs deməklə yanaşı inzibati vəzifə tutan müəllim (rektor, prorektor, dekan, dekan müavini, "
                "kafedra müdiri, şöbə müdiri, mərkəz rəhbəri, tyutor və s. — müəllimlikdən başqa aktiv rolu olan) "
                "üçün illik norma; ştat payından asılı deyil.",
            ),
            pgettext_lazy(_CTX, "saat"), min=50, max=1500,
        ),
        Spec(
            "workload.staff_rate_min", "workload", "decimal", lambda: Decimal("0.25"),
            pgettext_lazy(_CTX, "Bir müəllimə ən az ştat vahidi"),
            pgettext_lazy(
                _CTX,
                "Forma 7 siyahısından və ya başqa idxaldan gələn ştat payı bundan azdırsa yük profilinə yazılmır "
                "(hesabatda göstərilir). Saathesabı müəllimə (ştatsız) aid deyil.",
            ),
            pgettext_lazy(_CTX, "ştat"), min=0.05, max=1.0,
        ),
        Spec(
            "workload.staff_rate_max", "workload", "decimal", lambda: Decimal("1.5"),
            pgettext_lazy(_CTX, "Bir müəllimə ən çox ştat vahidi"),
            pgettext_lazy(
                _CTX,
                "KQ-12: bir müəllim ən çox 1,5 ştat tuta bilər. Bundan çox ştat payı yük profilinə yazılmır "
                "(hesabatda göstərilir).",
            ),
            pgettext_lazy(_CTX, "ştat"), min=0.5, max=3.0,
        ),
        Spec(
            "login.device_rate", "login", "rate", _setting("LOGIN_RATE_LIMIT", "5/10m"),
            pgettext_lazy(_CTX, "Bir cihazdan səhv parol cəhdi"), _RATE_HELP, min=3, max=100,
        ),
        Spec(
            "login.account_rate", "login", "rate", _setting("LOGIN_ACCOUNT_RATE_LIMIT", "20/1h"),
            pgettext_lazy(_CTX, "Bir hesaba səhv parol cəhdi (bütün cihazlardan)"), _RATE_HELP, min=5, max=200,
        ),
        Spec(
            "login.ip_rate", "login", "rate",
            lambda: getattr(settings, "LOGIN_IP_RATE_LIMIT", getattr(settings, "LOGIN_RATE_LIMIT", "5/10m")),
            pgettext_lazy(_CTX, "Bir İP ünvanından giriş cəhdi"),
            pgettext_lazy(_CTX, "Universitet Wi-Fi-ında yüzlərlə tələbə EYNİ İP-dən çıxır — çox aşağı saxlamayın."),
            min=20, max=5000,
        ),
        # Sahib 2026-10-15: sadə parol — yalnız uzunluq + qısa qadağa siyahısı (apps/accounts/password_policy.py).
        Spec(
            "password.min_length", "login", "int", _setting("PASSWORD_MIN_LENGTH", 8),
            pgettext_lazy(_CTX, "Parolun minimum uzunluğu"),
            pgettext_lazy(
                _CTX,
                "Yeni parol ən azı bu qədər simvol olmalıdır. Böyük hərf, rəqəm və ya simvol tələb olunmur — "
                "yalnız «12345678» kimi çox asan parollar və istifadəçi adı rədd edilir.",
            ),
            pgettext_lazy(_CTX, "simvol"), min=6, max=32,
        ),
        Spec(
            "otp.expiry_minutes", "otp", "int", lambda: max(1, int(getattr(settings, "AUTH_OTP_EXPIRY_SECONDS", 300)) // 60),
            pgettext_lazy(_CTX, "Kodun etibarlılıq müddəti"),
            pgettext_lazy(_CTX, "E-poçta gələn 6 rəqəmli kod bu qədər dəqiqə işləyir."),
            pgettext_lazy(_CTX, "dəqiqə"), min=2, max=60,
        ),
        Spec(
            "otp.max_sends_per_hour", "otp", "int", _setting("AUTH_OTP_MAX_SENDS_PER_HOUR", 5),
            pgettext_lazy(_CTX, "Bir e-poçta saatda göndərilən kod sayı"), "", pgettext_lazy(_CTX, "kod"), min=3, max=50,
        ),
        Spec(
            "otp.resend_cooldown_seconds", "otp", "int", _setting("AUTH_OTP_RESEND_COOLDOWN_SECONDS", 60),
            pgettext_lazy(_CTX, "Kodu yenidən göndərmə fasiləsi"), "", pgettext_lazy(_CTX, "saniyə"), min=30, max=600,
        ),
        Spec(
            "otp.max_attempts", "otp", "int", _setting("AUTH_OTP_MAX_ATTEMPTS", 5),
            pgettext_lazy(_CTX, "Bir kod üçün səhv yazma cəhdi"), "", pgettext_lazy(_CTX, "cəhd"), min=3, max=20,
        ),
        Spec(
            "otp.resend_rate", "otp", "rate", _setting("OTP_RESEND_RATE_LIMIT", "3/10m"),
            pgettext_lazy(_CTX, "Kodu yenidən istəmə (ilk giriş / qeydiyyat)"), _RATE_HELP, min=2, max=50,
        ),
        Spec(
            "otp.verify_rate", "otp", "rate", _setting("OTP_VERIFY_RATE_LIMIT", "5/10m"),
            pgettext_lazy(_CTX, "Kodu yoxlama cəhdi (qeydiyyat)"), _RATE_HELP, min=3, max=100,
        ),
        Spec(
            "otp.send_ip_rate", "otp", "rate", _setting("OTP_SEND_IP_RATE_LIMIT", "40/10m"),
            pgettext_lazy(_CTX, "Bir İP-dən parol bərpa kodu göndərmə"), _RATE_HELP, min=10, max=5000,
        ),
        Spec(
            "otp.verify_ip_rate", "otp", "rate", _setting("OTP_VERIFY_IP_RATE_LIMIT", "100/10m"),
            pgettext_lazy(_CTX, "Bir İP-dən parol bərpa kodunu yoxlama"), _RATE_HELP, min=20, max=5000,
        ),
        Spec(
            "session.idle_hours", "session", "int",
            lambda: max(1, int(getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 8 * 3600)) // 3600),
            pgettext_lazy(_CTX, "Hərəkətsizlikdən sonra avtomatik çıxış"),
            pgettext_lazy(_CTX, "İstifadəçi bu qədər saat heç nə etməsə, sistemdən çıxarılır (sessiya ən çox 24 saat yaşayır)."),
            pgettext_lazy(_CTX, "saat"), min=1, max=24,
        ),
        # 2026-10-15 (sahib «dəqiqə olaraq settings-ə əlavə et»): pəncərələr DƏQİQƏ ilə. Köhnə ``*_hours`` açarları
        # gizlidir — bazada qalan dəyər fallback kimi oxunur (registrar 0089 onları dəqiqəyə köçürür; trigger da
        # əvvəl dəqiqə, sonra saat açarını oxuyur). Oxu nöqtəsi YALNIZ ``apps.registrar.journal_edit_windows``.
        Spec(
            "journal.lesson_edit_minutes", "journal", "int", _setting("JOURNAL_LESSON_EDIT_MINUTES", 120),
            pgettext_lazy(_CTX, "Dərs sətrini (tarix, mövzu, saat) düzəltmə / silmə müddəti"),
            pgettext_lazy(
                _CTX,
                "Müəllim dərsi yaratdıqdan sonra bu qədər dəqiqə ərzində onun tarixini, növünü, mövzusunu, saatını "
                "dəyişə və ya dərsi silə bilər (120 dəqiqə = 2 saat). Sonra yalnız rəsmi düzəliş yolu.",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=1, max=4320, legacy_key="journal.lesson_edit_hours",
        ),
        Spec(
            "journal.mark_edit_minutes", "journal", "int", _setting("JOURNAL_MARK_EDIT_MINUTES", 120),
            pgettext_lazy(_CTX, "q/b, i/e və balı dəyişmə müddəti"),
            pgettext_lazy(
                _CTX,
                "Müəllimin yazdığı q/b, i/e və bal yazıldıqdan bu qədər dəqiqə sonra donur — sonra yalnız rəsmi "
                "düzəliş yolu. Verilənlər bazası da eyni müddəti yoxlayır (120 dəqiqə = 2 saat).",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=1, max=4320, legacy_key="journal.mark_edit_hours",
        ),
        Spec(
            "journal.late_entry_days", "journal", "int", _setting("JOURNAL_LATE_ENTRY_DAYS", 0),
            pgettext_lazy(_CTX, "Dərs tarixindən sonra gecikmiş yazı müddəti"),
            pgettext_lazy(
                _CTX,
                "0 — dərs və yeni q/b, i/e, bal yalnız dərsin öz günündə yazılır. N — müəllim dərs tarixindən ən "
                "çox N gün sonra həmin tarixə dərs aça və yeni qeyd yaza bilər; müddət bitəndə yazı bağlanır. "
                "RİM rəhbərinin rəsmi düzəliş yolu bu həddə tabe deyil.",
            ),
            pgettext_lazy(_CTX, "gün"), min=0, max=30,
        ),
        # ⚠️ Köhnə saat açarları — gizli (forma göstərmir/saxlamır), bazadakı dəyər fallbackdır. Adı DƏYİŞMƏYİN:
        # trigger (registrar 0084/0089) ``journal.mark_edit_hours``-u da oxuyur.
        Spec(
            "journal.lesson_edit_hours", "journal", "int", lambda: 2,
            pgettext_lazy(_CTX, "Dərs sətrini (tarix, mövzu, saat) düzəltmə / silmə müddəti"),
            pgettext_lazy(_CTX, "Müəllim dərsi yaratdıqdan sonra bu qədər saat ərzində dəyişə bilər."),
            pgettext_lazy(_CTX, "saat"), min=1, max=72, hidden=True,
        ),
        Spec(
            "journal.mark_edit_hours", "journal", "int", lambda: 2,
            pgettext_lazy(_CTX, "q/b, i/e və balı dəyişmə müddəti"),
            pgettext_lazy(_CTX, "Yazılmış qeyd bu qədər saatdan sonra donur (sonra yalnız rəsmi düzəliş yolu)."),
            pgettext_lazy(_CTX, "saat"), min=1, max=72, hidden=True,
        ),
        Spec(
            "journal.lesson_activation", "journal", "bool", _setting("JOURNAL_LESSON_ACTIVATION", False),
            pgettext_lazy(_CTX, "Cədvəldəki dərsi «Aktivləşdir» düyməsi"),
            pgettext_lazy(
                _CTX,
                "Söndürülüdə jurnalda «Aktivləşdir» düyməsi yoxdur — müəllim «Yeni dərs» ilə dərsi özü yaradır, "
                "forma dərs cədvəli və son dərsə görə əvvəlcədən doldurulur.",
            ),
        ),
        Spec(
            "journal.activation_write_minutes", "journal", "int", _setting("JOURNAL_ACTIVATION_WRITE_MINUTES", 120),
            pgettext_lazy(_CTX, "Aktivləşdirmədən sonra yazı müddəti"),
            pgettext_lazy(
                _CTX,
                "Yalnız «Aktivləşdir» yanılıdırsa: müəllim dərsi aktivləşdirdikdən (jurnalda açdıqdan) sonra q/b, "
                "i/e və balı bu qədər dəqiqə ərzində yazmalıdır; sonra həmin dərsə yeni qeyd yazılmır. Əvvəlcədən "
                "açılmış dərsdə müddət dərsin başlama saatından sayılır.",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=5, max=1440,
        ),
        Spec(
            "journal.hygiene_prevention", "journal", "bool", _setting("JOURNAL_HYGIENE_PREVENTION", True),
            pgettext_lazy(_CTX, "Ayrılmış tələbələrin jurnala yazılmasının qarşısını al"),
            pgettext_lazy(
                _CTX,
                "Yanılıdırsa hesabı arxivdə olan (məzun, xaric) tələbələr yeni jurnallara yazılmır, qrupun seçmə "
                "fənni dəyişəndə və ya fənn ləğv olunanda köhnə BOŞ yazılışlar çıxarılır. Balı olan yazılışlara "
                "toxunulmur.",
            ),
        ),
        Spec(
            "ai.model", "ai", "choice", lambda: "",
            pgettext_lazy(_CTX, "AI modeli (köməkçi, xülasə, yoxlama)"),
            pgettext_lazy(_CTX, "«Avtomatik» — mövcud server tənzimləməsi; seçilən model hamısında birinci yoxlanılır."),
            choices=_ai_model_choices,
        ),
        Spec(
            "ai.assistant_rate", "ai", "rate", _setting("AI_ASSISTANT_RATE_LIMIT", "25/1h"),
            pgettext_lazy(_CTX, "AI köməkçiyə bir istifadəçinin sual sayı"), _RATE_HELP, min=1, max=1000,
        ),
        Spec(
            "ai.assistant_button", "ai", "bool", _setting("AI_ASSISTANT_BUTTON", True),
            pgettext_lazy(_CTX, "AI köməkçi düyməsi"),
            pgettext_lazy(
                _CTX,
                "Söndürülüdə ekranın küncündəki AI düyməsi heç kimə göstərilmir. Yanılıdırsa hər istifadəçi onu öz "
                "ekranında gizlədə və sürüşdürüb yerini dəyişə bilər.",
            ),
        ),
        Spec(
            "exam.available_page", "exam", "bool", _setting("EXAM_AVAILABLE_PAGE", False),
            pgettext_lazy(_CTX, "«Mövcud imtahanlar» səhifəsi"),
            pgettext_lazy(
                _CTX,
                "Sahib 2026-10-10: hələlik lazım deyil. Söndürülüdə səhifə və ona aparan keçidlər görünmür; "
                "kod saxlanılır — yandıranda geri qayıdır.",
            ),
        ),
        Spec(
            "exam.pin_max_failures", "exam", "int", _setting("FINAL_EXAM_PIN_MAX_FAILURES", 5),
            pgettext_lazy(_CTX, "Final imtahan PIN-ini səhv yazma cəhdi"), "", pgettext_lazy(_CTX, "cəhd"), min=3, max=20,
        ),
        Spec(
            "exam.pin_lock_minutes", "exam", "int", _setting("FINAL_EXAM_PIN_LOCK_MINUTES", 10),
            pgettext_lazy(_CTX, "PIN səhvlərindən sonra kilid müddəti"), "", pgettext_lazy(_CTX, "dəqiqə"), min=1, max=120,
        ),
        # 2026-10-13 (gecə): apellyasiya pəncərəsi — sahib «3 gün ərzində»; oxu nöqtəsi apps/appeals/services/window.py.
        Spec(
            "exam.appeal_window_days", "exam", "int", _setting("APPEAL_WINDOW_DAYS", 3),
            pgettext_lazy(_CTX, "Apellyasiya müddəti"),
            pgettext_lazy(
                _CTX,
                "Nəticə tələbəyə açıldıqdan sonra neçə təqvim günü apellyasiya vermək olar (son günün sonunadək, "
                "Bakı vaxtı). Tələbə evdən də müraciət edə bilir; müddət bitəndə düymə gizlənir və server qəbul etmir.",
            ),
            pgettext_lazy(_CTX, "gün"), min=1, max=14,
        ),
        # 2026-10-17 (sahib): girişdən sonra boş FİN / telefon / e-poçt məcburi doldurulur — apps/accounts/profile_completion.py.
        Spec(
            "profile.required_fields_enabled", "profile", "bool", _setting("PROFILE_COMPLETION_ENABLED", True),
            pgettext_lazy(_CTX, "Girişdən sonra vacib məlumatları məcburi doldurmaq"),
            pgettext_lazy(
                _CTX,
                "Yanılıda FİN kodu, mobil telefonu və ya şəxsi e-poçtu boş olan tələbə və əməkdaş girişdən sonra "
                "«Məlumatlarınızı tamamlayın» səhifəsinə yönlənir və onları doldurmadan sistemdən istifadə edə bilmir. "
                "Söndürülüdə (qəza halı) heç kim dayandırılmır.",
            ),
        ),
        Spec("profile.require_fin", "profile", "bool", lambda: True, pgettext_lazy(_CTX, "FİN kod məcburidir")),
        Spec("profile.require_phone", "profile", "bool", lambda: True, pgettext_lazy(_CTX, "Mobil telefon məcburidir")),
        Spec("profile.require_email", "profile", "bool", lambda: True, pgettext_lazy(_CTX, "Şəxsi e-poçt məcburidir")),
    )
}  # fmt: skip


def enabled() -> bool:
    return bool(getattr(settings, "RUNTIME_SETTINGS_ENABLED", True))


def _load_overrides() -> dict:
    from django.apps import apps
    from django.db import DatabaseError, transaction

    try:
        model = apps.get_model("accounts", "RuntimeSetting")
        # Savepoint: cədvəl hələ yoxdursa (miqrasiyadan əvvəl) xarici tranzaksiya pozulmasın.
        with transaction.atomic():
            return dict(model.objects.values_list("key", "value"))
    except (LookupError, DatabaseError):
        logger.warning("runtime settings unavailable; using defaults", exc_info=True)
        return {}


def overrides() -> dict:
    """Bazadakı bütün dəyişikliklər (keşli). Xəta olarsa boş — defoltlar işləyir."""
    now = time.monotonic()
    if _local["data"] is not None and _local["expires"] > now:
        return _local["data"]
    from django.core.cache import cache

    data = None
    try:
        data = cache.get(CACHE_KEY)
    except Exception:  # noqa: BLE001 — Redis əlçatmazdırsa bazaya düş
        data = None
    if not isinstance(data, dict):
        data = _load_overrides()
        try:
            cache.set(CACHE_KEY, data, CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    _local.update(data=data, expires=now + LOCAL_TTL)
    return data


def invalidate() -> None:
    from django.core.cache import cache

    _local.update(data=None, expires=0.0)
    try:
        cache.delete(CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass


_TRUE_TEXT = frozenset({"1", "true", "on", "yes"})
_FALSE_TEXT = frozenset({"0", "false", "off", "no"})


def _rate_parts(raw) -> tuple[int, int] | None:
    from core.rate_limit import parse_rate

    try:
        parsed = parse_rate(str(raw or ""))
    except ValueError:
        return None
    if parsed is None or parsed.window_seconds < 60:
        return None
    return parsed.limit, parsed.window_seconds // 60


_CENT = Decimal("0.01")


def _decimal(raw) -> Decimal | None:
    """«1,5» / «1.50» / 1.5 → ``Decimal("1.50")`` (2 onluq); tanınmırsa ``None``. ``bool`` qəbul olunmur."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def decimal_text(value) -> str:
    """``Decimal("1.50")`` → «1.5», ``Decimal("1.00")`` → «1» (forma / müqayisə / JSON üçün)."""
    parsed = _decimal(value)
    if parsed is None:
        return ""
    return format(parsed.normalize(), "f")


def storable(spec: Spec, value):
    """Bazaya (JSONField) / audit-ə yazılan şəkil — ``Decimal`` JSON-a sığmır, mətn kimi saxlanır."""
    if spec.kind == "decimal" and value is not None:
        return decimal_text(value)
    return value


def coerce(spec: Spec, raw):
    """Saxlanmış / göndərilmiş dəyəri tipə və hədlərə uyğunlaşdırır; yararsızdırsa ``None``."""
    if spec.kind == "int":
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if spec.min <= value <= spec.max else None
    if spec.kind == "decimal":
        value = _decimal(raw)
        if value is None:
            return None
        return value if Decimal(str(spec.min)) <= value <= Decimal(str(spec.max)) else None
    if spec.kind == "rate":
        parts = _rate_parts(raw)
        if parts is None or not (spec.min <= parts[0] <= spec.max) or not (1 <= parts[1] <= 24 * 60):
            return None
        return f"{parts[0]}/{parts[1]}m"
    if spec.kind == "choice":
        value = str(raw or "")
        return value if value in {code for code, _label in (spec.choices() if spec.choices else [])} else None
    if spec.kind == "bool":
        if isinstance(raw, bool):
            return raw
        text = str(raw if raw is not None else "").strip().lower()
        if text in _TRUE_TEXT:
            return True
        if text in _FALSE_TEXT:
            return False
        return None
    return None


def override(key: str):
    """Yalnız RİM rəhbərinin saxladığı (yararlı) dəyər, yoxdursa ``None`` — çağıran öz əvvəlki qaydasını işlədir."""
    if not enabled():
        return None
    stored = overrides().get(key)
    return None if stored is None else coerce(SPECS[key], stored)


def get(key: str):
    spec = SPECS[key]
    if enabled():
        stored = overrides().get(key)
        if stored is not None:
            value = coerce(spec, stored)
            if value is not None:
                return value
    return spec.default()


def get_int(key: str) -> int:
    return int(get(key))


def get_decimal(key: str) -> Decimal:
    return _decimal(get(key)) or Decimal("0")


def get_bool(key: str) -> bool:
    """Bayraq oxusu. ⚠️ ``override(key) or fallback`` bayraqda İŞLƏMİR (``False`` atılır) — bunu çağırın."""
    return bool(get(key))


__all__ = [
    "CACHE_KEY",
    "GROUPS",
    "SPECS",
    "Spec",
    "coerce",
    "decimal_text",
    "enabled",
    "get",
    "get_bool",
    "get_decimal",
    "get_int",
    "invalidate",
    "override",
    "overrides",
    "storable",
]
