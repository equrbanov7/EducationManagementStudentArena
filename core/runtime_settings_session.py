"""«Sessiya» və «Elektron jurnal» qruplarına sessiya/fəaliyyətsizlik açarları (sahib 2026-10-27).

Sahib: «müəllim brauzeri bağlayanda və ya kompüteri söndürəndə kabinetdən çıxsın», «jurnalda bir müddət heç nə
etməsə jurnal bağlansın», «uzun açıq qalan səhifədə “səhifəni yeniləyin” çıxmasın».

* ``session.browser_close_scope`` — kimə tətbiq olunur: sessiya kukisi brauzer bağlananda silinir və
  «brauzer açıq deyil» limiti (aşağıda) işləyir. Defolt ``staff`` — müəllim və əməkdaşlar; tələbələr toxunulmur.
* ``session.presence_minutes`` — açıq səhifə hər bir neçə dəqiqədən bir serverə «buradayam» siqnalı göndərir;
  bu qədər dəqiqə HEÇ BİR sorğu gəlməyibsə (brauzer bağlanıb, kompüter sönüb / yuxu rejimində) sessiya bitir.
  Chrome-un «qaldığım yerdən davam et» funksiyası sessiya kukisini bərpa etsə də, server tərəfi bunu tutur. 0 —
  söndürülü.
* ``journal.idle_close_minutes`` — açıq jurnalda bu qədər dəqiqə heç bir hərəkət olmasa, gözləyən dəyişikliklər
  yadda saxlanılır və jurnal bağlanır («Davam et» təzə məlumatla açır). 0 — söndürülü.

Oxu nöqtələri YALNIZ bu modulun funksiyalarıdır (``apps.accounts.session_policy``, jurnal şablon teqi).
``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

KEY_SCOPE = "session.browser_close_scope"
KEY_PRESENCE = "session.presence_minutes"
KEY_JOURNAL_IDLE = "journal.idle_close_minutes"

SCOPE_OFF = "off"
SCOPE_STAFF = "staff"
SCOPE_ALL = "all"


def _scope_choices() -> list:
    return [
        (SCOPE_OFF, pgettext_lazy(_CTX, "Söndürülü (sessiya brauzer bağlandıqdan sonra da qalır)")),
        (SCOPE_STAFF, pgettext_lazy(_CTX, "Müəllim və əməkdaşlar (tələbələr xaric)")),
        (SCOPE_ALL, pgettext_lazy(_CTX, "Hamı (imtahan gedişində olan tələbə çıxarılmır)")),
    ]


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_SCOPE, "session", "choice", lambda: getattr(settings, "SESSION_BROWSER_CLOSE_SCOPE", SCOPE_STAFF),
            pgettext_lazy(_CTX, "Brauzer bağlananda və ya kompüter sönəndə çıxış"),
            pgettext_lazy(
                _CTX,
                "Seçilmiş istifadəçilərin sessiyası brauzer bağlananda bitir; brauzer «qaldığım yerdən davam et» ilə "
                "açılsa belə, aşağıdakı «brauzer açıq deyil» limiti keçibsə yenidən giriş tələb olunur. Tələbələr "
                "daxil edilsə də, imtahan gedişində (zal bileti, başlanmış cəhd, canlı imtahan) heç kim çıxarılmır.",
            ),
            choices=_scope_choices,
        ),
        spec_cls(
            KEY_PRESENCE, "session", "int", lambda: getattr(settings, "SESSION_PRESENCE_MINUTES", 30),
            pgettext_lazy(_CTX, "Brauzer açıq deyilsə çıxış"),
            pgettext_lazy(
                _CTX,
                "Açıq səhifə serverə mütəmadi «buradayam» siqnalı göndərir. Bu qədər dəqiqə heç bir siqnal gəlməsə "
                "(brauzer bağlanıb, kompüter sönüb və ya yuxu rejimindədir) sessiya bitir. Yalnız yuxarıda seçilmiş "
                "istifadəçilərə aiddir. 0 — söndürülü.",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=0, max=720,
        ),
        spec_cls(
            KEY_JOURNAL_IDLE, "journal", "int", lambda: getattr(settings, "JOURNAL_IDLE_CLOSE_MINUTES", 30),
            pgettext_lazy(_CTX, "Hərəkətsiz jurnalın bağlanması"),
            pgettext_lazy(
                _CTX,
                "Açıq jurnalda bu qədər dəqiqə heç bir hərəkət (klik, yazı, sürüşdürmə) olmasa, yadda saxlanmamış "
                "xanalar əvvəlcə yadda saxlanılır, sonra jurnal bağlanır; «Davam et» onu təzə məlumatla açır. "
                "0 — söndürülü.",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=0, max=480,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarları ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açarlar mövcud «session» / «journal» qruplarındadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def browser_close_scope() -> str:
    from core import runtime_settings

    value = runtime_settings.get(KEY_SCOPE)
    return value if value in (SCOPE_OFF, SCOPE_STAFF, SCOPE_ALL) else SCOPE_STAFF


def presence_seconds() -> int:
    from core import runtime_settings

    return max(0, int(runtime_settings.get(KEY_PRESENCE) or 0)) * 60


def journal_idle_minutes() -> int:
    from core import runtime_settings

    return max(0, int(runtime_settings.get(KEY_JOURNAL_IDLE) or 0))


__all__ = [
    "KEY_JOURNAL_IDLE",
    "KEY_PRESENCE",
    "KEY_SCOPE",
    "SCOPE_ALL",
    "SCOPE_OFF",
    "SCOPE_STAFF",
    "browser_close_scope",
    "build_specs",
    "journal_idle_minutes",
    "presence_seconds",
    "register",
]
