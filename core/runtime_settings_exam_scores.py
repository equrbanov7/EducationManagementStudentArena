"""«İmtahan balının daxil edilməsi» — «Sistem tənzimləmələri» açarları (sahib 2026-10-25).

Sahib: «daxil edən təsdiqdən sonra 15 dəqiqə ərzində dəyişə bilər; sonra yalnız təqdimat əsasında RİM
tərəfindən və ya apellyasiya ilə» və «yazılı/praktiki imtahan nəticəsi tələbə kabinetində 1 gün sonra görünsün».

* ``exam.score_edit_minutes`` (defolt 15) — təsdiqdən sonra DAXİL EDƏNİN öz balını sənədsiz dəyişə bildiyi
  müddət. Jurnal xanasının ``journal.mark_edit_minutes`` açarı QƏSDƏN təkrar istifadə OLUNMUR: o, müəllimin
  q/b və dərs balı kilididir — RİM onu müəllimlər üçün yumşaltsa (məs. 60 dəq) imtahan nəticəsinin kilidi
  səssizcə uzanmamalıdır (iki fərqli rol, iki fərqli risk). Defolt dəyər və mətn köməkçisi
  (``journal_edit_windows.duration_text``) eynidir.
* ``exam.score_release_hours`` (defolt 24) — kağız imtahan (midterm / final) nəticəsi təsdiqdən neçə saat
  sonra tələbə kabinetində görünür. 0 = dərhal.

Açarlar MÖVCUD «exam» qrupuna düşür. Oxu nöqtələri: :func:`edit_minutes`, :func:`release_hours` —
``apps.registrar.exam_score_assessment`` / ``apps.registrar.exam_score_release`` onları çağırır.
``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP_CODE = "exam"
KEY_EDIT_MINUTES = "exam.score_edit_minutes"
KEY_RELEASE_HOURS = "exam.score_release_hours"
DEFAULT_EDIT_MINUTES = 15
DEFAULT_RELEASE_HOURS = 24


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_EDIT_MINUTES, GROUP_CODE, "int", lambda: DEFAULT_EDIT_MINUTES,
            pgettext_lazy(_CTX, "İmtahan balını təsdiqdən sonra dəyişmə müddəti"),
            pgettext_lazy(
                _CTX,
                "«İmtahan balının daxil edilməsi» ekranında balı daxil edən təsdiqdən sonra bu qədər dəqiqə ərzində "
                "onu sənədsiz dəyişə bilər. Müddət bitəndən sonra bal yalnız apellyasiya (sənəd məcburi) və ya RİM "
                "rəhbərinin təqdimat əsasında düzəlişi ilə dəyişir.",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=1, max=1440,
        ),
        spec_cls(
            KEY_RELEASE_HOURS, GROUP_CODE, "int", lambda: DEFAULT_RELEASE_HOURS,
            pgettext_lazy(_CTX, "Kağız imtahan nəticəsinin tələbəyə görünmə gecikməsi"),
            pgettext_lazy(
                _CTX,
                "Yazılı / praktiki (kağız) midterm və final nəticəsi təsdiqdən bu qədər saat sonra tələbə kabinetində "
                "görünür. 0 — dərhal.",
            ),
            pgettext_lazy(_CTX, "saat"), min=0, max=720,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarları ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açarlar mövcud «exam» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def _int_setting(key: str, default: int) -> int:
    try:
        from core import runtime_settings

        return max(0, int(runtime_settings.get_int(key)))
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa defolt qayda işləyir (fail-safe)
        return default


def edit_minutes() -> int:
    """Təsdiqdən sonrakı sənədsiz düzəliş pəncərəsi (dəqiqə, ≥ 1)."""
    return max(1, _int_setting(KEY_EDIT_MINUTES, DEFAULT_EDIT_MINUTES))


def release_hours() -> int:
    """Kağız imtahan nəticəsinin tələbəyə görünmə gecikməsi (saat, ≥ 0)."""
    return _int_setting(KEY_RELEASE_HOURS, DEFAULT_RELEASE_HOURS)


__all__ = [
    "DEFAULT_EDIT_MINUTES",
    "DEFAULT_RELEASE_HOURS",
    "GROUP_CODE",
    "KEY_EDIT_MINUTES",
    "KEY_RELEASE_HOURS",
    "build_specs",
    "edit_minutes",
    "register",
    "release_hours",
]
