"""«Müəllimlər keçmiş tarixli jurnalı tam redaktə edə bilər (data bərpası)» — «Sistem tənzimləmələri» açarı.

Sahib 2026-10-27: «Bütün müəllimlərə access ver, sistem hissəsindən də icazə ver ki, köhnə tarixdə dəyişiklik etmək
olsun: əlavə etmək, hər şey etmək, gün silmək, mövzunu edit etmək. Dəyişikliyin səbəbi soruşulsun sadəcə, heç bir
təqdimat və s. olmadan … yeni sistemdə data bərpası üçün … Sistem tənzimləməsində bunu söndürüb-yandırmaq olsun.»

DEFOLT = SÖNÜLÜ — bütün mövcud qapılar (yazma pəncərəsi, 15 dəqiqəlik xana kilidi, dərs sətrinin pəncərəsi,
bağlı jurnal, sənədli düzəliş) olduğu kimi işləyir. Yandırılanda müəllim YALNIZ yazma hüququ olan jurnalda
(``journal_access.is_direct_editor`` + bölünmüş jurnalın əhatəsi) qısa səbəb yazıb keçmiş tarixli dərsi əlavə edir,
redaktə edir, silir və xanaları dəyişir/təmizləyir; hər əməl səbəblə audit jurnalına düşür. İmtahandan gələn
ballar (midterm / yekun / sinxronlanan aralıq qiymətləndirmə) və RİM-in sənədli düzəlişi olan xana bu açara tabe
deyil. Qapıların tətbiqi: :mod:`apps.registrar.journal_full_edit`; oxu nöqtəsi YALNIZ :func:`enabled`
(``apps.registrar.journal_policy.teacher_full_edit_enabled`` onu çağırır).

Testlərdə defolt ``settings.JOURNAL_TEACHER_FULL_EDIT`` ilə dəyişir (``override_settings``).
``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

KEY_TEACHER_FULL_EDIT = "journal.teacher_full_edit"


def _default() -> bool:
    return bool(getattr(settings, "JOURNAL_TEACHER_FULL_EDIT", False))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_TEACHER_FULL_EDIT, "journal", "bool", _default,
            pgettext_lazy(_CTX, "Müəllimlər keçmiş tarixli jurnalı tam redaktə edə bilər (data bərpası)"),
            pgettext_lazy(
                _CTX,
                "Yandırılanda müəllim öz jurnalında (bölünmüş jurnalda yalnız öz payında) istənilən keçmiş tarixə "
                "(semestr daxilində) dərs əlavə edə, dərsi və mövzusunu redaktə edə, dərsi qeydləri ilə birlikdə "
                "silə, q/b, i/e və balı dəyişib təmizləyə bilər — bağlanmış jurnalda da. Təqdimat və sənəd "
                "tələb olunmur, yalnız qısa səbəb yazılır; hər dəyişiklik köhnə və yeni dəyərlə audit jurnalına "
                "düşür. İmtahandan gələn ballar (midterm, yekun) və RİM-in sənədli düzəlişi olan xana bu rejimə "
                "tabe deyil. Söndürüləndə bütün adi qaydalar (yazma müddəti, xana kilidi, bağlı jurnal) qayıdır.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «journal» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def enabled() -> bool:
    """Data bərpası rejimi açıqdırmı (defolt: xeyr). Tənzimləmə oxunmasa — defolt (heç vaxt istisna atmır)."""
    try:
        from core import runtime_settings

        return runtime_settings.get_bool(KEY_TEACHER_FULL_EDIT)
    except Exception:  # noqa: BLE001 — oxunmasa qapılar bağlı qalır (təhlükəsiz tərəf)
        return _default()


__all__ = ["KEY_TEACHER_FULL_EDIT", "build_specs", "enabled", "register"]
