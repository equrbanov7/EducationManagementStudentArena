"""Kollokvium pəncərəsi gating servisi.

Jurnal (müəllim bal yazır) və İmtahan Mərkəzi (pəncərəni idarə edir) bu servisi
paylaşır. Bir yerdə saxlanır ki, "açıqdır?" qərarı hər iki tərəfdə eyni olsun.

Vəziyyətlər (``entry_state`` → ``status``):
    not_configured — İmtahan Mərkəzi bu K üçün pəncərə YARATMAYIB (müəllim yaza bilməz)
    inactive       — pəncərə var, amma aktivləşdirilməyib (müəllim yaza bilməz)
    scheduled      — aktivdir, amma açılış tarixi hələ gəlməyib
    open           — açıqdır (müəllim SƏRBƏST yaza/dəyişə bilər)
    closed         — son tarix keçib (kilidli)

``validate_window_save`` isə İmtahan Mərkəzi kabinetinin YARADILIŞ/REDAKTƏ
tərəfini qoruyur (QA 2026-09-05 P3-21) — pəncərə tarixlərinin keçmişə/yalan
sıraya düşməsinin qarşısını server-side alır (bax aşağıdakı funksiyanın
docstring-i).
"""

import datetime

from django.apps import apps as django_apps


def window_for(offering, k_index):
    """(offering.organization, offering.period, k_index) üçün pəncərə və ya None."""
    KollokviumWindow = django_apps.get_model("registrar", "KollokviumWindow")
    return (
        KollokviumWindow.objects.filter(
            organization_id=offering.organization_id,
            period_id=offering.period_id,
            k_index=k_index,
        )
        .prefetch_related("extra_grants")
        .first()
    )


def _offering_unit_ids(offering):
    """offering.group + onun bütün ata OrgUnit-ləri (fakültə/kafedra grant uyğunluğu üçün)."""
    ids = set()
    unit = getattr(offering, "group", None)
    guard = 0
    while unit is not None and guard < 12:
        ids.add(unit.id)
        unit = unit.parent
        guard += 1
    return ids


def effective_extra_days(window, offering):
    """Bu offering-ə tətbiq olunan grant-ların ƏN BÖYÜK əlavə günü (yoxdursa 0).

    ``offering.group is None`` (bütün-ixtisas dərsi) — org-unit ağacı yoxdur, ona
    görə fakültə/kafedra grant-ını dəqiq uzlaşdıra bilmirik. Müəllimi verilmiş
    uzatma müddətində KİLİDLƏMƏMƏK üçün belə offering-lərə pəncərənin BÜTÜN
    grant-larının ən böyüyünü tətbiq edirik (kilidlənmə > az uzatma).
    """
    best = 0
    unit_ids = None
    group_less = getattr(offering, "group", None) is None
    for grant in window.extra_grants.all():
        if grant.scope == "organization" or group_less:
            best = max(best, grant.extra_days)
        elif grant.org_unit_id:
            if unit_ids is None:
                unit_ids = _offering_unit_ids(offering)
            if grant.org_unit_id in unit_ids:
                best = max(best, grant.extra_days)
    return best


def effective_deadline(window, offering):
    """closes_on + effektiv əlavə gün → müəllimin son bal-yazma günü (daxil)."""
    return window.closes_on + datetime.timedelta(days=effective_extra_days(window, offering))


def entry_state(offering, k_index, today):
    """Bu offering-in K{k_index+1}-i üçün bal-yazma vəziyyəti (yuxarıdakı status-lar).

    ``window`` None ola bilər (not_configured); açıq statuslarda ``deadline`` var.
    """
    window = window_for(offering, k_index)
    if window is None:
        return {"status": "not_configured", "window": None}
    if not window.is_active:
        return {"status": "inactive", "window": window, "opens_on": window.opens_on}

    deadline = effective_deadline(window, offering)
    if today < window.opens_on:
        return {"status": "scheduled", "window": window, "opens_on": window.opens_on, "deadline": deadline}
    if today > deadline:
        return {"status": "closed", "window": window, "deadline": deadline}
    return {"status": "open", "window": window, "opens_on": window.opens_on, "deadline": deadline}


def is_open(offering, k_index, today):
    """Müəllim indi bu K-ya bal yaza/dəyişə bilərmi?"""
    return entry_state(offering, k_index, today)["status"] == "open"


class KollokviumWindowRuleError(Exception):
    """Pəncərə tarix qaydası pozuntusu — istifadəçiyə göstərilə bilən mesaj daşıyır.

    ``gradebook.LessonRuleError`` ilə eyni naxış: sadə AZ mətn, gettext YOXDUR
    (bu modul artıq plain AZ mesajlarla işləyir — ``entry_state`` statusları da
    tərcümə olunmur, çağıran tərəf UI mətnini özü seçir).
    """


def validate_window_save(*, organization, period, k_index, opens_on, closes_on, is_new, today):
    """Pəncərə yaradılışı/redaktəsi üçün tarix qaydalarını yoxlayır (QA P3-21).

    Qaydalar:

    1. **Keçmiş bağlanış — yalnız YARADILIŞDA qadağan.** Bağlanış tarixi
       bugündən əvvəldirsə və bu YENİ sətirdirsə (``is_new``), rədd et. Artıq
       mövcud (işləyən/bitmiş) pəncərəni UZATMAQ (redaktə) sərbətdir —
       İmtahan Mərkəzi səhv yazılmış köhnə pəncərəni düzəldə bilməlidir.
    2. **K-sırası / toqquşma.** Eyni (organization, period) əhatəsində
       fərqli ``k_index``-li pəncərələr üst-üstə düşə bilməz: kiçik K böyük K
       başlamazdan ƏVVƏL bitməlidir (``closes_on`` bərabər ola bilər — eyni
       gün keçid normaldır). ``(organization, period, k_index)`` unikallığı
       artıq EYNİ K-nin iki sətrini DB səviyyəsində qadağan edir — bura yalnız
       FƏRQLİ K-lər arasındakı toqquşmanı yoxlayır.

    ``KollokviumWindowRuleError`` qaldırır (view bunu forma xətasına çevirir).
    """
    KollokviumWindow = django_apps.get_model("registrar", "KollokviumWindow")

    if is_new and closes_on < today:
        raise KollokviumWindowRuleError(
            "Bağlanış tarixi keçmişdə ola bilməz — yeni pəncərə üçün gələcək tarix seçin "
            "(artıq mövcud pəncərəni uzatmaq üçün onun tarixini redaktə edin)."
        )

    siblings = KollokviumWindow.objects.filter(organization=organization, period=period).exclude(k_index=k_index)
    for sibling in siblings:
        if sibling.k_index < k_index and opens_on < sibling.closes_on:
            raise KollokviumWindowRuleError(
                f"K{k_index + 1} pəncərəsi K{sibling.k_index + 1} bitmədən "
                f"({sibling.closes_on:%d.%m.%Y}) əvvəl başlaya bilməz."
            )
        if sibling.k_index > k_index and closes_on > sibling.opens_on:
            raise KollokviumWindowRuleError(
                f"K{k_index + 1} pəncərəsi K{sibling.k_index + 1} başlamazdan "
                f"({sibling.opens_on:%d.%m.%Y}) əvvəl bitməlidir."
            )
