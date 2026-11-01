# Kafedra problem blankları — nəticə reyestri (RİM), 01.11.2026

Bu sənəd kafedraların «problem blankları»nda qaldırılmış məsələlərin **faktiki canlı
(production) vəziyyətini** bir yerə yığır. Mənbələr: repo sənədləri (`docs/ops/*.md`,
`docs/operations/*.md`, `docs/REVIEWED_*.md`), management command-ların `help`
mətnləri və GitHub Actions run logları (`prod-data-ops.yml` + `reviewed-*.yml`,
27.10.2026 01:41 UTC – 01.11.2026 18:57 UTC, 244 run). Heç bir sətir sənəd
mətnindən «tətbiq olunub» kimi götürülməyib — tətbiq faktı yalnız run logundakı
`mode=apply` / `status=applied` + batch/receipt ilə qeyd edilib.

Status açarları:

| İşarə | Mənası |
|---|---|
| ✅ | Production-da tətbiq olunub (run ID, batch/receipt var); təkrar dry-run `already_*` qaytarıb |
| 🟡 | Kod/mənbə hazırdır, canlı tətbiq GÖZLƏYİR (dry-run keçib, apply yoxdur — və ya workflow heç işlədilməyib) |
| 🔴 | Dry-run guard (qoruyucu) ilə dayanıb — qərar və ya əlavə düzəliş lazımdır |
| ⚙️ | Kod/konfiq dəyişikliyi — data əməliyyatı tələb etmir |

Vaxtlar UTC-dir (Bakı = UTC+4). Run keçidi: `https://github.com/equrbanov7/EducationManagementStudentArena/actions/runs/<run id>`.

## 1. Tətbiq olunub (production)

