# AUDIT — Məlumat bütövlüyü · Legacy miqrasiya · DB arxitekturası (slug `data`)

Tarix: 2026-09-13 (ikinci buraxılış, RESUME). Mənbə: QA klon `emsarena_rehearsal_a0d170000901` @127.0.0.1:55433 (yalnız SELECT/EXPLAIN, `BEGIN…ROLLBACK`). SQL və çıxışlar: `scratchpad/audit/data/sql/*.sql`, `out/*.out`, `*.sql`/`*.out` (kök).
Real DB (`:5432`) heç vaxt açılmayıb. MariaDB mənbəyi mövcud deyil → mənbə-ilə müqayisə NOT TESTED.

## 0. Sayğaclar (klon, `01_counts.sql` → `01_counts.out`)

| Cədvəl | Sətir |
|---|---|
| auth_user | 8 644 (legacy `myedu.*` 8 545, yeni 99) |
| accounts_userprofile | 8 641 (profil-siz: user id 1,2,3 — sistem hesabları) |
| organizations_organization | **1** (tək tenant) |
| organizations_membership | 8 700 |
| organizations_orgunit | 880 (faculty 13 · specialty 83 · chair 18 · group 766) |
| organizations_academicperiod | 13 |
| registrar_program / curriculum / curriculumsubject | 101 / 211 / 4 681 |
| registrar_subject | 2 501 |
| registrar_studentacademicrecord (SAR) | 7 807 (legacy 7 799 + 8 yeni) |
| registrar_courseoffering / assessmentscheme | 11 115 / 11 115 |
| registrar_assessmentcomponent | 51 746 |
| registrar_enrollment | 150 157 |
| registrar_finalgrade | 115 403 |
| registrar_lesson / lessonmark | 304 805 / 3 921 304 |
| registrar_componentscore | 696 204 |
| registrar_resitrecord | 5 121 |
| registrar_legacygradefact / legacygradeartifact / legacyexcusedocument | 171 080 / 52 386 / 2 964 |
| legacy_import_legacyentitymap / issue / batch / run | 1 374 364 / 461 944 / 20 / 1 |
| exams_exam / examattempt / appeals_appeal | 1 / 0 / 0 |
| audit_auditlog | 22 485 |

Codex (2026-09-12) saydığı 8 443 user / 7 703 SAR / 148 020 enrollment / 114 021 final ilə fərq: klon 2026-09-07 dump-undan (QA hesabları + sonrakı QA yazıları) — fərqlər kiçikdir və izah olunandır (QA klon 8 644 user brief-də də göstərilib).

## 1. Referential integrity (FK sweep + soft refs)

**1.1 FK meta** (`02_fk_meta.sql`): 487 FK constraint, **0 NOT VALID**, hamısı `DEFERRABLE INITIALLY DEFERRED` (Django standartı), 0 multi-column; contype: f 487 · c 236 · p 171 · u 111 · t 3. Bütün 487 FK-nin `confdeltype = 'a'` (NO ACTION) — kaskad DB-də deyil, yalnız Django `on_delete`-dədir (bax §6.5).

**1.2 Dangling FK sweep** (`03_fk_gen.sql` → `03_fk_sweep_generated.sql` → `out/02_fk_sweep.out`): 487 FK-nin hamısı üçün `LEFT JOIN parent … WHERE child.fk IS NOT NULL AND parent.id IS NULL` — **487/487 = 0 dangling**. **PASS**.

**1.3 Soft referanslar** (`sql/03_soft_refs.sql` → `out/03_soft_refs.out`):

| Yoxlama | Nəticə | Status |
|---|---|---|
| `legacy_import_legacyentitymap` state=migrated → `target_pk` hədəf sətri mövcuddur (17 model etiketi, 1 112 098 sətir) | 0 itkin | PASS |
| `registrar_journalcorrection.lesson_mark_ref/lesson_ref/enrollment_ref` | 0 sətir (cədvəl boş) | NOT APPLICABLE |
| `registrar_correctionreversal.reverted_by_ref`, `workload_workloadamendment.target_id`, `registrar_grouptransferevidence.actor_ref/audit_ref/expected_enrollment_ids` | 0 sətir | NOT APPLICABLE |
| `accounts_accountactivationevidence.user_ref/actor_ref` (8 528) | 0 qeyri-rəqəm, 0 itkin user | PASS |
| `registrar_legacygradefact.source_student_ref` → legacy map student | 171 080-dən **573 xəritəsiz** (mapping_status: unresolved 556, discarded_source 17) — bunlar onsuz da `enrollment_id IS NULL` və `requires_exam_center_review` olan faktlardır | PARTIAL (gözlənilən, §8) |
| `registrar_legacyexcusedocument` student_unresolved | 8 / 2 964 (`student_id IS NULL`) | PARTIAL (gözlənilən) |
| `audit_auditlog.object_id` vs content_type (top-10 tip) | yalnız `exams.examroom` 2 dangling (id 159 create/update — otaq sonradan silinib; audit tarixçəsi normaldır) | PASS |
| JSON id siyahıları (`live_exam_livesession.selected_question_ids`, `liveanswer.choice_ids`, `examattempt.marked_question_ids`) | 0 sətir | NOT APPLICABLE |
| `legacyentitymap.reconciliation_status` | **1 374 364 sətrin hamısı `pending`** (migrated 1 112 098, quarantined 17 313, skipped 244 953) | FAIL-P2 (bax §8: reconciliation fazası bağlanmayıb) |

**Nəticə §1:** sərt FK bütövlüyü tam; soft-ref itkinləri yalnız legacy «unresolved» sinifindədir və modeldə bu vəziyyət açıq şəkildə saxlanılır.

## 2. Tenant (organization_id) uyğunluğu

**Kontekst:** klonda **1 təşkilat** var (`12_tenant_multihop.out` §12.2) → `organization_id` fərqi yalnız NULL-lar üzərindən yarana bilər; multi-tenant sınağı bu verilənlərlə mənalı deyil (NOT TESTED multi-org; sxem-səviyyəli mühafizə §6-da).

**2.1 Generik cüt-cüt yoxlama** (`04_tenant_gen.sql` → `04_tenant_generated.sql` → `04_tenant.out`): hər iki tərəfində `organization_id` olan **142 FK** üçün `child.organization_id IS DISTINCT FROM parent.organization_id` → **142/142 = 0**. PASS.

**2.2 Çox-addımlı cütlər** (`12_tenant_multihop.sql` → `out/12_tenant_multihop.out`, 39 cüt): finalgrade↔enrollment↔offering, componentscore↔component↔offering, lessonmark↔lesson↔enrollment (offering eyniliyi), selfworkmark↔topic, enrollment↔offering↔period, SAR↔group/program/curriculum(program), SAR.group.parent = program.specialty_unit, orgunit↔parent (org və `path`), membership↔role/scope_unit, exam↔course/subject, appeal↔attempt↔exam, offering↔group(org, unit_type), instructor/lesson.instructor aktiv üzvlük, legacygradefact/resit/curriculumsubject org — **hamısı 0**, istisnalar:

