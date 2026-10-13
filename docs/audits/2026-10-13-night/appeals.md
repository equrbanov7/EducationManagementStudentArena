# Apellyasiya — gecə paketi 2026-10-13 (`appeals`)

Sahibin sözü: «Apellyasiyaya verilmə, cavabın düzəldilməsi, sonra evdən 3 gün ərzində apellyasiya verilə. bunların hamısını et.»

## 1. Apellyasiyanın verilməsi (tələbə) — yoxlanıldı, kiçik düzəlişlər

* Hansı suallar: yalnız həmin cəhdə ÇATDIRILAN suallar (`services/creation.py::_clean_items`), final + midterm
  (`permissions.is_appealable_exam`), sınaq cəhdi yox, yoxlanmamış yazılı iş yox. Səbəb tipi + şərh (30–5000 simvol).
  Fayl əlavəsi YOXDUR (dəyişmədi — sahib tələb etməyib).
* Dublikat: eyni apellyasiyada DB unique, başqa apellyasiyada eyni sual servisdə bloklanır; cəhd sətri
  `select_for_update` ilə kilidlənir (paralel POST).
* «Apellyasiyalarım» status izləmə + 5 dəq redaktə pəncərəsi gizlətməsi — mövcud, test olunub.
* **Düzəliş:** imtahan mərkəzinə «Yeni apellyasiya» bildirişi indi rol ADI ilə yox, `appeal.respond` AÇARI ilə
  (`services/notify.py::exam_center_recipients`; wildcard `*` rollar spam almasın deyə daxil deyil; açarlı heç kim
  yoxdursa köhnə rol adlarına düşür).

## 2. Cavabın düzəldilməsi — YENİ

İki variant qərar modalındadır:

1. **Yalnız bu tələbə** — mövcud «Qəbul et» (+1, `decisions.accept_appeal_item`).
2. **Açar səhvdir → hamı üçün** — `services/key_corrections.py::apply_key_correction`:
   * düzgün variant(lar) + səbəb (≥10 simvol), təsdiq dialoqu;
   * həmin imtahanın bu sualını cavablayan bütün bitmiş, sınaq olmayan cəhdlər yoxlanır; YENİ açara uyğun cavab
     verib köhnə açarla səhv sayılan hər kəsə eyni kredit (`APPEAL_ACCEPT_BONUS_POINTS`, sual balı ilə məhdud);
   * **heç kimin balı azalmır**; snapshot/seçimlər toxunulmaz — kredit additiv `KeyCorrectionCredit` sətridir;
   * ledger (`ExamGradeEvent`, fail-closed), audit (`appeals.answer_key_correction`), jurnal (`sync_attempt_to_journal`
     → registrar `ExamScoreEntry(kind=appeal)` append-only), tələbə + müəllim bildirişləri — hamısı commit-dən sonra;
   * bir sual üçün bir aktiv düzəliş (DB partial unique), fərdi qəbul + açar krediti oxuma anında dedup olunur;
   * **geri alma** (`revoke_key_correction`): sətir silinmir, kreditlər `reverted`, ledger/audit/jurnal/bildiriş.
* Müəllim bildirişi (yeni): qərar balı dəyişəndə imtahan müəllifi + fənn müəllimi(lər)i bilir. Final → «jurnal
  avtomatik yeniləndi»; **midterm → «jurnalda özünüz yeniləyin»** (sahibin qərarı ilə midterm jurnala avtomatik yazılmır).
* Rədd olunmuş apellyasiya heç nəyi dəyişmir; təkrar qəbul bir dəfə kreditləyir (testlə).

## 3. Apellyasiya pəncərəsi — evdən, 3 təqvim günü

* `appeal_window_days()` → «Sistem tənzimləmələri» `exam.appeal_window_days` → `settings.APPEAL_WINDOW_DAYS` (3).
* Son gün sərhədi HƏMİŞƏ `APPEAL_WINDOW_TIMEZONE` (Asia/Baku) ilə — əvvəl aktiv tz-dən asılı idi.
* Nəticə gizlidirsə (`results_hidden_from_students`) pəncərə AÇILMIR; gizli → görünən edildikdə
  `Exam.results_published_at` (yeni sahə, miqrasiya `exams.0075`) yazılır və pəncərə ondan sayılır.
* «Apellyasiya son tarixi: …» — yaratma səhifəsi, «Yeni apellyasiya» modalı, nəticə səhifəsi. Müddət bitəndə
  forma/düymə yoxdur, server `create_appeal`-da rədd edir (dəyişməyib).
* Şəbəkə: `/appeals/*` heç bir daxili-şəbəkə qapısına düşmür. Regresiya testi (`test_window_2026_10_13.py::AppealFromHomeTests`)
  `NETWORK_ZONE_ENFORCED + NETWORK_ZONE_STAFF_INTERNAL_ONLY + EXAM_FINAL_INTERNAL_ONLY=True` və xarici İP ilə
  yaratma GET/POST, «Apellyasiyalarım», detal fraqmentini yoxlayır. **Orkestrator üçün:** `EXAM_FINAL_INTERNAL_ONLY`
  birləşəndən sonra bu test yaşıl qalmalıdır — qırılırsa həmin bayraq `/appeals/` və ya kabinet yollarını tutur.

## 4. İmtahan mərkəzinin baxış UI-ı

* Müqayisə indi ÇATDIRILMA snapshot-undan (`views/teacher/_review_context.py`): müəllif sonradan sualı/açarı
  dəyişsə də mərkəz tələbənin gördüyünü görür; dondurulmuş seçim; yazılıda tələbə cavabı ↔ ideal cavab yan-yana.
* Aktiv açar düzəlişi kartı («Düzəldilmiş açar» işarəsi), forma, geri alma; apellyasiya tarixçəsi (göndərilmə →
  qərarlar → bal düzəlişləri → açar düzəlişləri).
* N+1: sorğu sayı item sayından asılı deyil (testlə; tapılan `answer.question` N+1 düzəldildi).
* Təhlükəsizlik: açar düzəlişi endpoint-ləri POST-only, `can_review_appeal` (tenant) + `appeal.respond`+`appeal.decide`;
  özgə org / tələbə → 404, açarsız işçi → 403; RLS siyasəti yeni cədvəllərə (`appeals.0006`).

## 5. Tarixçə koordinator/dekan üçün — YENİ oxu səthi

* «Akademik qeydlər» tələbə çekməcəsinə (dekan/koordinator `student.records_view` scope-u) «İmtahan cəhdləri və
  apellyasiyalar» bloku: final + midterm cəhdləri, rəsmi/ləğv olundu, faiz, apellyasiya qərarları, açar düzəlişləri
  (`appeals.public.student_exam_history`). Jurnal «Yekun» tab-ındakı tarixçə də açar düzəlişi sətirlərini göstərir.

## Miqrasiyalar

`exams.0075_exam_results_published_at` (nullable sahə), `appeals.0005_answer_key_correction` (2 cədvəl),
`appeals.0006_rls_answer_key_correction` (RLS). Hamısı additiv, geri alına bilir.

## Səhər yoxlanmalı

* Prod-da imtahan mərkəzi rəhbəri ilə bir test apellyasiyasında «Açar səhvdir?» formasını açıb baxmaq (düzəliş ETMƏDƏN).
* Açar düzəlişi krediti = +1 (sahibin «qəbul → +1» qaydası). Sualın balı >1 olan testlərdə tam bal istənirsə — qərar sahibindir.
* Müəllim bildirişi ilk yekun qərarda gedir; reviewer 5 dəq ərzində qərarı dəyişsə yeni bildiriş getmir.