| № | Case / komanda | Müəllim · qrup · fənn | Problem | Nə edildi | Tətbiq (UTC · run · batch/receipt) | Blank üçün cavab mətni |
|---|---|---|---|---|---|---|
| 1 | MR-000027 · `recover_mr27_journal` | Jurnal `567a6fc3-…`; legacy qrup 902; legacy tələbələr 10127, 10128; ixtisas 103 (Bioekologiya, mag); İbrahim 2510; dərs müəllimi Ramiz | 14.09-dan sonra yaranmış 2 tələbə və master ixtisası delta ilə gəlməmişdi; 21 tarixi xana və 05.10 mühazirəsi çatmırdı | Master proqramı `005566-M` + boş curriculum, 2 legacy hesab, 2 qeydiyyat, 1 tarixi dərs, 15 xana; 22.10 bəyanatı (10/10/9) ayrıca bayraqla | ✅ 30.10 11:12 · 41046425582 · created_user=2, enrollment=2, lesson=1, lessonmark=15, marks_already_present=6 | Tələbələr sistemə əlavə edildi, 21 tarixi xana bərpa olundu, 05.10 dərsi yaradıldı. Həll olunub. |
| 2 | MR-000046 · `recover_mr46_syllabus` | Jurnal `acc97b99-…`; müəllif/sahib 7942; köhnə sillabus 8891 | Müəllimin köhnə jurnal sillabusu yeni jurnalda yox idi | Köhnə sillabus (23 mövzu, 18 sərbəst iş, 10 bölmə) `approved` versiya kimi bərpa edildi | ✅ 28.10 23:30 · 40787856376 · `mr46-20261028-233409-89bb` | Köhnə sillabus tam məzmunla bərpa edilib və təsdiqlidir. Həll olunub. |
| 3 | MR-000034 · `repair_mr34_teacher_load` | Hesab 11588 → 9510; 3 yük sətri, 5 təyinat, 135 saat | Dublikat hesab keçidindən sonra 5 təyinat köhnə hesabda qalmışdı | 5 təyinat canonical hesaba (9510) bağlandı; rol/jurnal dəyişməyib | ✅ 01.11 04:51 · 41274673266 · receipt `34027065-b4b5-47f3-a34b-9b83c5c8960c` (assignments=5, hours=135) | Dərs yükü düzgün hesaba keçirildi (5 təyinat, 135 saat). Həll olunub. |
| 4 | Biostat 9544 · `repair_biostat_seminar_share` | Müəllim 9544; BIO jurnalı `e09d3997-…`; mühazirəçi 8170 saxlanılıb | Seminar müəlliminin seminar xanalarına girişi yox idi | Yalnız `seminar` növlü, explicit siyahılı `workload` payı yaradıldı (roster=30, 15 saat) | ✅ 01.11 04:57 · 41275016488 · baseline `38eb72bf…`; 05:01 dry-run `already_present=1` | Seminar müəlliminə öz seminar xanalarına giriş verildi; mühazirəçinin girişi dəyişməyib. Həll olunub. |
| 5 | 233KE / 233 KE az · `repair_233ke_group_alias` | Qruplar `233KE` və `233 KE az`; Aida, Jalə; Optimallaşdırma üsulları, Təcrübə, Kompleks analiz | Eyni qrup iki adla yaranmışdı; jurnal/yük sətirləri parçalanmışdı | 7 sətir düzəldi, 5 cədvəl slotu yaradıldı, 26 qonaq qeydiyyatı; alias passiv + `canonical_group` | ✅ 31.10 17:47 · 41226205652 · `ke233-20261031-175057-d7e0`; 17:51 `already_applied=1` | Dublikat qrup birləşdirildi; jurnallar və dərs yükü canonical qrupa bağlandı. Həll olunub. |
| 6 | 135 Sİ · `repair_si135_legacy_roster` | Qrup 135 Sİ; köhnə 932 (23 tələbə) / 933 (22 tələbə) | Tələbələr alt qruplara mənbəyə uyğun bölünməmişdi | 45 tələbə iki alt qrupa köçürüldü, 1 nəfər əsas qrupda saxlanıldı | ✅ 30.10 08:03 · 41023911710 · `si135-roster-20261030-080722-9b94a85f` | Alt qrup bölgüsü köhnə sistemə uyğun bərpa edildi (23+22). Həll olunub. |
| 7 | 135 TSPX · `repair_tspx_legacy_roster` | Qrup 135 TSPX; 49 tələbə | Eyni | 23 + 26 tələbə alt qruplara köçürüldü, 1 nəfər əsas qrupda | ✅ 30.10 08:41 · 41028183457 · `tspx-roster-20261030-084530-e7b65162` | Alt qrup bölgüsü bərpa edildi (23+26). Həll olunub. |
| 8 | 536 Bİ/MU · `repair_bi_mu536_legacy_roster` | Qrup 536 Bİ/MU; 41 tələbə | Eyni | 41 tələbə (MU 21 + Bİ 20) alt qruplara köçürüldü | ✅ 30.10 09:27 · 41033607119 · `bimu536-roster-20261030-093134-995e4739` | Alt qrup bölgüsü bərpa edildi (21+20). Həll olunub. |
| 9 | 12 M/S cütü · `repair_balanced_workload_pairs` | 12 sabit mühazirə/seminar cütü (`balanced_pairs_spec.py`) | Mühazirə/seminar cütlərində assignment/plan/cəm uyğunsuzluğu | 12 sətir canonical ardıcıllıqla düzəldildi | ✅ 30.10 00:27 · 40979808213 · `balanced12-20261030-003108-0d1c` (changed_rows=12) | 12 mühazirə/seminar cütünün saat bölgüsü düzəldildi. Həll olunub. |
| 10 | Kafedra dəsti · `repair_owner_activity_batch` (rows seçimi) | 22 sabit sətir (`owner_activity_spec.py`); «rows:c27218…» seçimi | Eyni jurnal sahibinin fəaliyyət bölgüsü yük sətirlərində düzgün deyildi | 21 sətir düzəldi, 21 fəaliyyət təyinatı yaradıldı (3 sətirlik seçim) | ✅ 30.10 00:39 · 40981078712 · `owneract-20261030-004316-2da9` | Seçilmiş sətirlərdə fəaliyyət bölgüsü düzəldildi. (Kafedra üzrə tam seçim üçün bax §3 №10.) |
| 11 | İki təkrar seminar · `repair_repeated_sections_workload` | Sətirlər `52debb1c-…`, `be8e8251-…` | Təkrar seminar sayı səhv idi | 2 sətir düzəldildi | ✅ 30.10 00:57 · 40982865089 · `sections2-20261030-010040-d8c6` | Təkrar seminar sayı düzəldildi. Həll olunub. |
| 12 | Bilal 135T · `recover_workload_syllabi` | Bilal; qrup 135T; Tarix fəlsəfəsi; köhnə sillabus 8430 | Yük yoxlamasında jurnalda sillabus boşluğu | Öz köhnə sillabusu (8 mövzu, 10 bölmə) bərpa edildi | ✅ 30.10 01:06 · 40983808194 · `wksyl-20261030-010951-6680` | Köhnə sillabus bərpa edildi. Həll olunub. |
| 13 | 6 yük jurnalı · `recover_six_workload_syllabi` | Altı sabit yük jurnalı | Öz-mənbə sillabusları çatmırdı | 6 sillabus (59 mövzu, 41 sərbəst iş, 60 bölmə) | ✅ 30.10 12:15 · 41053928949 · `sixsyl-20261030-121845-70b7` | 6 jurnalın sillabusu bərpa edildi. Həll olunub. |
| 14 | 15 boş yük jurnalı · `recover_empty_workload_syllabi` | On beş boş yük jurnalı | Eyni | 15 sillabus (119 mövzu, 35 sərbəst iş, 150 bölmə) | ✅ 31.10 22:56 · 41250407091 · `emptysyl-20261031-230035-5030`; 23:00 `already_present=15` | 15 jurnalın sillabusu bərpa edildi. Həll olunub. |
| 15 | İnsan genetikası · `recover_genetics_workload_syllabus` | İnsan genetikası jurnalı | Eyni | 1 sillabus (15 mövzu, 28 sərbəst iş) | ✅ 01.11 01:07 · 41259700286 · `gensyl-20261101-011045-8874` | Sillabus bərpa edildi. Həll olunub. |
| 16 | Boş qaralama yanında öz-mənbə sillabus (2 case) · `recover_blank_draft_syllabi` | source 7474 → 123f89bf (müəllif 8306, QKU-14); source 8744 → 0a71ca40 (müəllif 8333, QKU-846) | Jurnalda yalnız boş insan qaralaması var idi, təsdiqli sillabus yox | Qaralama saxlanmaqla ayrıca `approved` mənbə versiyası əlavə edildi | ✅ 01.11 16:03 · 41324350562 · receipt `c94e96ec-2dfe-4327-a770-f9d517d93e47` (cases=2, human_drafts_preserved=2); 16:04/16:05 `already_present` | Hər iki jurnalda təsdiqli sillabus əlavə edildi, qaralamalar toxunulmayıb. Həll olunub. |
| 17 | 235 İT sektor · `repair_it235_sector` | Qrup 235 İT; 2 mənbə-təsdiqli sektor keçidi | Sektor səhv idi | 2 keçid tətbiq olundu | ✅ 01.11 01:12 · 41260122311 · applied=2; 01:16 pending=0 | Sektor keçidləri tətbiq edildi. Həll olunub. |
| 18 | 132 F dublikat · `repair_empty_132f_alias` | `132 F` (legacy 388) → `132F` (legacy 367) | Tam boş dublikat qrup | Boş qrup passiv + `canonical_group`; köçürmə/silmə yoxdur | ✅ 01.11 01:18 · 41260542035 · receipt `6535de05-6072-4d5f-b95a-7cf4dd680865` | Boş dublikat qrup passivləşdirildi, əsl qrupa yönləndirildi. Həll olunub. |
| 19 | IT row84 · `repair_it8179_load` | IT mənbəsinin 84-cü sətri | Kontakt saatları ikiqat sayılırdı (2 sətir) | Sətirlər birləşdirildi: 180 → 90 saat, 1 artıq sətir silindi, 2 fiziki jurnal saxlanıldı | ✅ 01.11 03:30 · 41269432948 · baseline `b1be2632…`; 03:34 `already_present=1` | Artıq sayılan yük düzəldildi (180 → 90 saat). Həll olunub. |
| 20 | Qoşqar · `repair_qosqar_journals` (source6591) | Qoşqar; iki jurnal cütü; modelling sillabusu | Səhv fənn bağı, boş dublikat açılışlar, cədvəl slotları | 2 boş açılış retire, 2 fənn bağı düzəldi, 1 öz sillabus payı bərpa, 8 slot yaradıldı / 8 park, 1 səhv sətir silindi | ✅ 01.11 04:39 · 41273962256 · baseline `139c7d4d…`; 04:43 `already_present=1` | Jurnal cütləri düzəldildi, sillabus payı bərpa olundu. Həll olunub (modelling guard-ı üçün bax §3 №6). |
| 21 | Magistratura 10 sətir · `repair_master_degree_metadata` | 10 yük sətri; Qadir müəllimin 2 jurnalı | `degree_level=bachelor` əvəzinə `master` olmalı idi | 10 sətirdə yalnız `degree_level` düzəldi | ✅ 01.11 04:45 · 41274324537 · receipt `2660ccbb-e5b1-47c7-9a70-91ce61f298d1` (planned=10); 04:49 `already_applied` | 10 magistratura sətrinin dərəcə səviyyəsi düzəldildi. Həll olunub. |
| 22 | Tətbiqi riyaziyyat · `repair_applied_math_journal` | Mənbə 14316; öz sillabus 6690 | Səhv sətir + boş açılış; sillabus çatmırdı | Boş açılış retire, səhv sətir silindi, 7 dərs/81 xana saxlanıldı, öz sillabus (15 mövzu, 15 sərbəst iş) yaradıldı | ✅ 01.11 06:47 · 41282211828 · baseline `2fde8761…`; 06:51 `already_present=1` | Jurnal ID-ləri saxlanmaqla düzəldildi, sillabus bərpa olundu. Həll olunub. |
| 23 | Kafedra contact hüquqları · `repair_reviewed_chair_contacts` | tarix_europe · tarix_region · az_morphology · az_onomastics | Mənbədəki müəllim/növ paylarına uyğun davamiyyət/giriş hüquqları çatmırdı | 4 kursda attendance/barred düzəlişləri | ✅ 01.11 06:53 `73b14910-c8c2-477a-ac9c-af6f1242d377` (30/10) · 06:59 `097daf71-f77d-46ab-aa0a-b3b2745bc85f` (14/0) · 07:06 `d769ba9d-fda2-48a7-8e45-89cac2df4ed5` (52/0) · 07:12 `4da32de1-24cc-48bd-97fd-1b9b7f2d5c46` (27/0); hamısında sonra `already_correct` | 4 fənn üzrə müəllim girişləri mənbəyə uyğunlaşdırıldı. Həll olunub. |
| 24 | Onomastics ev siyahısı · `repair_onomastics_roster` (workflow) | Onomastics (2 jurnal); 5 ev tələbəsi | Contact düzəlişindən sonra 5 tələbənin paylara bağlantısı çatmırdı | 10 bağlantı əlavə edildi; sahibin fallback girişi daraldıldı | ✅ 01.11 07:18 · 41284274029 · receipt `402b26fe-ebc4-442e-b76e-287d173db386` (links=10); 07:19 links=0 | Tələbə bağlantıları tamamlandı. Həll olunub. |
| 25 | Leyla kataloq · `repair_reviewed_leyla_catalog` (workflow) | Leyla; yük sətirləri `02d98bd9-…` (233 İ az), `da34a218-…` (235 İ-1/İ-2 az); 3 dolu jurnal | İki yük sətri sintetik fənn kodlarına bağlı idi; 6 cədvəl slotu yanlış jurnallarda | 2 `subject_id` düzgün kataloqa keçdi, 6 slot park + 6 surət | ✅ 01.11 18:52 · 41338846859 · receipt `976d6c6c-5108-40b8-a930-b3209aa1674b` (rows=2, slots=6); 18:53 `already_applied` | Fənn bağları və cədvəl düzəldildi; 550 mövcud xana toxunulmayıb. Həll olunub. |
| 26 | Nigar + Aruz + Vəfa 234KE — 3 yük FK · `repair_reviewed_catalog_load_chain` (workflow) | Üç sabit yük sətri (iki kataloq + Vəfa legacy mənbəsi) | Yük sətirlərinin fənn bağı səhv kataloqa idi | 3 FK bir atomik əməliyyatda düzəldi (26 model, 771 qorunan sətir dəyişməz) | ✅ 01.11 18:31 · 41337017867 · receipt `8a4bd43c-a63d-4a13-9769-93b207968e4d` (rows=3); eyni job-da `already_applied` təkrarı | Üç yük sətrinin fənn bağı düzəldildi; qiymət/kredit/sillabus toxunulmayıb. Həll olunub. |
| 27 | Kafedra Forma-1 mənbə sətirləri · `repair_reviewed_workload_batch` | finance45 · chairs1 · chairs2 · policy39 · extra20 · held5 · source105 · safe20 · pending13 | Kafedra mənbəsində olan, sistemdə çatışmayan/yanlış yük sətirləri və jurnallar | Seçilmiş sətirlər üzrə jurnal + sətir yaradılması / patch | ✅ 30.10 05:23 finance45 `source-20261030-052805-9df79d28` (29 jurnal, 23 sətir, 4 patch) · 05:32 chairs1 `…053639-bce311ac` (87 jurnal, 71 sətir) · 06:05 chairs2 `…061002-fd403573` (53 jurnal, 60 sətir) · 07:07 policy39 `…071153-ef2f5dea` (49 jurnal, 39 sətir) · 09:12 extra20 `…091701-eb7301db` (22 jurnal, 15 sətir, 5 patch) · 11:02 held5 (104,117,179,197) `…110658-54002b72` (7 jurnal) · 11:37 source105 `…114210-0679d2e9` · 11:56 safe20 `…120051-6e7644d1` (20 patch) · 31.10 11:46 pending13 `source-20261031-115041-c3b80408` (11 patch) · 17:55 rows 1001,1003 `…175920-0e780fe2` (2 patch) | Kafedra mənbəsindəki sətirlər üzrə jurnallar yaradıldı/düzəldildi (cəmi 247 jurnal, 208 sətir, 42 patch). Rədd olunan sətirlər üçün bax §3 №11–13. |
| 28 | Jurnal xanalarının mənbədən bərpası · `repair_reviewed_journal_content` | 22-51 (jurnallar `1206a0f5-…`, `2bcf2c6e-…`) · absence4 · salman2 | Köçürülməmiş dərs/xanalar | 22-51: 7 dərs + 35 xana; absence4: 4 xana; salman2: 1 xana | ✅ 31.10 10:34 `content-20261031-103925-fada92f5` · 11:58 `content-20261031-120332-f25832db` · 12:29 `content-20261031-123416-7ad38c02` | Çatışmayan dərslər və xanalar mənbədən bərpa edildi (42 xana, 7 dərs). Həll olunub. |