| Cüt | Say | Şərh | Status |
|---|---|---|---|
| `enrollment.offering.group <> SAR.group` | 14 892 | Tarixi qeydiyyatlar — tələbə sonradan qrup dəyişib; `enrollment.source_group_id` legacy sətirlərdə boşdur (0 fərq = hamısı NULL) → qrup tarixçəsi yalnız `offering.group` ilə bərpa olunur | P3 (məlumat modeli qeydi) |
| `SAR.student profile org <> SAR.org` | 8 | 8 yeni (QA) SAR — profil `organization_id` NULL (§4 `SAR_no_group` ilə eyni id-lər 8647–8654) | P3 |
| `membership.org <> userprofile.org` (primary aktiv) / `userprofile.org IS NULL` | 35 / 35 | 35 qeyri-legacy `member` rollu hesab (QA/staff); `UserProfile.organization` doldurulmayıb | P3 — fix: `apps/accounts` membership yaradanda `profile.organization` sinxronu (və ya `organization` sahəsini törəmə saymaq) |

**Nəticə §2:** PASS (tək tenant daxilində); DB trigger-ləri (`registrar_same_org_*_guard` ×60+, `registrar_organization_immutable_guard`) çarpaz-tenant yazını sxem səviyyəsində bloklayır (`out/triggers_functions.txt`).

## 3. Dublikatlar və identity (`sql/05_duplicates.sql` → `out/05_duplicates.out`; id siyahıları `09_dup_ids.sql` → `out/09_dup_ids.out`; `13_followup2.sql` §13.11)

| Yoxlama | Nəticə | Status |
|---|---|---|
| FIN dublikatı (exact / upper-trim) | 0 / 0 (FIN yalnız 576 profildə dolu — §5) | PASS |
| `institutional_identifier` dublikatı (org daxilində, NFKC-normalizə unikal indeks var) | 0 | PASS |
| Normalizə ad+ata adı+doğum tarixi dublikatı (bütün istifadəçilər) | 4 qrup / 8 sətir; **hər ikisi SAR-lı 1 cüt: user id 1030 & 3279** — eyni qrup, eyni proqram, `admission_year=1950` (placeholder), FIN yox, hər ikisi legacy `myedu.*`, qeydiyyatlar üst-üstə düşən dövrlərdə (1030: 32 enrollment 2021/22–2024/25; 3279: 4 enrollment 2022/23–2023/24) → **ehtimal olunan ikiqat tələbə hesabı** (legacy mənbədə iki student sətri) | FAIL-P2 |
| Yalnız ad dublikatı (doğum tarixi olmadan, tələbələr) | 130 qrup / 266 sətir — doğum tarixi 72,8 % boş olduğu üçün qiymətləndirilə bilmir | NOT TESTED (mənbə lazımdır) |
| Eyni org-da çox üzvlük | eyni org+rol+scope: **0**; eyni org fərqli rol: 57 istifadəçi (teacher+tutor 12, chair_head+teacher 10, dean+teacher 5 …) — dizayn (çox-rollu), `is_primary` >1: 0, aktiv-amma-primary-siz: 0 | PASS |
| Qrup adı dublikatı (eyni parent altında, `unit_type=group`) | **7 qrup / 15 orgunit** — məs. parent `5f91a8c6…` altında «532 t ing» ×2 (SAR 12 və 9), `6195eeac…` «532 bi ing» ×2 (7 və 9), «2535 bi» ×2 (15 və 0), «235 k» ×2 (25 və 0). Slug unikal olduğu üçün (`organization_id, slug`) DB icazə verir; ad üzrə unikal constraint yoxdur | FAIL-P2 (legacy `groups` cədvəlində dublikat sətirlər; birləşdirmə registrar qərarıdır) |
| Orgunit `code` dublikatı | `050501` ×2 specialty; **`5555` ×24 specialty** (placeholder kod) | FAIL-P3 |
| Fənn adı dublikatı (org, lower(name)) | **9 cüt** (hamısı `MYEDU-L…` kodlu, məs. `MYEDU-L1974`/`L2213` — 24 və 7 açılış) | FAIL-P3 (legacy `lessons` cədvəlində eyni adlı iki fənn; kod fərqli olduğu üçün constraint keçir) |
| Proqram adı+dərəcə dublikatı | 1 cüt: kodlar `050403` və `MYEDU-67` (5 + 5 SAR) | FAIL-P3 |
| Enrollment dublikatı (student, offering) | 0 (unikal `uniq_student_offering`); eyni fənn+dövr fərqli açılış: 0 | PASS |
| FinalGrade per enrollment >1 | 0 (OneToOne) | PASS |
| ExamAttempt (exam,user,number) | 0 (unikal indeks var; cədvəl boş) | PASS / NOT APPLICABLE |
| Offering (subject, group, period) | 0 (unikal) | PASS |
| SAR per student >1 | 0 | PASS |
| auth_user email / username (ci) | 0 / 0; boş email 59 (hamısı qeyri-legacy `member`/`teacher`), placeholder `@placeholder.invalid` 114 | PASS |
| Dövr (org,name,year), lesson (offering,date,kind,start), lessonmark, componentscore, scheme, resit | 0 | PASS |
| Tələbə==müəllim (teacher rolu + SAR) | 0 | PASS |
| Profilsiz user / üzvlüksüz user | {1,2,3} / {1,2,3,4} — sistem/superadmin hesabları | PASS |

**Nəticə §3:** sxem-səviyyəli unikallıq tam; legacy-dən gələn «yumşaq» dublikatlar (1 tələbə cütü, 7 qrup adı, 9 fənn adı, 1 proqram, 25 specialty kodu) var. Kiçik fix: `OrgUnit` üçün `UniqueConstraint(Lower('name'), 'parent', condition=unit_type='group')` — **yalnız 7 mövcud dublikat həll olunandan sonra** (DDL §6.4).

## 4. Akademik tarixçənin tamlığı (`sql/06_completeness.sql` → `out/06_completeness.out`; `10_completeness2.sql` → `out/10_completeness2.out`; `11_followup.sql` → `out/11_followup.out`)

**4.1 Dövr üzrə** (13 dövr, 2021/22 Payız → 2025/26 Yay):

| Dövr | Açılış | Müəllimsiz | Enrollment | Heç bir balı olmayan | Komponentsiz | Final-sız | Final |
|---|---|---|---|---|---|---|---|
| 2021/22 Payız | 27 | 17 | 383 | 0 | 0 | 383 | 0 |
| 2021/22 Yaz | 758 | 259 | 11 155 | 0 | 0 | 10 431 | 724 |
| 2022/23 Payız | 1 384 | 353 | 18 238 | 0 | 0 | 3 479 | 14 759 |
| 2022/23 Yaz | 1 009 | 171 | 12 544 | 0 | 0 | 2 186 | 10 358 |
| 2022/23 Yay | 39 | 4 | 67 | 0 | 0 | 63 | 4 |
| 2023/24 Payız | 1 409 | 180 | 17 730 | 0 | 0 | 2 775 | 14 955 |
| 2023/24 Yaz | 1 061 | 152 | 12 914 | 0 | 0 | 2 468 | 10 446 |
| 2024/25 Payız | 1 539 | 36 | 20 481 | 0 | 0 | 3 700 | 16 781 |
| 2024/25 Yaz | 1 093 | 0 | 14 599 | 0 | 0 | 2 717 | 11 882 |
| 2024/25 Yay | **0** | 0 | 0 | 0 | 0 | 0 | 0 |
| 2025/26 Payız | 1 574 | 0 | 22 945 | 0 | 0 | 3 785 | 19 160 |
| 2025/26 Yaz (cari) | 1 212 | 0 | 19 042 | 0 | 0 | 2 708 | 16 334 |
| 2025/26 Yay | 10 | 0 | 59 | 0 | 0 | 59 | 0 |

