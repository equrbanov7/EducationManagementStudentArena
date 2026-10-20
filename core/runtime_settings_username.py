"""«İstifadəçi adını dəyiş» — «Sistem tənzimləmələri» açarları (sahib 2026-10-20).

Sahib: «hər kəs öz username-ni dəyişə bilər — profil redaktədə hissə qoy». Açarlar MÖVCUD «profile» qrupuna
düşür (yeni qrup yaradılmır). Oxu nöqtəsi YALNIZ ``apps.accounts.services.username_change``
(``change_enabled`` / ``cooldown_days``) — çağıranlar açarı birbaşa oxumur.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

#: Açarların düşdüyü MÖVCUD qrup (``runtime_settings.GROUPS``-da artıq var).
GROUP_CODE = "profile"


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            "profile.username_change_enabled", GROUP_CODE, "bool", lambda: True,
            pgettext_lazy(_CTX, "İstifadəçi öz istifadəçi adını dəyişə bilər"),
            pgettext_lazy(
                _CTX,
                "Yandırılanda tələbə və əməkdaş «Profil redaktə» bölməsində mövcud parolu ilə təsdiqləyərək öz "
                "istifadəçi adını dəyişə bilir; köhnə ad dərhal işləməz olur. Söndürüləndə həmin hissə gizlənir və "
                "server dəyişikliyi qəbul etmir.",
            ),
        ),
        spec_cls(
            "profile.username_change_cooldown_days", GROUP_CODE, "int", lambda: 30,
            pgettext_lazy(_CTX, "İstifadəçi adı dəyişmələri arasındakı müddət"),
            pgettext_lazy(
                _CTX,
                "Uğurlu dəyişiklikdən sonra neçə gün keçməlidir ki, istifadəçi adını yenidən dəyişmək mümkün olsun. "
                "0 — məhdudiyyət yoxdur.",
            ),
            pgettext_lazy(_CTX, "gün"), min=0, max=365,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarları ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açarlar mövcud «profile» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


__all__ = ["GROUP_CODE", "build_specs", "register"]