### 1a. RİM müraciətləri üzrə toplu düzəlişlər (27–28.10, hamısı tətbiq olunub)

| № | Komanda | Nəticə | Tətbiq (UTC · run) |
|---|---|---|---|
| 29 | `fix_legacy_lesson_kinds` (rim-fix-20261027b) | 115 dərs yoxlanıldı: 70 + 37 dərs lab növünə keçirildi, 16+13 açılış düzəldi | ✅ 27.10 23:56 · 40605452460; 28.10 00:01 · 40606074422 (`--include-mixed`) |
| 30 | `relocate_twin_enrollment` | 22 fantom qeydiyyat əsl açılışa, 117 xana daşındı, 55 fantom dərs silindi | ✅ 28.10 00:07 · 40606680793 |
| 31 | `merge_twin_offerings` | 31 cütdən 29 əkiz açılış birləşdirildi (2186 xana, 204 dərs, 26 sillabus) | ✅ 28.10 00:12 · 40607276345 |
| 32 | `fix_slot_week_parity` | 606 üst/alt slot təsdiqləndi, 46 slot həftəlik oldu | ✅ 28.10 00:18 · 40607877249 |
| 33 | `relocate_superseded_marks` (MR-000010 / 30.1) | 1142 namizəddən 1026 xana varis jurnala daşındı | ✅ 28.10 00:23 · 40608469821 |
| 34 | `apply_journal_shares` (journal-shares-20261027b; mr63) | 440 pay: 17 yaradıldı, 154 yeniləndi, 4 söndürüldü; MR63: 2 pay söndürüldü | ✅ 28.10 00:29 · 40609040660; 19:37 · 40756004574 |
| 35 | `legacy_delta_apply` (redate · unfake · syllabi) | 409 iştirak + 124 qayıb + 53 bal; 14 açılış; 123 sillabus versiyası | ✅ 28.10 00:34 `delta-20261028-043802-ab57` · 00:39 `delta-20261028-044323-0b45` · 05:30 `delta-20261028-093434-e273` |
| 36 | `merge_duplicate_student` | 1 dublikat tələbə hesabı birləşdirildi (31 xana daşındı) | ✅ 28.10 00:45 · 40610769133 |
| 37 | `fix_exam_journal_gaps` | İmtahan 61/62 qrup boşluqları yoxlanıldı (relinked=0, 1 tələbə jurnalsız — variant fənn) | ✅ 28.10 00:50 · 40611343597 |
| 38 | `set_practical_offerings` | 214 açılışda «Praktiki məşğələ» bayrağı | ✅ 28.10 05:23 · 40637764275 |
| 39 | `restore_archived_students` (131 T) | 10 səhvən arxivlənmiş cari tələbənin girişi bərpa edildi | ✅ 27.10 17:06 · 40547439438 |
| 40 | `dedupe_notifications` | 8 qrup, 9 təkrar bildiriş silindi | ✅ 27.10 05:48 · 40457418466 |

