"""View-as SİYASƏT datası — hansı marşrut, hansı rol, hansı hədəf.

`view_as.py` bu siyasəti TƏTBİQ edir; burada isə yalnız siyasətin özü saxlanılır.
Bölgünün səbəbi praktikdir: siyasət siyahıları (imtahan əməliyyatları, mutasiya
edən GET-lər, qadağan olunmuş hədəf rolları) tez-tez dəyişir və hər dəyişiklik
servis məntiqini oxumağı çətinləşdirirdi; modul da ölçü büdcəsini keçmişdi.

Bütün adlar `view_as`-dan re-export olunur — mövcud importlar qırılmır.
"""

from ..models import ProfileRole

#: İmtahan Mərkəzinin LIMITED rejimdə YAZA bildiyi marşrutlar.
#:
#: Siyahı təxminlə deyil, layihənin BÜTÜN mutasiya marşrutlarının (128 ədəd)
#: təsnifatından çıxarılıb: hər marşrutun view-u oxunub, sonra ayrıca əks-yoxlama
#: (red team) keçidində «imtahandan kənar akademik nəticəyə, HR/şəxsi məlumata
#: və ya rol/icazəyə toxunanlar» geri endirilib. Təsnifat arxivi:
#: ``docs/audits/2026-08-emsarena-tam-audit/faza6-view-as-marsrut-tesnifati.json``.
#:
#: Siyahıya DAXİL EDİLMƏYƏNLƏRDƏN bilinməli olanlar:
#:  * ``exams:exam_center_ticket_remove`` — tələbəni imtahandan çıxarır və
#:    ``sync_attempt_to_journal`` körpüsü ilə jurnala 0 (F) yazır; bu, imtahan
#:    əməliyyatı deyil, akademik nəticədir.
#:  * ``accounts:exam_chance`` — final biletinin proktorinq sübutunu (removed_by,
#:    removal_reason, reconnect_count) snapshot-suz silir.
#:  * ``exams:question_submission_*`` (müəllim tərəfi) — göndərişi qəbul edən
#:    marşrutla birlikdə verilsə, eyni aktor həm göndərişi uydurar, həm qəbul edər.
EXAM_OPERATION_URL_NAMES = frozenset(
    {
        "exams:add_exam_question",
        "exams:ai_generate_bank_questions",
        "exams:ai_generate_question_bank",
        "exams:bank_question_add",
        "exams:bank_question_edit",
        "exams:create_exam",
        "exams:delete_exam",
        "exams:delete_exam_question",
        "exams:duplicate_exam",
        "exams:edit_exam",
        "exams:edit_exam_question",
        "exams:exam_bank_picker",
        "exams:exam_center_room_end_all",
        "exams:exam_center_room_open_all",
        "exams:exam_center_room_start_all",
        "exams:exam_center_session_cancel",
        "exams:exam_center_session_end",
        "exams:exam_center_session_open_entry",
        "exams:exam_center_session_start",
        "exams:exam_center_ticket_readmit",
        "exams:exam_center_ticket_reentry",
        "exams:exam_center_ticket_resume",
        "exams:exam_center_ticket_seat",
        "exams:exam_language_manager",
        "exams:grant_extra_attempt",
        "exams:grant_extra_attempt_group",
        "exams:permanent_delete_exam",
        "exams:process_question_bank",
        "exams:question_bank_bulk_add",
        "exams:question_bank_detail",
        "exams:question_bank_list",
        "exams:question_bank_update",
        "exams:question_submission_decide",
        "exams:restore_exam",
        "exams:start_text_extraction",
        "exams:teacher_questions_bank",
        "exams:test_question_bank",
        "exams:toggle_exam_active",
        "exams:toggle_exam_archive",
        "exams:toggle_exam_results_visibility",
    }
)

