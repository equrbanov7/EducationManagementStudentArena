#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-11: kurs tapşırıqları modulu «Sərbəst iş» deyil, «Tapşırıq» adlanır.

Sahib 2026-10-10 sərbəst işi (jurnal/sillabus/fənn qovluğu, 10 bal) ləğv etdi; `apps.assignments` (kurs
tapşırıqları) AYRI funksiyadır, amma interfeysdə də «Sərbəst işlər» adlanırdı — qarışıqlıq olmasın deyə yalnız
onun kontekstlərindəki mətnlər dəyişdirilir (sahib 2026-10-11: «tövsiyə edilən kimi et»). Jurnal/sillabus/fənn
qovluğu sərbəst işinin mətnlərinə TOXUNULMUR — onlar `academic.selfwork_enabled` ilə geri qayıdır.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir (FORCE); sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_11_assignments_label.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


ONE = _t("Tapşırıq", "Assignment", "Задание", "Ödev")
MANY = _t("Tapşırıqlar", "Assignments", "Задания", "Ödevler")

# (ctx, msgid) → {az, en, ru, tr}
ENTRIES = {
    ("accounts.pending_answers", "filter_free_work"): ONE,
    ("accounts.pending_answers", "kpi_free_work_note"): _t(
        "tapşırıq cavabları", "assignment submissions", "ответы на задания", "ödev teslimleri"
    ),
    ("profile.assigned_tasks", "tab_assignments"): MANY,
    ("profile.results", "tab_assignments"): MANY,
    ("accounts.my_result_detail.type", "course"): ONE,
    ("assignment.app", "title"): MANY,
    ("assignment.model.meta", "verbose_name"): ONE,
    ("assignment.model.meta", "verbose_name_plural"): MANY,
    ("assignment.detail", "Bu sərbəst işi göndərmək istədiyinizə əminsiniz?"): _t(
        "Bu tapşırığı göndərmək istədiyinizə əminsiniz?",
        "Are you sure you want to submit this assignment?",
        "Вы уверены, что хотите отправить это задание?",
        "Bu ödevi göndermek istediğinizden emin misiniz?",
    ),
    ("assignment.section", "title"): MANY,
    ("assignment.section", "empty_teacher"): _t(
        "Hələ ki tapşırıq yoxdur", "No assignments yet", "Заданий пока нет", "Henüz ödev yok"
    ),
    ("assignment.section", "add_first"): _t(
        "İlk tapşırığı əlavə et", "Add your first assignment", "Добавьте первое задание", "İlk ödevinizi ekleyin"
    ),
    ("assignment.section", "empty_student"): _t(
        "Sizə təyin olunmuş tapşırıq yoxdur",
        "No assignments have been assigned to you",
        "Вам не назначено ни одного задания",
        "Size atanmış ödev yok",
    ),
    ("assignment.section", "empty_generic"): _t("Tapşırıq yoxdur", "No assignments", "Заданий нет", "Ödev yok"),
    ("assignment.legacy.modals", "modal_add_title"): _t(
        "Yeni tapşırıq əlavə et", "Add a new assignment", "Добавить новое задание", "Yeni ödev ekle"
    ),
    ("assignment.modals", "modal_add_title"): _t("Yeni tapşırıq", "New assignment", "Новое задание", "Yeni ödev"),
    ("assignment.legacy.review", "empty_not_found"): _t(
        "Heç bir tapşırıq tapılmadı", "No assignments found", "Задания не найдены", "Hiç ödev bulunamadı"
    ),
    ("", "Bu seçim geri qaytarılmır. Seçilmiş sərbəst iş cavabları silinəcək."): _t(
        "Bu seçim geri qaytarılmır. Seçilmiş tapşırıq cavabları silinəcək.",
        "This action cannot be undone. The selected assignment answers will be deleted.",
        "Это действие нельзя отменить. Выбранные ответы на задания будут удалены.",
        "Bu seçim geri alınamaz. Seçilen ödev cevapları silinecek.",
    ),
    ("assignments.views.message", "no_assignment_access"): _t(
        "Bu tapşırığa girişiniz yoxdur.",
        "You do not have access to this assignment.",
        "У вас нет доступа к этому заданию.",
        "Bu ödeve erişiminiz yok.",
    ),
    ("assignments.views.message", "assignment_created"): _t(
        "Tapşırıq yaradıldı.", "Assignment created.", "Задание создано.", "Ödev oluşturuldu."
    ),
    ("assignments.views.message", "assignment_updated"): _t(
        "Tapşırıq yeniləndi.", "Assignment updated.", "Задание обновлено.", "Ödev güncellendi."
    ),
    ("assignments.views.message", "assignment_deleted"): _t(
        "Tapşırıq silindi.", "Assignment deleted.", "Задание удалено.", "Ödev silindi."
    ),
    ("", "Assignment"): ONE,
    ("notifications.event.task_kind", "assignment"): _t("tapşırıq", "assignment", "задание", "ödev"),
    ("notifications.event", "New assignment assigned: {title}"): _t(
        "Yeni tapşırıq təyin olundu: {title}",
        "New assignment assigned: {title}",
        "Назначено новое задание: {title}",
        "Yeni ödev atandı: {title}",
    ),
    ("notifications.event", "New assignment submission: {student}"): _t(
        "Yeni tapşırıq cavabı: {student}",
        "New assignment submission: {student}",
        "Новая отправка задания: {student}",
        "Yeni ödev yanıtı: {student}",
    ),
    ("notifications.event", "Your assignment result is ready: {title}"): _t(
        "Tapşırıq nəticəniz hazırdır: {title}",
        "Your assignment result is ready: {title}",
        "Результат вашего задания готов: {title}",
        "Ödev sonucunuz hazır: {title}",
    ),
    ("courses.dashboard", "hint_assignments"): _t(
        "Tələbələr üçün tapşırıqlar və təqdimatlar",
        "Assignments and submissions for students",
        "Задания и ответы студентов",
        "Öğrenciler için ödevler ve teslimler",
    ),
    ("review.page", "kind_assignment"): ONE,
    ("organizations.permission.label", "Sərbəst işi silmək"): _t(
        "Tapşırığı silmək", "Delete assignment", "Удаление задания", "Ödevi silme"
    ),
    ("organizations.permission.label", "Sərbəst işi redaktə etmək"): _t(
        "Tapşırığı redaktə etmək", "Edit assignment", "Редактирование задания", "Ödevi düzenleme"
    ),
}


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for (ctx, msgid), values in ENTRIES.items():
        want = values[lang]
        entry = index.get((ctx, msgid))
        if entry is None:
            po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
            added += 1
            continue
        if entry.msgstr != want or "fuzzy" in entry.flags or entry.obsolete:
            entry.msgstr = want
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            entry.obsolete = False
            changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