## 2. Hazırdır — canlı tətbiq gözləyir

| № | Case / workflow | Müəllim · qrup · fənn | Vəziyyət | Nə etməli |
|---|---|---|---|---|
| 1 | Fəridə — artıq inferensiya slotunun parkı · `reviewed-farida-slot.yml` | Fəridə; AZ1 slotu `68f5682e-…` | 🟡 Workflow heç işlədilməyib; release `reviewed-farida-inferred-slot-20261101` hazırdır | Actions → «Reviewed Farida inferred weekly slot only»: `actor=<superadmin>`, `apply=false` → nəticədəki `baseline` ilə `apply=true`, `confirm=APPLY` |
| 2 | Yarım cütlük saatlar (3 dərs, 2→1 saat) · `reviewed-half-pair-hours.yml` | Bulud texnologiyaları AZ1/AZ2 + ingilis bölməsi; 2026-10-15 15:15 | 🟡 Heç işlədilməyib; release `reviewed-half-pair-hours-v3-20261101` | Eyni addımlar («Reviewed three source-proven half-pair lesson hours») |
| 3 | Source58 q/b bərpası (58 q/b, 9 dərs, 6 açılış) · `reviewed-source58-qb.yml` | 44 qeydiyyat | 🟡 Heç işlədilməyib; release `reviewed-source58-qb-20261101`; sənəd: «təzə sübut olmadan təhlükəsiz tətbiq sayı məlum deyil» | Dry-run → nəticəyə bax → apply (`baseline`, `confirm=APPLY`) |
| 4 | Aydın — köhnə draft source FK · `reviewed-aydin-lineage.yml` | Aydın | 🟡 Heç işlədilməyib (kod 01.11 21:51-də hazırlanıb) | Dry-run → apply |
| 5 | İlahə 336T1 — subject535 bağı + 8668 paylaşımı · `reviewed-ilahe-subject.yml` | İlahə; müəllim 7776; jurnal `caad2073-…` | 🟡 Heç işlədilməyib; diaqnostika exportu (`ilahe_reference_graph`) hazırdır | Dry-run → apply |
| 6 | Jalə — 13980 jurnalının 1797→2295 fənn bağı · `reviewed-jale-subject.yml` | Jalə | 🟡 Heç işlədilməyib | Dry-run → apply |
| 7 | Nigar+Aruz · `reviewed-two-catalog.yml`, Vəfa · `reviewed-vefa-catalog.yml` | — | ✅ Məzmunu §1 №26 (load chain) ilə artıq tətbiq olunub; bu iki workflow yalnız ayrıca yoxlama/undo üçündür | Əlavə iş lazım deyil (dry-run `already_applied` verməlidir) |
| 8 | 336F2 mənbə xanaları · `repair_reviewed_journal_content` (`reviewed-content-336f2-20261101`, target `6a4ffa61-…`) | 336F2 | 🟡 Dry-run keçib (01.11 03:39, baseline `4b1fc5b8…`), apply YOXDUR | Prod Data Ops: eyni inputlar + `apply=true`, `confirm=APPLY`, `row_subject=<təzə dry baseline>` |
| 9 | Pervin45 yük mənbəsi (`reviewed-workload-20261101-pervin45`) | Pərvin | 🟡 Release 01.11 15:45-də yaradılıb; run qeydi yoxdur | `repair_reviewed_workload_batch` dry-run (`roster_tag`, `batch`=SHA, `row_group`=sətirlər) → apply |
| 10 | `sync_workload_journal_shares --year 2026/2027` | Bütün kafedralar | 🟡 Run qeydi yoxdur; sənəd: «əvvəl workload/qrup bərpaları tamamlanmalıdır» (indi tamamlanıb) | Prod Data Ops dry-run → `batch=baselineSHA` ilə apply |
| 11 | Cavid — Maliyyə source35/36 · `repair_cavid_source_batch` | Cavid Xəlilov / Murad11586; 533MU, 403/5MN | 🟡 27.10–01.11 aralığında run qeydi yoxdur | Dry-run → apply (bax `docs/ops/CAVID_SOURCE_35_36.md`) |
| 12 | 197 rəsmi yük dəstinin xanaları (`reviewed-content-20261030-197`) | 197 dəst | 🟡 Yalnız dry-run (30.10 08:10–08:13) | Nəticəyə baxıb apply |