#: İKT Rəhbərinin LIMITED rejimdə yaza bildiyi marşrutlar — QƏSDƏN BOŞ.
#:
#: Qayda «texniki dəstək və AÇIQ ŞƏKİLDƏ İCAZƏ VERİLMİŞ sistem əməliyyatları»
#: deyir. Marşrut təsnifatında İKT üçün namizəd olan iki axın
#: (``registrar:correction_apply`` / ``correction_delete``) əks-yoxlamada
#: rədd olundu: hər ikisi jurnal balını və davamiyyəti dəyişir (yəni imtahandan
#: kənar akademik nəticədir), üstəlik impersonasiya altında düzəliş HƏDƏFİN
#: adına və imzası ilə yazılır — sənədli düzəlişin bütün zəmanəti itir.
#: İKT Rəhbəri bu səlahiyyəti ÖZ kimliyi ilə saxlayır (``journal.correct``);
#: view-as onun üçün müşahidə alətidir.
#:
#: Konkret sistem əməliyyatına icazə lazım olsa, marşrutun adı buraya əlavə
#: olunur — mexanizm hazırdır, sadəcə hələ heç nə icazəli deyil.
IKT_TECHNICAL_URL_NAMES = frozenset()

#: LIMITED rejimdə rol → icazəli yazma marşrutları.
LIMITED_WRITE_ALLOWLIST = {
    ProfileRole.EXAM_CENTER: EXAM_OPERATION_URL_NAMES,
    ProfileRole.EXAM_CENTER_HEAD: EXAM_OPERATION_URL_NAMES,
    ProfileRole.IKT_REHBER: IKT_TECHNICAL_URL_NAMES,
}

#: LIMITED aktor bu rollardakı istifadəçini hədəf seçə bilməz.
#:
#: Qayda: «Heç biri avtomatik olaraq bütün məxfi akademik, HR və ya şəxsi
#: məlumatlara məhdudiyyətsiz giriş almamalıdır.» İdarəçi və HR hesabları məhz
#: o məlumatın toplandığı yerdir.
#:
#: DİQQƏT — bu siyahı ƏL İLƏ YAZILMIR. Əvvəllər yazılırdı və beş ad saxlayırdı
#: (org_owner, org_admin, hr, rector, vice_rector). Problem odur ki, «idarəçi
#: kimdir» sualının cavabı BAŞQA YERDƏ verilir: `ProfileRole` istənilən rola
#: `org_admin` aliasını `ADMIN_EQUIVALENT_ROLE_NAMES`-ə görə VƏ ya `level >= 80`
#: şərtinə görə verir. Yəni `department_head` (80), `senior_instructor` (80),
#: `vice_dean` (85) faktiki olaraq org-admin oxu səthinə sahibdir, amma əl ilə
#: yazılmış siyahıda yox idi — imtahan mərkəzi (85) kafedra müdirinə keçib
#: bütün tenant idarəetmə bölmələrini aça bilirdi.
#:
#: İndi siyahı həmin mənbədən TÖRƏDİLİR, ona görə mənbə dəyişəndə burası da
#: dəyişir. Səviyyə şərti isə ayrıca tətbiq olunur (aşağıda), çünki tenant öz
#: adı ilə yeni rol yarada bilər.
LIMITED_FORBIDDEN_TARGET_ROLES = frozenset(ProfileRole.ADMIN_EQUIVALENT_ROLE_NAMES | {ProfileRole.HR})

#: `org_admin` aliasının səviyyə əsaslı verildiyi hədd. `aliases_for_membership_role`
#: ilə eyni mənbədən oxunur.
ADMIN_ALIAS_LEVEL = ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80)

#: GET ilə çağırılsa da SERVER VƏZİYYƏTİNİ dəyişən marşrutlar.
#:
#: View-as qapısı HTTP metoduna bağlı idi (`GET/HEAD/OPTIONS/TRACE` = təhlükəsiz),
#: yəni bu marşrutlar həm rejim yoxlamasından, həm də audit qeydindən qaçırdı:
#: READONLY aktor sadəcə linkə keçməklə İŞLƏYƏN CANLI İMTAHANI bitirə bilirdi
#: (`live_create_session_by_slug` əvvəlcə aktiv sessiyaları `finish_session` edir,
#: sonra yenisini yaradır) və audit-də heç bir iz qalmırdı.
#:
#: Siyahının köhnəlməməsi `apps/accounts/tests/test_view_as.py`-dakı skan testi
#: ilə qorunur: marşrut cədvəlində metod qapısı olmayan YENİ mutasiya edən view
#: peyda olarsa test düşür.
MUTATING_GET_URL_NAMES = frozenset(
    {
        "liveExam:create_session_slug",
    }
)

#: İcazənin tam yenidən yoxlanma intervalı (saniyə). Aralıq sorğularda yalnız
