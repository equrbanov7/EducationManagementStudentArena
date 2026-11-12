"""Dublikat fənlər, 2-ci dövrə (sahib 2026-11-11 səhər) — birləşmənin TƏHLÜKƏSİZLİK qaydaları.

Sahib: «birləşdirərsən onları … dublikat qalmamış olsun». Koordinatorun şərti (best practice): birləşmədən əvvəl tədris
planına bax — iki fənn EYNİ tədris planında ayrı sətirlərdirsə (tələbənin kredit planı ikisini də tələb edir), onlar
həqiqətən fərqli fənlərdir və BİRLƏŞDİRİLMİR.

* :func:`shared_curricula` — fənlərdən ən azı ikisini birlikdə daşıyan tədris planları (hər status: qaralama da). Plan
  bir qəbul ilinin bir ixtisasıdır, yəni qrup BİR plana bağlıdır — eyni ixtisasın FƏRQLİ illərinin planları fərqli
  kartlara istinad edə bilər (bu, məhz dublikatın özüdür), ona görə yoxlama plan səviyyəsindədir, ixtisas səviyyəsində yox;
* :func:`past_shell` — keçmiş dövrün BOŞ qabığı (dərs yoxdur, aktiv qeydiyyat yoxdur, ``twin_inert`` boşdur): onu passiv
  etmək bitmiş semestrin heç bir nəticəsinə toxunmur — kataloq birləşməsinin K2 qaydası sonra onu snapshot-la silir;
* :func:`rename_keeper` / :func:`restore_names` — saxlanılan kartın adının düzəlişi (məs. «Beynelxalq» → «Beynəlxalq»),
  köhnə ad paket qəbzindədir, geri qaytarmada bərpa olunur (ad sonradan dəyişibsə toxunulmur).

Kredit (ECTS) fərqi: ``merge_subjects``-in ``credit_mismatch`` qaydası (mənbənin YEKUN QİYMƏTLİ tələbəsi varsa blok) olduğu
kimi qalır — saxlanılan kart planda elə seçilir ki, qiymətlənmiş tərəf saxlanılsın; tədris planı sətrinin öz krediti
(``CurriculumSubject.credits``) sətirlə birlikdə köçür, yəni planın krediti dəyişmir (``credit_source`` onu əsas götürür).
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.utils import timezone

from .twin_inert import is_empty_twin


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def shared_curricula(subject_ids, only=None) -> list:
    """Fənlərdən ən azı İKİSİNİ birlikdə daşıyan tədris planlarının id-ləri (sabit sıra).

    ``only`` (2026-11-12, oxşar adlı cütlər) — yalnız bu planlar (qrupun öz planları) yoxlanılır."""
    ids = [value for value in subject_ids if value]
    if len(set(ids)) < 2:
        return []
    by_plan = defaultdict(set)
    rows = _model("CurriculumSubject")._base_manager.filter(subject_id__in=ids)
    if only is not None:
        rows = rows.filter(curriculum_id__in=list(only))
    for curriculum_id, subject_id in rows.values_list("curriculum_id", "subject_id"):
        by_plan[str(curriculum_id)].add(subject_id)
    return sorted(plan for plan, subjects in by_plan.items() if len(subjects) > 1)


def past_shell(offering, period) -> bool:
    """Keçmiş dövrün boş qabığıdırmı (bax modulun sənədi)."""
    if period is None or offering.period_id == period.pk:
        return False
    if _model("Lesson").objects.filter(offering=offering).exists():
        return False
    if _model("Enrollment").objects.filter(offering=offering).exclude(status="dropped").exists():
        return False
    return is_empty_twin(offering)


def rename_keeper(keeper, name, renames, counts) -> None:
    name = " ".join(str(name or "").split())[:255]
    if not name or name == keeper.name:
        return
    renames.append({"id": str(keeper.pk), "old": keeper.name, "new": name})
    _model("Subject")._base_manager.filter(pk=keeper.pk).update(name=name, updated_at=timezone.now())
    keeper.name = name
    counts["catalogue_keeper_renamed"] += 1


def restore_names(renames, counts) -> None:
    Subject = _model("Subject")
    for item in reversed(renames or []):
        updated = Subject._base_manager.filter(pk=item["id"], name=item["new"]).update(
            name=item["old"], updated_at=timezone.now()
        )
        counts["undo_keeper_names_restored" if updated else "undo_keeper_name_changed_kept"] += 1


__all__ = ["past_shell", "rename_keeper", "restore_names", "shared_curricula"]
