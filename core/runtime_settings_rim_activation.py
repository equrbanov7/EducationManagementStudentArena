"""«Profil aktivləşdirəndə RİM-ə bildiriş» — «Sistem tənzimləmələri» açarı (sahib 2026-10-23).

Açar MÖVCUD «login» qrupuna («Giriş və parol cəhdləri») düşür. Oxu nöqtəsi YALNIZ
``apps.accounts.services.rim.activation.notify_rim_of_activation``.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

#: Açarın düşdüyü MÖVCUD qrup (``runtime_settings.GROUPS``-da artıq var).
GROUP_CODE = "login"


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            "login.notify_rim_on_activation", GROUP_CODE, "bool", lambda: True,
            pgettext_lazy(_CTX, "Profil aktivləşdiriləndə RİM-ə bildiriş"),
            pgettext_lazy(
                _CTX,
                "Yandırılanda istifadəçi e-poçtunu təsdiqləyib öz parolunu quranda (ilk giriş və ya parol bərpası) "
                "RİM mərkəzinin bütün üzvlərinə bildiriş gedir: kim aktivləşdirdi və cəmi neçə nəfər aktivləşdirib. "
                "Toplu aktivləşdirmə günlərində bildiriş çox olarsa söndürün — say RİM mərkəzində görünməyə davam edir.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «login» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


__all__ = ["GROUP_CODE", "build_specs", "register"]
