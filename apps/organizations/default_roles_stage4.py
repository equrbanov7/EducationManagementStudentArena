"""Dərs yükü zəncirinin açarları — dizayn Mərhələ 4 (ekran 12/13/15/16/17).

Rol YARATMIR — yalnız MÖVCUD rollara `workload.*` ailəsinin qalan açarlarını
paylayır. `workload.view/manage/distribute/report` FAZA 3-də (miqrasiya
``workload/0003``) əkilib; burada zəncirin dörd halqası açılır:

    Tədris şöbəsi   → workload.submit    (12)
    Koordinator     → workload.review    (13)
    Dekan           → workload.approve   (15)
    Müəllim         → workload.object    (16)

──────────────────────────────────────────────────────────────────────────────
SƏLAHİYYƏT AYRILIĞI
──────────────────────────────────────────────────────────────────────────────
Heç bir akademik rol zəncirin iki qonşu halqasını daşımır: göndərən (tədris
şöbəsi) təsdiqləmir, viza verən (koordinator) qaytarmır, təsdiqləyən (dekan)
bölmür. RİM (``ikt_rehber``), prorektor və rektor operator olduğu üçün
`workload.*` / `*` daşıyır — bu QƏSDƏNDİR (fövqəladə hallarda zənciri
hərəkətə gətirən yeganə səth).

Ayrı modul + ayrı migration: Mərhələ 1/2/3 migrasiyalarının geri dönüşü bu
açarları səssizcə silməsin.
"""

#: Rol adı → verilən açarlar. Rol yoxdursa (tenant onu işlətmirsə) atlanır.
STAGE4_ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    # Ekran 12 — tapşırığı yaradan və dekanlıqlara göndərən səth.
    "teaching_office_head": (
        "workload.view",
        "workload.manage",
        "workload.submit",
        "workload.report",
    ),
    # Əməkdaş yaradır və göndərir, HESABAT səthi yoxdur (rəhbərin görünüşü).
    "teaching_office_staff": (
        "workload.view",
        "workload.manage",
        "workload.submit",
    ),
    # Ekran 13 — yalnız ÖZ ixtisasının sətirlərinə viza/irad.
    "program_coordinator": ("workload.view", "workload.review"),
    # Ekran 15 — fakültə diliminin təsdiqi/qaytarılması.
    "dean": ("workload.view", "workload.approve", "workload.report"),
    # Ekran 16 — müəllim yükü təsdiqləyir və ya etiraz edir.
    "teacher": ("workload.view", "workload.object"),
    "assistant": ("workload.view", "workload.object"),
    "lab_assistant": ("workload.view", "workload.object"),
    # Ekran 17 — rektorluq yalnız OXUYUR (aqreqasiya).
    "rector": ("workload.report",),
    "vice_rector": ("workload.report",),
}


def apply_stage4_grants(roles):
    """``STAGE4_ROLE_GRANTS``-i rol siyahısına idempotent tətbiq edir."""
    for role in roles:
        wanted = STAGE4_ROLE_GRANTS.get(role.get("name"))
        if not wanted:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions:
            continue
        for permission in wanted:
            prefix_wildcard = f"{permission.split('.', 1)[0]}.*"
            if permission in permissions or prefix_wildcard in permissions:
                continue
            permissions.append(permission)
    return roles


__all__ = ["STAGE4_ROLE_GRANTS", "apply_stage4_grants"]