- Hər enrollment-in ən azı bir komponent balı var (0 «boş» qeydiyyat) — PASS.
- **Final-sız qeydiyyatlar:** 2021/22 dövrləri (93 %) və Yay dövrləri demək olar tam final-sızdır; 2022/23-dən sonra 13–19 %. Bütün 115 403 final `journal_finals` fazasından gəlir (entity map-də «new» görünür, çünki faza hədəfi `courseoffering`-dir). 2021/22 üçün legacy mənbədə final sətri olub-olmaması yoxlanıla bilmir → **NOT TESTED (mənbə yoxdur)**; bu dövr üçün transkript/ÜOMG hesabı «qiymətləndirilməyib» sinfinə düşür.
- `2024/2025 Yay` dövrü boşdur (0 açılış) — P3 (boş dövr; UI-də seçilə bilir).
- Müəllimsiz açılış: **1 172 / 11 115 (10,5 %)**, hamısı 2024/25 Payız-a qədər (legacy `worker` bağlantısı tapılmayan); dərslərin 10,2 %-i (31 026) `instructor_id` NULL — P2 (yük/həvalə hesabatları bu açılışları görmür).
- Dərsi olan amma heç bir qiyməti olmayan açılış: cəmi 203 (dövr üzrə 1–49) — P3.
- Açılış: enrollment-siz 150, dərssiz 422, scheme-siz 0; bütün 11 115 scheme `approved+published` (legacy `journal_lock`) — PASS.

**4.2 Tələbə / qrup / kurikulum:**
- SAR 7 807, hamısı `enrolled`/aktiv; qrupsuz SAR **8** (user id 8647–8654 — QA hesabları, legacy deyil); `student` rollu amma SAR-sız: 2 (id 8638, 8645 — QA). PASS (legacy tam).
- SAR-lı amma heç bir enrollment-i olmayan: **371** (358 aktiv, 13 arxiv). Qrup adı şablonuna görə 227-si «Level ####-####» (dil hazırlığı pseudo-qrupları), qalanı kiçik qruplar — P3 (gözlənilən, amma «Level» qrupları `unit_type=group` kimi modelləşib; `9.9`: «silinmelidir», «xaric olunanlar ####» adlı 3 qrup da var — registrar təmizləməsi).
- Boş qruplar (aktiv SAR-sız): 169 / 766 — P3.
- **Kurikulum: 211-dən 118 approved kurikulumda fənn sətri yoxdur; 3 685 SAR (47 %) boş kurikuluma bağlıdır.** Legacy `curricula_plan` 3 424 sətirdən 263 karantinə düşüb, amma boşluq əsasən mənbənin özündədir (plan PDF-lərdə — bax memory `wcu-curriculum-plan-sources`). Nəticə: bu tələbələr üçün «kurikulum üzrə irəliləyiş / məcburi fənn qeydiyyatı» funksiyaları işləməz. **FAIL-P2 (məlumat tamlığı; miqrasiya xətası deyil)**.
- Dövr həyat dövrü sahələri: 13 dövrün hamısı `opening_status=not_started`, `registration_start`/`exam_session_start` NULL, `locked_at` NULL — keçmiş dövrlər də «başlamayıb» görünür — P3 (UI/iş qaydası: keçmiş dövrlər `closed` olmalıdır).

**4.3 Legacy vs yeni paylanma** (`6.6`): courseoffering 11 115/11 115 legacy; enrollment 150 157/150 157; subject 2 501/2 501; orgunit 880/880; SAR 7 799 legacy + 8 yeni; user 8 545 legacy + 99 yeni; lesson 304 805 hamısı map-dadır (11 735 `is_legacy_synthesised`); finalgrade 115 403 «yeni» (faza məhsulu). Yəni klon **~99 % legacy** məlumatdır; yeni sistemdə yaradılan akademik sətir demək olar yoxdur (`enrollment.created_at` hamısı 2026-09-03).

**4.4 Legacy grade-fact uzlaşması** (`10.10`, `11.2`, `3.9`): 171 080 faktın mapping_status: linked 151 228 · unresolved 7 881 · discarded_source 7 728 · conflict 2 279 · group_mismatch 1 964; **hamısı `requires_exam_center_review=true`** (171 080). Linked faktlarda: `exam` faktı var, FinalGrade yox — 563 (balı olmayan, zərərsiz); **`exam_entry_exit` 5 719 faktda exam_score var amma FinalGrade sətri yoxdur**; **`summary` 300 faktda final_score var, FinalGrade yoxdur**; exam_score fərqi: exam 16, summary 888, exam_entry_exit 116. Bunlar `legacy_journal_reconcile_final_deviation` (15 112 issue) ilə qeydə alınıb, amma **461 944 issue-nun hamısı `review_status=open`** — imtahan mərkəzi baxışı başlamayıb. FAIL-P2 (proses; §8).

**4.5 Resit:** 5 121 `completed`, 446-sının FinalGrade-i yoxdur (resit var, əsas imtahan yoxdur) — P3, imtahan mərkəzi baxış siyahısına.

## 5. Encoding / tarix / diapazon sanity (`sql/07_sanity.sql` → `out/07_sanity.out`; `13_followup2.sql` → `out/13_followup2.out`)

