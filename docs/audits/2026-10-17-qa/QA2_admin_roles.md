# QA-2 — inzibati rollar (RİM, dekan / müavin, kafedra müdiri, koordinator / tyutor, imtahan mərkəzi, HR, tədris şöbəsi)

**Tarix:** 2026-10-17 · **Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (`127.0.0.1:55433`) · **Kod:** `Develop` @ `9ea233634`
**Mən yalnız klonda işlədim** (prod / `emsarena_db` toxunulmadı). `qa.*` parolları dəyişdirilmədi.
Hesabat YALNIZ təkrar istehsal etdiyim şeyləri yazır.

## 0. Metodologiya və xəbərdarlıqlar

* **Test müştərisi (əsas yol):** `manage.py shell` + Django `Client.force_login()`, `config.settings.local`, `.claude/dev-clone.env`
  (`emsarena_app` rolu, RLS işləyir). Ssenari skriptləri: `/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/qa/t*.py`
  (ortaq köməkçi `h.py`). Bütün URL-lər real marşrutlardır, cavablar real şablon/JSON-dur.
* **Brauzer (vizual):** ayrı serverdə (`127.0.0.1:8042`, `qa2.localhost` hostu, `--noreload`), öz tab-ım (`tab-5`), sessiya `force_login` ilə
  yaradılıb (parola toxunulmayıb). Ekran şəkilləri: `…/scratchpad/qa/shots/` (12 fayl). Server və saxta Loki testdən sonra söndürüldü.
* **Klon miqrasiyası:** klonda `accounts.0031_profile_completed_at` tətbiq olunmamışdı (profil səhifəsi 500 verirdi) — sahib DSN-i ilə `migrate` işlətdim
  (yalnız bu 1 miqrasiya).
* **Real heyət hesabları:** klonda `qa.*` içində `rim_staff` və `vice_dean` yoxdur → `m.babyev` (RİM əməkdaşı), `f.veliyeva.2` (dekan müavini), `naila.quliyeva`
  (YTİM dekanı), `kamran.imameliev` (RİM + öz yükü var) və s. işlətdim. Bu hesablarda `password_change_required` bayrağını sınaq müddətinə `False` etdim və
  **hər dəfə `finally`-də geri `True` qoydum** (sonda yoxladım: hamısı `True`). «Məlumatlarınızı tamamlayın» qapısını yalnız prosesin yaddaşında söndürdüm
  (`gate_off()`), qapının özünü §6-da ayrıca yoxladım.
* ⚠️ **`qa.rector` superuserdur** (`is_superuser=True`) → onun 86 menyu bəndi və «Sistem tənzimləmələri» / monitorinq hüquqları real rektoru əks etdirmir.
  Matrisdə «Rektor*» sütunu ona görə ulduzludur. Real rektor üçün ayrıca hesab lazımdır.
* ⚠️ **`qa.*` hesabları profil-tamamlama qapısından azaddır** (`profile_completion.is_exempt_user`) → bu hesablarla qapı heç vaxt görünmür; qapını yalnız real
  heyət hesabı ilə sınaya bilərsiniz.
* **Klonda yan təsirlər (adi istifadəçi yazıları):**
  * `Murad Abbasov` (`murad.abbasov2`, record `0fd6b8b4…`) **`235 KE ing`-dən `235 KE-2`-yə köçürülüb və geri qaytarıla bilmir** (F-06) — dondur/xaric/bərpa
    əmrləri də yazılıb (`QA/1`…`QA/10`). Klon birdəfəlikdir.
  * «Proqramlaşdırma…» kafedrasının tapşırığında bir sətir düzəlişlə dəyişdirilib və geri qaytarılıb, bir bölgü silinib-yenidən əlavə olunub, sənəd
    `distributed`-ə qayıdıb; 2 «Bölgünü təsdiqlə» bildirişi (`notified: 15`) gedib.
  * Fənndən azad etmə: dekan və RİM sınadı, **mənimki geri qaytarıldı** (jurnalda «Gate ZZQA QA1» başqa agentindir).
  * «Sistem tənzimləmələri»: sınanan bütün dəyərlər defolta qaytarıldı (`password.min_length`, `journal.*_minutes`, `late_entry_days`, `profile.require_fin`).
    Bazada qalan `login.*` / `otp.*` sətirləri mənə aid deyil.

---

## 1. Rol × bölmə görünürlük matrisi (sol menyu)

Mənbə: `/accounts/profile/` cavabındakı `<aside class="profile-sidebar">`, hər rol üçün 1 nümunə hesab:
RİM rəhbəri `qa.ikt_rehber`, RİM əməkdaşı `m.babyev`, rektor `qa.rector`*, prorektor `qa.vice_rector`, dekan `qa.dean` (Dizayn), dekan müavini `f.veliyeva.2`,
kafedra müdiri `qa.chair_head`, koordinator `qa.program_coordinator`, tyutor `qa.tutor`, imtahan mərkəzi `qa.exam_center_head` / `qa.sec.exam_center_staff`,
tədris şöbəsi `qa.teaching_office_head` / `qa.teaching_office_staff`, HR `qa.sec.hr`, tələbə xidmətləri `qa.student_services`, müqayisə üçün müəllim `qa.teacher`.
Hamıya ortaq bəndlər (Ana səhifə, Bildirişlər, Müraciətlərim, Sorğular, Elanlar, Statistika, Profil məlumatları/redaktə, Şifrəni dəyiş, Akademik təqvim, Dərs cədvəli)
göstərilmir. Xam məlumat: `scratchpad/qa/sidebars.json`.

