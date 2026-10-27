"""Yeni dərsin növ kilidi — cədvəl TƏK növ verəndə, amma yalnız başqa növə sübut YOXDURSA (RİM 2026-10-27).

Köhnə qayda (``journal_extras.locked_lesson_kind``): açılışın cədvəlində yalnız bir növ slot varsa (məs. yalnız
mühazirə) yeni dərsin növü seçilmir — həmin növə düşür. Köçürmədən sonra cədvəl çox vaxt NATAMAMDIR: slotlar
``infer_timetable_from_lessons`` / docx idxalı ilə yalnız tapılan növ üçün yaranıb, seminar slotu ya yoxdur, ya
alt qrupun açılışındadır. Nəticə (MR-000054 «seminar kilidlidir, yalnız mühazirə əlavə olunur», MR-000017 «jurnal
mühazirə göstərir, seminar olmalıdır»): müəllim planındakı növü ümumiyyətlə yaza bilmir; bölünmüş jurnalın
seminar payı olan müəllimi isə kilidlənmiş «mühazirə» ilə tamamilə bloklanır (pay növü kilidlə uyuşmur → 403).
Prod nüsxəsində (2026-10-27) cari dövrün tək-növ cədvəlli 457 açılışından 254-ündə başqa növə sübut var.

Yeni qayda: tək slot növü yalnız açılışın PLANLI növlərinin hamısı odursa kilidləyir. Başqa növə sübut:

1. açılışda həmin başqa növdə dərs artıq var (köhnə sistemdən gələn və ya əvvəl yazılan);
2. bölünmüş jurnalın aktiv payı başqa növü daşıyır (``JournalShare.kinds``);
3. dərs yükü (TAPŞIRIQ) sətrində qrupun həmin növ üzrə saatı var (``plan_hours_load``).

Sübut varsa kilid YOXDUR — müəllim növü seçir (pay sahibinə yalnız öz növləri göstərilir —
``journal_share_guard`` dəyişmir). Sorğu sırası ucuzdan bahaya, ilk sübutda dayanır.
"""

from __future__ import annotations

from django.apps import apps as django_apps

KINDS = ("lecture", "seminar", "lab")


def _model(name: str):
    return django_apps.get_model("registrar", name)


def single_slot_kind(offering):
    """Açılışın cədvəlində (silinməmiş slotlar) TƏK növ varsa həmin növ, əks halda ``None``."""
    kinds = list(_model("ScheduleSlot").objects.filter(offering=offering).values_list("kind", flat=True).distinct())
    return kinds[0] if len(kinds) == 1 else None


def has_other_kind_evidence(offering, kind) -> bool:
    """Açılışın ``kind``-dan BAŞQA planlı növü varmı (mövcud dərs, aktiv pay, dərs yükü saatı)."""
    if _model("Lesson").objects.filter(offering=offering).exclude(kind=kind).exists():
        return True
    share_kinds = (
        _model("JournalShare").objects.filter(offering=offering, is_active=True).values_list("kinds", flat=True)
    )
    if any(other in KINDS and other != kind for kinds in share_kinds for other in (kinds or [])):
        return True
    from .plan_hours_load import workload_hours_for_offering

    return any(other != kind and hours for other, hours in workload_hours_for_offering(offering).items())


def locked_lesson_kind(offering):
    """Yeni dərsin məcburi növü və ya ``None`` (seçim sərbəstdir) — bax modul sənədi."""
    kind = single_slot_kind(offering)
    if kind is None or has_other_kind_evidence(offering, kind):
        return None
    return kind


__all__ = ["has_other_kind_evidence", "locked_lesson_kind", "single_slot_kind"]