| Yoxlama | Nəticə | Status |
|---|---|---|
| Mojibake (`Ã Å Ä Ð Ñ Â â€`), U+FFFD, `??` runs, HTML entity, control chars — first/last/patronymic, subject.name, orgunit.name, program.name, selfworktopic.title (69 404), lesson.topic (272 709), email | **0** hər sütunda | PASS |
| Baş/son boşluq | selfworktopic.title 348, lesson.topic 190 | P3 (kosmetik; `strip()` import zamanı) |
| Ad forması | tam BÖYÜK hərfli ad 2 874 (legacy 8 545-in 33 %), tam kiçik 52, tək-hərf 16, kiril 1, boş adlı aktiv: {1,2,3,4} sistem hesabları, rəqəmli ad 6/12/5 | P3 (kosmetik; görünüş title-case normalizasiyası) |
| Doğum tarixi > bu gün / < 1900 / yaş<15 / yaş>80 | 0 / 0 / 0 / 0 | PASS |
| **Doğum tarixi NULL (aktiv tələbə)** | 5 680 / 7 807 (72,8 %) | P2 (legacy mənbədə yoxdur — NOT TESTED; identity dublikat yoxlaması zəifləyir) |
| FIN boş | 8 065 / 8 641 (93,3 %); dolu olanlar formatı `^[A-Z0-9]{7}$` 100 % | P2 (eyni səbəb) |
| phone (aktiv tələbə) boş | 100 % | P3 |
| **`SAR.admission_year = 1950`** (placeholder) | **2 427 / 7 807 (31 %)** (`out/16_admission_year.out`); 2026: 94 | P2 (qəbul ili transkript/kurs hesabında istifadə olunur; legacy mənbədə boş idi) |
| `date_joined` gələcək / `last_login < date_joined` / `updated_at < created_at` (final, enrollment, membership) / üzvlük user-dən əvvəl | 0 | PASS |
| Dövr start>end, eyni tipli kəsişmə, `is_current` sayı | 0 / 0 / 1 | PASS |
| Dərs tarixi dövr pəncərəsindən kənar (±14 gün) | 228 / 304 805: 2021/22 Payız-a aid 25 dərs Fev–May 2022-də; 2021/22 Yaz-a aid 97 dərs Sen–Dek 2021-də; 2022/23 Payız 82 dərs Iyul–Avq 2023; 2023/24 Yaz 19; 2025/26 Yay 5 — açılış səhv dövrə bağlanıb (legacy `journal` dövr kodu) | P3 |
| Gələcək tarixli dərs | 0 | PASS |
| LessonMark score <0 / >10; status≠present amma score var; present amma score NULL | 0 / 0 / 3 150 126 (present-də NULL normaldır: iştirak qeydə alınıb, bal yoxdur) | PASS |
| ComponentScore > max_score | 0 | PASS |
| Hesablanmış giriş balı (generic+kollokvium capped + selfwork) > `entry_score_max` | 0 / 150 157 (max 50,00) | PASS |
| **FinalGrade.exam_score > 50** | **349** (max 89,00; hamısı `entry_score_max=50` sxemində, yəni imtahan max 50) — 2022/23 Payız 188, 2023/24 Payız 77, 2022/23 Yaz 53, 2023/24 Yaz 31. Legacy faktlarla müqayisə: 418 `exam` faktı **eyni dəyəri** daşıyır (mənbədə də >50: 443 exam, 59 exam_entry_exit, 193 summary; `summary.final_score>100`: 47) → miqrasiya sadiq, **mənbə məlumatı şkaladan kənardır** (ehtimal: bəzi jurnal sətirlərində «imtahan» sütununa yekun bal yazılıb). `finals.compute_final_result` cəmi 100-ə clamp edir, amma transkriptdə imtahan balı 89 kimi görünür; yeni daxil etmə `_clamp` ilə qorunur, **DB CHECK yoxdur** | FAIL-P1 (akademik nəticə düzgünlüyü) — id-lər: `13_followup2.out` §13.4 (top 10), tam siyahı üçün `SELECT id FROM registrar_finalgrade WHERE exam_score>50` |
| `registrar_legacygradeartifact` payload | 52 386-nın hamısında `payload_size_bytes ≠ length(payload_zlib)` — `payload_size_bytes` sıxılmamış ölçüdür (model: bax `legacy_grade.py`), sha256 hamısında var; zlib cəmi 87 MB | PASS (yanlış pozitiv) |
| Excuse sənədləri | 2 964; `document` faylı 0 (yalnız metadata), pəncərə NULL 0, tərs pəncərə 0 | PASS |

## 6. Sxem baxışı (`sql/08_schema.sql` → `out/08_schema.out`; `13_followup2.sql` §13.7–13.9; `14_explain_hot.sql` → `out/14_explain_hot.out`; `out/triggers_functions.txt`)

**Qeyd (statistika):** `pg_stat_*` sayğacları klonun yaradılmasından (2026-09-07, `stats_reset` NULL) bəri QA/audit trafikini əks etdirir — **istehsal yükü deyil**; «unused index» nəticələri buna görə yalnız işarədir.

**6.1 FK indeksləri:** FK sütunu olub, aparıcı sütunu o olan indeksi olmayan FK — **0** (Django hər FK-ya indeks yaradır). PASS.

**6.2 Dublikat / artıq indekslər (8.3, 8.4, 8.8):**
- Eyni açar üzrə 9 dublikat cüt: `accounts_userprofile` (`requested_organization_id` ×2, `role` ×2), `appeals_scoreadjustment.attempt_id` ×2, `courses_course.slug` ×2, `courses_coursegroup` (`instructor_id`, `course_id`) ×2, `courses_coursetopic (course_id, order)`, `exams_examstudentpin`, **`registrar_resitrecord.enrollment_id`** (adi + unikal). P3.
- `registrar_lessonmark` (952 MB, ən böyük cədvəl) üzərində 3 org-əsaslı indeks — `organization_id` (26 MB), `(organization_id)::text` (27 MB, RLS üçün), `(organization_id, enrollment_id)` (32 MB) — tək tenantda `organization_id` seçiciliyi 0-dır; `enrollment_id` indeksi onsuz da var. `entered_by_id` (26 MB) 100 % NULL. Eyni şablon `componentscore`, `enrollment`, `finalgrade`, `lesson` üzərində. Yazma yolunda (jurnal qeydi = lessonmark INSERT/UPDATE) hər əlavə indeks xərcdir. P3 (perf) — təklif: `Meta.indexes`-dən `(organization, enrollment)` kompozitlərini FK indeksi ilə əvəz etmək **və ya** tək-sütun `organization_id` FK indeksini `db_index=False` etmək (kompozit onu örtür). Təxmini qənaət lessonmark-da ~60 MB, cəmi ~100 MB.
- `registrar_studentacademicrecord` üzərində `national_athlete_exemption`, `is_active`, `education_form`, `funding_type`, `status` (+`_like`) tək-sütun indeksləri — aşağı kardinallıq, faydasız. P3.

**6.3 Unikal / CHECK constraint-lər (8.7, 8.10):** biznes qaydalarını örtən unikallıq mövcuddur: `uniq_student_offering (org, student, offering)`, `uniq_offering_subject_period_group`, `finalgrade.enrollment_id` OneToOne, `uniq_lesson_enrollment_mark`, `uniq_component_enrollment_score`, `uniq_resit_per_enrollment`, `uniq_student_program`, `uniq_attempt_number_per_user_exam`, `uniq_active_attempt_per_user_exam` (partial), `accounts_student_ident_canon_uniq` (NFKC), `fin` unikal, `membership (user, org, role, scope_unit)`. CHECK-lər əsasən `>= 0`; `superseded_enrollment_is_dropped`, `registrar_scheme_publish_state_valid` var. **Çatışmayanlar** (biznes qaydası var, sxem yoxdur):

