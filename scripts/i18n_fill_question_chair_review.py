#!/usr/bin/env python3
"""EMSArena i18n — Sual göndərişi → KAFEDRA TƏSDİQİ (question-chair-review)
mətnləri (4 dil). İdempotent.

Mənbə: `docs/audits/2026-09-02/PHASE_QUESTION_CHAIR_APPROVAL.md` §7 +
`scripts/check_i18n_catalogs.py --report` (`source_missing 0 → 125`) tərəfindən
tapılan 125 (ctx, msgid) cütü, ARTı AST/şablon skanerinin GÖRMƏDİYİ 20 cüt:

  * `apps/exams/services/question_chair_review.py` — modul-səviyyəli
    `_EVENT_CTX = "exams.service.question_chair_review"` dəyişəni ilə
    çağırılan 13 `pgettext(_EVENT_CTX, …)`;
  * `apps/exams/views/teacher/submission_chair.py` — `_CTX =
    "exams.view.question_submission.chair"` ilə çağırılan 4
    `pgettext(_CTX, …)`;
  * `apps/accounts/views/profile/_sections/question_chair_review.py::_status_cards`
    — eyni `_CTX = "accounts.profile.question_chair_review"` ilə çağırılan
    statistika kartı etiketlərindən 3-ü («Təsdiqlədiyim», «Düzəliş istənilən»,
    «Ümumi») şablonda TƏKRARLANMIR, ona görə skanerin gördüyü 23-ə əlavədir.

  Səbəb: `scripts/i18n_source_scan.py` AST ilə işləyir və kontekst arqumenti
  literal `str` deyil, DƏYİŞƏN (`_CTX`/`_EVENT_CTX`) olduqda cütü tanımır —
  bax `i18n_fill_ems_ui.py`-dəki eyni xəbərdarlıq. Yoxlanılıb: bu üç faylda
  BAŞQA `pgettext(_CTX, …)` çağırışı yoxdur (əl ilə qrep edilib).

  Cəmi: 125 + 13 + 4 + 3 = 145 yeni (ctx, msgid) cütü.

⚠️ TEXNİKİ KONTEKSTLƏR — AZ identity YANLIŞDIR. Model sahə/seçim/meta və
   icazə kontekstlərində (`exams.model.question_submission.*`,
   `exams.model.question_submission_event.*`,
   `exams.service.access.permission`) mənbə çağırışının İKİNCİ arqumenti
   Azərbaycanca DEYİL — ya xam sahə adı (`chair_unit`, `chair_decision`, …),
   ya da xam icazə açarıdır (`question_submission_chair_review_denied`).
   Mövcud kataloqda bu kontekstlərin BÜTÜN sıra yoldaşları (`reviewer_note`,
   `exam_rooms_manage_superadmin_only`, …) AZ üçün DƏ əl ilə yazılmış həqiqi
   Azərbaycanca mətn daşıyır (yoxlanılıb — bax `AZ_OVERRIDES`); ona görə bu
   fayl da həmin konvensiyanı izləyir və AZ-a `msgid`-i EYNƏN yazmır.

⚠️ PARALEL AGENT TƏHLÜKƏSİZLİYİ: eyni sessiyada başqa bir agent də (dizayn
   handoff üçün) eyni 4 `.po` faylına ƏLAVƏ edə bilər. Ona görə:
     * mövcudluq yoxlaması `polib` ilə aparılır (bax `existing_pairs`);
     * YAZMADAN DƏRHAL ƏVVƏL fayl YENİDƏN oxunur (ən təzə məzmun üzərində
       işlənir — `fill()` daxilində, `existing_pairs()`-dən SONRA);
     * yazma `polib`-in `catalog.save()` metodu ilə DEYİL, xam mətn əlavəsi
       ilə aparılır (bax `i18n_fill_ems_ui.py`) — çünki `save()` BÜTÜN
       kataloqu öz `wrapwidth`-i ilə yenidən serializasiya edir və mövcud
       girişlərin sətir bölgüsünü poza bilər. Yalnız ƏLAVƏ olunur — mövcud
       sətirlərə TOXUNULMUR, yenidən sıralanmır, fuzzy flag-lar dəyişdirilmir.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir).

İstifadə:  python scripts/i18n_fill_question_chair_review.py
Sonra:     django-admin compilemessages && python scripts/check_i18n_catalogs.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


# ─────────────────────────────────────────────────────────────────────────────
# accounts.profile.question_chair_review — profil «Sual təsdiqi» bölməsi
# (23 şablondan AST-görünən + 3 `_status_cards` kor nöqtəsi)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_QCHAIR = {
    "Bax və qərar ver": _e("View and decide", "Просмотреть и решить", "Görüntüle ve karar ver"),
    "Başlıq, fənn, qrup və ya müəllim üzrə axtar…": _e(
        "Search by title, subject, group, or teacher…",
        "Поиск по названию, предмету, группе или преподавателю…",
        "Başlık, ders, grup veya öğretmene göre ara…",
    ),
    "Bu şərtlərə uyğun sual dəsti tapılmadı.": _e(
        "No question set matches these filters.",
        "По этим условиям пакет вопросов не найден.",
        "Bu koşullara uyan soru paketi bulunamadı.",
    ),
    "Bütün imtahan növləri": _e("All exam types", "Все виды экзаменов", "Tüm sınav türleri"),
    "Bütün müəllimlər": _e("All teachers", "Все преподаватели", "Tüm öğretmenler"),
    "Düzəliş istənilib": _e("Revision requested", "Запрошена доработка", "Düzeltme istendi"),
    "Filtri təmizlə": _e("Clear filters", "Сбросить фильтры", "Filtreleri temizle"),
    "Filtrlə": _e("Filter", "Фильтровать", "Filtrele"),
    "Kafedra müdiri təyin edilməyib — dekanlığa yönləndirilib": _e(
        "No chair head is assigned — routed to the dean's office",
        "Заведующий кафедрой не назначен — направлено в деканат",
        "Bölüm başkanı atanmamış — dekanlığa yönlendirildi",
    ),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "Müəllimdə": _e("With the teacher", "У преподавателя", "Öğretmende"),
    "Müəllimlərinizin imtahan sual dəstlərini təsdiqləyin — yalnız təsdiqdən sonra İmtahan Mərkəzinə gedir.": _e(
        "Approve your teachers' exam question sets — they reach the Exam Centre only after approval.",
        "Утверждайте пакеты экзаменационных вопросов ваших преподавателей — они попадают в "
        "Экзаменационный центр только после утверждения.",
        "Öğretmenlerinizin sınav soru paketlerini onaylayın — yalnızca onaydan sonra Sınav Merkezine ulaşır.",
    ),
    "Mərkəz baxır": _e("Centre is reviewing", "Центр рассматривает", "Merkez inceliyor"),
    "Mərkəz qəbul etdi": _e("Centre accepted", "Центр принял", "Merkez kabul etti"),
    "Rədd edilib": _e("Rejected", "Отклонено", "Reddedildi"),
    "Status filtri": _e("Status filter", "Фильтр по статусу", "Durum filtresi"),
    "Sual dəstlərində axtar": _e("Search question sets", "Поиск по пакетам вопросов", "Soru paketlerinde ara"),
    "Təmizlə": _e("Clear", "Очистить", "Temizle"),
    "Təsdiq gözləyir": _e("Awaiting approval", "Ожидает утверждения", "Onay bekliyor"),
    "Təsdiq gözləyən sual dəsti yoxdur.": _e(
        "There are no question sets awaiting approval.",
        "Нет пакетов вопросов, ожидающих утверждения.",
        "Onay bekleyen soru paketi yok.",
    ),
    "Təsdiqlənib — mərkəzdə": _e("Approved — at the centre", "Утверждено — в центре", "Onaylandı — merkezde"),
    "«%(title)s» dəstinə bax": _e(
        "View the “%(title)s” set", "Просмотреть пакет «%(title)s»", "“%(title)s” paketini görüntüle"
    ),
    "İmtahan növü": _e("Exam type", "Вид экзамена", "Sınav türü"),
    # `_status_cards()` kor nöqtəsi (bax modul başlığı) — «Təsdiq gözləyir» artıq yuxarıdadır.
    "Təsdiqlədiyim": _e("Approved by me", "Утверждённые мной", "Onayladıklarım"),
    "Düzəliş istənilən": _e("Awaiting revision", "Ожидает доработки", "Düzeltme bekliyor"),
    "Ümumi": _e("Total", "Всего", "Toplam"),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.profile.question_submissions — mövcud «Sual göndərişləri» bölməsinə
# kafedra mərhələsi status pill-ləri
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_QSUBS = {
    "Kafedra düzəliş istəyib": _e(
        "Chair head requested revision", "Заведующий кафедрой запросил доработку", "Bölüm başkanı düzeltme istedi"
    ),
    "Kafedra müdirinə göndərilib": _e(
        "Sent to the chair head", "Отправлено заведующему кафедрой", "Bölüm başkanına gönderildi"
    ),
    "Kafedra qeydi": _e("Chair note", "Примечание кафедры", "Bölüm notu"),
    "Kafedra təsdiqləyib — İmtahan Mərkəzində": _e(
        "Approved by the chair head — at the Exam Centre",
        "Утверждено заведующим кафедрой — в Экзаменационном центре",
        "Bölüm başkanı onayladı — Sınav Merkezinde",
    ),
    "Qaralama": _e("Draft", "Черновик", "Taslak"),
    "Rədd edilib — düzəldib yenidən göndərə bilərsiniz": _e(
        "Rejected — you may revise and resubmit",
        "Отклонено — вы можете исправить и отправить повторно",
        "Reddedildi — düzeltip yeniden gönderebilirsiniz",
    ),
    "Yolu izlə": _e("Track the path", "Отследить путь", "Yolu izle"),
    "İmtahan Mərkəzi baxır": _e(
        "Exam Centre is reviewing", "Экзаменационный центр рассматривает", "Sınav Merkezi inceliyor"
    ),
    "İmtahan Mərkəzi düzəliş istəyib": _e(
        "Exam Centre requested revision", "Экзаменационный центр запросил доработку", "Sınav Merkezi düzeltme istedi"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.notification.question_submission — bildiriş mətnləri (mövcud rədd
# mesajı DƏYİŞİB, yeni kontekst dəsti eyni qalır — bax faza sənədi §7)
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_NOTIFICATION = {
    '"{title}" sual göndərişiniz rədd edildi: {reason}': _e(
        'Your question submission "{title}" was rejected: {reason}',
        "Ваша отправка вопросов «{title}» отклонена: {reason}",
        '"{title}" soru gönderiminiz reddedildi: {reason}',
    ),
    '"{title}" sual göndərişiniz İmtahan Mərkəzi tərəfindən düzəliş üçün qaytarıldı: {reason}': _e(
        'Your question submission "{title}" was returned by the Exam Centre for revision: {reason}',
        "Ваша отправка вопросов «{title}» возвращена Экзаменационным центром на доработку: {reason}",
        '"{title}" soru gönderiminiz Sınav Merkezi tarafından düzeltme için iade edildi: {reason}',
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.service.question_submission.error — mövcud kontekstə əlavə (səbəb
# uzunluğu xətası, kafedra mərhələsi ilə paylaşılır)
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_SERVICE_QSUB_ERROR = {
    "Səbəb ən azı {count} simvol olmalıdır — müəllim nəyi düzəltməli olduğunu bilməlidir.": _e(
        "The reason must be at least {count} characters — the teacher needs to know what to fix.",
        "Причина должна содержать не менее {count} символов — преподаватель должен понимать, что нужно исправить.",
        "Gerekçe en az {count} karakter olmalı — öğretmen neyi düzeltmesi gerektiğini bilmeli.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.template.question_chain — zəncir zolağı + hadisə lenti etiketləri
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_TEMPLATE_QCHAIN = {
    "Dekanlıq təsdiqi": _e("Dean's office approval", "Утверждение деканатом", "Dekanlık onayı"),
    "Düzəldilib kafedraya yenidən göndərildi": _e(
        "Revised and resubmitted to the chair head",
        "Исправлено и повторно отправлено заведующему кафедрой",
        "Düzeltilip bölüm başkanına yeniden gönderildi",
    ),
    "Göndərişin yolu": _e("Submission path", "Путь заявки", "Gönderim yolu"),
    "Kafedra düzəliş istədi": _e(
        "Chair head requested revision", "Заведующий кафедрой запросил доработку", "Bölüm başkanı düzeltme istedi"
    ),
    "Kafedra müdirinə göndərildi": _e(
        "Sent to the chair head", "Отправлено заведующему кафедрой", "Bölüm başkanına gönderildi"
    ),
    "Kafedra rədd etdi": _e("Chair head rejected", "Заведующий кафедрой отклонил", "Bölüm başkanı reddetti"),
    "Kafedra tarixçəsi": _e("Chair history", "История кафедры", "Bölüm geçmişi"),
    "Kafedra təsdiqi": _e("Chair approval", "Утверждение кафедрой", "Bölüm onayı"),
    "Kafedra təsdiqlədi — İmtahan Mərkəzinə göndərildi": _e(
        "Chair head approved — sent to the Exam Centre",
        "Заведующий кафедрой утвердил — отправлено в Экзаменационный центр",
        "Bölüm başkanı onayladı — Sınav Merkezine gönderildi",
    ),
    "Müəllim göndərdi": _e("Teacher submitted", "Преподаватель отправил", "Öğretmen gönderdi"),
    "Qəbul edildi": _e("Accepted", "Принято", "Kabul edildi"),
    "Rədd edildi": _e("Rejected", "Отклонено", "Reddedildi"),
    "Yekun qərar": _e("Final decision", "Итоговое решение", "Nihai karar"),
    "İmtahan Mərkəzi": _e("Exam Centre", "Экзаменационный центр", "Sınav Merkezi"),
    "İmtahan Mərkəzi baxışa götürdü": _e(
        "Exam Centre took it under review",
        "Экзаменационный центр взял на рассмотрение",
        "Sınav Merkezi incelemeye aldı",
    ),
    "İmtahan Mərkəzi düzəliş istədi": _e(
        "Exam Centre requested revision", "Экзаменационный центр запросил доработку", "Sınav Merkezi düzeltme istedi"
    ),
    "İmtahan Mərkəzi qəbul etdi": _e(
        "Exam Centre accepted", "Экзаменационный центр принял", "Sınav Merkezi kabul etti"
    ),
    "İmtahan Mərkəzi rədd etdi": _e("Exam Centre rejected", "Экзаменационный центр отклонил", "Sınav Merkezi reddetti"),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.template.question_chair — kafedra qərar səhifəsi
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_TEMPLATE_QCHAIR = {
    "Bu göndəriş artıq kafedra mərhələsində deyil — qərar dəyişdirilə bilməz.": _e(
        "This submission is no longer at the chair stage — the decision cannot be changed.",
        "Эта заявка больше не на этапе кафедры — решение изменить нельзя.",
        "Bu gönderim artık bölüm aşamasında değil — karar değiştirilemez.",
    ),
    "Bu kafedraya müdir təyin edilmədiyi üçün təsdiq DEKANLIĞA yönləndirilib.": _e(
        "No head is assigned to this chair, so approval has been routed to the DEAN'S OFFICE.",
        "Заведующий на эту кафедру не назначен, поэтому утверждение направлено В ДЕКАНАТ.",
        "Bu bölüme başkan atanmadığından onay DEKANLIĞA yönlendirilmiştir.",
    ),
    "Bu şərtlərə uyğun sual tapılmadı.": _e(
        "No question matches these filters.", "По этим условиям вопрос не найден.", "Bu koşullara uyan soru bulunamadı."
    ),
    "Daha çox yüklənir…": _e("Loading more…", "Загружается ещё…", "Daha fazla yükleniyor…"),
    "Düzəliş istə": _e("Request revision", "Запросить доработку", "Düzeltme iste"),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Kafedra": _e("Department", "Кафедра", "Bölüm"),
    "Kafedra qərarı": _e("Chair decision", "Решение кафедры", "Bölüm kararı"),
    "Kafedra təsdiqi": _e("Chair approval", "Утверждение кафедрой", "Bölüm onayı"),
    "Müəllim nəyi düzəltməlidir? Səbəb ona bildiriş kimi gedəcək.": _e(
        "What should the teacher fix? The reason will be sent to them as a notification.",
        "Что должен исправить преподаватель? Причина будет отправлена ему в виде уведомления.",
        "Öğretmen neyi düzeltmeli? Gerekçe kendisine bildirim olarak gönderilecek.",
    ),
    "Müəllimin qeydi": _e("Teacher's note", "Примечание преподавателя", "Öğretmenin notu"),
    "Növbəyə qayıt": _e("Back to the queue", "Вернуться в очередь", "Sıraya dön"),
    "Rədd et": _e("Reject", "Отклонить", "Reddet"),
    "Rəddin səbəbini yazın — göndəriş İmtahan Mərkəzinə çatmayacaq.": _e(
        "Write the reason for rejection — the submission will not reach the Exam Centre.",
        "Укажите причину отклонения — заявка не попадёт в Экзаменационный центр.",
        "Ret gerekçesini yazın — gönderim Sınav Merkezine ulaşmayacak.",
    ),
    "Sual filtri": _e("Question filter", "Фильтр вопросов", "Soru filtresi"),
    "Sual və ya variant mətnində axtar…": _e(
        "Search question or option text…", "Поиск по тексту вопроса или варианта…", "Soru veya seçenek metninde ara…"
    ),
    "Suallar və xəbərdarlıqlar": _e("Questions and warnings", "Вопросы и предупреждения", "Sorular ve uyarılar"),
    "Suallarda axtar": _e("Search questions", "Поиск по вопросам", "Sorularda ara"),
    "Səbəb": _e("Reason", "Причина", "Neden"),
    "Təmiz": _e("Clean", "Чистые", "Temiz"),
    "Təsdiq et": _e("Approve", "Утвердить", "Onayla"),
    "Təsdiqdən sonra dəst İmtahan Mərkəzinə göndəriləcək. Düzəliş və rədd üçün səbəb məcburidir.": _e(
        "After approval the set will be sent to the Exam Centre. A reason is required for revision or rejection.",
        "После утверждения пакет будет отправлен в Экзаменационный центр. Для доработки или отклонения причина обязательна.",
        "Onaydan sonra paket Sınav Merkezine gönderilecek. Düzeltme ve ret için gerekçe zorunludur.",
    ),
    "Təsdiqlə": _e("Approve", "Утвердить", "Onayla"),
    "Xəbərdarlıq": _e("Warning", "Предупреждение", "Uyarı"),
    "Xətalı": _e("With errors", "С ошибками", "Hatalı"),
    "məs. 3-cü sualda düzgün cavab işarələnməyib, 7-ci sual mövzudan kənardır…": _e(
        "e.g. the correct answer is not marked in question 3, question 7 is off-topic…",
        "напр. в вопросе 3 не отмечен правильный ответ, вопрос 7 не по теме…",
        "örn. 3. soruda doğru cevap işaretlenmemiş, 7. soru konu dışı…",
    ),
    "Ümumi sual sayı": _e("Total number of questions", "Общее число вопросов", "Toplam soru sayısı"),
    "İmtina": _e("Cancel", "Отмена", "Vazgeç"),
    "Ən azı {min} simvol — hazırda {n}.": _e(
        "At least {min} characters — currently {n}.",
        "Минимум {min} символов — сейчас {n}.",
        "En az {min} karakter — şu anda {n}.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.template.question_submission — müəllim tərəfi (mövcud kontekstə əlavə)
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_TEMPLATE_QSUB = {
    "Düzəliş istə": _e("Request revision", "Запросить доработку", "Düzeltme iste"),
    "Düzəliş üçün geri qaytar": _e("Return for revision", "Вернуть на доработку", "Düzeltme için iade et"),
    "Dəst rədd edilir — müəllim istəsə düzəldib yenidən kafedra təsdiqinə göndərə bilər.": _e(
        "The set will be rejected — the teacher may revise and resubmit it for chair approval if they wish.",
        "Пакет будет отклонён — при желании преподаватель может исправить и отправить его на утверждение "
        "кафедрой повторно.",
        "Paket reddedilecek — öğretmen isterse düzeltip bölüm onayına yeniden gönderebilir.",
    ),
    "Kafedra müdirinə göndər": _e("Send to the chair head", "Отправить заведующему кафедрой", "Bölüm başkanına gönder"),
    "Kafedra qeydi": _e("Chair note", "Примечание кафедры", "Bölüm notu"),
    "Kafedra təsdiqinə sual göndər": _e(
        "Send questions for chair approval",
        "Отправить вопросы на утверждение кафедрой",
        "Soruları bölüm onayına gönder",
    ),
    "Müəllim düzəldib yenidən göndərəcək — düzəlişdən sonra dəst TƏKRAR kafedra təsdiqindən keçir.": _e(
        "The teacher will revise and resubmit — after the fix the set goes through chair approval AGAIN.",
        "Преподаватель исправит и отправит повторно — после исправления пакет СНОВА проходит утверждение кафедрой.",
        "Öğretmen düzeltip yeniden gönderecek — düzeltmeden sonra paket TEKRAR bölüm onayından geçer.",
    ),
    "Rədd et": _e("Reject", "Отклонить", "Reddet"),
    "Sualları yazın və ya fayl yükləyin, önizləyin — xəbərdarlıqları görün, sonra kafedra müdirinə göndərin; "
    "təsdiqdən sonra İmtahan Mərkəzinə çatacaq.": _e(
        "Write the questions or upload a file, preview them — check the warnings, then send them to the chair "
        "head; after approval they will reach the Exam Centre.",
        "Введите вопросы или загрузите файл, просмотрите их — проверьте предупреждения, затем отправьте "
        "заведующему кафедрой; после утверждения они попадут в Экзаменационный центр.",
        "Soruları yazın veya dosya yükleyin, önizleyin — uyarıları kontrol edin, ardından bölüm başkanına "
        "gönderin; onaydan sonra Sınav Merkezine ulaşacak.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.view.question_submission.message — mövcud kontekstə əlavə (flash mesajlar)
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_VIEW_QSUB_MESSAGE = {
    "Düzəliş tələbi müəllimə göndərildi — düzəlişdən sonra yenidən kafedradan keçəcək.": _e(
        "The revision request was sent to the teacher — after the fix it will go through the chair again.",
        "Запрос на доработку отправлен преподавателю — после исправления заявка снова пройдёт через кафедру.",
        "Düzeltme talebi öğretmene gönderildi — düzeltmeden sonra tekrar bölümden geçecek.",
    ),
    "Göndəriş kafedra müdirinin təsdiqinə göndərildi ({count} sual, {groups} qrup).": _e(
        "The submission was sent for the chair head's approval ({count} questions, {groups} groups).",
        "Заявка отправлена на утверждение заведующему кафедрой ({count} вопросов, {groups} групп).",
        "Gönderim bölüm başkanının onayına gönderildi ({count} soru, {groups} grup).",
    ),
    "Göndəriş yeniləndi və kafedra müdirinin təsdiqinə təkrar göndərildi.": _e(
        "The submission was updated and resent for the chair head's approval.",
        "Заявка обновлена и повторно отправлена на утверждение заведующему кафедрой.",
        "Gönderim güncellendi ve bölüm başkanının onayına yeniden gönderildi.",
    ),
    "Rədd/düzəliş üçün müəllimə ən azı {count} simvolluq qeyd yazın — nəyi düzəltməlidir.": _e(
        "For a rejection or revision, write the teacher a note of at least {count} characters — what needs "
        "to be fixed.",
        "Для отклонения или доработки напишите преподавателю примечание не менее {count} символов — что "
        "нужно исправить.",
        "Ret/düzeltme için öğretmene en az {count} karakterlik bir not yazın — neyi düzeltmesi gerektiğini "
        "belirtin.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.sidebar — yeni bölmə menyu adı
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_SIDEBAR = {
    "Sual təsdiqi": _e("Question approval", "Утверждение вопросов", "Soru onayı"),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.service.question_chair_review — KOR NÖQTƏ (bax modul başlığı):
# `apps/exams/services/question_chair_review.py` — bildiriş başlıq/mətnləri +
# səbəb xətası, `_EVENT_CTX` dəyişəni ilə çağırılır (AST-ə görünməz)
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_SERVICE_QCHAIR_REVIEW = {
    "Səbəb ən azı {count} simvol olmalıdır — müəllim nəyi düzəltməli olduğunu bilməlidir.": _e(
        "The reason must be at least {count} characters — the teacher needs to know what to fix.",
        "Причина должна содержать не менее {count} символов — преподаватель должен понимать, что нужно исправить.",
        "Gerekçe en az {count} karakter olmalı — öğretmen neyi düzeltmesi gerektiğini bilmeli.",
    ),
    "Kafedra təsdiqli sual göndərişi": _e(
        "Chair-approved question submission", "Отправка вопросов, утверждённая кафедрой", "Bölüm onaylı soru gönderimi"
    ),
    '{teacher} — "{title}" ({subject} · {group}, {count} sual) kafedra tərəfindən təsdiqləndi '
    "və İmtahan Mərkəzinə göndərildi.": _e(
        '{teacher} — "{title}" ({subject} · {group}, {count} questions) was approved by the chair and '
        "sent to the Exam Centre.",
        "{teacher} — «{title}» ({subject} · {group}, {count} вопросов) утверждена кафедрой и отправлена "
        "в Экзаменационный центр.",
        '{teacher} — "{title}" ({subject} · {group}, {count} soru) bölüm tarafından onaylandı ve Sınav '
        "Merkezine gönderildi.",
    ),
    "Sual dəsti kafedra təsdiqini gözləyir": _e(
        "Question set awaiting chair approval",
        "Пакет вопросов ожидает утверждения кафедрой",
        "Soru paketi bölüm onayını bekliyor",
    ),
    '{teacher} "{title}" sual dəstini təsdiqə göndərdi. Kafedra müdiri təyin edilmədiyi üçün '
    "təsdiq DEKANLIĞA yönləndirildi ({subject} · {group}, {count} sual).": _e(
        '{teacher} sent the question set "{title}" for approval. Since no chair head is assigned, '
        "approval was routed to the DEAN'S OFFICE ({subject} · {group}, {count} questions).",
        "{teacher} отправил(а) пакет вопросов «{title}» на утверждение. Так как заведующий кафедрой не "
        "назначен, утверждение направлено В ДЕКАНАТ ({subject} · {group}, {count} вопросов).",
        '{teacher}, "{title}" soru paketini onaya gönderdi. Bölüme başkan atanmadığından onay DEKANLIĞA '
        "yönlendirildi ({subject} · {group}, {count} soru).",
    ),
    '{teacher} "{title}" sual dəstini kafedra təsdiqinə göndərdi ({subject} · {group}, {count} sual).': _e(
        '{teacher} sent the question set "{title}" for chair approval ({subject} · {group}, {count} questions).',
        "{teacher} отправил(а) пакет вопросов «{title}» на утверждение кафедрой ({subject} · {group}, "
        "{count} вопросов).",
        '{teacher}, "{title}" soru paketini bölüm onayına gönderdi ({subject} · {group}, {count} soru).',
    ),
    "Bu göndəriş artıq kafedra mərhələsində deyil — qərar verilə bilməz.": _e(
        "This submission is no longer at the chair stage — a decision cannot be made.",
        "Эта заявка больше не на этапе кафедры — решение принять нельзя.",
        "Bu gönderim artık bölüm aşamasında değil — karar verilemez.",
    ),
    "Kafedra sual dəstinizi təsdiqlədi": _e(
        "The chair approved your question set", "Кафедра утвердила ваш пакет вопросов", "Bölüm soru paketinizi onayladı"
    ),
    '"{title}" sual dəstiniz kafedra tərəfindən təsdiqləndi və İmtahan Mərkəzinə göndərildi.': _e(
        'Your question set "{title}" was approved by the chair and sent to the Exam Centre.',
        "Ваш пакет вопросов «{title}» утверждён кафедрой и отправлен в Экзаменационный центр.",
        '"{title}" soru paketiniz bölüm tarafından onaylandı ve Sınav Merkezine gönderildi.',
    ),
    "Kafedra düzəliş istədi": _e(
        "The chair requested revision", "Кафедра запросила доработку", "Bölüm düzeltme istedi"
    ),
    '"{title}" sual dəstiniz kafedra tərəfindən düzəliş üçün qaytarıldı: {reason}': _e(
        'Your question set "{title}" was returned by the chair for revision: {reason}',
        "Ваш пакет вопросов «{title}» возвращён кафедрой на доработку: {reason}",
        '"{title}" soru paketiniz bölüm tarafından düzeltme için iade edildi: {reason}',
    ),
    "Kafedra sual dəstini rədd etdi": _e(
        "The chair rejected the question set", "Кафедра отклонила пакет вопросов", "Bölüm soru paketini reddetti"
    ),
    '"{title}" sual dəstiniz kafedra tərəfindən rədd edildi: {reason}': _e(
        'Your question set "{title}" was rejected by the chair: {reason}',
        "Ваш пакет вопросов «{title}» отклонён кафедрой: {reason}",
        '"{title}" soru paketiniz bölüm tarafından reddedildi: {reason}',
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# exams.view.question_submission.chair — KOR NÖQTƏ (bax modul başlığı):
# `apps/exams/views/teacher/submission_chair.py::question_submission_chair_decide`
# `_CTX` dəyişəni ilə çağırılır (AST-ə görünməz)
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_VIEW_QSUB_CHAIR = {
    "Sual dəsti təsdiqləndi və İmtahan Mərkəzinə göndərildi.": _e(
        "The question set was approved and sent to the Exam Centre.",
        "Пакет вопросов утверждён и отправлен в Экзаменационный центр.",
        "Soru paketi onaylandı ve Sınav Merkezine gönderildi.",
    ),
    "Düzəliş tələbi müəllimə göndərildi.": _e(
        "The revision request was sent to the teacher.",
        "Запрос на доработку отправлен преподавателю.",
        "Düzeltme talebi öğretmene gönderildi.",
    ),
    "Sual dəsti rədd edildi və müəllimə bildirildi.": _e(
        "The question set was rejected and the teacher was notified.",
        "Пакет вопросов отклонён, преподаватель уведомлён.",
        "Soru paketi reddedildi ve öğretmene bildirildi.",
    ),
    "Yanlış əməliyyat.": _e("Invalid action.", "Некорректное действие.", "Geçersiz işlem."),
}

# ─────────────────────────────────────────────────────────────────────────────
# Texniki kontekstlər — AZ identity YANLIŞDIR (bax modul başlığı). msgid xam
# sahə/seçim/icazə açarıdır; AZ üçün DƏ əl ilə yazılmış həqiqi mətn lazımdır.
# ─────────────────────────────────────────────────────────────────────────────
EXAMS_MODEL_QSUB_FIELD = {
    "chair_unit": _e("Chair unit", "Кафедральное подразделение", "Bölüm birimi"),
    "chair_reviewer": _e("Chair reviewer", "Проверяющий от кафедры", "Bölüm incelemesi yapan"),
    "chair_decision": _e("Chair decision", "Решение кафедры", "Bölüm kararı"),
    "chair_note": _e("Chair note", "Примечание кафедры", "Bölüm notu"),
}
AZ_MODEL_QSUB_FIELD = {
    "chair_unit": "Kafedra vahidi",
    "chair_reviewer": "Kafedra rəyçisi",
    "chair_decision": "Kafedra qərarı",
    "chair_note": "Kafedra qeydi",
}

EXAMS_MODEL_QSUB_STATUS = {
    "draft": _e("Draft", "Черновик", "Taslak"),
    "submitted_to_chair": _e(
        "Submitted to the chair head", "Отправлено заведующему кафедрой", "Bölüm başkanına gönderildi"
    ),
    "chair_revision": _e(
        "Chair head requested revision", "Заведующий кафедрой запросил доработку", "Bölüm başkanı düzeltme istedi"
    ),
    "chair_approved": _e("Approved by the chair head", "Утверждено заведующим кафедрой", "Bölüm başkanı onayladı"),
    "center_review": _e(
        "Under Exam Centre review", "На рассмотрении Экзаменационного центра", "Sınav Merkezi incelemesinde"
    ),
    "center_revision": _e(
        "Exam Centre requested revision", "Экзаменационный центр запросил доработку", "Sınav Merkezi düzeltme istedi"
    ),
}
AZ_MODEL_QSUB_STATUS = {
    "draft": "Qaralama",
    "submitted_to_chair": "Kafedra müdirinə göndərilib",
    "chair_revision": "Kafedra düzəliş istəyib",
    "chair_approved": "Kafedra təsdiqləyib",
    "center_review": "İmtahan Mərkəzi baxır",
    "center_revision": "İmtahan Mərkəzi düzəliş istəyib",
}

EXAMS_MODEL_QSUB_CHAIR_DECISION = {
    "approved": _e("Approved", "Утверждено", "Onaylandı"),
    "rejected": _e("Rejected", "Отклонено", "Reddedildi"),
    "revision": _e("Revision requested", "Запрошена доработка", "Düzeltme istendi"),
}
AZ_MODEL_QSUB_CHAIR_DECISION = {
    "approved": "Təsdiqləndi",
    "rejected": "Rədd edildi",
    "revision": "Düzəliş istənildi",
}

EXAMS_MODEL_EVENT_CHOICE = {
    "submitted": _e("Submitted", "Отправлено", "Gönderildi"),
    "resubmitted": _e("Resubmitted", "Повторно отправлено", "Yeniden gönderildi"),
    "chair_approved": _e("Chair approved", "Кафедра утвердила", "Bölüm onayladı"),
    "chair_revision": _e("Chair requested revision", "Кафедра запросила доработку", "Bölüm düzeltme istedi"),
    "chair_rejected": _e("Chair rejected", "Кафедра отклонила", "Bölüm reddetti"),
    "center_opened": _e("Centre opened for review", "Центр взял на рассмотрение", "Merkez incelemeye aldı"),
    "center_accepted": _e("Centre accepted", "Центр принял", "Merkez kabul etti"),
    "center_revision": _e("Centre requested revision", "Центр запросил доработку", "Merkez düzeltme istedi"),
    "center_rejected": _e("Centre rejected", "Центр отклонил", "Merkez reddetti"),
}
AZ_MODEL_EVENT_CHOICE = {
    "submitted": "Göndərildi",
    "resubmitted": "Yenidən göndərildi",
    "chair_approved": "Kafedra təsdiqlədi",
    "chair_revision": "Kafedra düzəliş istədi",
    "chair_rejected": "Kafedra rədd etdi",
    "center_opened": "İmtahan Mərkəzi baxışa götürdü",
    "center_accepted": "İmtahan Mərkəzi qəbul etdi",
    "center_revision": "İmtahan Mərkəzi düzəliş istədi",
    "center_rejected": "İmtahan Mərkəzi rədd etdi",
}

EXAMS_MODEL_EVENT_FIELD = {
    "submission": _e("Submission", "Отправка", "Gönderi"),
    "organization": _e("Organization", "Организация", "Kurum"),
    "actor": _e("Actor", "Исполнитель", "İşlemi yapan"),
}
AZ_MODEL_EVENT_FIELD = {
    "submission": "Göndəriş",
    "organization": "Təşkilat",
    "actor": "İcraçı",
}

EXAMS_MODEL_EVENT_META = {
    "singular": _e("Question submission event", "Событие отправки вопросов", "Soru gönderim olayı"),
    "plural": _e("Question submission events", "События отправки вопросов", "Soru gönderim olayları"),
}
AZ_MODEL_EVENT_META = {
    "singular": "Sual göndərişi hadisəsi",
    "plural": "Sual göndərişi hadisələri",
}

EXAMS_SERVICE_ACCESS_PERMISSION = {
    "question_submission_chair_review_denied": _e(
        "You do not have permission to review this question submission as the chair head.",
        "У вас нет прав рассматривать эту отправку вопросов в качестве заведующего кафедрой.",
        "Bu soru gönderimini bölüm başkanı olarak inceleme yetkiniz yok.",
    ),
    "question_submission_requires_chair_approval": _e(
        "This question submission must be approved by the chair head before it can reach the Exam Centre.",
        "Эта отправка вопросов должна быть утверждена заведующим кафедрой, прежде чем попасть в "
        "Экзаменационный центр.",
        "Bu soru gönderiminin Sınav Merkezine ulaşabilmesi için önce bölüm başkanı tarafından onaylanması " "gerekir.",
    ),
}
AZ_SERVICE_ACCESS_PERMISSION = {
    "question_submission_chair_review_denied": (
        "Bu sual göndərişini kafedra müdiri kimi nəzərdən keçirməyə səlahiyyətiniz yoxdur."
    ),
    "question_submission_requires_chair_approval": (
        "Bu sual göndərişi İmtahan Mərkəzinə çatmazdan əvvəl kafedra müdirinin təsdiqindən keçməlidir."
    ),
}

ENTRIES = {
    "accounts.profile.question_chair_review": ACCOUNTS_QCHAIR,
    "accounts.profile.question_submissions": ACCOUNTS_QSUBS,
    "exams.notification.question_submission": EXAMS_NOTIFICATION,
    "exams.service.question_submission.error": EXAMS_SERVICE_QSUB_ERROR,
    "exams.template.question_chain": EXAMS_TEMPLATE_QCHAIN,
    "exams.template.question_chair": EXAMS_TEMPLATE_QCHAIR,
    "exams.template.question_submission": EXAMS_TEMPLATE_QSUB,
    "exams.view.question_submission.message": EXAMS_VIEW_QSUB_MESSAGE,
    "profile.sidebar": PROFILE_SIDEBAR,
    "exams.service.question_chair_review": EXAMS_SERVICE_QCHAIR_REVIEW,
    "exams.view.question_submission.chair": EXAMS_VIEW_QSUB_CHAIR,
    "exams.model.question_submission.field": EXAMS_MODEL_QSUB_FIELD,
    "exams.model.question_submission.choice.status": EXAMS_MODEL_QSUB_STATUS,
    "exams.model.question_submission.choice.chair_decision": EXAMS_MODEL_QSUB_CHAIR_DECISION,
    "exams.model.question_submission_event.choice": EXAMS_MODEL_EVENT_CHOICE,
    "exams.model.question_submission_event.field": EXAMS_MODEL_EVENT_FIELD,
    "exams.model.question_submission_event.meta": EXAMS_MODEL_EVENT_META,
    "exams.service.access.permission": EXAMS_SERVICE_ACCESS_PERMISSION,
}

# `az` üçün identity-nin YANLIŞ olduğu kontekstlər (bax modul başlığı).
AZ_OVERRIDES = {}
for _ctx, _table in (
    ("exams.model.question_submission.field", AZ_MODEL_QSUB_FIELD),
    ("exams.model.question_submission.choice.status", AZ_MODEL_QSUB_STATUS),
    ("exams.model.question_submission.choice.chair_decision", AZ_MODEL_QSUB_CHAIR_DECISION),
    ("exams.model.question_submission_event.choice", AZ_MODEL_EVENT_CHOICE),
    ("exams.model.question_submission_event.field", AZ_MODEL_EVENT_FIELD),
    ("exams.model.question_submission_event.meta", AZ_MODEL_EVENT_META),
    ("exams.service.access.permission", AZ_SERVICE_ACCESS_PERMISSION),
):
    for _msgid, _az_text in _table.items():
        AZ_OVERRIDES[(_ctx, _msgid)] = _az_text


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def existing_pairs(lang):
    """`polib` ilə mövcudluq yoxlaması (bax modul başlığı — YAZMA üçün deyil)."""
    import polib

    return {(e.msgctxt or "", e.msgid) for e in polib.pofile(po_path(lang)) if not e.obsolete}


def fill(lang):
    path = po_path(lang)
    existing = existing_pairs(lang)

    # Yazmadan DƏRHAL ƏVVƏL fayl yenidən oxunur — paralel agentin bu arada
    # etdiyi əlavələr itirilməsin.
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            key = (ctx, msgid)
            if key in existing:
                continue
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            if lang == "az":
                msgstr = AZ_OVERRIDES.get(key, msgid)
            else:
                msgstr = translations[lang]
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
