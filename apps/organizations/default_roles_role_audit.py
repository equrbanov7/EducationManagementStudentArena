"""Rol auditi 2026-10-13 — «hər rol öz norması qədər» (sahib: «tövsiyə olunan variantlarla et»).

Hesabat: ``docs/audits/2026-10-13-claude/ROL_AUDITI.md`` (B bəndləri). Rol YARATMIR — mövcud rollara
açar verir / alır. Mövcud tenantlar: miqrasiya ``organizations/0061`` (eyni xəritə, sətir-sətir köçürülüb).

Yeni açarlar (kataloq: ``permissions_role_audit.py``):

* ``exam_center.decide`` — imtahan mərkəzinin QƏRAR əməlləri (ikinci şans, kollokvium pəncərəsi, sual
  göndərişinin qəbulu/rəddi). Prefiks QƏSDƏN ``exam.`` deyil: ``exam.*`` imtahan mərkəzi işçisində, dekanda,
  kafedra müdirində də var — qərar onlara avtomatik keçməməlidir (B1: işçi «görür və köməklik edir»).
* ``student.records_view`` — «Akademik qeydlər» (GPA/transkript) bölməsi + data əhatəsi (B2). Əvvəl rol ADI
  ilə qapılı idi və mərkəzi rollara açarsız org-wide verilirdi. ``grade.view`` seçilmədi: o, kurs/vahid
  əhatəli laborant və müəllimdə də var — GPA reyestri onlara açılardı.
* ``user.import_staff`` — «Müəllim idxalı» (toplu heyət hesabı) (B3). Əvvəl tələbə qəbulu ilə eyni
  ``user.import`` açarında idi və Tələbə xidmətləri müəllim hesabı yarada bilirdi.
* ``notification.publish`` — «Bildiriş göndər» (B14). Əvvəl rol BAYRAQLARI ilə açılırdı (org_admin aliası, müəllim,
  imtahan mərkəzi, HR); bu gün bölməni görən HƏR rol açarı alır (görünüş dəyişmir, indi redaktordan idarə olunur).
  Qeyri-universitet şablonları ``default_roles.py``-dadır; mövcud tenantlar — miqrasiya ``organizations/0062``.
"""

#: Rol adı → VERİLƏN açarlar. Açar, onun ``<prefiks>.*`` wildcard-ı və ya ``*`` artıq varsa atlanır.
ROLE_AUDIT_GRANTS: dict[str, tuple[str, ...]] = {
    # B1 — qərar yalnız rəhbərdə; işçi və RİM əməkdaşı görür.
    "exam_center_head": ("exam_center.decide", "student.records_view", "notification.publish"),
    "exam_center": ("exam_center.decide", "student.records_view", "notification.publish"),
    # B20 — kataloq kontaktsız (`people.view_contacts` verilmir); B2 — akademik qeydlər əvvəlki kimi.
    "exam_center_staff": (
        "people.view_students",
        "people.view_teachers",
        "student.records_view",
        "notification.publish",
    ),
    # B3 — müəllim idxalı HR-dadır.
    "hr": ("user.import_staff", "notification.publish"),
    # B4 — «assistent» QKU-da elmi-pedaqoji vəzifədir: fənnin müəllimi ola bilsin (`grade.input`
    # olmadan yük sinxronu onu `instructor_blocked` sayırdı), sillabus yazsın, imtahan yaratsın.
    "assistant": (
        "grade.input",
        "syllabus.view",
        "syllabus.edit",
        "syllabus.submit",
        "exam.create",
        "exam.edit",
        "exam.host",
        "notification.publish",
    ),
    # B14 — bölməni bu gün müəllim bayrağı ilə görən digər tədris rolları.
    "teacher": ("notification.publish",),
    "lab_assistant": ("notification.publish",),
    # B5 — Tədris şöbəsi: jurnal/qeyd/cədvəl OXUSU; rəhbər tələbə reyestrini də görür (xaric axını).
    "teaching_office_head": (
        "student.records_view",
        "journal.view",
        "journal.lessons_unit",
        "schedule.view",
        "student.registry_view",
    ),
    "teaching_office_staff": ("student.records_view", "journal.view", "journal.lessons_unit", "schedule.view"),
    # B11 — prorektor cədvəli YALNIZ-OXU görür; B2 — akademik qeydlər əvvəlki kimi.
    "vice_rector": ("schedule.view", "student.records_view", "notification.publish"),
    # B2 — bu gün «Akademik qeydlər»i görən rollar açarı alır (görünüş dəyişmir, indi redaktordan idarə olunur).
    "dean": ("student.records_view", "notification.publish"),
    "vice_dean": ("student.records_view", "notification.publish"),
    "chair_head": ("student.records_view", "notification.publish"),
    "rim_staff": ("student.records_view", "notification.publish"),
}

#: Rol adı → ALINAN açarlar (B6: HR-ın tələbə tərəfi Tələbə xidmətlərinə keçib).
ROLE_AUDIT_REVOKES: dict[str, tuple[str, ...]] = {
    "hr": ("user.import", "people.view_students"),
}

#: Heç nəyi qapılamayan açarlar (B13) — kataloqdan və bütün rollardan çıxarılır.
DEAD_PERMISSION_KEYS: tuple[str, ...] = ("grade.publish", "assignment.edit")


def _covered(permissions, key) -> bool:
    prefix_wildcard = f"{key.split('.', 1)[0]}.*"
    return key in permissions or prefix_wildcard in permissions or "*" in permissions


def apply_role_audit_grants(roles):
    """Xəritələri rol şablonları siyahısına idempotent tətbiq edir (yerində)."""
    for role in roles:
        name = role.get("name")
        permissions = role.setdefault("permissions", [])
        permissions[:] = [key for key in permissions if key not in DEAD_PERMISSION_KEYS]
        for key in ROLE_AUDIT_REVOKES.get(name, ()):
            while key in permissions:
                permissions.remove(key)
        for key in ROLE_AUDIT_GRANTS.get(name, ()):
            if not _covered(permissions, key):
                permissions.append(key)
    return roles


__all__ = ["DEAD_PERMISSION_KEYS", "ROLE_AUDIT_GRANTS", "ROLE_AUDIT_REVOKES", "apply_role_audit_grants"]