| # | Qayda | Sübut | Təklif olunan DDL (İCRA EDİLMƏYİB) |
|---|---|---|---|
| C1 | `FinalGrade.exam_score` 0..50 (sxem `entry_score_max=50`, `finals._clamp` yalnız tətbiqdə) | 349 sətir >50 (§5) | `ALTER TABLE registrar_finalgrade ADD CONSTRAINT registrar_finalgrade_exam_score_range CHECK (exam_score IS NULL OR (exam_score >= 0 AND exam_score <= 50)) NOT VALID;` — 349 sətir imtahan mərkəzi tərəfindən düzəldiləndən sonra `VALIDATE CONSTRAINT`. Model: `apps/registrar/models/grading.py:FinalGrade.Meta.constraints` |
| C2 | `FinalGrade.bonus` ağlabatan diapazon | bonus hamısı 0 | `CHECK (bonus BETWEEN -50 AND 50)` (model constraint) |
| C3 | Qrup adı parent altında unikal | 7 dublikat (§3) | `CREATE UNIQUE INDEX organizations_orgunit_group_name_parent_uniq ON organizations_orgunit (parent_id, lower(btrim(name))) WHERE unit_type='group' AND is_active;` — dublikatlar birləşdiriləndən sonra |
| C4 | Orgunit `code` org daxilində unikal (boş olmayanda) | `5555` ×24, `050501` ×2 | `CREATE UNIQUE INDEX organizations_orgunit_code_uniq ON organizations_orgunit (organization_id, code) WHERE code <> '';` — placeholder kodlar təmizlənəndən sonra |
| C5 | Fənn adı org daxilində unikal (ci) | 9 cüt | Yalnız qərar sonrası: `UNIQUE (organization_id, lower(name)) WHERE NOT is_archived` |
| C6 | `Lesson.date` açılışın dövr pəncərəsində | 228 sətir kənarda | DB-də çarpaz cədvəl → trigger və ya `gradebook.create_lesson` validasiyası (artıq `allow_past` var) — legacy sətirlər üçün yalnız hesabat |
| C7 | `AssessmentComponent` cəmi `entry_score_max`-ı keçmir | 0 pozuntu | mövcud `registrar_component_score_coherence_guard` trigger-i bunu artıq örtür — PASS |

**6.4 RLS (8.14, 8.15, 13.7–13.9):** 171 cədvəl: **139 RLS+FORCE**, 2 RLS-li amma FORCE-suz (`accounts_accountactivationevidence`, `accounts_accountrestoreevidence` — trigger ilə immutable), **30 RLS-siz**, onlardan `organization_id` daşıyan: **`accounts_userprofile` (8 641 sətir) və `registrar_guestrosterdocument`**. Tətbiq rolu `emsarena_app` cədvəl sahibi deyil (sahib `emsarena_staging`) və `BYPASSRLS` deyil → siyasətlər FORCE-suz da tətbiq olunur; FORCE yalnız sahib üçün fərq edir. Siyasət forması: `bypass_rls='on' OR organization_id IS NULL OR organization_id::text = current_setting('app.current_org_id')` (permissive, `*`). **`accounts_userprofile`-ın RLS-siz olması** çox-tenant ssenarisində profil sahələrinin (FIN, doğum tarixi, telefon) başqa tenantdan oxunmasına sxem səviyyəsində imkan verir — hazırda 1 tenant, tətbiq qatı `organization` filtri ilə qoruyur → P2 (dizayn borcu; Codex §RLS bunu qeyd etməyib). Fix: `core/rls` miqrasiyasına `accounts_userprofile` və `registrar_guestrosterdocument` üçün eyni siyasət + `FORCE` əlavə etmək (diqqət: `hot_queries.json`-da hər sorğunun 2–3-cü sətri — profil `staged/archived` yoxlaması — `app.current_org_id` və `bypass_rls` qurulmazdan ƏVVƏL gedir; RLS əlavə olunarsa bu oxunuş `bypass_rls()` sarğısına alınmalı və ya siyasətə `user_id = current_setting('app.current_user_id')` qolu əlavə edilməlidir).
- 53 cədvəl `organization_id`-siz amma siyasətli (dolayı tenant — exams/labs/courses alt cədvəlləri) — PASS.

**6.5 Silinmə kaskadı (8.13 + model `on_delete`):** DB səviyyəsində bütün 487 FK `NO ACTION` — kaskad **yalnız Django-dadır**. `AUTH_USER_MODEL`-ə FK-lar: SET_NULL 93 · **CASCADE 36** · PROTECT 5 · M2M 11. Kritik zəncir: `StudentAcademicRecord.student` CASCADE, `Enrollment.student` CASCADE → `LessonMark`, `ComponentScore`, `CriterionScore`, `SelfWorkMark`, `CourseWork`, `FinalGrade`, `ResitRecord` (hamısı `enrollment` CASCADE). Yeganə DB-səviyyəli əyləc: `LegacyGradeFact.enrollment` PROTECT (linked fakt varsa `ProtectedError`) və append-only trigger-lər (`registrar_legacygradefact/artifact/review`, `studentmovement`, `audit_auditlog`). `hard_delete_account` (`apps/accounts/services/account_deletion.py:510`, çağırış `apps/accounts/views/account_management.py:426`, superadmin) yalnız «özü / superadmin / son admin» yoxlayır. **Klon ölçüsü:** 7 807 SAR-lı tələbədən **875-i heç bir linked legacy faktı olmadığı üçün PROTECT-ə düşmür**, 504-ünün qeydiyyatı var → superadmin «hard_delete» ilə **40 763 dərs qiyməti + qeydiyyat + SAR + final** səssiz silinər (audit yalnız «User deleted» sətri yazar). **FAIL-P1 (məlumat itkisi vektoru).** Ən kiçik fix: `hard_delete_account`-da `if user.academic_records.exists() or Enrollment.objects.filter(student=user).exists(): raise AccountDeletionError("hard_delete_blocked")` (və ya `Enrollment.student`/`SAR.student` → `PROTECT`, sonra `hard_delete` yalnız akademik tarixçəsiz hesablara). Əlavə: `registrar_legacygradefact` append-only trigger-i CASCADE zəncirində `ProtectedError` deyil DB xətası verə bilər → view `AccountDeletionError` tutmur → 500 (P3).

**6.6 Digər:** PK-sız cədvəl 0; int4 PK-lar yalnız `auth_user` (8 654 / 2^31) və Django daxili cədvəllər — UUID əsas; `emsarena_app` 169/171 cədvəldə DELETE hüququ, TRUNCATE 0 — append-only cədvəllər trigger ilə qorunur (PASS). Trigger inventarı: 60+ `registrar_same_org_*_guard`, `*_organization_immutable_guard`, `registrar_reference_identity_guard`, `trg_journal_mark_guard`, `registrar_student_group_transfer_guard`, `accounts_reject_*` — sxem-səviyyəli invariantlar güclüdür.

**6.7 EXPLAIN (ANALYZE, BUFFERS) — ORM-dən tutulmuş isti sorğular** (`test_capture_hot_queries.py` sandbox-da 7 səhifə, 287 sorğu → `out/hot_queries.json`; klonda real id-lərlə təkrar: açılış `a235093b…` (55 qeydiyyat, 32 dərs), müəllim 7864/8070, tələbə 195, cari dövr `4c5f453d…`):