## 3. Dry-run guard ilə dayanıb — qərar / düzəliş lazımdır

| № | Case | Son nəticə (UTC · run) | Guard nə deyir | Növbəti addım |
|---|---|---|---|---|
| 1 | **Dörd mövcud xana (fixed-four QB)** · `repair_reviewed_journal_content`, tag `reviewed-content-20261101-four-exact`, batch `00fd0056…`, targets `03ac22fc-…`, `b9add126-…` | 🔴 01.11 17:49 · 41333391187 · `reviewed_four_contrary_clear_delete_or_malformed_intent` | Audit tarixçəsində iki «texniki» silinmə qeydi bərpanı bloklayırdı | **Codex-in son commit-i (259a180, 22:02) həmin iki qeydi bayt-pinlənmiş «technical cleanup» kimi tanıdır; prod-a deploy olunub (CI 18:24 UTC). Dry-run YENİDƏN işlədilməlidir** — bax §4 |
| 2 | **Source28 (1 seminar, 28 iştirak xanası)** · tag `reviewed-content-20261101-source28`, batch `ce94b0cf…`, target `1aca3f3c-…` | 🔴 10:48 `four_cell_audit_byte_budget_exceeded` → 16:28 `fixed_workload_receipt_semantics_unverified` → 17:25 · 41331379490 xəta tokeni loga ÇIXMAYIB | Token rəqəmli (`reviewed_source28_*`) olduğu üçün log süzgəci onu gizlədirdi | 0e03913 (21:51) süzgəci düzəldib; dry-run yenidən işlədilsin — token görünəcək, sonra qərar (bax §4) |
| 3 | MR-000083 sillabus · `repair_mr83_syllabus` | 🔴 31.10 12:56 · `reviewed_topic_count_changed` | Hədəf sillabusun mövzu sayı baxılan snapshot-dan sonra dəyişib | Təzə snapshot ilə mənbə yenidən baxılmalı, sonra dry-run |
| 4 | MR-000112 saatlar (QKU1150, 30M15S) · `repair_mr112_hours` | 🔴 31.10 13:13 · `exact_version_missing` | Gözlənilən sillabus versiyası tapılmır | Versiya ID-si yenidən müəyyənləşdirilməli |
| 5 | Qoşqar dublikat · `repair_qosqar_duplicate` | 🔴 01.11 01:05 · `reviewed_schedule_conflict` | Cədvəl toqquşması | №20-nin (qosqar_journals) tətbiqindən sonra yenidən dry-run; qalırsa cədvəl baxılmalı |
| 6 | Qoşqar modelling · `repair_qosqar_modelling` | 🔴 01.11 01:04 · `empty_offering_has_content_or_history_registrar_journalhygienedecision` | Boş sayılan açılışın hygiene qərarı var | `repair_qosqar_journals` (04:39) modelling sillabus payını bərpa edib — bu komandanın hələ lazım olub-olmadığı yoxlanmalı |
| 7 | 235 SBİO · `repair_sbio235_workload` | 🔴 30.10 00:32 · `task_not_amended` | Tapşırıq sənədi düzəliş (amendment) vəziyyətində deyil | Tapşırıq düzəliş axınına salınmalı, sonra dry-run |
| 8 | Owner activity — kafedra üzrə seçim (`chairs:14a0…`) | 🔴 30.10 00:35 · `blocked_rows=3c4de001-b2d7-4b87-a6f1-a4660e27f628:teacher_or_activity_assign` | 1 sətirdə müəllim/fəaliyyət təyinatı bloklayır | Həmin sətir ayrıca baxılmalı; rows seçimi tətbiq olunub (§1 №10) |
| 9 | Math sabit row `eb41b840-…` (Applied Math amendment) | 🔴 01.11 03:28 · `wrong_row_has_prior_amendment` → sonra 06:47 apply (§1 №22) | Guard REVIEWED_MATH_CONTACT_HISTORY_GUARDS ilə dəqiqləşdirildi | Həll olunub — yalnız tarixçə üçün |
| 10 | Forma-1 batch — finance45 rədd olunan sətirlər | 🔴 30.10 04:32–04:42 · `bounded_sync_rejected_source_course` (3,5,8,12,15…) · 04:44 `outside_academic_work_or_access_changed` | Mənbə kursu kanonik sinxrona uyğun deyil | Rədd edilən sətirlər kafedra ilə dəqiqləşdirilməli |
| 11 | Forma-1 batch — held5 sətri 77 | 🔴 30.10 09:36 · `canonical_source_batch_rejected` (4/5 tətbiq olunub) | — | Sətir 77 ayrıca baxılmalı |
| 12 | Forma-1 batch — chairs2 qalıq | 🔴 30.10 06:14 · `new_course_workload_already_exists` (əsas hissə 06:05-də tətbiq olunub) | Yük artıq mövcuddur | Yəqin ki, əlavə iş lazım deyil — dry-run ilə təsdiqlənsin |
| 13 | Forma-1 batch — 9375b388 / pending13-fresh / safe20 (köhnə variantlar) | 🔴 `new_row_degree_program_context_not_unique`, `reviewed_legacy_snapshot_fingerprint_changed` | Köhnə mənbə variantları | Sonrakı «-degree» / «-fresh» / «-oct31» variantları ilə ƏVƏZ OLUNUB (§1 №27) — əlavə iş yoxdur |

