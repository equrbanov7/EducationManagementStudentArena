#!/usr/bin/env python3
"""
EMSArena i18n cleanup script (idempotent).

- Replaces hardcoded UI strings in templates with {% trans "key" context "ctx" %}.
- Appends the corresponding msgctxt/msgid/msgstr entries to all 4 .po files
  (az/en/ru/tr) if they are not already present.
- Fills selected empty/untranslated msgstr entries that already exist in the .po.

Safe to run multiple times: template replacements only fire on the literal
hardcoded text, and .po entries are only appended when the (msgctxt,msgid)
pair is missing.
"""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


# ---------------------------------------------------------------------------
# Translation catalog.
# Each entry: (context, key) -> {az, en, ru, tr}
# These are appended to the .po files. The template uses
#   {% trans "key" context "context" %}
# ---------------------------------------------------------------------------
CATALOG = {
    # ---- audit.list ----
    ("audit.list", "title"): {"az": "Audit jurnalı", "en": "Audit Log", "ru": "Журнал аудита", "tr": "Denetim Günlüğü"},
    ("audit.list", "heading"): {
        "az": "Audit jurnalı",
        "en": "Audit Log",
        "ru": "Журнал аудита",
        "tr": "Denetim Günlüğü",
    },
    ("audit.list", "subtitle_all_orgs"): {
        "az": "Bütün təşkilatlar üzrə son fəaliyyət qeydləri",
        "en": "Recent activity logs across all organizations",
        "ru": "Последние записи активности по всем организациям",
        "tr": "Tüm organizasyonlar için son etkinlik kayıtları",
    },
    ("audit.list", "subtitle_recent"): {
        "az": "Son fəaliyyət qeydləri",
        "en": "Recent activity logs",
        "ru": "Последние записи активности",
        "tr": "Son etkinlik kayıtları",
    },
    ("audit.list", "col_time"): {"az": "Vaxt", "en": "Time", "ru": "Время", "tr": "Zaman"},
    ("audit.list", "col_user"): {"az": "İstifadəçi", "en": "User", "ru": "Пользователь", "tr": "Kullanıcı"},
    ("audit.list", "col_action"): {"az": "Əməliyyat", "en": "Action", "ru": "Действие", "tr": "İşlem"},
    ("audit.list", "col_resource"): {"az": "Resurs", "en": "Resource", "ru": "Ресурс", "tr": "Kaynak"},
    ("audit.list", "col_organization"): {
        "az": "Təşkilat",
        "en": "Organization",
        "ru": "Организация",
        "tr": "Organizasyon",
    },
    ("audit.list", "anonymous"): {"az": "Anonim", "en": "Anonymous", "ru": "Аноним", "tr": "Anonim"},
    ("audit.list", "empty"): {
        "az": "Hələ audit qeydi yoxdur.",
        "en": "No audit records yet.",
        "ru": "Записей аудита пока нет.",
        "tr": "Henüz denetim kaydı yok.",
    },
    # ---- common buttons / labels ----
    ("common", "search"): {"az": "Axtar", "en": "Search", "ru": "Поиск", "tr": "Ara"},
    ("common", "search_clear"): {
        "az": "Axtarışı təmizlə",
        "en": "Clear search",
        "ru": "Очистить поиск",
        "tr": "Aramayı temizle",
    },
    ("common", "save"): {"az": "Yadda saxla", "en": "Save", "ru": "Сохранить", "tr": "Kaydet"},
    ("common", "delete"): {"az": "Sil", "en": "Delete", "ru": "Удалить", "tr": "Sil"},
    ("common", "confirm"): {"az": "Təsdiqlə", "en": "Confirm", "ru": "Подтвердить", "tr": "Onayla"},
    ("common", "cancel"): {"az": "Ləğv et", "en": "Cancel", "ru": "Отмена", "tr": "İptal"},
    ("common", "close"): {"az": "Bağla", "en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    ("common", "select_all"): {"az": "Hamısını seç", "en": "Select all", "ru": "Выбрать всё", "tr": "Tümünü seç"},
    ("common", "reject"): {"az": "Rədd et", "en": "Reject", "ru": "Отклонить", "tr": "Reddet"},
    ("common", "resend_code"): {
        "az": "Kodu yenidən göndər",
        "en": "Resend code",
        "ru": "Отправить код повторно",
        "tr": "Kodu yeniden gönder",
    },
    # ---- student org management ----
    ("accounts.student_org", "students_title"): {
        "az": "Təşkilat tələbələri",
        "en": "Organization students",
        "ru": "Студенты организации",
        "tr": "Organizasyon öğrencileri",
    },
    ("accounts.student_org", "col_user"): {"az": "İstifadəçi", "en": "User", "ru": "Пользователь", "tr": "Kullanıcı"},
    ("accounts.student_org", "col_username"): {
        "az": "İstifadəçi adı",
        "en": "Username",
        "ru": "Имя пользователя",
        "tr": "Kullanıcı adı",
    },
    ("accounts.student_org", "col_email"): {"az": "E-poçt", "en": "Email", "ru": "Эл. почта", "tr": "E-posta"},
    ("accounts.student_org", "col_action"): {"az": "Əməliyyat", "en": "Action", "ru": "Действие", "tr": "İşlem"},
    ("accounts.student_org", "col_selected_org"): {
        "az": "Seçilmiş təşkilat",
        "en": "Selected organization",
        "ru": "Выбранная организация",
        "tr": "Seçilen organizasyon",
    },
    ("accounts.student_org", "col_message"): {"az": "Mesaj", "en": "Message", "ru": "Сообщение", "tr": "Mesaj"},
    ("accounts.student_org", "col_status_note"): {
        "az": "Status/Qeyd",
        "en": "Status/Note",
        "ru": "Статус/Примечание",
        "tr": "Durum/Not",
    },
    ("accounts.student_org", "col_role_type"): {
        "az": "Rol növü",
        "en": "Role type",
        "ru": "Тип роли",
        "tr": "Rol türü",
    },
    ("accounts.student_org", "col_sender"): {"az": "Göndərən", "en": "Sender", "ru": "Отправитель", "tr": "Gönderen"},
    ("accounts.student_org", "col_request_date"): {
        "az": "Müraciət tarixi",
        "en": "Request date",
        "ru": "Дата заявки",
        "tr": "Başvuru tarihi",
    },
    ("accounts.student_org", "remove_from_org"): {
        "az": "Təşkilatdan uzaqlaşdır",
        "en": "Remove from organization",
        "ru": "Удалить из организации",
        "tr": "Organizasyondan çıkar",
    },
    ("accounts.student_org", "no_students"): {
        "az": "Tələbə tapılmadı.",
        "en": "No students found.",
        "ru": "Студенты не найдены.",
        "tr": "Öğrenci bulunamadı.",
    },
    ("accounts.student_org", "pending_title"): {
        "az": "Təsdiq gözləyən tələbələr",
        "en": "Students pending approval",
        "ru": "Студенты, ожидающие подтверждения",
        "tr": "Onay bekleyen öğrenciler",
    },
    ("accounts.student_org", "pending_desc"): {
        "az": 'Qeydiyyat zamanı bu təşkilatı seçən tələbələri buradan tək-tək və ya hamısını seçib əlavə edə bilərsiniz. Artıq başqa təşkilata qəbul olanların müraciəti "Bağlanıb" kimi görünəcək.',
        "en": 'Here you can add students who selected this organization at sign-up, individually or all at once. Requests of those already accepted by another organization will appear as "Closed".',
        "ru": "Здесь вы можете добавить студентов, выбравших эту организацию при регистрации, по одному или всех сразу. Заявки тех, кто уже принят в другую организацию, отобразятся как «Закрыто».",
        "tr": 'Kayıt sırasında bu organizasyonu seçen öğrencileri buradan tek tek veya hepsini seçerek ekleyebilirsiniz. Başka bir organizasyona kabul edilmiş olanların başvurusu "Kapatıldı" olarak görünür.',
    },
    ("accounts.student_org", "pending_search_ph"): {
        "az": "Təsdiq gözləyən tələbə axtar...",
        "en": "Search students pending approval...",
        "ru": "Поиск студентов, ожидающих подтверждения...",
        "tr": "Onay bekleyen öğrenci ara...",
    },
    ("accounts.student_org", "add_selected"): {
        "az": "Seçilənləri təşkilata əlavə et",
        "en": "Add selected to organization",
        "ru": "Добавить выбранных в организацию",
        "tr": "Seçilenleri organizasyona ekle",
    },
    ("accounts.student_org", "add_selected_count"): {
        "az": "Seçilənləri təşkilata əlavə et ({count} seçildi)",
        "en": "Add selected to organization ({count} selected)",
        "ru": "Добавить выбранных в организацию (выбрано: {count})",
        "tr": "Seçilenleri organizasyona ekle ({count} seçildi)",
    },
    ("accounts.student_org", "min_one_student"): {
        "az": "Ən az 1 tələbə seçin",
        "en": "Select at least 1 student",
        "ru": "Выберите хотя бы 1 студента",
        "tr": "En az 1 öğrenci seçin",
    },
    ("accounts.student_org", "min_one"): {
        "az": "Ən az 1 seçin",
        "en": "Select at least 1",
        "ru": "Выберите хотя бы 1",
        "tr": "En az 1 seçin",
    },
    ("accounts.student_org", "delete_selected"): {
        "az": "Seçilənləri sil",
        "en": "Delete selected",
        "ru": "Удалить выбранных",
        "tr": "Seçilenleri sil",
    },
    ("accounts.student_org", "delete_selected_count"): {
        "az": "Seçilənləri sil ({count} seçildi)",
        "en": "Delete selected ({count} selected)",
        "ru": "Удалить выбранных (выбрано: {count})",
        "tr": "Seçilenleri sil ({count} seçildi)",
    },
    ("accounts.student_org", "add_to_org"): {
        "az": "Təşkilata əlavə et",
        "en": "Add to organization",
        "ru": "Добавить в организацию",
        "tr": "Organizasyona ekle",
    },
    ("accounts.student_org", "no_pending"): {
        "az": "Təsdiq gözləyən tələbə yoxdur.",
        "en": "No students pending approval.",
        "ru": "Нет студентов, ожидающих подтверждения.",
        "tr": "Onay bekleyen öğrenci yok.",
    },
    ("accounts.student_org", "unassigned_title"): {
        "az": "Təşkilata bağlı olmayan tələbələr",
        "en": "Students not linked to an organization",
        "ru": "Студенты без организации",
        "tr": "Organizasyona bağlı olmayan öğrenciler",
    },
    ("accounts.student_org", "unassigned_desc"): {
        "az": "Təşkilat seçmədən qeydiyyatdan keçən tələbələrə dəvət göndərin. Tələbə kabinetində qəbul etdikdən sonra təşkilata qoşulacaq.",
        "en": "Send invitations to students who signed up without selecting an organization. They join the organization after accepting the invitation in their account.",
        "ru": "Отправьте приглашения студентам, которые зарегистрировались без выбора организации. Они присоединятся после принятия приглашения в личном кабинете.",
        "tr": "Organizasyon seçmeden kayıt olan öğrencilere davet gönderin. Öğrenci kendi hesabında kabul ettikten sonra organizasyona katılır.",
    },
    ("accounts.student_org", "unassigned_search_ph"): {
        "az": "Təşkilatsız tələbə axtar...",
        "en": "Search students without an organization...",
        "ru": "Поиск студентов без организации...",
        "tr": "Organizasyonsuz öğrenci ara...",
    },
    ("accounts.student_org", "invite_selected"): {
        "az": "Seçilənlərə dəvət et",
        "en": "Invite selected",
        "ru": "Пригласить выбранных",
        "tr": "Seçilenleri davet et",
    },
    ("accounts.student_org", "invite_selected_count"): {
        "az": "Seçilənlərə dəvət et ({count} seçildi)",
        "en": "Invite selected ({count} selected)",
        "ru": "Пригласить выбранных (выбрано: {count})",
        "tr": "Seçilenleri davet et ({count} seçildi)",
    },
    ("accounts.student_org", "invite"): {"az": "Dəvət et", "en": "Invite", "ru": "Пригласить", "tr": "Davet et"},
    ("accounts.student_org", "no_invite_targets"): {
        "az": "Dəvət göndəriləcək tələbə tapılmadı.",
        "en": "No students found to invite.",
        "ru": "Не найдено студентов для приглашения.",
        "tr": "Davet edilecek öğrenci bulunamadı.",
    },
    ("accounts.student_org", "sent_invites_title"): {
        "az": "Göndərilmiş dəvətlər",
        "en": "Sent invitations",
        "ru": "Отправленные приглашения",
        "tr": "Gönderilen davetler",
    },
    ("accounts.student_org", "sent_invites_desc"): {
        "az": "Hələ qəbul edilməmiş dəvətləri buradan tək-tək və ya toplu şəkildə geri çəkə bilərsiniz.",
        "en": "You can revoke invitations that have not been accepted yet, individually or in bulk.",
        "ru": "Вы можете отозвать ещё не принятые приглашения по одному или массово.",
        "tr": "Henüz kabul edilmemiş davetleri buradan tek tek veya toplu olarak geri çekebilirsiniz.",
    },
    ("accounts.student_org", "sent_invite_search_ph"): {
        "az": "Göndərilən dəvət axtar...",
        "en": "Search sent invitations...",
        "ru": "Поиск отправленных приглашений...",
        "tr": "Gönderilen davet ara...",
    },
    ("accounts.student_org", "revoke_selected"): {
        "az": "Seçilənləri geri çək",
        "en": "Revoke selected",
        "ru": "Отозвать выбранные",
        "tr": "Seçilenleri geri çek",
    },
    ("accounts.student_org", "revoke_selected_count"): {
        "az": "Seçilənləri geri çək ({count} seçildi)",
        "en": "Revoke selected ({count} selected)",
        "ru": "Отозвать выбранные (выбрано: {count})",
        "tr": "Seçilenleri geri çek ({count} seçildi)",
    },
    ("accounts.student_org", "revoke"): {"az": "Geri çək", "en": "Revoke", "ru": "Отозвать", "tr": "Geri çek"},
    ("accounts.student_org", "no_active_invite"): {
        "az": "Geri çəkiləcək aktiv dəvət yoxdur.",
        "en": "No active invitations to revoke.",
        "ru": "Нет активных приглашений для отзыва.",
        "tr": "Geri çekilecek aktif davet yok.",
    },
    ("accounts.student_org", "ts_requests_title"): {
        "az": "Müəllim / İşçi müraciətləri",
        "en": "Teacher / Staff requests",
        "ru": "Заявки преподавателей / сотрудников",
        "tr": "Öğretmen / Personel başvuruları",
    },
    ("accounts.student_org", "ts_requests_desc"): {
        "az": "Bu bölmədə müəllim və ya işçi olaraq qeydiyyatdan keçib bu təşkilatı seçən istifadəçilərin müraciətlərini görə, təsdiqləyə və ya rədd edə bilərsiniz.",
        "en": "In this section you can view, approve or reject requests from users who signed up as a teacher or staff member and selected this organization.",
        "ru": "В этом разделе вы можете просматривать, подтверждать или отклонять заявки пользователей, которые зарегистрировались как преподаватель или сотрудник и выбрали эту организацию.",
        "tr": "Bu bölümde öğretmen veya personel olarak kayıt olup bu organizasyonu seçen kullanıcıların başvurularını görüntüleyebilir, onaylayabilir veya reddedebilirsiniz.",
    },
    ("accounts.student_org", "ts_search_ph"): {
        "az": "Müəllim / işçi axtar...",
        "en": "Search teacher / staff...",
        "ru": "Поиск преподавателя / сотрудника...",
        "tr": "Öğretmen / personel ara...",
    },
    ("accounts.student_org", "role_teacher"): {
        "az": "Müəllim",
        "en": "Teacher",
        "ru": "Преподаватель",
        "tr": "Öğretmen",
    },
    ("accounts.student_org", "role_staff"): {"az": "İşçi", "en": "Staff", "ru": "Сотрудник", "tr": "Personel"},
    ("accounts.student_org", "role_student"): {"az": "Tələbə", "en": "Student", "ru": "Студент", "tr": "Öğrenci"},
    ("accounts.student_org", "approve"): {"az": "Təsdiqlə", "en": "Approve", "ru": "Подтвердить", "tr": "Onayla"},
    ("accounts.student_org", "no_ts_requests"): {
        "az": "Təsdiq gözləyən müəllim / işçi müraciəti yoxdur.",
        "en": "No teacher / staff requests pending approval.",
        "ru": "Нет заявок преподавателей / сотрудников, ожидающих подтверждения.",
        "tr": "Onay bekleyen öğretmen / personel başvurusu yok.",
    },
    ("accounts.student_org", "revoke_invite"): {
        "az": "Dəvəti geri çək",
        "en": "Revoke invitation",
        "ru": "Отозвать приглашение",
        "tr": "Daveti geri çek",
    },
    ("accounts.student_org", "revoke_confirm"): {
        "az": "Seçilən dəvətləri geri çəkmək istədiyinizi təsdiqləyin.",
        "en": "Confirm that you want to revoke the selected invitations.",
        "ru": "Подтвердите, что хотите отозвать выбранные приглашения.",
        "tr": "Seçilen davetleri geri çekmek istediğinizi onaylayın.",
    },
    ("accounts.student_org", "remove_lead"): {
        "az": "Aşağıdakı istifadəçini təşkilatdan uzaqlaşdırmaq istədiyinizi təsdiqləyin.",
        "en": "Confirm that you want to remove the following user from the organization.",
        "ru": "Подтвердите, что хотите удалить указанного пользователя из организации.",
        "tr": "Aşağıdaki kullanıcıyı organizasyondan çıkarmak istediğinizi onaylayın.",
    },
    ("accounts.student_org", "field_name"): {"az": "Ad", "en": "Name", "ru": "Имя", "tr": "Ad"},
    ("accounts.student_org", "field_org"): {
        "az": "Təşkilat",
        "en": "Organization",
        "ru": "Организация",
        "tr": "Organizasyon",
    },
    ("accounts.student_org", "field_role_change"): {
        "az": "Dəyişəcək rol",
        "en": "Role to change",
        "ru": "Изменяемая роль",
        "tr": "Değişecek rol",
    },
    ("accounts.student_org", "remove_reason_label"): {
        "az": "Uzaqlaşdırma səbəbi (məcburi)",
        "en": "Removal reason (required)",
        "ru": "Причина удаления (обязательно)",
        "tr": "Çıkarma nedeni (zorunlu)",
    },
    ("accounts.student_org", "remove_reason_ph"): {
        "az": "Uzaqlaşdırma səbəbi...",
        "en": "Removal reason...",
        "ru": "Причина удаления...",
        "tr": "Çıkarma nedeni...",
    },
    ("accounts.student_org", "add_lead"): {
        "az": "Seçilən istifadəçi(lər)i təşkilata əlavə etməyi təsdiqləyin.",
        "en": "Confirm adding the selected user(s) to the organization.",
        "ru": "Подтвердите добавление выбранного(ых) пользователя(ей) в организацию.",
        "tr": "Seçilen kullanıcı(lar)ı organizasyona eklemeyi onaylayın.",
    },
    ("accounts.student_org", "invite_lead"): {
        "az": "Seçilən istifadəçi(lər)ə dəvət göndərməyi təsdiqləyin.",
        "en": "Confirm sending an invitation to the selected user(s).",
        "ru": "Подтвердите отправку приглашения выбранному(ым) пользователю(ям).",
        "tr": "Seçilen kullanıcı(lar)a davet göndermeyi onaylayın.",
    },
    ("accounts.student_org", "no_active_org"): {
        "az": "Aktiv təşkilat tapılmadı.",
        "en": "No active organization found.",
        "ru": "Активная организация не найдена.",
        "tr": "Aktif organizasyon bulunamadı.",
    },
    ("accounts.student_org", "student_search_ph"): {
        "az": "Tələbə axtar...",
        "en": "Search students...",
        "ru": "Поиск студентов...",
        "tr": "Öğrenci ara...",
    },
    ("accounts.student_org", "this_user"): {
        "az": "Bu istifadəçi",
        "en": "This user",
        "ru": "Этот пользователь",
        "tr": "Bu kullanıcı",
    },
    ("accounts.student_org", "revoke_single_suffix"): {
        "az": "üçün göndərilmiş dəvəti geri çəkmək istədiyinizi təsdiqləyin.",
        "en": "— confirm that you want to revoke the invitation sent.",
        "ru": "— подтвердите, что хотите отозвать отправленное приглашение.",
        "tr": "— gönderilen daveti geri çekmek istediğinizi onaylayın.",
    },
    ("accounts.student_org", "revoke_selected_confirm"): {
        "az": "Seçilmiş dəvətləri geri çəkmək istədiyinizi təsdiqləyin.",
        "en": "Confirm that you want to revoke the selected invitations.",
        "ru": "Подтвердите, что хотите отозвать выбранные приглашения.",
        "tr": "Seçilen davetleri geri çekmek istediğinizi onaylayın.",
    },
    ("accounts.student_org", "selected_invite_count"): {
        "az": "Seçilən dəvət sayı",
        "en": "Selected invitations",
        "ru": "Выбрано приглашений",
        "tr": "Seçilen davet sayısı",
    },
    ("accounts.student_org", "select_one_invite_first"): {
        "az": "Əvvəlcə ən azı bir dəvət seçin.",
        "en": "Select at least one invitation first.",
        "ru": "Сначала выберите хотя бы одно приглашение.",
        "tr": "Önce en az bir davet seçin.",
    },
    ("accounts.student_org", "confirm_disabled_hint"): {
        "az": "Bu halda təsdiqlə düyməsi deaktiv edilir.",
        "en": "In this case the confirm button is disabled.",
        "ru": "В этом случае кнопка подтверждения отключена.",
        "tr": "Bu durumda onay düğmesi devre dışı bırakılır.",
    },
    ("accounts.student_org", "add_lead_single"): {
        "az": "İstifadəçini təşkilata əlavə etməyi təsdiqləyin.",
        "en": "Confirm adding the user to the organization.",
        "ru": "Подтвердите добавление пользователя в организацию.",
        "tr": "Kullanıcıyı organizasyona eklemeyi onaylayın.",
    },
    ("accounts.student_org", "selected_user_count"): {
        "az": "Seçilən istifadəçi sayı",
        "en": "Selected users",
        "ru": "Выбрано пользователей",
        "tr": "Seçilen kullanıcı sayısı",
    },
    ("accounts.student_org", "invite_lead_single"): {
        "az": "İstifadəçiyə dəvət göndərməyi təsdiqləyin.",
        "en": "Confirm sending an invitation to the user.",
        "ru": "Подтвердите отправку приглашения пользователю.",
        "tr": "Kullanıcıya davet göndermeyi onaylayın.",
    },
    # ---- superadmin org features ----
    ("accounts.superadmin_org_features", "col_org"): {
        "az": "Təşkilat",
        "en": "Organization",
        "ru": "Организация",
        "tr": "Organizasyon",
    },
    ("accounts.superadmin_org_features", "col_type"): {"az": "Növ", "en": "Type", "ru": "Тип", "tr": "Tür"},
    ("accounts.superadmin_org_features", "col_owner"): {"az": "Sahib", "en": "Owner", "ru": "Владелец", "tr": "Sahip"},
    ("accounts.superadmin_org_features", "col_features"): {
        "az": "Xüsusiyyətlər",
        "en": "Features",
        "ru": "Возможности",
        "tr": "Özellikler",
    },
    ("accounts.superadmin_org_features", "no_org"): {
        "az": "Təşkilat tapılmadı.",
        "en": "No organizations found.",
        "ru": "Организации не найдены.",
        "tr": "Organizasyon bulunamadı.",
    },
    ("accounts.superadmin_org_features", "title"): {
        "az": "Təşkilat xüsusiyyətləri",
        "en": "Organization features",
        "ru": "Возможности организации",
        "tr": "Organizasyon özellikleri",
    },
    ("accounts.superadmin_org_features", "intro"): {
        "az": "Buradan təşkilatlara aid yoxlama görünürlüyü xüsusiyyətlərini ayrıca açıb-bağlaya bilərsiniz. Xüsusiyyət aktiv olanda müəllim tələbə adını anonim pəncərə bitmədən də görür, lakin bal redaktəsi vaxtı olduğu kimi qalır.",
        "en": "Here you can enable or disable review-visibility features for each organization. When enabled, the teacher can see the student's name even before the anonymous window ends, while the grade-editing window stays the same.",
        "ru": "Здесь вы можете включать или отключать функции видимости проверки для каждой организации. Когда функция включена, преподаватель видит имя студента ещё до окончания анонимного окна, при этом окно редактирования оценки остаётся прежним.",
        "tr": "Buradan her organizasyon için değerlendirme görünürlüğü özelliklerini ayrı ayrı açıp kapatabilirsiniz. Özellik etkinleştirildiğinde öğretmen, anonim pencere bitmeden de öğrencinin adını görür; not düzenleme süresi ise aynı kalır.",
    },
    ("accounts.superadmin_org_features", "flags_title"): {
        "az": "Yoxlama görünürlüyü bayraqları",
        "en": "Review visibility flags",
        "ru": "Флаги видимости проверки",
        "tr": "Değerlendirme görünürlüğü bayrakları",
    },
    ("accounts.superadmin_org_features", "code"): {"az": "Kod", "en": "Code", "ru": "Код", "tr": "Kod"},
    ("accounts.superadmin_org_features", "active_name_visible"): {
        "az": "Aktivdir, ad görünür",
        "en": "Active, name visible",
        "ru": "Активно, имя видно",
        "tr": "Aktif, ad görünür",
    },
    ("accounts.superadmin_org_features", "default_anonymity"): {
        "az": "Standart anonimlik aktivdir",
        "en": "Default anonymity is active",
        "ru": "Действует анонимность по умолчанию",
        "tr": "Varsayılan anonimlik etkin",
    },
    ("accounts.superadmin_org_features", "restore_anonymous"): {
        "az": "Anonim yoxlamanı qaytar",
        "en": "Restore anonymous review",
        "ru": "Вернуть анонимную проверку",
        "tr": "Anonim değerlendirmeye dön",
    },
    ("accounts.superadmin_org_features", "activate"): {
        "az": "Aktiv et",
        "en": "Activate",
        "ru": "Активировать",
        "tr": "Etkinleştir",
    },
    # ---- blog create question ----
    ("blog.create_question", "title"): {
        "az": "Sual yarat",
        "en": "Create Question",
        "ru": "Создать вопрос",
        "tr": "Soru oluştur",
    },
    ("blog.create_question", "subtitle"): {
        "az": "Yeni sual yaradın və kimlərin görə biləcəyini seçin.",
        "en": "Create a new question and choose who can see it.",
        "ru": "Создайте новый вопрос и выберите, кто его увидит.",
        "tr": "Yeni bir soru oluşturun ve kimlerin görebileceğini seçin.",
    },
    ("blog.create_question", "save"): {
        "az": "Sualı yadda saxla",
        "en": "Save question",
        "ru": "Сохранить вопрос",
        "tr": "Soruyu kaydet",
    },
    ("blog.create_question", "my_questions"): {
        "az": "Suallarım",
        "en": "My Questions",
        "ru": "Мои вопросы",
        "tr": "Sorularım",
    },
    # ---- admin verify otp ----
    ("admin.verify_otp", "description"): {
        "az": "Admin panelə keçid yalnız OTP təsdiqindən sonra açılır. E-poçt ünvanınıza göndərilən 6 rəqəmli kodu daxil edin.",
        "en": "Access to the admin panel is granted only after OTP verification. Enter the 6-digit code sent to your email address.",
        "ru": "Доступ к панели администратора открывается только после подтверждения OTP. Введите 6-значный код, отправленный на ваш адрес эл. почты.",
        "tr": "Yönetici paneline erişim yalnızca OTP doğrulamasından sonra açılır. E-posta adresinize gönderilen 6 haneli kodu girin.",
    },
    ("admin.verify_otp", "expiry"): {
        "az": "Kod {minutes} dəqiqə etibarlıdır.",
        "en": "The code is valid for {minutes} minutes.",
        "ru": "Код действителен {minutes} минут.",
        "tr": "Kod {minutes} dakika geçerlidir.",
    },
    ("admin.verify_otp", "messages_label"): {
        "az": "Bildirişlər",
        "en": "Notifications",
        "ru": "Уведомления",
        "tr": "Bildirimler",
    },
    ("admin.verify_otp", "errors_label"): {
        "az": "Xəta mesajları",
        "en": "Error messages",
        "ru": "Сообщения об ошибках",
        "tr": "Hata mesajları",
    },
    ("admin.verify_otp", "otp_errors_label"): {
        "az": "OTP xətaları",
        "en": "OTP errors",
        "ru": "Ошибки OTP",
        "tr": "OTP hataları",
    },
    ("admin.verify_otp", "retry_note"): {
        "az": "Təkrar cəhd etməzdən əvvəl {seconds} saniyə gözləyin.",
        "en": "Please wait {seconds} seconds before trying again.",
        "ru": "Подождите {seconds} секунд перед повторной попыткой.",
        "tr": "Tekrar denemeden önce {seconds} saniye bekleyin.",
    },
    ("admin.verify_otp", "submit"): {"az": "Təsdiqlə", "en": "Confirm", "ru": "Подтвердить", "tr": "Onayla"},
    ("admin.verify_otp", "resend"): {
        "az": "Kodu yenidən göndər",
        "en": "Resend code",
        "ru": "Отправить код повторно",
        "tr": "Kodu yeniden gönder",
    },
}


# ---------------------------------------------------------------------------
# Template replacements: (relative_path) -> list of (old, new)
# ---------------------------------------------------------------------------
def t(key, ctx):
    return '{%% trans "%s" context "%s" %%}' % (key, ctx)


TEMPLATE_EDITS = {
    "apps/blog/templates/blog/create_question.html": [
        (
            "{% block title %}Create Question{% endblock %}",
            "{% block title %}" + t("title", "blog.create_question") + "{% endblock %}",
        ),
        ('<h1 class="mb-2">Create Question</h1>', '<h1 class="mb-2">' + t("title", "blog.create_question") + "</h1>"),
        (
            '<p class="text-muted mb-0">Yeni sual yaradın və kimlərin görə biləcəyini seçin.</p>',
            '<p class="text-muted mb-0">' + t("subtitle", "blog.create_question") + "</p>",
        ),
        (
            '<button type="submit" class="btn btn-primary">Save Question</button>',
            '<button type="submit" class="btn btn-primary">' + t("save", "blog.create_question") + "</button>",
        ),
        (
            'class="btn btn-outline-secondary">My Questions</a>',
            'class="btn btn-outline-secondary">' + t("my_questions", "blog.create_question") + "</a>",
        ),
    ],
    "templates/admin/verify_otp.html": [
        (
            "Admin panelə keçid yalnız OTP təsdiqindən sonra açılır. Email ünvanınıza göndərilən 6 rəqəmli kodu daxil edin.",
            t("description", "admin.verify_otp"),
        ),
        (
            "Kod {{ otp_expiry_minutes }} dəqiqə etibarlıdır.",
            '{% blocktrans context "admin.verify_otp" with minutes=otp_expiry_minutes %}The code is valid for {{ minutes }} minutes.{% endblocktrans %}',
        ),
        ('aria-label="Bildirişlər"', 'aria-label="{% trans "messages_label" context "admin.verify_otp" %}"'),
        ('aria-label="Xəta mesajları"', 'aria-label="{% trans "errors_label" context "admin.verify_otp" %}"'),
        ('aria-label="OTP xətaları"', 'aria-label="{% trans "otp_errors_label" context "admin.verify_otp" %}"'),
        (
            "Təkrar cəhd etməzdən əvvəl {{ retry_after }} saniyə gözləyin.",
            '{% blocktrans context "admin.verify_otp" with seconds=retry_after %}Please wait {{ seconds }} seconds before trying again.{% endblocktrans %}',
        ),
        (">Təsdiqlə</button>", ">" + t("submit", "admin.verify_otp") + "</button>"),
        (">Kodu yenidən göndər</button>", ">" + t("resend", "admin.verify_otp") + "</button>"),
    ],
}

# verify_otp.html uses {% load static %} only - needs i18n loaded.
LOAD_I18N_FIX = {
    "templates/admin/verify_otp.html": ("{% load static %}", "{% load static i18n %}"),
}


def apply_template_edits():
    report = []
    # ensure i18n loaded where needed
    for rel, (old, new) in LOAD_I18N_FIX.items():
        p = os.path.join(BASE, rel)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        if "{% load i18n" not in content and "i18n" not in content.split("\n")[0]:
            if old in content:
                content = content.replace(old, new, 1)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                report.append(f"  + load i18n -> {rel}")
    for rel, edits in TEMPLATE_EDITS.items():
        p = os.path.join(BASE, rel)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        orig = content
        for old, new in edits:
            if old in content:
                content = content.replace(old, new)
            elif new not in content:
                report.append(f"  ! NOT FOUND in {rel}: {old[:60]!r}")
        if content != orig:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            report.append(f"  ~ edited {rel}")
    return report


def po_has_entry(content, ctx, key):
    # match an entry block with this msgctxt + msgid
    pat = re.compile(r'msgctxt "%s"\nmsgid "%s"\n' % (re.escape(ctx), re.escape(key)))
    return bool(pat.search(content))


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def append_po_entries():
    report = []
    for lang in LOCALES:
        p = po_path(lang)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        additions = []
        for (ctx, key), trans in CATALOG.items():
            if po_has_entry(content, ctx, key):
                continue
            msgstr = trans.get(lang, trans["en"])
            additions.append('\nmsgctxt "%s"\nmsgid "%s"\nmsgstr "%s"\n' % (esc(ctx), esc(key), esc(msgstr)))
        if additions:
            if not content.endswith("\n"):
                content += "\n"
            content += "".join(additions)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            report.append(f"  + {lang}: appended {len(additions)} entries")
        else:
            report.append(f"  = {lang}: nothing to append")
    return report


if __name__ == "__main__":
    print("== Template edits ==")
    for line in apply_template_edits():
        print(line)
    print("== .po appends ==")
    for line in append_po_entries():
        print(line)
    print("Done.")