| # | Sorğu (səhifə) | Plan | Exec | Buffers | Qiymət |
|---|---|---|---|---|---|
| H1 | jurnal grid: `lessonmark ⋈ lesson WHERE lesson.offering_id` (teacher_journal_detail) | Bitmap `lesson_offering_id` → Index `lessonmark_lesson_id` (32 loop, 1 241 sətir) | 3,5 ms | 307 | PASS |
| H2 | jurnal siyahısı: `enrollment ⋈ user ⟕ orgunit WHERE offering,status` | Bitmap `enrollment_offering_id` + quicksort 55 | 1,0 ms | 174 | PASS |
| H3 | komponent balları: `componentscore ⋈ enrollment WHERE component IN(5)` | Bitmap `uniq_component_enrollment_score` ×5 → 271 sətir | 5,1 ms | 1 138 | PASS |
| H4 | müəllim açılışları (journal_list): `courseoffering ⋈ user/period ⟕ enrollment … EXTRACT(MONTH) GROUP BY LIMIT 3` | BitmapAnd(instructor_id, period_id) → 3 açılış, 101 enrollment | 1,4 ms | 55 | PASS (EXTRACT dövr cədvəlində, 13 sətir — sargable olmaması zərərsiz) |
| H5 | tələbə imtahan siyahısı (DISTINCT 32 sütun + FILTER aqreqatlar) | `exams_exam_organization_id` → 0 sətir (klonda 1 imtahan) | 1,1 ms | 21 | NOT TESTED (məlumat yoxdur; sorğu 5 KB, 6 LEFT JOIN + korrelyasiyalı alt-sorğu — imtahan sayı artanda risk) |
| H6 | üzv reyestri: `membership ⋈ user ⋈ role ⟕ orgunit ORDER BY role.level DESC, username LIMIT 3` | Seq role (25) → Index `membership_role_id` (8 679 sətir) → **8 679 × auth_user_pkey**; top-N heapsort | **23,4 ms** | **26 443** | PARTIAL-P3: LIMIT/OFFSET səhifələmə hər səhifədə bütün 8,7 k üzvü user ilə birləşdirir; planner `rows=416` (RLS `current_setting` filtri səbəbilə 20× az təxmin). Təklif: sıralama açarını `membership`-ə denormalizə (`role_level`) + `(organization_id, is_active, role_level DESC, user_id)` indeks, və ya keyset səhifələmə |
| H7 | statistika: `SAR ⋈ program WHERE org,status GROUP BY program.name LIMIT 8` | Seq Scan SAR (7 807) + Seq program (101) — tam skan, org-daxili aqreqat üçün normal | 4,8 ms | 172 | PASS |
| H8 | statistika: `courseoffering ⟕ scheme COUNT (dövr)` | Bitmap `courseoffering_period_id` (1 212) + Seq `assessmentscheme` (11 115, hash) | 4,6 ms | 196 | PASS |
| H9 | tələbə enrollment COUNT (student, org, status≠dropped) | Index Scan `uniq_student_offering (org, student, offering)` → 59 sətir | 2,1 ms | 62 | PASS |

`transcript_pdf` sandbox-da 404 qaytardı (fixture-də transkript şərti ödənmir) → transkript sorğusu **NOT TESTED**; tələbə `my_subjects` bölməsi qabıqda registrar sorğusu vermir (bölmə AJAX ilə yüklənir) — H9 ilə əvəz olundu. Ümumi: bütün tutulan sorğular indeks yolu ilə gedir, tək «isti» nöqtə H6 (reyestr səhifələməsi).

## 7. Backup / restore (yalnız oxu: `docker-compose.prod.yml:208-250,467`, `docs/operations/deployment.md §12`, `apps/monitoring/collectors.py`)

- **Mexanizm:** `postgres-backup` servisi (`prodrigestivill/postgres-backup-local:16-alpine`), `SCHEDULE=@daily`, `pg_dump -Z6 --blobs` → `./backups/postgres/{daily,weekly,monthly}/*.sql.gz` (host bind-mount), saxlama 7 gün / 4 həftə / 3 ay; healthcheck `:8080` (son backup uğursuzdursa unhealthy → TargetDown). Celery worker `./backups/postgres:ro` görür → `emsarena_backup_age_seconds` Prometheus metrikası (`collectors.py:62`). **Off-site nüsxə** sənəddə «REQUIRED», amma compose-da yoxdur — host cron/rclone nümunəsi verilir, real konfiqurasiya yoxlanıla bilmir → **NOT TESTED / PARTIAL-P2** (Codex də açıq qoyub). PITR/WAL arxivi yoxdur → RPO = 24 saat (P2, akademik qiymət yazıları üçün böyükdür; `wal_level`/`archive_command` compose-da yoxdur).
- **Restore proseduru** `deployment.md §12` «(tested!)» yazır, amma Codex evidence `backup-integrity.json`: gzip bütövlüyü PASS (708 MB / 2,46 GB), `"restore": "NOT TESTED"`. Repo-da `backups/postgres/emsarena_db_20260908_0228.dump` (custom format, 710 MB) + `globals_*.sql` — cutover dump-u (QA klonu bundan qurulub → real məlumatla restore faktiki 1 dəfə edilib, amma prosedur sənəddəki plain-SQL yolundan fərqlidir: `pg_restore`, deyil `psql`).
- **Sintetik restore məşqi (bu audit, agent sandbox :55432):** `pg_dump -Z6 --blobs` sintetik `test_ems_audit_exams` (172 cədvəl, 283 miqrasiya, 0 user) → `gunzip -c | psql` yeni `ems_audit_data_restore`-a: 2 s; paritet **tam** — 172 cədvəl, 283 miqrasiya, 210 trigger, 142 siyasət, 142 RLS / 140 FORCE, 492 FK, 1 241 indeks (mənbə ilə eyni). Yeganə xəta: `unrecognized configuration parameter "transaction_timeout"` — **pg_dump 17 klient / PG 16 server** uyğunsuzluğu (zərərsiz, amma istehsalda dump/restore alət versiyası server ilə eyni olmalıdır; compose-dakı image 16-alpine → uyğundur). Sonra DB silindi. **PASS (sintetik)**; real ölçüdə (2,5 GB SQL, 4 M lessonmark) restore müddəti NOT TESTED.
- Qeyd: klon sxemi (487 FK) Develop HEAD-dən (492 FK) 5 FK geridədir — 2026-09-07-dən sonrakı miqrasiyalar (ExamScoreSheet və s.); audit nəticələri bu 5 cədvələ aid deyil.

## 8. Legacy miqrasiya — etibarlılıq qiymətləndirməsi

**Mənbə:** klon `legacy_import_*` cədvəlləri (`10_completeness2.sql` §10.6–10.7, `13_followup2.sql` §13.13–13.16), `docs/migration/reports/LEGACY_MIGRATION_FINAL_AUDIT_2026-09-06.md`, `LEGACY_DATA_QUALITY_V1.json`. **MariaDB mənbəsi əlçatan deyil → sahə-sahə mənbə↔hədəf müqayisəsi NOT TESTED**; aşağıdakılar hədəf tərəfdə yoxlanıla bilənlərdir.