## 4. Codex-in yarımçıq qoyduğu iki addım — dəqiq təlimat

Hər ikisi **yalnız oxuyan dry-run**dır (REPEATABLE READ, transaction geri qaytarılır).
GitHub → Actions → «🧰 Prod Data Ops» → *Run workflow* (branch `main`):

| Input | Fixed-four (dörd xana) | Source28 |
|---|---|---|
| `command` | `repair_reviewed_journal_content` | `repair_reviewed_journal_content` |
| `apply` | ☐ (false) | ☐ (false) |
| `year` | `2026/2027` | `2026/2027` |
| `roster_tag` | `reviewed-content-20261101-four-exact` | `reviewed-content-20261101-source28` |
| `batch` | `00fd00569b1a1af9460c57db647313622a70b0026d06716cf3843311d490ba1f` | `ce94b0cfc7a35f5d4595005474283492854f690b8532e9c57463f3a5ff377bc3` |
| `row_group` | `03ac22fc-5153-4e27-bec2-c804373c612f,b9add126-024d-4865-97b4-26abdfbd3193` | `1aca3f3c-5677-494e-af12-5622d2c1ea0a` |
| gözlənilən nəticə | `reviewed_content: mode=dry_run … baseline=<SHA> created_marks=4` | `reviewed_content: mode=dry_run … baseline=<SHA> created_lessons=1 created_marks=28` |

