#!/usr/bin/env python3
"""Xam açar sızmalarının doldurulması (2026-07-31 audit, Faza 2).

Problem
-------
``apps/exams`` model/form təriflərində etiketlər insan mətni yerinə **sahə adı**
ilə açarlanıb::

    verbose_name=pgettext_lazy("exams.model.room_computer.field", "ip_address")

msgid özü açar olduğu üçün AZ kataloqunda ``msgstr == msgid`` qalıb və istifadəçi
interfeysdə hərfi ``ip_address`` görür. EN/RU/TR üçün əvvəlki mərhələlərdə
tərcümə verilib, AZ (mənbə dil sayıldığından) boş qalıb.

Bu skript AZ mətnlərini doldurur; EN/RU/TR yalnız orada da açar sızdığı və ya
``help`` mətni etiketin surəti olduğu hallarda düzəlir.

Skript **idempotentdir**: yalnız msgstr hazırda açarın özüdürsə (və ya bilinən
saxta mətndirsə) yazır, mövcud düzgün tərcüməyə toxunmur.

İstifadə::

    python scripts/i18n_fill_raw_key_leaks.py --dry-run
    python scripts/i18n_fill_raw_key_leaks.py
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

#: ``(msgctxt, msgid) -> {lang: mətn}``. ``az`` həmişə var; digər dillər yalnız
#: hazırkı dəyər səhv olanda göstərilir.
TRANSLATIONS: dict[tuple[str, str], dict[str, str]] = {
    # ── Kodlaşdırma sualları ────────────────────────────────────────────────
    ("exams.model.coding_test_case.field", "input_data"): {"az": "Giriş məlumatı"},
    ("exams.model.coding_submission.field", "memory_usage_kb"): {"az": "Yaddaş istifadəsi (KB)"},
    ("exams.form.coding.error", "test_cases_must_be_json"): {"az": "Test halları düzgün JSON olmalıdır."},
    ("exams.form.coding.error", "test_case_must_be_object"): {"az": "Hər test halı obyekt olmalıdır."},
    ("exams.form.coding.label", "visible_test_cases"): {"az": "Görünən test halları"},
    ("exams.form.coding.label", "hidden_test_cases"): {"az": "Gizli test halları"},
    # help mətnləri etiketin surəti idi — 4 dildə də əsl izaha çevrilir.
    ("exams.form.coding.help", "visible_test_cases"): {
        "az": "Tələbəyə nümunə kimi göstərilən test halları.",
        "en": "Test cases shown to the student as examples.",
        "ru": "Тестовые случаи, показываемые студенту в качестве примеров.",
        "tr": "Öğrenciye örnek olarak gösterilen test durumları.",
    },
    ("exams.form.coding.help", "hidden_test_cases"): {
        "az": "Tələbəyə göstərilməyən, yalnız qiymətləndirmədə işlədilən test halları.",
        "en": "Test cases hidden from the student and used only for grading.",
        "ru": "Тестовые случаи, скрытые от студента и используемые только для оценивания.",
        "tr": "Öğrenciden gizlenen ve yalnızca değerlendirmede kullanılan test durumları.",
    },
    ("exams.model.coding_test_case.choice.visibility", "visible"): {
        "az": "Görünən",
        "en": "Visible",
        "ru": "Видимый",
        "tr": "Görünür",
    },
    # ── İmtahan ─────────────────────────────────────────────────────────────
    ("exams.model.exam.field", "ai_difficulty_balance_enabled"): {"az": "AI çətinlik balansı aktivdir"},
    ("exams.model.exam.help", "ai_difficulty_balance_enabled"): {
        "az": "Sual seçimində çətinlik səviyyələri avtomatik balanslaşdırılır.",
        "en": "Difficulty levels are balanced automatically when questions are selected.",
        "ru": "Уровни сложности балансируются автоматически при подборе вопросов.",
        "tr": "Sorular seçilirken zorluk seviyeleri otomatik olarak dengelenir.",
    },
    ("exams.model.exam.field", "excluded_users"): {"az": "İstisna edilən tələbələr"},
    ("exams.form.exam.label", "excluded_users"): {"az": "İstisna edilən tələbələr"},
    ("exams.model.exam.help", "excluded_users"): {
        "az": "Qrupunun girişi olsa belə, bu tələbələr imtahanda iştirak edə bilməz."
    },
    ("exams.model.question.choice.difficulty_source", "manual"): {
        "az": "Əl ilə",
        "en": "Manual",
        "ru": "Вручную",
        "tr": "Elle",
    },
    ("live_exam.view.permission", "org_suspended_or_inactive"): {"az": "Təşkilat dayandırılıb və ya aktiv deyil."},
    ("exams.service.access.permission", "exam_rooms_manage_superadmin_only"): {
        "az": "İmtahan zallarını yalnız superadmin idarə edə bilər."
    },
    # ── Qrup ────────────────────────────────────────────────────────────────
    ("exams.form.group.error", "tenant_subjects_only"): {
        "az": "Qrupa yalnız eyni təşkilatın fənləri əlavə oluna bilər."
    },
    ("exams.form.group.label", "org_unit"): {"az": "Struktur bölmə"},
    ("exams.form.group.help", "org_unit"): {"az": "Qrupun aid olduğu akademik bölmə (fakültə/kafedra/ixtisas)."},
    ("exams.form.group.label", "subjects"): {"az": "Fənlər"},
    ("exams.form.group.help", "subjects"): {"az": "Bu qrupa tədris olunan fənlər."},
    ("exams.model.student_group.field", "org_unit"): {"az": "Akademik bölmə"},
    ("exams.model.student_group.field", "subjects"): {"az": "Fənlər"},
    # ── Cəhd / qiymətləndirmə ───────────────────────────────────────────────
    ("exams.model.attempt.field", "graded_by"): {"az": "Qiymətləndirən"},
    ("exams.model.attempt.field", "room_computer"): {"az": "Zal kompüteri"},
    ("exams.model.attempt.field", "room"): {"az": "Zal"},
    ("exams.model.attempt_grant.field", "extra_attempts"): {"az": "Əlavə cəhdlər"},
    ("exams.model.attempt_grant.field", "granted_by"): {"az": "Hüququ verən"},
    ("exams.model.attempt_grant.field", "exam"): {"az": "İmtahan"},
    ("exams.model.attempt_grant.field", "student"): {"az": "Tələbə"},
    ("exams.model.grade_event.field", "attempt"): {"az": "Cəhd"},
    ("exams.model.grade_event.field", "grader"): {"az": "Qiymətləndirən"},
    ("exams.model.grade_event.field", "question"): {"az": "Sual"},
    # ── İmtahan zalı ────────────────────────────────────────────────────────
    ("exams.model.exam_room.field", "computer_count"): {"az": "Kompüter sayı"},
    ("exams.model.exam_room.field", "created_by"): {"az": "Yaradan"},
    ("exams.model.exam_room.field", "is_active"): {"az": "Aktiv"},
    ("exams.model.exam_room.field", "building"): {"az": "Bina"},
    ("exams.model.exam_room.field", "capacity"): {"az": "Tutum"},
    ("exams.model.exam_room.field", "code"): {"az": "Kod"},
    ("exams.model.exam_room.field", "floor"): {"az": "Mərtəbə"},
    ("exams.model.exam_room.field", "invigilators"): {"az": "Nəzarətçilər"},
    ("exams.model.exam_room.field", "name"): {"az": "Ad"},
    ("exams.model.exam_room.field", "notes"): {"az": "Qeydlər"},
    ("exams.model.exam_room.field", "organization"): {"az": "Təşkilat"},
    ("exams.model.exam_room.help", "capacity"): {"az": "Zalın ümumi yer tutumu."},
    ("exams.model.exam_room.help", "code"): {"az": "Zalın qısa kodu (təşkilat daxilində unikal)."},
    ("exams.model.exam_room.help", "invigilators"): {
        "az": "Bu zala təyin olunan işçilər zalda keçirilən bütün oturumları izləyə və idarə edə bilər."
    },
    # ── Zal kompüteri ───────────────────────────────────────────────────────
    ("exams.model.room_computer.field", "ip_address"): {"az": "IP ünvan"},
    ("exams.model.room_computer.field", "mac_address"): {"az": "MAC ünvan"},
    ("exams.model.room_computer.field", "seat_number"): {"az": "Yer nömrəsi"},
    ("exams.model.room_computer.field", "is_active"): {"az": "Aktiv"},
    ("exams.model.room_computer.field", "label"): {"az": "Etiket"},
    ("exams.model.room_computer.field", "notes"): {"az": "Qeydlər"},
    ("exams.model.room_computer.field", "organization"): {"az": "Təşkilat"},
    ("exams.model.room_computer.field", "room"): {"az": "Zal"},
    ("exams.model.room_computer.help", "ip_address"): {"az": "Kompüterin IP ünvanı (məcburi deyil)."},
    ("exams.model.room_computer.help", "mac_address"): {
        "az": "İmtahan girişində kompüteri tanımaq üçün MAC ünvan (məs. AA:BB:CC:DD:EE:FF)."
    },
    ("exams.model.room_computer.help", "seat_number"): {
        "az": "Bu kompüterə zalda ayrılmış yer nömrəsi (məcburi deyil)."
    },
    ("exams.model.room_computer.help", "label"): {"az": "Zal planında görünən kompüter etiketi (məs. PC-01)."},
    # ── Zal sessiyası ───────────────────────────────────────────────────────
    ("exams.model.room_session.choice.state", "entry_open"): {"az": "Giriş açıqdır"},
    ("exams.model.room_session.choice.state", "active"): {"az": "Aktiv"},
    ("exams.model.room_session.choice.state", "cancelled"): {"az": "Ləğv edilib"},
    ("exams.model.room_session.choice.state", "ended"): {"az": "Bitib"},
    ("exams.model.room_session.choice.state", "prepared"): {"az": "Hazırlanıb"},
    ("exams.model.room_session.field", "ended_at"): {"az": "Bitmə vaxtı"},
    ("exams.model.room_session.field", "ended_by"): {"az": "Bitirən"},
    ("exams.model.room_session.field", "scheduled_end"): {"az": "Planlaşdırılan bitmə"},
    ("exams.model.room_session.field", "scheduled_start"): {"az": "Planlaşdırılan başlama"},
    ("exams.model.room_session.field", "started_at"): {"az": "Başlama vaxtı"},
    ("exams.model.room_session.field", "started_by"): {"az": "Başladan"},
    ("exams.model.room_session.field", "invigilator"): {"az": "Nəzarətçi"},
    ("exams.model.room_session.field", "notes"): {"az": "Qeydlər"},
    ("exams.model.room_session.field", "organization"): {"az": "Təşkilat"},
    ("exams.model.room_session.field", "room"): {"az": "Zal"},
    ("exams.model.room_session.field", "staff"): {"az": "İşçilər"},
    ("exams.model.room_session.field", "state"): {"az": "Vəziyyət"},
    ("exams.model.room_session.help", "staff"): {"az": "Bu sessiyaya təyin olunan əlavə imtahan mərkəzi işçiləri."},
    # ── Yekun imtahan bileti ────────────────────────────────────────────────
    ("exams.model.final_ticket.field", "seat_number"): {"az": "Yer nömrəsi"},
    ("exams.model.final_ticket.field", "attempt"): {"az": "Cəhd"},
    ("exams.model.final_ticket.field", "exam"): {"az": "İmtahan"},
    ("exams.model.final_ticket.field", "language"): {"az": "Dil"},
    ("exams.model.final_ticket.field", "organization"): {"az": "Təşkilat"},
    ("exams.model.final_ticket.field", "session"): {"az": "Sessiya"},
    ("exams.model.final_ticket.field", "status"): {"az": "Status"},
    ("exams.model.final_ticket.field", "student"): {"az": "Tələbə"},
    ("exams.model.final_ticket.help", "language"): {
        "az": "Tələbənin imtahanı verəcəyi dil (boş = imtahanın standart dili)."
    },
    ("exams.model.final_ticket.choice.removal", "removed"): {"az": "Çıxarılıb"},
    ("exams.model.final_ticket.choice.removal", "suspended"): {"az": "Dayandırılıb"},
    ("exams.model.final_ticket.choice.removal", "technical"): {"az": "Texniki problem"},
    ("exams.model.final_ticket.choice.status", "absent"): {"az": "İştirak etməyib"},
    ("exams.model.final_ticket.choice.status", "active"): {"az": "Aktiv"},
    ("exams.model.final_ticket.choice.status", "assigned"): {"az": "Təyin edilib"},
    ("exams.model.final_ticket.choice.status", "completed"): {"az": "Tamamlanıb"},
    ("exams.model.final_ticket.choice.status", "ready"): {"az": "Hazır"},
    ("exams.model.final_ticket.choice.status", "removed"): {"az": "Çıxarılıb"},
    ("exams.model.final_ticket.choice.status", "waiting"): {"az": "Gözləyir"},
    ("exams.model.student_pin.field", "expires_at"): {"az": "Etibarlıdır"},
    ("exams.model.student_pin.field", "revoked_at"): {"az": "Ləğv edilmə vaxtı"},
    ("exams.model.student_pin.field", "exam"): {"az": "İmtahan"},
    ("exams.model.student_pin.field", "student"): {"az": "Tələbə"},
    # ── Sual bankı / göndərişlər ────────────────────────────────────────────
    ("exams.model.question_bank.field", "exam_kind"): {"az": "İmtahan növü"},
    ("exams.model.question_bank.field", "source_teacher"): {"az": "Sualı göndərən müəllim"},
    ("exams.model.question_bank.field", "subject_ref"): {"az": "Fənn (bazadan)"},
    ("exams.model.question_submission.field", "accepted_bank"): {"az": "Hədəf sual bankı"},
    ("exams.model.question_submission.field", "exam_kind"): {"az": "İmtahan növü"},
    ("exams.model.question_submission.field", "group_label"): {"az": "Qrup (sərbəst mətn)"},
    ("exams.model.question_submission.field", "raw_text"): {"az": "Xam sual mətni"},
    ("exams.model.question_submission.field", "reviewer_note"): {"az": "Yoxlayanın qeydi"},
    ("exams.model.question_submission.field", "student_group"): {"az": "Tələbə qrupu"},
    ("exams.model.question_submission.field", "student_groups"): {"az": "Tələbə qrupları"},
    ("exams.model.question_submission.field", "subject_ref"): {"az": "Fənn (bazadan)"},
    ("exams.model.question_submission.field", "teacher_note"): {"az": "Müəllimin qeydi"},
    ("exams.model.question_submission.field", "language"): {"az": "Dil"},
    ("exams.model.question_submission.field", "organization"): {"az": "Təşkilat"},
    ("exams.model.question_submission.field", "reviewer"): {"az": "Yoxlayan"},
    ("exams.model.question_submission.field", "status"): {"az": "Status"},
    ("exams.model.question_submission.field", "subject"): {"az": "Fənn"},
    ("exams.model.question_submission.field", "teacher"): {"az": "Müəllim"},
    ("exams.model.question_submission.field", "title"): {"az": "Başlıq"},
    ("exams.model.question_submission.help", "title"): {
        "az": "Göndəriş üçün qısa başlıq (məs. mövzu və ya fəsil adı)."
    },
    ("exams.model.question_submission.choice.status", "accepted"): {"az": "Qəbul edilib"},
    ("exams.model.question_submission.choice.status", "pending"): {"az": "Gözləyir"},
    ("exams.model.question_submission.choice.status", "rejected"): {"az": "Rədd edilib"},
    # ── Nəzarət (supervision) ───────────────────────────────────────────────
    ("supervision.config.choice.template", "custom"): {
        "az": "Fərdi",
        "en": "Custom",
        "ru": "Пользовательский",
        "tr": "Özel",
    },
    ("supervision.incident.field", "severity"): {
        "az": "Ciddilik dərəcəsi",
        "en": "Severity",
        "ru": "Уровень серьёзности",
        "tr": "Önem derecesi",
    },
    # ── Canlı imtahan şablonları (AZ/EN düzgün, RU/TR-də açar qalıb) ────────
    ("exams.template.student_exam_list", "live_card_pin_required_error"): {
        "ru": "Введите PIN-код.",
        "tr": "PIN kodunu girin.",
    },
    ("exams.template.student_exam_list", "live_card_pin_mismatch_error"): {
        "ru": "PIN не совпадает. Введите код, показанный преподавателем на экране.",
        "tr": "PIN eşleşmiyor. Öğretmenin ekranda gösterdiği kodu girin.",
    },
    ("exams.template.teacher_exam_detail", "live_resume_modal_pin"): {"ru": "PIN", "tr": "PIN"},
    ("exams.template.teacher_exam_detail", "live_resume_modal_new"): {
        "ru": "Начать новую сессию",
        "tr": "Yeni oturum başlat",
    },
    ("exams.template.teacher_exam_detail", "live_resume_modal_return"): {
        "ru": "Вернуться к сессии",
        "tr": "Oturuma dön",
    },
    # ── Profil ──────────────────────────────────────────────────────────────
    ("profile.courses", "explore_courses"): {"az": "Kurslara bax"},
    ("profile.section", "overall_academic"): {"az": "Ümumi akademik məlumat"},
    ("profile.sidebar", "group_blog"): {"az": "Qrup bloqu"},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Xam açar sızmalarını doldur")
    parser.add_argument("--dry-run", action="store_true", help="dəyişiklik yazma")
    args = parser.parse_args()

    try:
        import polib
    except ImportError:
        print("❌ polib lazımdır: pip install polib")
        return 1

    total = 0
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        catalog = polib.pofile(path)
        index = {(e.msgctxt or "", e.msgid): e for e in catalog if not e.obsolete}

        changed = 0
        missing: list[tuple[str, str]] = []
        for key, texts in TRANSLATIONS.items():
            text = texts.get(lang)
            if text is None:
                continue
            entry = index.get(key)
            if entry is None:
                missing.append(key)
                continue
            # İdempotent: yalnız hazırkı dəyər açarın özüdürsə və ya bu skriptin
            # düzəltmək istədiyi saxta mətndirsə yaz.
            if entry.msgstr == text:
                continue
            is_raw_leak = entry.msgstr == entry.msgid
            is_forced = len(texts) > 1  # çoxdilli giriş = bilinən saxta mətn
            if not (is_raw_leak or is_forced or not entry.msgstr):
                continue
            entry.msgstr = text
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            changed += 1

        if changed and not args.dry_run:
            catalog.save(path)
        total += changed
        note = f", {len(missing)} açar kataloqda tapılmadı" if missing else ""
        print(f"  {lang}: {changed} giriş dolduruldu{note}")
        for key in missing[:5]:
            print(f"      ⚠️  {key}")

    print(f"\n✅ Cəmi {total} giriş {'dolduruLACAQ' if args.dry_run else 'dolduruldu'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