**8.1 Nə təsdiqlənir (PASS):**
- 1 run (`mode=rehearsal`, `status=succeeded`, `accounting_mode=batch`, snapshot sha `177ef2269027…`, transform `rehearsal-identity-v2.aca98087fe65`, 2026-09-03): identity kohortu 15 496 mənbə sətri = 15 232 migrated + 0 skipped + 264 quarantined; 20 batch, **batch cəmi = run cəmi, `sum_mismatch=0`, `chain_breaks=0` (previous_chain_digest zənciri), `seq_gaps=0`**.
- Entity map: 1 374 364 sətir, `state=migrated` olan 1 112 098 sətrin **hamısının hədəf sətri mövcuddur** (17 model etiketi üzrə 0 itkin) — hədəf silinmələri/yenidən yazılmalar yoxdur.
- Kohort sayları (map vs hədəf): student 7 816 → SAR 7 799 (+17 `student_record` skipped = §10 «SAR-sız 17»), worker 729, group_unit 766 = 766 qrup, speciality 83, department 31, lesson_subject 2 521 map sətri → 2 501 fərqli hədəf fənn (20 mənbə fənni eyni hədəfə birləşdirilib — dedupe, hədəf itkisi yox; `out/15_curriculum_origin.out`), curriculum_plan 125 map (hədəf 211: **87 approved kurikulum map-siz, 2026-09-03 tarixli, hamısı fənsiz** — ehtimal `student_record` fazasının SAR üçün yaratdığı boş «placeholder» kurikulumlar + 1 draft 2026-09-09; map-li 125-in 31-i fənsiz), plan_row 3 161 (+263 karantin), academic_period 13, syllabus 7 049 / 1 213 skipped, excuse 2 964, grade_fact 171 080, artifact 52 386 (sha256 + ölçü hamısında).
- Hədəf bütövlüyü: 0 dangling FK, 0 dublikat enrollment/final/mark, 0 komponent balı > max, 0 hesablanmış giriş balı > 50, mojibake 0, tarix anomaliyası 0 — **transform sadiqdir, «yarımçıq yazı» əlaməti yoxdur** (bütün `enrollment.created_at` = 2026-09-03, tək run).
- Append-only / immutable trigger-lər (`legacy_import_*_no_delete/no_truncate/integrity`, `registrar_legacy_grade_*`) və `LegacyGradeFact.enrollment PROTECT` — sübut zənciri DB-də qorunur.