Dry-run keçərsə: eyni inputlar + `apply=true`, `confirm=APPLY`,
`row_subject=<dry-run baseline SHA>`. Təkrar dry-run `already_done` verməlidir.
Xəta çıxarsa token (`reviewed_source28_*` / `reviewed_four_*`) artıq loga düşür —
həmin tokenlə növbəti düzəliş hazırlanır.

Heç işlədilməmiş `reviewed-*` workflow-ları (§2 №1–6) üçün: Actions → workflow adı →
`actor=<aktiv superadmin istifadəçi adı>`, `apply=false` → nəticədəki `baseline` SHA-nı
`baseline` inputuna yazıb `apply=true`, `confirm=APPLY`.

## 5. Bu gün `main`-ə çatan kod dəyişiklikləri (kafedra şikayətlərinə cavab, deploy olunub)

| Dəyişiklik | Commit |
|---|---|
| Müəllim kabinetində jurnallar cari yük və öz tarixçəsi ilə uyğunlaşdırıldı; «tarixçə» etiketi tərcümə ilə | b79cb8e, 3fef142, 1272f5a |
| Sillabus müəllifləri və kafedra əhatəli müəllim süzgəci (dərc statusu ilə) | 6f3ea8a, 2965bdc |
| Birləşmiş jurnalda tələbə etiketində akademik ev qrupu əsas saxlanıldı; standart jurnal UI defolt | ad21343, a87f0a2, 3931e1f |
| Cədvəl inferensiyası yalnız real müəllifli/saatlı dərslərdən; sabit cədvəl sübutu exportu | 401a2e6, 6ed6f30 |
| Dövrü sillabus mənbə zənciri rədd edilir; cycle-held sillabus fingerprint exportu | d142fa7, 4a52cb6 |
| Fixed-four: iki texniki təmizləmə auditinin tanınması (§3 №1) | 259a180 |
| Fixed repair xəta tokenlərinin loga çıxarılması (§3 №2) | 0e03913 |
| CI shard balansı, gitleaks ORM digest istisnası | e72df3e, 0b3ac05 |

Hamısı CI-dən keçib (run 41334651447, `deploy-production` ✅ 18:24 UTC).

## 6. Bu sessiyadan mümkün olmayanlar və növbəti addımlar

- **Excel blankları və «RİM» qovluğu Mac-dadır** (`~/Downloads`, Codex-in lokal sessiyası). Bulud sessiyası
  onlara çata bilmir; bu reyestr həmin blanklara köçürülə bilən cavab mətnlərini («Blank üçün cavab»
  sütunu) və eyni məzmunlu `.xlsx` faylını verir. Mac-dakı faylları birbaşa doldurmaq üçün: Claude
  Desktop → Settings → Claude Code → Remote Control ilə `Downloads` (və ya RİM qovluğu) paylaşılsın,
  sonra yeni sessiyada «blankları reyestrə görə doldur» deyilsin.
- **Workflow dispatch** bu sessiyanın GitHub inteqrasiyasında icazəli deyil (403) — §4 addımları
  Actions səhifəsindən əl ilə işə salınmalıdır.
- Sidebar-dakı «Xarici dil səviyyə qrupları» keçidi, səhifənin ləngiməsi və dizaynı ayrıca PR-dadır.
