"""Versiya TƏSNİFATI — «kiçik» seçimi struktur dəyişikliyində qəbul edilmir.

Sahibin qərarı (`docs/design/handoff_full/README.md` §10.3 →
`HANDOFF_FULL_PLAN.md` §2/18–20): **versiya təsnifatı müəllimin seçimidir,
LAKİN mövzu / çəki / struktur dəyişikliyi avtomatik MAJOR-a qaldırır.**

Niyə: təsdiqlənmiş sillabus jurnalın struktur mənbəyidir (§8/0 və §8/3) —
həftəlik mövzular jurnalda dərs sətirlərini, qiymətləndirmə çəkiləri sütun
maksimumlarını, sərbəst iş strukturu isə sərbəst iş sütunlarının sayını
yaradır.  «Kiçik» versiya CARİ semestrə tətbiq olunur, yəni artıq açılmış
jurnalın strukturunu ANİ dəyişərdi; buna görə həmin üç bölmə dəyişəndə versiya
NÖVBƏTİ semestrə gedən MAJOR-a qaldırılır.

Təsnifat SUBMIT anında aparılır, versiya yaradılan anda YOX: müəllim qaralamanı
açanda hələ heç nə dəyişməyib, struktur fərqi yalnız redaktədən sonra bilinir.
"""

from __future__ import annotations

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import SectionKey
from ..models import ChangeKind, SyllabusVersion

#: Dəyişməsi avtomatik MAJOR tələb edən bölmələr (jurnal strukturunun mənbəyi).
STRUCTURAL_SECTIONS = (
    SectionKey.WEEK.value,
    SectionKey.ASSESS.value,
    SectionKey.SELF.value,
)

#: Audit qeydində və UI mesajında işlədilən səbəb kodu.
ESCALATION_CODE = "version.structural_change_requires_major"


def baseline_for(version):
    """Müqayisə bazası: versiyanın mənbəyi, yoxsa dosyenin təsdiqlənmiş nüsxəsi.

    Baza tapılmasa ``None`` — ilk versiyanın müqayisə edəcəyi heç nə yoxdur,
    yəni təsnifat qaydası ona ŞAMİL EDİLMİR.
    """
    if version.source_version_id:
        return version.source_version
    return getattr(version.syllabus, "approved_version", None)


def structural_changes(version, *, baseline=None) -> tuple:
    """Bazaya nisbətən dəyişmiş STRUKTUR bölmələrinin açarları."""
    base = baseline if baseline is not None else baseline_for(version)
    if base is None or base.pk == version.pk:
        return ()
    old = {row.section_id: (row.data or {}) for row in base.sections.all()}
    new = {row.section_id: (row.data or {}) for row in version.sections.all()}
    return tuple(key for key in STRUCTURAL_SECTIONS if old.get(key, {}) != new.get(key, {}))


def classify(version, *, baseline=None) -> str:
    """``"major"`` — struktur dəyişib; əks halda müəllimin seçdiyi növ qalır."""
    if structural_changes(version, baseline=baseline):
        return ChangeKind.MAJOR.value
    kind = version.change_kind
    return kind if kind in {ChangeKind.MINOR.value, ChangeKind.MAJOR.value} else ChangeKind.MINOR.value


def _next_major(version) -> int:
    """Dosyedəki ən böyük ``major`` + 1 — nömrə toqquşması olmasın."""
    highest = (
        SyllabusVersion.objects.filter(syllabus_id=version.syllabus_id)
        .order_by("-major")
        .values_list("major", flat=True)
        .first()
    )
    return int(highest or version.major) + 1


@transaction.atomic
def escalate_if_structural(version, *, actor=None, request=None):
    """MİNOR seçilib, amma struktur dəyişibsə — versiyanı MAJOR-a qaldırır.

    Nəticə ``(version, changed_sections)``: ``changed_sections`` boşdursa heç nə
    dəyişməyib.  Qaldırma versiyanı YENİDƏN NÖMRƏLƏYİR (``vN.m`` → ``v(N+1).0``)
    və tətbiq semestrini olduğu kimi saxlayır — semestr seçimi ayrıca əməldir,
    burada uydurulmur.

    Çağırış yeri: :func:`apps.syllabus.services.workflow.submit` — yəni qayda
    HTTP səthindən asılı deyil, hər göndərmə yolunda işləyir.
    """
    if version.change_kind != ChangeKind.MINOR.value:
        return version, ()
    changed = structural_changes(version)
    if not changed:
        return version, ()

    old_label = version.label
    version.major = _next_major(version)
    version.minor = 0
    version.change_kind = ChangeKind.MAJOR.value
    version.save(update_fields=["major", "minor", "change_kind", "updated_at"])
    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=version.organization,
        obj=version,
        request=request,
        resource_type="syllabus.version",
        resource_id=str(version.pk),
        resource_repr=f"{version.syllabus_id} {version.label}",
        old_values={"version": old_label, "change_kind": ChangeKind.MINOR.value},
        new_values={"version": version.label, "change_kind": ChangeKind.MAJOR.value},
        changes={"reason": ESCALATION_CODE, "sections": list(changed)},
    )
    return version, changed


__all__ = [
    "ESCALATION_CODE",
    "STRUCTURAL_SECTIONS",
    "baseline_for",
    "classify",
    "escalate_if_structural",
    "structural_changes",
]