**8.2 Nə açıqdır (miqrasiya prosesi):**
| # | Fakt | Say | Severity |
|---|---|---|---|
| L1 | `LegacyEntityMap.reconciliation_status` — **hamısı `pending`** (verified/mismatch/not_applicable 0); `LegacyMigrationIssue.review_status` — **461 944-ün hamısı `open`** (info 386 732, warning 75 212). «Deep reconciliation» (GO şərti #7) və İmtahan Mərkəzi baxışı (#9) **başlamayıb**. `review_issue`/`review_and_remap_entity` servisləri var (`apps/legacy_import/services/review.py`), UI çağıranı tapılmadı (`grep review_issue apps/` — yalnız servis) | 1,37 M / 462 k | P2 |
| L2 | Bağlanmayan faktlar: unresolved 7 881 + discarded 7 728 + conflict 2 279 + group_mismatch 1 964 = **19 852** (`enrollment_id IS NULL`: 17 573 — 2026-09-06 auditi ilə eyni rəqəm); 573 faktın tələbə ref-i map-də yoxdur | 19 852 | P2 (məlum, review gözləyir) |
| L3 | Linked faktlarda hədəf çatışmazlığı: `exam_entry_exit` 5 719 (bal var, FinalGrade yox), `summary` 300 (final_score var, FinalGrade yox); dəyər fərqi exam 16 / summary 888 / entry_exit 116 → `legacy_journal_reconcile_final_deviation` 15 112 issue | ~7 000 | P2 (review) |
| L4 | **FinalGrade.exam_score > 50: 349** — mənbədəki `exam` xanası (443 fakt) olduğu kimi köçüb; 2026-09-06 auditi yalnız `yekun.imtahanda` üzrə 193 saymışdı (Tier-1 48). Canlı qiymət cədvəlində şkala pozuntusu | 349 | **P1** |
| L5 | 2021/22 dövrlərində final 93 % boş; `journal_finals` fazasında 1 649 skipped + 57 quarantined açılış — mənbədə olub-olmaması yoxlanıla bilmir | — | NOT TESTED |
| L6 | Kurikulum: 118 approved kurikulum fənsiz (87-si legacy map-də olmayan placeholder + 31 map-li), 3 685 SAR onlara bağlı (`curricula_plan` 263 karantin + mənbə boşluğu) | 118 / 3 685 | P2 |
| L7 | Müəllimsiz açılış 1 172 (10,5 %), dərs `instructor_id` NULL 31 026 — mənbədə `worker` istinadı olmayan jurnallar (məlum: «Mövcud olmayan müəllimə istinad edən jurnal 1 531») | 1 172 | P2 |
| L8 | Demoqrafiya: doğum tarixi 72,8 %, FIN 93 % boş; ad 33 % BÖYÜK hərf; `admission_year=1950` placeholder **2 427 SAR (31 %)** | 2 427 | P2 |
| L9 | Yumşaq dublikatlar (§3): 1 ehtimal ikiqat tələbə (1030/3279), 7 qrup adı, 9 fənn adı, 1 proqram, `5555` ×24 specialty kodu — mənbənin öz vəziyyəti, avtomatik birləşdirilməyib (düzgün qərar), amma qərar siyahısı yoxdur | ~45 | P2/P3 |
| L10 | `enrollment.source_group_id` 100 % NULL — legacy qeydiyyatların qrup tarixçəsi yalnız `offering.group` ilə; `StudentMovement` 0 sətir — qrup köçürmə tarixçəsi köçürülməyib | 150 157 | P3 |

**8.3 Yoxlanıla bilməyənlər və səbəbi:** (a) mənbə MariaDB snapshot-u audit mühitində yoxdur → sahə-sahə diff, «mənbədə var / hədəfdə yox» sinifləri (L5), 17 SAR-sız tələbənin səbəbi; (b) run yalnız `rehearsal` rejimindədir — istehsal cutover run-ı (`mode=cutover`) klonda yoxdur, yəni klon = repetisiya nəticəsi (docs `NO-GO` statusu ilə uyğundur); (c) `LegacyEntityObservation` (1,37 M) determinizm hesabatı (iki run müqayisəsi) yalnız sənəddə (`LEGACY_REHEARSAL_FULL_V1/V2_RUN1.json`) — klonda tək run.

**Etibarlılıq hökmü:** *Transform sadiqliyi* — yüksək (hədəfdə heç bir struktur pozuntusu, sübut zənciri bütöv). *Məlumat tamlığı* — orta (mənbə boşluqları: müəllim, kurikulum, demoqrafiya, 2021/22 finalları). *Proses tamamlığı* — aşağı (reconciliation/review 0 % irəliləmiş; L4 kimi şkala pozuntuları canlı cədvəldə). Docs-dakı «NO-GO» hökmü ilə uyğundur.

## 9. Xülasə, severity sayları, ballar

**Tapıntılar (severity):**
- **P0: 0**
- **P1: 2** — (F1) `FinalGrade.exam_score > 50` 349 sətir canlı qiymət cədvəlində, DB CHECK yoxdur (§5, C1); (F2) superadmin `hard_delete_account` → Django CASCADE ilə SAR/enrollment/40 763 mark/final səssiz silinməsi, 875 tələbə PROTECT-siz (§6.5).
- **P2: 9** (bir neçəsi çox-maddəli) — reconciliation/issue review 0 % (L1); 19 852 bağlanmayan + ~7 000 uyğunsuz legacy fakt review gözləyir (L2/L3); 118 boş kurikulum / 3 685 SAR (L6); 1 172 müəllimsiz açılış (L7); ehtimal ikiqat tələbə 1030/3279 + 7 dublikat qrup adı (§3); `accounts_userprofile` RLS-siz (§6.4); demoqrafiya boşluğu FIN/doğum tarixi + `admission_year=1950` 2 427 SAR (§5); off-site backup + PITR yoxluğu, real-ölçü restore NOT TESTED (§7).
- **P3: 12** — dublikat/artıq indekslər (9 cüt + org-indeks şişməsi ~100 MB); aşağı kardinallıq SAR indeksləri; reyestr səhifələmə sorğusu (H6); fənn/proqram/specialty-kod dublikatları; boş `2024/25 Yay` dövrü + dövr həyat dövrü sahələri boş; 228 dərs dövr pəncərəsindən kənar; 371 qeydiyyatsız SAR («Level» pseudo-qrupları, «silinmelidir» adlı qrup); 446 final-sız resit; profil `organization` NULL 35 üzv; `source_group`/`StudentMovement` boş; ad/başlıq boşluq və BÖYÜK hərf kosmetikası; hard-delete-də trigger xətasının 500 kimi çıxması.

**PASS-lar (yenidən yoxlanılıb):** 487/487 FK 0 dangling; 142 birbaşa + 39 çox-addımlı tenant cütü 0 uyğunsuzluq; unikallıq (enrollment, final, mark, componentscore, attempt, SAR, offering, FIN, inst. id) 0 dublikat; mojibake 0; tarix anomaliyası 0; komponent balı > max 0; hesablanmış giriş balı > 50 0; legacy batch zənciri bütöv; sintetik dump→restore paritet tam; 60+ same-org/immutable/append-only trigger; 139 cədvəl RLS+FORCE.

**Ballar (0–100):**
| Sahə | Bal | Əsaslandırma |
|---|---|---|
| **Database Design** | **78** | Güclü: UUID PK, hər FK indeksli, 111 unikal + 236 CHECK, 60+ invariant trigger-i, RLS 139/171 FORCE, append-only sübut cədvəlləri, `NOT VALID` yoxdur. Zəif: kaskad yalnız ORM-də və tələbə tarixçəsi PROTECT-siz (P1), `FinalGrade.exam_score` diapazonu sxemdə yoxdur (P1), `accounts_userprofile` RLS-siz (P2), qrup adı/kod unikallığı yoxdur, ~100 MB sıfır-seçicilikli org indeksləri, 9 dublikat indeks, dövr həyat dövrü sahələri istifadəsiz. |
| **Database Integrity** | **88** | Sərt bütövlük tam (FK, unikal, tenant, tarix, encoding, bal diapazonları komponent səviyyəsində). Çıxılan: 349 şkaladan kənar imtahan balı (P1), 1 ehtimal ikiqat tələbə, 7 dublikat qrup, 228 dövr-kənar dərs, 8+35 profil/org boşluğu — hamısı legacy mənbədən, yeni yazı yolu qorunur. |
| **Legacy Migration** | **66** | Transform sadiq və sübut zənciri bütöv (batch/chain/digest 0 fərq, hədəf 0 itkin), amma proses yarımçıqdır: reconciliation 0/1,37 M, issue review 0/462 k, 19 852 bağlanmayan fakt, 118 boş kurikulum, 10,5 % müəllimsiz açılış, demoqrafiya 70–93 % boş; mənbə müqayisəsi mümkün olmadığı üçün tamlıq yalnız hədəf tərəfdən qiymətləndirilib. Docs «NO-GO» ilə uyğundur. |

**Fix agenti üçün ən kiçik təhlükəsiz addımlar (prioritetlə):**
1. `apps/accounts/services/account_deletion.py:hard_delete_account` — akademik tarixçəsi olan istifadəçi üçün `AccountDeletionError("hard_delete_blocked")` (test: SAR-lı user → 875 halı).
2. `apps/registrar/models/grading.py:FinalGrade.Meta.constraints` — `CheckConstraint(exam_score >= 0 AND <= 50)` + miqrasiya `NOT VALID` (RunSQL) və 349 sətrin id siyahısı İmtahan Mərkəzinə (`SELECT id FROM registrar_finalgrade WHERE exam_score > 50`).
3. `core/rls` — `accounts_userprofile`, `registrar_guestrosterdocument` üçün siyasət + FORCE (giriş-öncəsi profil oxunuşlarını `bypass_rls()`-ə almaqla).
4. Legacy review UI/CLI-nin işə salınması (`services/review.py` çağıranı) — 462 k issue üçün ən azı `warning` sinfi (75 212) və 19 852 bağlanmayan fakt.
5. `OrgUnit`/`Subject`/`Program` dublikat qərar siyahısı (id-lər `out/09_dup_ids.out`), sonra C3/C4 unikal indeksləri.
6. `Meta.indexes` təmizliyi (9 dublikat, org tək-sütun indeksləri) — ayrıca miqrasiya, `CONCURRENTLY`.

**Artefaktlar:** bu fayl; SQL: `sql/00–08_*.sql`, `01_counts.sql`, `02_fk_meta.sql`, `03_fk_gen.sql`+`03_fk_sweep_generated.sql`, `04_tenant_gen.sql`+`04_tenant_generated.sql`, `09_dup_ids.sql`, `10_completeness2.sql`, `11_followup.sql`, `12_tenant_multihop.sql`, `13_followup2.sql`, `14_explain_hot.sql`; çıxışlar `out/*.out`, `01_counts.out`, `02_fk_meta.out`, `04_tenant.out`; ORM tutma `test_capture_hot_queries.py` → `out/hot_queries.json` (+`hot_queries_registrar_dump.txt`, `pytest_capture.log`); trigger/RLS inventarı `out/triggers_functions.txt`; restore məşqi `out/restore_errors.log`. Heç bir tracked fayl dəyişdirilməyib; real DB-yə toxunulmayıb; klonda yalnız `BEGIN … ROLLBACK` SELECT/EXPLAIN; restore məşqi agent sandbox-da (:55432) sintetik DB ilə, sonra silinib.