| bölmə (menyu) | RİM rəhbəri | RİM əməkdaşı | Rektor* | Prorektor | Dekan | Dek. müavini | Kaf. müdiri | Koordinator | Tyutor | İM rəhbəri | İM əməkdaşı | Tədris ş. rəhbəri | Tədris ş. əməkdaşı | HR | Tələbə xid. | Müəllim (müq.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Bildiriş göndər (`publish-notification`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | ✅ | · | ✅ |
| Cədvəl idarəetməsi (`schedule-manage`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | · |
| Elektron jurnal (`/jurnal/`) | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | ✅ |
| Keçilmiş dərslər (`lessons-log`) | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | ✅ |
| Fənn qovluqları (`subject-folders`) | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | ✅ |
| Jurnal bağlama (`journal-close`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Fənn təhvili (`teaching-handover`) | ✅ | · | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · |
| Dərs yüküm (`my-workload`) | ✅ | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | ✅ |
| Dərs yükü mərkəzi (`workload-center`) | ✅ | · | ✅ | ✅ | · | · | ✅ | · | · | · | · | ✅ | ✅ | · | · | · |
| Yük bölgüsü (`workload-distribution`) | ✅ | · | ✅ | ✅ | · | · | ✅ | · | · | · | · | ✅ | ✅ | · | · | · |
| Yük vizası (`workload-visa`) | ✅ | · | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · |
| Yük təsdiqi (`workload-approval`) | ✅ | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · |
| Yük — ümumi baxış (`workload-overview`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · | · | · | · |
| Sillabuslar (`syllabus-list`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | ✅ |
| Sillabus təsdiqi (`syllabus-review`) | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · |
| Sual Bankı (`question-bank`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | · | · | ✅ |
| Sual göndərişləri (`question-submissions`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | ✅ |
| Sual təsdiqi (`question-chair-review`) | ✅ | · | ✅ | · | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · |
| İmtahanlarım (`my-exams`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | · | · | ✅ |
| Yaratdığım kurslar (`my-courses`) | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | ✅ |
| Tapşırıq yoxlaması (`subject-folder-review`) | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | ✅ |
| Apellyasiyalar (`manage-appeals`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| İmtahan Nəzarət Sistemi (`/exams/center/rooms/`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| PIN axtarışı (`exam-center-pins`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| İmtahan statistikaları (`exam-center-stats`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| Apellyasiya statistikası (`appeal-stats`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| İmtahan şansı ver (`exam-chance`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| İmtahan balının daxil edilməsi (`exam-score-entry`) | ✅ | · | ✅ | · | · | · | · | · | · | ✅ | · | · | · | · | · | · |
| Köçürülmüş nəticələr (`legacy-grade-review`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Midterm pəncərələri (`kollokvium-windows`) | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| Universitet strukturu (`org-structure-tree`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| Kafedra profili (`chair-profile`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| İxtisaslar (`programs-registry`) | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | ✅ | · |
| Fənn kataloqu (`subject-catalog`) | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | ✅ | · |
| Tədris planı (`curriculum-editor`) | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | · |
| Qruplar (`groups-registry`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| Semestr açılışı (`semester-opening`) | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | ✅ | ✅ | · | · | · |
| Registrar (kataloq) (`registrar-catalog`) | ✅ | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · |
| Tələbə qəbulu (`student-admission`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | ✅ | · |
| Tələbə reyestri (`student-registry`) | ✅ | · | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | ✅ | · | · | ✅ | · |
| Tələbələr (`people-students`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | · |
| Müəllimlər (`people-teachers`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| Kadr analitikası (`hr-analytics`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | ✅ | · | · |
| Akademik qeydlər (`academic-records`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | ✅ | · | · | · |
| Sorğu nəticələri (`evaluation-results`) | ✅ | · | ✅ | ✅ | · | · | ✅ | · | · | · | · | ✅ | ✅ | · | · | · |
| Sorğu kampaniyaları (`evaluation-campaigns`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Sorğu qurucusu (`surveys-builder`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Akademik analitika (`analytics`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| Təşkilat paneli (`org-overview`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| Fakültələr (`org-faculties`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| Kafedralar (`org-kafedras`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| Struktur üzvləri (`org-members`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | · |
| Təşkilat rolları (`org-roles`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Audit jurnalı (`audit-log`) | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | · | ✅ | · | · |
| Rol təyin et (`role-assignment`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | ✅ | · | · |
| RİM mərkəzi (`rim-center`) | ✅ | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | ✅ | · | · |
| Sistem tənzimləmələri (`system-settings`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Jurnal təmizliyi (`journal-hygiene`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Müəllim əlavəsi (toplu) (`teacher-intake`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | ✅ | · | · |
| Heyət idarəetməsi (`student-organization-management`) | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · | · |
| İcazələr (`permission-editor`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Rolları idarə et (`manage-roles`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | ✅ | · | · |
| İmtahan zalları (`superadmin-exam-rooms`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Sistem Monitorinqi (`system-monitoring`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Parol sıfırlama (`account-password-reset`) | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Yoxlanılacaq (`pending-review`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ |
| Dəyərləndirilmiş nəticələr (`review-results`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ |
| Təşkilat məlumatları (`superadmin-org-inspector`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Təşkilat özəllikləri (`superadmin-org-features`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Superadmin nəzarəti (`superadmin-organizations`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| İstifadəçi İdarəetməsi (`superadmin-users`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| AI Tənzimləmələri (`superadmin-ai`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Əlaqə mesajları (`superadmin-contact-messages`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Kateqoriya yarat (`create-category`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Kateqoriyalar (`category-management`) | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| Bölmə imtahanları (`unit-exams`) | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · |

**Matrisdən müşahidələr (mən təkrar istehsal etdim, hamısı menyu səviyyəsindədir):**

* Kafedra müdiri: «Fəndən azad et» düyməsi YOXDUR (jurnal 404/düymə yoxdur, POST 403 — §4.4). «Semestr açılışı» bölməsini görür (sahibin 2026-10-14 qərarı:
  yalnız dekan + kafedra müdiri), amma **heç bir yazma düyməsi yoxdur** və POST-lar 403 verir (§4.5) — qayda yazma tərəfində düzgündür; oxu əhatəsi isə F-01-dir.
* Tyutor = Koordinator (migr. 0064) — hər ikisində «Semestr açılışı», «Yük mərkəzi / bölgüsü» yoxdur ✅ (yalnız «Yük vizası»). Tyutor menyuda 27 bənd görür (ROL_MATRISI.md 10-13-də 15 idi; fərq
  2026-10-14 «tyutor = koordinator» qərarındandır, bug deyil).
* HR menyusunda **«Qruplar»**, **«RİM mərkəzi»**, «Rol təyin et», «Rolları idarə et» var — HR-ın tələbə kataloqu (`people-students`) yoxdur, amma qruplar vasitəsilə tələbə
  siyahısı açılır (F-03).
* Prorektor «RİM mərkəzi» görür və `/accounts/rim/search/` 200 verir (menyu ilə uyğundur); RİM əməkdaşı (`m.babyev`) görmür (403) ✅.
* RİM əməkdaşının «Dərs yükü mərkəzi / Yük bölgüsü / Yük təsdiqi» bölmələri yoxdur — yalnız «Yük — ümumi baxış».
* 537 bölmə fraqmenti (15 rol × bütün menyu bəndləri) `…/api/sections/<bölmə>/` ilə açıldı: **0 × 500, 0 × «EMS Arena», 0 × xam `{{`/`undefined`/`NaN`**.

### Əməl (action) matrisi — yazma qapıları

| əməl | RİM rəhbəri | RİM əməkdaşı | dekan (öz fak.) | kafedra müdiri | koordinator / tyutor | tədris şöbəsi | prorektor | tələbə xid. | HR | müəllim |
|---|---|---|---|---|---|---|---|---|---|---|
| Yük: sətir saatı / bölgü əlavə-sil (düzəliş axını) | ✅ | 403 | 403 | ✅ yalnız öz kafedrası (başqası 403) | 403 | 403 | 403 | — | — | 403 |
| Yük: oxu (sətirlər) | hamısı | hamısı | öz fakültəsi | öz kafedrası | tyutor: öz kafedrası | hamısı | hamısı | — | — | 403 |
| Cədvəl redaktoru (yaz / köçür / sil) | ✅ | düymə yox | ✅ öz qrupları | bölmə var, **0 qrup** (F-05) | koord. ✅ öz ixtisası; tyutor qrup yox | düymə yox (403) | düymə yox | — | — | 403 |
| Qrup reyestri: «Qrupu dəyiş» / redaktə / arxivlə | ✅ | ✗ | ✗ | ✗ | ✗ | ✅ | ✅ | ✗ | ✗ | 403 |
| Tələbə: Dondur / Uzaqlaşdır / Bərpa et | ✅ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ |
| «Fəndən azad et» / «Bərpa et» (jurnal) | ✅ | ✗ | ✅ öz fakültəsi | ✗ (403) | koord./tyutor: sınanan jurnalda 404 | ✗ | ✗ | ✗ | ✗ | ✗ |
| Semestr açılışı: yarat/göndər/kilidlə/ləğv | ✅ | ✗ | ✗ (oxu) | ✗ (oxu) | bölmə yoxdur | ✅ | ✅ | — | — | — |
| «Sistem tənzimləmələri» yaz | ✅ | 403 | 403 | 403 | 403 | 403 | 403 | 403 | 403 | 403 |
| Sistem monitorinqi (API) | ✅ | — | 403 | 403 | 403 | 403 | 403 | — | 403 | — |
| RİM mərkəzi axtarış | ✅ | 403 | 403 | 403 | 403 | 403 | ✅ (200) | 403 | **200** | 403 |

---

## 2. Tapıntılar (xülasə)

| № | sev | rol | səhifə / əməl | başlıq |
|---|---|---|---|---|
| F-01 | **P2** | dekan, kafedra müdiri | Semestr açılışı | Oxu əhatəsi yoxdur — başqa fakültənin açılışları, müəllim adları, say, «Kafedra» süzgəci görünür |
| F-02 | **P2** | dekan, kaf. müdiri, koordinator, tyutor | Tədris planı (curriculum-editor) | Bütün fakültələrin plan sətirləri və 304 ixtisasın siyahısı əhatəsiz oxunur |
| F-03 | **P2** | HR | Qruplar, RİM mərkəzi | HR-ın tələbə kataloqu bağlıdır, amma qruplar çekmecəsi 8 796 tələbənin adı/istifadəçi adı/ixtisasını, RİM mərkəzi isə şəxsi e-poçtunu verir və «redaktə» icazəsi var |
| F-04 | **P2** | dekan (başqa fakültə), HR, istənilən inzibati rol | `/accounts/users/<ad>/` | Tələbənin şəxsi e-poçtu əhatə yoxlamadan göstərilir (reyestr kartı eyni adam üçün 404 verir) |
| F-05 | **P2** | kafedra müdiri, tyutor | Cədvəl idarəetməsi | Menyuda var, amma qrup siyahısı 0 — redaktor işləmir (izahsız boş vəziyyət) |
| F-06 | **P2** | RİM / tədris şöbəsi | Qrup çekmecəsi «Qrupu dəyiş» | Yanlış köçürməni geri qaytarmaq olmur (409 «inzibati yoxlama»), yolu göstərilmir |
| F-07 | P3 | RİM, tədris şöbəsi | «Qrupu dəyiş» | Sifariş (əmr №/tarix) yoxdur, `StudentMovement` izi yoxdur; qalan hərəkətlərlə ziddiyyət |
| F-08 | P3 | RİM | «Bərpa et» | Tutum təyin olunmayan qrupda hardkod 30 limit bərpanı bloklayır |
| F-09 | P3 | hamı | API kontraktları | Yanlış HTTP kodları / yanıldıcı sahələr |
| F-10 | P3 | kaf. müdiri, dekan, koord., tyutor | cədvəl redaktoru / yük redaktoru seçiciləri | Müəllim, qrup, ixtisas seçiciləri təşkilat səviyyəlidir |
| F-11 | P3 | RİM, dekan, koordinator | «Xanaya dərs qoy» | Korpus adları, fənn defoltu, 26 px toxunma hədəfi, boşluq |
| F-12 | P3 | heyət (boş FİN/telefon) | məcburi profil qapısı | `/exams/` prefiksi imtahan MƏRKƏZİ idarə səhifələrini də qapıdan azad edir |
| F-13 | P3 | RİM | «Məlumat natamam» süzgəci | Say (8 380) qapının dayandıracağı hesablardan (11) fərqlidir; test hesabı yoxdur |
| F-14 | P3 | RİM | Sistem monitorinqi → Loglar | Loki əlçatmaz olanda süzgəc seçiciləri native; Loki `status:error` detalı maskalanmır |
| F-15 | P3 | RİM | Sistem tənzimləmələri | Mətn səhvləri («Söndürülüdə», «Yanılıda») və yanlış hədd mesajı |
| F-16 | P3 | hamı | seçicilər / reyestr | Test/zibil qruplar (`.`, `test1543`, `Silinmelidir`), ortaq-ana qrup əlaqəsi görünmür |
| F-17 | P3 | RİM, kaf. müdiri | Yük bölgüsü | «Tapşırıq yarat» mövcud tapşırıqda da görünür; təsdiq cavabı şişkin |

**Say: P0 = 0 · P1 = 0 · P2 = 6 · P3 = 11.**

---

## 3. Tapıntılar (ətraflı)

### F-01 · P2 · Semestr açılışı oxu əhatəsi yoxdur
* **Rol/səhifə:** dekan (`qa.dean` Dizayn, `naila.quliyeva` YTİM), kafedra müdiri (`qa.chair_head`, `qa.sec.chair_head_b`) → profil → «Semestr açılışı».
* **Təkrar:** `GET /accounts/profile/api/sections/semester-opening/` (`HTTP_X_REQUESTED_WITH=XMLHttpRequest`) hər 4 hesabla (skript `t44.py`, `t45.py`).
* **Gözlənilən:** 2026-10-14 qərarı «dekan / kafedra müdiri yalnız öz fakültəsini görür» (`6ab96b888`, `46ea5f266`) — açılış siyahısı, say, «Kafedra» süzgəci öz fakültəsi ilə məhdud.
* **Faktiki:** 4 hesabın hamısı eyni cədvəli görür: «Proqramlaşdırma və informasiya təhlükəsizliyi» açılışları (QKU-14, QKU-17 …), «77 açılış / 60 müəllim təyin olunub / 4190 saat», müəllim
  adları, çatışmayan sillabus/cədvəl sayları və **bütün universitetin kafedra siyahısı**. Dizayn dekanı YTİM kafedrasının açılışlarını, İT kafedrasının müdiri Proqramlaşdırma kafedrasını görür.
  `?sm_chair=<istənilən kafedra id>` süzgəci də qəbul olunur.
* **Sübut:** `t45.py` — 5 hesabın «kafedra» sətirləri eynidir (`'Proqramlaşdırma və informasiya təhlükəsi…'`), yalnız RİM-də düymələr var. Yazma yolları düzgün bağlıdır
  (`/jurnal/semestr/emel/` → 403 hamısı, `t46.py`).
* **Fayl:** `apps/registrar/semester_open.py` → `build_semester_opening()` (`CourseOffering.objects.filter(organization=…, period=…)` — əhatə filtri yoxdur; `coverage()` / `offering_issues()` də eyni),
  `build_semester_section` (`apps/accounts/views/profile/_sections/curriculum_sections.py:~410`).

### F-02 · P2 · «Tədris planı» oxu əhatəsi yoxdur
* **Rol:** `qa.dean` (Dizayn), `naila.quliyeva`, `qa.chair_head`, `qa.sec.chair_head_b`, `qa.program_coordinator`, `qa.tutor`.
* **Təkrar:** `GET /accounts/profile/api/sections/curriculum-editor/?cu_program=<id>&cu_plan=<id>` (`t48.py`, `t71.py`).
  Test planları: «Dizayn (Qrafik)» (Dizayn), «Tarix» (Psixologiya), «Turizm işinin təşkili» (Biznes məktəbi).
* **Gözlənilən:** İxtisas seçici və plan sətirləri yalnız öz fakültəsinin ixtisasları ilə (programs-registry bunu edir: dekan 863 simvol, RİM 3149 — əhatəlidir).
* **Faktiki:** Hər 6 hesab üçün 3 planın da bütün sətirləri açılır (`QKU-` şifr sayı 152/172/152 — RİM ilə eyni). İxtisas seçicisində bütün universitetin ixtisasları görünür (dekan üçün səhifədə 304 `<option>`).
  Kafedra müdirinin (`qa.chair_head`) cavabı RİM cavabı ilə **bayt-bayt eynidir** (50 377 simvol, «Yeni plan» düyməsi daxil). Yazma `program_in_scope` ilə düzgün bağlıdır.
* **Fayl:** `apps/registrar/curriculum_registry.py` (`build_curriculum_editor`, `plan_options`, `program_choices` — oxu tərəfində `plan_scope` tətbiq olunmur; yazı tərəfində `program_in_scope`/`plan_in_scope` var).

### F-03 · P2 · HR tələbə tərəfini «Qruplar» və «RİM mərkəzi» ilə görür
* **Rol:** `qa.sec.hr`.
* **Təkrar:** (a) `GET /organizations/qku/groups/a751a0d1-4264-4900-b086-40b1068ed2c4/students/` → 200, 32 sətir: ad, `username`, ixtisas, status, qəbul ili, `profile_url`.
  `GET /accounts/profile/api/sections/groups-registry/` → «TƏLƏBƏ 8796». (b) `GET /accounts/rim/search/?kind=student&q=abbasov` → 200, 97 nəticə: ad + **şəxsi e-poçt**
  (`necibeabbasova25@gmail.com`), `GET /accounts/rim/user/499/` → `actions: {edit: true}`. (c) `GET /accounts/people/students/list/` → total 0 (kataloq bağlıdır). (`t18.py`, `t20.py`, `t41.py`, `t42.py`)
* **Gözlənilən:** 2026-10-13 rol auditi qərarı: «HR = yalnız heyət idxalı; tələbə kataloqu → Tələbə xidmətləri» (`docs/audits/2026-10-13-claude/ROL_AUDITI.md` B6). Eyni ruhda HR-ın tələbə siyahısını / şəxsi e-poçtunu / redaktəsini görməsi gözlənilmir.
* **Faktiki:** kataloq bağlıdır, amma iki yan yol açıqdır. Hierarxiya düzgündür (HR-dan yüksək hesablar 404).
* **Fayl:** HR şablonu `unit.view` (qruplar) və `user.search`/`user.edit` (RİM mərkəzi): `apps/organizations/default_roles_role_audit.py` (HR bloku), `apps/organizations/group_students.py:can_view_groups`,
  `apps/accounts/services/rim/policy.py` (`PERM_SEARCH`, `PERM_EDIT`).

### F-04 · P2 · Ümumi profil səhifəsi tələbənin şəxsi e-poçtunu əhatəsiz göstərir
* **Rol:** `qa.dean` (Dizayn), `qa.sec.hr`; (müəllim `qa.teacher` və tələbə görmür).
* **Təkrar:** `GET /accounts/users/murad.abbasov2/` (YTİM tələbəsi). (`t63.py`, `t64.py`)
* **Gözlənilən:** Eyni adam üçün `student-registry/card/<id>/`, `people/person/<id>/`, `people/student/<id>/card/` Dizayn dekanı üçün **404** verir → ümumi profil də yad fakültənin tələbəsinin şəxsi
  məlumatını göstərməməlidir (profil-tamamlama səhifəsinin vədi: «yalnız RİM, dekanlıq, kadrlar şöbəsi görür»).
* **Faktiki:** Hər iki rol üçün 200: «Struktur məlumatı — Vəzifə: Tələbə, E-poçt: `murad.abbasov.235keing@gmail.com`». Əhatə yoxlaması yoxdur.
* **Fayl:** `apps/accounts/views/profile/public.py` → `public_user_profile` (satır ~100) və `accounts/public_profile.html`.

### F-05 · P2 · Kafedra müdiri və tyutorda «Cədvəl idarəetməsi» boşdur
* **Rol:** `qa.chair_head`, `r.durdane` (kafedra müdiri, kafedra əhatəli), `qa.tutor`.
* **Təkrar:** `GET /accounts/profile/?section=schedule-manage` → qrup seçicisində **0 qrup**, KPI «Cədvəldə dərs 0 / Boş xana 48», yalnız «Yalnız öz struktur bölmələriniz» yazısı; redaktoru açmaq olmur. (`t15.py`, `t17.py`, `t16.py`)
  Müqayisə: koordinator 12, dekan 29–64, RİM 822 qrup.
* **Gözlənilən:** Menyuda bölmə varsa, ya istifadə oluna bilməli, ya da gizlədilməli (və ya izahlı boş vəziyyət).
* **Səbəb (kodda):** `schedule_manage.scoped_groups()` `scope.unit_subtree_q()` ilə süzür; qruplar ixtisasın (fakültənin) altındadır, kafedranın altında yox → kafedra əhatəli müdir/tyutor üçün alt-ağac boşdur
  (qrup reyestri isə 2026-10-14 «ən yaxın fakültə» genişlənməsi ilə işləyir — iki bölmə fərqli əhatə qaydası işlədir).
* **Qeyd:** Dekan və koordinator düzgün işləyir; ixtisas əhatəli «kafedra müdirləri» (g.mustafayeva 3, a.veliyev 18 qrup) görür — klonda strukturun qarışıqlığı. Prod-da yoxlayın.
* **Fayl:** `apps/registrar/schedule_manage.py:112` (`scoped_groups`).

### F-06 · P2 · «Qrupu dəyiş» geri qaytarılmır
* **Rol:** `qa.ikt_rehber`, `qa.teaching_office_head`, `qa.vice_rector`, `qa.rector`.
* **Təkrar:** `POST /organizations/qku/groups/action/` `{action: move_student, id: <235 KE-2>, record_id: 0fd6b8b4…, reason: 'QA sınaq'}` → 200 `moved: 2`; sonra eyni əmr əks istiqamətdə
  (`id: <235 KE ing>`) → **409 `transfer_rejected`: «Yeni qrupun açılışında bu tələbəyə aid tarixi qeydiyyat var; tarixçəni yenidən aktivləşdirmədən əvvəl inzibati yoxlama tələb olunur.»** (`t26.py`, `t28.py`)
* **Gözlənilən:** Yanlış qrupa köçürmə (çox rast gələn səhv) üçün işlək yol; ən azı mesajda kimə müraciət etmək / hansı alət (Tələbə reyestri → rəsmi köçürmə?) göstərilməli.
* **Faktiki:** UI-da heç bir alternativ yoxdur; xaric edib «Bərpa et» də eyni tarixçə qaydasına düşə bilər. Tələbə bu vəziyyətdə qalır (klonda `murad.abbasov2` belə qalıb).
* **Fayl:** `apps/registrar/transfer.py:182`, `apps/organizations/group_actions.py::_move_student`.

### F-07 · P3 · «Qrupu dəyiş» əmr nömrəsi / tarixi tələb etmir
* Brif: «Dondur, Uzaqlaşdır … əmr nömrəsi/tarix MƏCBURİ, səbəb istəyə bağlı». **Dondur / Uzaqlaşdır / Bərpa et** bu qaydaya uyğundur (`order_number_required`, `order_date_required`,
  `effective_until_required`, `order_date_invalid`, boş səbəblə 200; ledger sətri «Akademik məzuniyyət · Əmr № QA/1 · 16.10.2026») ✅ (`t21.py`).
* **«Qrupu dəyiş»** isə əksinə: səbəb MƏCBURİ (≥3 simvol), əmr nömrəsi/tarixi **yoxdur** və `StudentMovement` yazılmır (yalnız audit): `t27.py` — ledgerdə yalnız 3 sətir
  (`academic_leave`, `expulsion`, `reinstatement`), qrup dəyişməsi görünmür. Kod şərhi bunu qəsdən (sahib 2026-09-07/08) göstərir; brifdəki qayda ilə fərq üçün sahib təsdiqi lazımdır.
* **Fayl:** `apps/organizations/group_actions.py::_move_student`.

### F-08 · P3 · «Bərpa et» tutumu təyin olunmayan qrupda hardkod 30 limitlə bloklanır
* `POST /accounts/student-registry/action/` `kind=reinstatement, target_group=<235 KE ing>` → 409 `group_full` «`235 KE ing` qrupunda boş yer yoxdur (32 / 30)». Qrupun `settings.capacity`-si yoxdur →
  `group_capacity()` `DEFAULT_GROUP_CAPACITY` (30) qaytarır; qrupda isə artıq 32 tələbə var. Yalnız qrupun `capacity`-sini əllə yazandan sonra bərpa keçdi (`t21.py`, `t24.py`).
* UI-da tutumu dəyişdirmək üçün «Redaktə» dialoqu var, amma bərpa xətası bunu söyləmir. **Fayl:** `apps/accounts/services/student_groups.py:67`, `apps/accounts/services/people/movements.py:150`.

### F-09 · P3 · API kontraktlarında sapmalar
* `POST /accounts/student-registry/action/` xəta cavabları (400/409) icazəsi olan RİM üçün də `"has_access": false` daşıyır (`order_number_required`, `illegal_transition`, `group_full`).
* `workload.invalid_reason` və `workload.hours_exceeded` HTTP **403** ilə qayıdır (məzmun xətasıdır — 400/409/422).
* `POST …/schedule-manage/editor/ action=delete` artıq silinmiş slotda **403 permission_denied** verir (404 gözlənilir).
* `action=check` əhatədən kənar qrupda **400 «Semestr və qrup seçilməlidir»**, `action=plan` isə **403** verir (eyni qrup, eyni rol).
* `login.device_rate` və s. `rate` tənzimləməsində pəncərə (`window`) səhv olanda mesaj «Dəyər 3–100 aralığında olmalıdır» (say aralığı) göstərir — problem pəncərədədir (`t37.py`).
* «Bölgünü təsdiqlə» cavabı (`sync.group_offering_ids`) yüzlərlə UUID daşıyır (~10 KB).

### F-10 · P3 · Seçici API-ləri təşkilat səviyyəlidir
* `action=options` (cədvəl redaktoru) dekan / koordinator / kafedra müdiri / tyutor üçün **400 müəllim** (bütün təşkilat) qaytarır, qrup əhatədən kənar olsa da (`t57.py`); `action=suggest` yad qrup üçün 200.
* Yük redaktorunun `…/ders-yuku/secimler/?chair=` cavabı kafedra müdirinə **bütün təşkilatın qruplarını (822) və ixtisaslarını (85)** verir («Qruplar» çoxseçimli seçicisində başqa fakültələrin qrupları + `Level - Group N`, `test1543` …).
  Yazı serverdə doğrulanır deyə risk aşağıdır; amma istifadəçi yanlış qrup seçə bilər.
* **Fayl:** `apps/accounts/views/schedule_editor.py::_options`, `apps/workload/views/distribution_api.py::options`.

### F-11 · P3 · «Xanaya dərs qoy» dialoqunda kiçik UX problemləri
* **Korpus** seçicisinin seçimləri sadəcə `1`, `2`, `3`, `5`, `Bütün korpuslar` (başlıq «Korpus» var, amma seçimin özü rəqəmdir). Otaq mətni «201 · 20 nəfər» düzgündür; korpusa görə süzgəc işləyir (53/150 otaq) ✅.
* **Fənn** seçicisində boş «Seçin» yoxdur; müəllim seçilməyəndə **ilk fənn** («QKU-145 — Azərbaycan tarixi») avtomatik seçilir → səhvən «Cədvələ yaz» yanlış fənni yerləşdirə bilər.
* **375 px:** səhifədə üfüqi sürüşmə yoxdur ✅, dialoq tam ekrandır ✅; lakin «Uyğun vaxtlar» şəbəkəsi (`.sedit-plan__slot`, 48 ədəd) 26 px hündürlükdə, rejim düymələri (`.sedit-plan__mode`) 26 px — 44 px hədəfdən kiçik (`shots/12_…`).
* «Bərpa et» dialoqunda «ƏMR TARİXİ» etiketi yuxarıdakı sahəyə yapışıb (boşluq yoxdur, `shots/07_…`).
* **Fayl:** `apps/accounts/static/accounts/css/schedule_editor_planner.css`, `…/profile/sections/schedule/_cell_fields.html`, `teaching_office/_movement_extra_fields.html`.

### F-12 · P3 · Məcburi profil qapısı bütün `/exams/` yolunu azad edir
* `m.babyev` (FİN/telefon boş, qapı AÇIQ): `/accounts/profile/` → 302 `…/complete-profile/`, `/jurnal/` → 302 (`?next=`), AJAX → 403 JSON `profile_completion_required` ✅;
  **`/exams/center/rooms/` → 200** (imtahan mərkəzinin idarə səhifəsi). Səbəb: `EXAM_PREFIXES = ("/exams/",)` (şərh yalnız tələbənin imtahan axınını nəzərdə tutur). Heyət idarə səhifələri bu qaydaya düşür (`t43.py`).
* **Fayl:** `apps/accounts/middleware_profile_completion.py` (`EXAM_PREFIXES`, `_is_exempt_path`).

### F-13 · P3 · «Məlumat natamam» süzgəci qapının mənasından fərqlənir
* `GET /accounts/rim/search/?flag=incomplete&counts=1` → **8 380** nəticə (tələbə 7 612, aktiv heyət 47). `manage.py profile_completion_report --org qku` isə qapının dayandıracağı hesabları **11** (tələbə) / 0 (heyət) deyir
  («azad / rolsuz: 9 612»). Süzgəc `_incomplete()` azadlıqları (ilk-giriş axınındakı hesab, `qa.*`, arxiv) tətbiq etmir, sənəd şərhi isə «Qapının dayandıracağı hesablar» deyir.
* Tab sayı (`counts.all`) süzgəclə ardıcıldır ✅; yalnız RİM rəhbəri və HR çağıra bilir (digərləri 403).
* **Fayl:** `apps/accounts/services/rim/search.py::_incomplete`. Klonda gate-i sınamaq üçün `qa.*` olmayan hesab lazımdır (§0).
* Qapı səhifəsi özü yaxşıdır: yalnız boş sahələri göstərir, hər birinə «Nəyə lazımdır» izahı, FİN/telefon/e-poçt validasiyası xəta mesajları ilə (`t43.py`).

### F-14 · P3 · Sistem monitorinqi → «Loglar»
* **Xəta halı (Loki əlçatmaz):** «Log mənbəyinə qoşulmaq olmadı: Loki xidmətinə bağlantı qurulmadı…» + `{job="docker"} · 1 saat` ✅ (`shots/05_…`). Lakin bu halda **«Bütün konteynerlər» / «Bütün səviyyələr» seçiciləri `is-enhanced` olmur** (native `<select>`, 240 px) — yalnız Loki cavab verəndən sonra stilli komponentə çevrilir.
* **Boş hal (saxta Loki):** `streams_known=0` → «Loki son 6 saatda heç bir konteynerdən log almayıb — problem log toplayıcıdadır (promtail), sorğuda deyil»; `streams_known=5` → yalnız «bu sorğuya uyğun log yoxdur» ✅ (`shots/10_…`). HTTP 500, yararsız JSON, `status:error` hallarında `error.kind` düzgün.
* **Sirr maskası:** HTTP 500 cavabında `token=SECRETTOKEN123` → `token=***` ✅; sətirlərdə `password=`, `Authorization: Bearer …`, `sessionid=` maskalanır, `<script>` mətn kimi göstərilir ✅. Lakin Loki **`{"status":"error","error":"… password=hunter2"}`** cavabının `detail`-i maskalanmır
  (`logs.error_response` → `LokiClient._fetch`, `str(payload.get("error"))[:200]`).
* **Fayl:** `apps/monitoring/clients.py::LokiClient._fetch`, `apps/accounts/static/accounts/js/monitoring/system_monitoring*.js`.

### F-15 · P3 · «Sistem tənzimləmələri» mətnləri
* Köməkçi mətnlərdə qeyri-sözlər təkrarlanır: «**Söndürülüdə** …», «**Yanılıda** …», «**Yanılıdırsa** …» (`core/runtime_settings.py`: akademik qaydalar, sillabus, jurnal, AI, imtahan). Düzgün: «söndürüləndə/söndürülübsə», «yandırılanda/yandırılıbsa».
* Validasiya özü sağlamdır (§5).

### F-16 · P3 · Məlumat / reyestr müşahidələri
* Qrup seçicilərinin başında `.` adlı qrup (id `d539bcef…`, Psixologiya fakültəsi), siyahıda `test1543`, `testuchunqrup2`, `testqrup-localda`, `Silinmelidir`, `Xaric olanlar`, `aaa` (ixtisas). Prod-da da varsa kataloqdan çıxarılmalıdır.
* Qruplar reyestri: «KURATORSUZ 822» (bütün qruplar), Kurs/Dil sektoru sütunları «—». `ensure_parent_groups` (dry-run: 14 ailə, 8 mövcud, 3 yaradılacaq, 22 bağlanacaq, 3 qeyri-müəyyən — ikisi `duplicate_parent`: iki «235 K» qrupu) **işləyir**, amma ana/alt qrup əlaqəsi reyestrdə göstərilmir
  (`234 KE-1` sətrində «alt qrup, ana: 234 KE az» işarəsi yoxdur).

### F-17 · P3 · Yük bölgüsü — kiçik
* `distributed` tapşırığı olan kafedrada «**Tapşırıq yarat**» düyməsi görünür (idempotent olsa da qarışdırır); `shots/08_…` yuxarısında.

---

## 4. İş axını yoxlamaları — nəticələr

### 4.1 Yükün düzəliş axını (RİM / kafedra müdiri) — **OK**
(`t6`–`t10`, `t68`)
* Oxu: RİM / prorektor / rektor / tədris şöbəsi hamısı, kafedra müdiri yalnız öz kafedrasının tapşırığı (başqası 403), dekan yalnız `workload-overview`/`approval`, tyutor öz kafedrasını **oxuyur**, müəllim/HR/imtahan mərkəzi/tələbə 403.
* Yazı (`row_save`, `row_delete`, `bolgu`, `bolgu/sil`, `bolgu/tesdiq`, `duzelis`): müəllim 403 (`view_denied`/`distribute_denied`), RİM əməkdaşı 403 (`manage_denied`), yad kafedra müdiri 403, tyutor 403, tədris şöbəsi 403, dekan 403.
* Kafedra müdiri: səbəbsiz → **409 `workload.amendment_required`**; `amend_reason=correction` + qeyd ilə 200, tapşırıq `amended`, sətir `is_amend_target`; cəmi bölünmüşdən aşağı salmaq → 409 `total_below_assigned`; `shrink_assignments` ilə bölgü avtomatik 15→14; bölgünü sil / yenidən əlavə et 200; «Bölgünü təsdiqlə» → `distributed`.
* RİM rəhbəri eyni sətirləri düzəldib (saat 15, bölgü 15), artıq saat → 403 `hours_exceeded`, təsdiq `notified: 15`.
* «Mənim dərs yüküm» (`kamran.imameliev`, RİM rəhbəri + 25 saatlıq yük): 13 sətir fənn+qrup üzrə birləşir («Mühazirə 30 · Seminar/təcrübi 30»), hər sətirdə «Redaktə et» (`?section=workload-distribution&chair=…&row=…`); müəllimdə (`qa.teacher`) 0 «Redaktə et» ✅; Excel ixracı 200.
* **UI** (`shots/08_…`, `09_…`): düzəliş bildirişi «Bölgü təsdiqlənib. Sətri, saatı və ya müəllimi dəyişə … hər dəyişiklikdə düzəliş səbəbi və qeydi soruşulur», sətir modalı sahələrlə dolu gəlir, «Qruplar» **stilli axtarışlı çoxseçimli** (Hamısı / Təmizlə, onay qutuları) ✅.
* `fix_task_row_hours` (quru icra, aktor `qa.rector`): `amendments_opened=3 · assignments_removed=2 · hours_removed=90 · reconfirmed=1 · rows_changed=2 · rows_matched=2` ✅ (`--apply` verilmədi). Aktor aktiv superuser olmalıdır (klonda `qa.rector`).

### 4.2 Cədvəl redaktoru — **OK, F-05/F-10/F-11 istisna**
(`t12`–`t14`, `t57`–`t60`, `shots/01`–`03`)
* «Xanaya dərs qoy»: müəllim / fənn / dərsi aparan müəllim / növ / həftə / gün / saat / **Korpus + Otaq** stilli seçicilərdir; otaq korpusa görə süzülür; mətn «201 · 20 nəfər».
* «Uyğun vaxtlar»: 3 rejim («Hər ikisi / Müəllim / Qrup üçün uyğun»); `plan` cavabı: `cells[]` statusu `free|teacher|group|room`, `top[]` qısa siyahı (gün + boşluqsuz), `rooms.rows[]` (`capacity`, `fits`, `same_campus`, `is_lab`); müəllim məşğul xana səbəblə («Müəllimin Şənbə 08:30-da 235 KE ing qrupunda dərsi var (QKU-2693).») ✅. «Qrup» rejimində müəllim-məşğul xana `suggested:true` olur (dizayn).
* Toqquşmalar: `save` müəllim toqquşması → 409 `conflict`; qrup eyni vaxt → 409 `group_conflict`; `check_move` → 200 `ok:false, conflicts[]`; `move` məcburi olmadan 409; `force=1` səbəbsiz → 400 `reason_required` (≥10 simvol); azad xanaya `move` 200; `delete` yumşaq silmə 200.
* Əhatə: dekan/koordinator öz qruplarını görür (29 / 12), yad qrup `sm_group` ilə göndərilsə `select` ilk əhatəli qrupa düşür və yad qrupun slotu görünmür ✅; `plan` yad qrup → 403.
* Yazma açarı: RİM / dekan / koordinator ✅; RİM əməkdaşı, prorektor, tədris şöbəsi → düymə yox, `action` 403 ✅.

### 4.3 Qruplar reyestri — **OK, F-06…F-08 istisna**
(`t18`, `t21`, `t26`, `t51`, `shots/06`, `07`, `11`)
* Oxu əhatəsi: dekan/koordinator yalnız öz fakültəsi (yad qrup → 404), kafedra müdiri/tyutor öz fakültəsi (`can_manage:false`), RİM/rektor/tədris şöbəsi/prorektor `can_manage:true`.
* Çekmecə: statuslar (Qeydiyyatlı / Məzuniyyətdə / **Xaric edilib** süzgəci), «Qrupu dəyiş · Dondur · Uzaqlaşdır» düymələri, xaric edilmişdə «Bərpa et» + «Əmr № QA/9 (17.10.2026)» ✅. Dialoq sahələri: Əmr nömrəsi*, Əmr tarixi*, Səbəb (istəyə bağlı); məcburi sahələr dolanana qədər təsdiq düyməsi disabled, sonra 200 ✅ (UI ilə bərpa sınandı).
* Hərəkət hüquqları: `people.move_students` — RİM, rektor, tələbə xidmətləri (kafedra müdiri, tyutor, RİM əməkdaşı, müəllim 403).

### 4.4 «Fəndən azad et» — **OK**
(`t31`–`t33`, `t65`, `shots/04`)
* Düymə görünür: RİM, rektor*, YTİM dekanı (öz fakültəsi); görünmür: müəllim, tədris şöbəsi, kafedra müdiri (jurnal 404). POST: müəllim/tədris şöbəsi/kafedra müdiri/imtahan mərkəzi/HR → **403**, tyutor/yad dekan → **404**.
* Dekan: səbəbsiz/sənədsiz azad 200 → «**Azad edilənlər 1**» qatlanan siyahı («Fəndən azad edildi · Nailə Quliyeva · 17.10.2026 17:32 · Bərpa et») → «Bərpa et» 200 → siyahı yox. Təkrar azad 409 `not_enrolled`; təkrar bərpa 404 `not_revertable`; yanlış tarix 400 `invalid_date`; yanlış id 404.

### 4.5 Semestr açılışı yazma qapıları — **OK** (oxu: F-01)
`remind_readiness / send_to_chairs / lock / cancel_offering` → kafedra müdiri, dekan, tyutor, koordinator, RİM əməkdaşı, müəllim: **403**. Düymələr RİM rəhbəri, rektor, prorektor, tədris şöbəsi rəhbəri üçündür (tədris şöbəsi əməkdaşında «kilidlə» yoxdur).

---

## 5. «Sistem tənzimləmələri» — **OK**
(`t34`, `t36`, `t37`, `t38`)
* Yazma yalnız RİM rəhbəri (+ superuser): prorektor, kafedra müdiri, dekan, HR, imtahan mərkəzi, tədris şöbəsi, RİM əməkdaşı, müəllim → 403 (bölmə GET də 403).
* Sahələr: `journal.lesson_edit_minutes` / `mark_edit_minutes` (1–4320, dəqiqə), `journal.late_entry_days` (0–30), `journal.activation_write_minutes` (5–1440), `password.min_length` (6–32), `profile.required_fields_enabled` + `require_fin/phone/email`.
* Hədd xaricində dəyərlər → 400 + sahə xətası «Dəyər 6–32 aralığında olmalıdır» (5, 33, `abc`, boş, −3, 8.5, XSS sətri); bool üçün «maybe» → «Yandırılmış və ya söndürülmüş olmalıdır»; cüt (`staff_rate_min` > `max`) → «Ən az dəyər ən çox dəyərdən böyük ola bilməz»; naməlum açar sakitcə atılır; `ai.model` yararsız → «Siyahıdan seçin». Brauzerdə `min/max` atributları + native yoxlama işləyir. Boşluqlu `" 12 "` → 12 saxlanır (trim).
* Defolta bərabər dəyər sətri silir (`reset:true`) ✅; qeydlər auditə düşür.
* Parol siyasəti: `abc`/`abcdefg` → «Parol ən azı 8 simvol olmalıdır»; `12345678`, `Qwerty12`, `Parol123`, istifadəçi adı → «çox asan»; `aaaaaaaa`, `     8888` (boşluqlu) qəbul olunur (sahibin «sadə parol» qərarı).

## 6. Digər yoxlamalar

* **«Məlumat natamam» və qapı:** §F-12/F-13. Səhifə mətni: «Məlumatlarınızı tamamlayın … FİN kod / Mobil telefon / Şəxsi e-poçt — Nəyə lazımdır: …», məxfilik qeydi, «Saxla və davam et» ✅. `/live/`, `/static/`, `/health/`, `/exams/…` açıq; `logout` POST-dur.
* **Konsol/CSP:** CSP başlığı aktivdir (`script-src 'self' clarity.ms`); `scripts/check_inline_assets.py` → «inline yoxdur» ✅; brauzer konsolu cədvəl redaktoru səhifəsində təmiz idi (CSP pozuntusu/xəta qeydə düşmədi); qalan səhifələrin konsolunu ayrıca oxumadım. Qeyd: lokal klonda Microsoft Clarity skripti CSP-də icazəlidir (`_clck/_clsk` çərəzləri görünür).
* **375 px:** `workload-distribution`, `schedule-manage` (+dialoq), `groups-registry`, `system-settings`, `rim-center` — `scrollWidth == 375` (üfüqi səhifə sürüşməsi yoxdur; cədvəllər öz konteynerində sürüşür) ✅. Toxunma hədəfləri: F-11.
* **Native `<select>`:** `rim-center`, `system-settings`, `semester-opening`, `workload-center`, `student-registry`, `hr-analytics`, `org-members`, `people-students/teachers`, `audit-log`, `journal-hygiene`, `curriculum-editor`, `schedule-manage` — hamısı stilli komponent; istisna: F-14.
* **«EMS Arena»:** istifadəçiyə görünən mətndə yoxdur (şablonlar/`.po` təmiz; yalnız kod şərhləri `apps/organizations/decorators.py`, `apps/accounts/models.py`, `templates/partials/_seo_head.html`). Brend «Qərbi Kaspi Universiteti» ✅.
* **Tərcümə sızması:** 537 bölmə fraqmentində ingilis sözlər (Save/Cancel/Loading/…) yoxdur («Status» azərbaycancadır).
* **RİM mərkəzi / insan axtarışı:** `flag=incomplete|initial|never|unverified`, `kind`, `status`, `counts=1` işləyir; yalnız RİM rəhbəri və HR üçün (HR → F-03).

## 7. Nə OK idi (qısa)

* Rol → menyu uyğunluğu 2026-10-13 rol auditi qərarlarına uyğundur (prorektor/tədris şöbəsi/RİM əməkdaşı/imtahan mərkəzi fərqləri, tyutor=koordinator).
* Yük düzəliş axını (RİM + kafedra müdiri) və müəllim qadağası; «Redaktə et» keçidləri; `fix_task_row_hours` quru icrası.
* Fəndən azad et / bərpa (bütün rollar üçün düzgün 403/404/409), «Azad edilənlər» siyahısı.
* Dondur/Uzaqlaşdır/Bərpa et validasiyası (əmr №/tarixi məcburi, səbəb istəyə bağlı, keçid qaydaları, `unknown_kind`, `record_not_found`).
* Sistem tənzimləmələrinin validasiyası və rol qapısı; parol uzunluğu dəyişikliyi `validate_password`-a dərhal təsir edir.
* Monitorinq loglarının xəta/boş/dolu halları, sirr maskası, XSS yoxdur.
* Cədvəl redaktorunun dialoqu, otaq/korpus süzgəci, uyğun vaxt paneli, toqquşma/məcburi köçürmə axını.
* 537 bölmə fraqmenti: 0 × 500.

## 8. Təkrar istehsal üçün

```bash
cd /Users/elvin/Developer/EMSArena
Q=/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/qa
. $Q/env.sh            # dev-clone.env (emsarena_app), config.settings.local
venv/bin/python manage.py shell < $Q/t45.py   # məs.: F-01
# sahib DSN-i yalnız oxu/miqrasiya üçün: . $Q/envowner.sh
```
Skript → tapıntı: `t44/t45/t46` F-01 · `t48/t50/t71` F-02 · `t18/t19/t20/t41/t42` F-03 · `t63/t64` F-04 · `t15/t16/t17` F-05 · `t26/t28` F-06 · `t21/t24/t27` F-07/F-08 · `t57` F-10 · `t43` F-12/F-13 · `t39/t67 (+fakeloki.py)` F-14 · `t36/t37` §5.
