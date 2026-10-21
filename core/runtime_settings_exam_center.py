"""İmtahan mərkəzi — zal kompüteri yoxlaması + kateqoriyaya görə sual sayı (sahib 2026-10-21).

Sahib (1): «Sistem tənzimləmələrində ayrıca hissə olsun — MAC ünvanları götürmək alınmaz, problem olar. Mən bunu
söndürüb-yandıra bilim: yenə universitet şəbəkəsi olacaq, sadəcə MAC ünvanlar olmasa da uşaqlar imtahana girə
bilsin.» → ``exam.hall_computer_check`` (bool, defolt YANDIRILIB — mövcud davranış dəyişmir). Oxu nöqtəsi
:func:`hall_computer_check` — ``apps.exams.services.exam_center_gate`` onu çağırır, açarı birbaşa oxumur.
Söndürüləndə YALNIZ kompüter/MAC/IP-allowlist tələbi düşür; universitet şəbəkəsi qaydası
(``apps.exams.services.exam_network``), istifadəçi adı + PIN və cəhdin ilk cihaza bağlanması QALIR.

Sahib (2): «Finalda 50 sualdır, midterm imtahanında 30 sual — bunu avtomatik sistem tənzimləsin, yəni midterm
seçərkən özü 30 sual gəlsin, yaddan çıxa bilər.» → ``exam.final_question_count`` (50) və
``exam.midterm_question_count`` (30). Oxu nöqtəsi :func:`category_question_count` — imtahan forması
(``apps.exams.forms.exam_question_count``) onu çağırır.

Açarlar MÖVCUD «exam» qrupuna düşür (yeni qrup yaradılmır). ``Spec`` sinfi IMPORT EDİLMİR (dövri import
olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

#: Açarların düşdüyü MÖVCUD qrup (``runtime_settings.GROUPS``-da artıq var).
GROUP_CODE = "exam"
KEY_HALL_COMPUTER_CHECK = "exam.hall_computer_check"
KEY_FINAL_QUESTION_COUNT = "exam.final_question_count"
KEY_MIDTERM_QUESTION_COUNT = "exam.midterm_question_count"

FINAL_QUESTION_COUNT_DEFAULT = 50
MIDTERM_QUESTION_COUNT_DEFAULT = 30
QUESTION_COUNT_MIN = 1
QUESTION_COUNT_MAX = 200

_COUNT_KEYS = {"final": KEY_FINAL_QUESTION_COUNT, "midterm": KEY_MIDTERM_QUESTION_COUNT}
_COUNT_DEFAULTS = {"final": FINAL_QUESTION_COUNT_DEFAULT, "midterm": MIDTERM_QUESTION_COUNT_DEFAULT}


def _default_hall_computer_check() -> bool:
    # 2026-10-21 (sahib, ikinci qərar): yandırılıb = SƏRT rejim — «açmadığım müddətcə heç kim kənar kompüterlə o
    # səhifəni belə aça bilməsin» (apps.exams.services.exam_center_gate.ensure_hall_computer).
    # Defolt YANDIRILIB: açar əlavə olunanda istehsal davranışı DƏYİŞMƏMƏLİDİR (qeydli zal kompüterləri /
    # ARP agenti ilə MAC / FINAL_EXAM_ALLOWED_IPS harada konfiqurasiya olunubsa, əvvəlki kimi tətbiq olunur).
    return bool(getattr(settings, "EXAM_HALL_COMPUTER_CHECK", True))


def _default_final_count() -> int:
    return FINAL_QUESTION_COUNT_DEFAULT


def _default_midterm_count() -> int:
    return MIDTERM_QUESTION_COUNT_DEFAULT


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_HALL_COMPUTER_CHECK, GROUP_CODE, "bool", _default_hall_computer_check,
            pgettext_lazy(_CTX, "Zal kompüteri yoxlaması (MAC/IP)"),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa (defolt) final və midterm səhifələrini YALNIZ imtahan zalının qeydiyyatlı "
                "kompüterləri (MAC ünvanı ARP agenti ilə, əks halda IP) aça bilər; qeydiyyatsız kompüterdə giriş "
                "forması əvəzinə xəbərdarlıq və həmin kompüterin ünvanı göstərilir. Heç bir kompüter qeydiyyatda "
                "deyilsə, heç kim daxil ola bilmir. Söndürüləndə kompüter tələbi YOXDUR — universitet şəbəkəsindəki "
                "istənilən kompüterdən daxil olmaq olar. Universitet şəbəkəsi qaydası, istifadəçi adı + PIN və "
                "cəhdin ilk cihaza bağlanması hər iki halda qalır.",
            ),
        ),
        spec_cls(
            KEY_FINAL_QUESTION_COUNT, GROUP_CODE, "int", _default_final_count,
            pgettext_lazy(_CTX, "Final imtahanında sual sayı"),
            pgettext_lazy(
                _CTX,
                "Yeni imtahanda «Final» kateqoriyası seçiləndə sual sayı avtomatik bu dəyərə qoyulur. "
                "Müəllif sayı əl ilə dəyişə bilər; mövcud imtahanların sayı dəyişmir.",
            ),
            pgettext_lazy(_CTX, "sual"), min=QUESTION_COUNT_MIN, max=QUESTION_COUNT_MAX,
        ),
        spec_cls(
            KEY_MIDTERM_QUESTION_COUNT, GROUP_CODE, "int", _default_midterm_count,
            pgettext_lazy(_CTX, "Midterm imtahanında sual sayı"),
            pgettext_lazy(
                _CTX,
                "Yeni imtahanda «Midterm» kateqoriyası seçiləndə sual sayı avtomatik bu dəyərə qoyulur. "
                "Müəllif sayı əl ilə dəyişə bilər; mövcud imtahanların sayı dəyişmir.",
            ),
            pgettext_lazy(_CTX, "sual"), min=QUESTION_COUNT_MIN, max=QUESTION_COUNT_MAX,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarları ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açarlar mövcud «exam» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def hall_computer_check() -> bool:
    """Zal kompüteri (MAC/IP) yoxlaması aktivdirmi. Tənzimləmə oxunmasa — defolt (yandırılıb, fail-closed)."""
    try:
        from core import runtime_settings

        return runtime_settings.get_bool(KEY_HALL_COMPUTER_CHECK)
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa da imtahan girişi işləməlidir
        return _default_hall_computer_check()


def category_question_count(category) -> int | None:
    """Kateqoriyanın avtomatik sual sayı (final → 50, midterm → 30); başqa kateqoriya → ``None``."""
    key = _COUNT_KEYS.get(category or "")
    if key is None:
        return None
    try:
        from core import runtime_settings

        value = int(runtime_settings.get_int(key))
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa da forma işləməlidir
        value = _COUNT_DEFAULTS[category]
    return max(QUESTION_COUNT_MIN, min(QUESTION_COUNT_MAX, value))


def category_question_counts() -> dict:
    """``{"final": 50, "midterm": 30}`` — forma/JS üçün (hər açar bir dəfə oxunur)."""
    return {category: category_question_count(category) for category in _COUNT_KEYS}


__all__ = [
    "FINAL_QUESTION_COUNT_DEFAULT",
    "GROUP_CODE",
    "KEY_FINAL_QUESTION_COUNT",
    "KEY_HALL_COMPUTER_CHECK",
    "KEY_MIDTERM_QUESTION_COUNT",
    "MIDTERM_QUESTION_COUNT_DEFAULT",
    "build_specs",
    "category_question_count",
    "category_question_counts",
    "hall_computer_check",
    "register",
]
