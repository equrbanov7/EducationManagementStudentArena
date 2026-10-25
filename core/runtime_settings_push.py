"""«Bildirişlər» — «Sistem tənzimləmələri» açarı: telefona push (sahib 2026-10-25).

Sahib: «bildiriş gələrkən (telefonun) notification-ında görünsün». Push FCM kredensialı (``FCM_SERVICE_ACCOUNT_JSON``)
qoşulubsa defolt AÇIQDIR; RİM onu buradan söndürə bilər (bildirişlər kabinetdə yaranmağa davam edir, yalnız telefona
getmir). Kredensial yoxdursa açar yandırılı olsa da push NO-OP-dur.

Oxu nöqtəsi YALNIZ ``apps.notifications.push.config.push_enabled``.
``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP = ("notifications", pgettext_lazy(_CTX, "Bildirişlər"))

KEY_PUSH_ENABLED = "notifications.push_enabled"


def _default_push_enabled() -> bool:
    return bool(getattr(settings, "PUSH_NOTIFICATIONS_ENABLED", True))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_PUSH_ENABLED, GROUP[0], "bool", _default_push_enabled,
            pgettext_lazy(_CTX, "Push bildirişləri aktivdir (telefona göndər)"),
            pgettext_lazy(
                _CTX,
                "Yandırılanda yeni bildiriş (q/b, bal, imtahan, elan və s.) mobil tətbiqi quraşdırıb hesabına "
                "daxil olmuş istifadəçinin telefonunda bildiriş kimi görünür. Söndürüləndə bildirişlər yalnız "
                "kabinetdə qalır. Firebase açarı serverdə qoşulmayıbsa bu açar heç nəyi dəyişmir.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """``runtime_settings``-ə qrup və açarı əlavə edir; yeni ``GROUPS``-u qaytarır (idempotent)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    if any(code == GROUP[0] for code, _label in groups):
        return groups
    return groups + (GROUP,)


def push_enabled_setting() -> bool:
    """Açarın dəyəri (kredensialdan asılı DEYİL); oxunmasa defolt."""
    try:
        from core import runtime_settings

        return bool(runtime_settings.get(KEY_PUSH_ENABLED))
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa defolt (bildiriş yaradılması sınmasın)
        return _default_push_enabled()


__all__ = ["GROUP", "KEY_PUSH_ENABLED", "build_specs", "push_enabled_setting", "register"]
