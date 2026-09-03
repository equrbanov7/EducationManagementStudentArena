# Mərkəzi problem / tapşırıq siyahısı — köçürmədən sonrakı audit (2026-09-02)

Status: OPEN · IN-PROGRESS · FIXED (klonda yoxlanıb) · DEFERRED (sahib qərarı) · WONTFIX (qəsdən belədir)

## P0 — data / təhlükəsizlik / autentifikasiya / icazə
| # | Problem | Mənbə | Status |
|---|---|---|---|
| P0-1 | 2,291 cari tələbə səhvən `archived`+`alumni` (qrupun `start_year='0000'`, 248 qrup) → giriş bağlı | PHASE1 data audit | FIXED (klon): `rehearsal_sar_phase._decide` yalnız `azadedildi=1` ilə arxivləyir; `legacy_repair_archive_status --apply` → archived 2,490→199, active 5,948→8,239, 2,291 audit sətri, 2-ci icra 0; `accounts/0018_account_restore_evidence` |
| P0-2 | 100 tələbə + 14 işçi hesabsız (14 e-poçt toqquşması karantin, 86 etibarsız e-poçt); 12 karantinli işçiyə 62 jurnal bağlıdır | PHASE1 | FIXED (klon): identity fazası placeholder e-poçt; `legacy_repair_missing_accounts --from-source --apply` → 114 yaradıldı (tələbə 7,716→7,816, işçi 715→729), 45 açılış müəllim aldı (müəllimsiz 1,203→1,168), 2-ci icra 0. Demoqrafiya: birth_date 0→2,175, gender 0→1,693 |
| P0-3 | Hədəfdə cari akademik dövr yoxdur (mənbədə `semestr_jurnal.id=13 is_current=1`), 2026/2027 yaradılmayıb → «Fənlərim» boş | PHASE1 | FIXED (klon): `legacy_repair_current_period` → 2025/2026 Yaz cari (1,212 açılış), 2026/2027 yaradıldı (0 açılış) |
| P0-4 | Cədvəli açılışın istənilən müəllimi dəyişə bilirdi; icazə açarı, koordinator/RİM yolu, audit, bildiriş yox idi | PHASE2 rol matrisi | FIXED (klon): `schedule.manage`, «Cədvəl idarəetməsi», müəllim 403, 26 yeni test, dövr fallback (R-1) |
| P0-5 | Dərs yükü axını mövcud deyildi (`apps/workload` yox) | PHASE2 | FIXED (klon): `apps/workload` F0+F3+F4 — 5 model + RLS/saat-balans/append-only trigger, `workload.*` icazə ailəsi, 14 JSON endpoint, «Yük bölgüsü» + «Dərs yüküm» bölmələri, offering sinxronu; 71 test; canlı: kafedra müdiri 3 sətir/6 bölgü → 3 açılış + 2 bildiriş; audit branch-ına birləşdirildi (d32e3d37). Qalan: F1 tədris şöbəsi redaktoru, F2 dekanlıq təsdiqi, F5 hesabat/amendment UI |
| P0-6 | Müraciətlər / ESD modulu yox idi | tapşırıq | FIXED (klon): `apps/applications` (152 test) + kabinet bölməsi «Müraciətlərim» (9 test); canlı: tələbə→koordinator→RİM→həll→bağla, 0 konsol/CSP xətası, 375 px slide-over |
| P0-7 | Login rate-limit-i superadmin «escape hatch»-i ilə yan keçilir (`login.py:219-241`, `_shared.py:135-145`) | PHASE23 security | FIXED: rate sətri yanlışdırsa startup-da `ImproperlyConfigured`, runtime fail-closed; escape hatch yenidən yoxlanılmalı (re-verify siyahısında) |
| P0-8 | Şəxsi düzəliş/tibbi PDF-lər anonim istifadəçiyə verilir (7 prefiksdən 1-i qorunurdu; 2,087 real sənəd; **prod-da da açıq idi** — nginx `/media/`-ni Django-ya ötürür) | PHASE23 | FIXED: `core/media_policies.py` 7 prefiks + per-prefix siyasət, anonim 302, yad 404; 8/8 real HTTP re-verify |
| P0-9 | İmtahan mərkəzi əməkdaşı başqa müəllimin sual bankından sualı auditsiz silə bilir | PHASE23 | FIXED: `question_bank_detail` POST-da sahiblik qapısı + audit |
| P0-10 | Portal qapısı `POST /accounts/login/` ilə keçilir | PHASE23 | FIXED: `effective_audience()` neytral endpoint-i staff sayır; tələbə girə bilmir |
| P0-11 | Müəllim başqa müəllimin sillabusunu klonlaya bilir | PHASE23 | FIXED: `copy_from_previous` eyni qapı |
| P0-12 | RLS örtüyü: `audit_auditlog`, `monitoring_securityevent`, `ai_assistant_aiassistantlog` siyasətsiz; `accounts_userprofile` siyasətsiz; CI RLS qapısı superuser ilə boş keçir | PHASE23 | QİSMƏN: 3 cədvələ RLS əlavə edildi (`audit/0003`, `monitoring/0002`, `ai_assistant/0003`); audit jurnalı silinməz (`has_delete_permission` False + `delete()` raise); RLS meta-testlər; `accounts_userprofile` QƏSDƏN açıq (tenant bootstrap cədvəlidir, fail-open riski) — 4 addımlı təklif PHASE23_SECURITY_FIXES §5; CI workflow dəyişikliyi yalnız təklif |

## P1 — əsas akademik axınların çatışmayan hissələri
| # | Problem | Mənbə | Status |
|---|---|---|---|
| P1-1 | Sillabus axını heç bir bildiriş göndərmirdi | scout | FIXED (klon) — `apps/syllabus/services/notifications.py` |
| P1-2 | Kollokvium pəncərəsi / jurnal bağlanması müəllimlərə bildirilmirdi | scout | FIXED (klon) — `registrar/kollokvium_notifications.py`, `journal_close_notifications.py` |
| P1-3 | Tələbə jurnalında dərs otağı/korpusu görünmürdü | scout | FIXED (klon) |
| P1-4 | journal_detail 10,075 sorğu / 15.9 s; my-results 692; overall-academic 688 | PHASE24 | FIXED — 102 / 68 / 64 sorğu, çıxış bayt-bəbayt eyni |
| P1-5 | 12,457 bal + 19,116 qayıb xanası dərs sətirsiz (J12 `journal_lesson_recovery` fazası işlədilməyib) | PHASE1 | FIXED (təzə repetisiya): `emsarena_rehearsal_d44526b97cbc` (run 8a476c8c, 0 xəta, 4s51d) — J12 +11,735 dərs, 158 otaq, SAR 7,799, arxiv 200; cutover tövsiyəsi **A = bu baza** + HEAD miqrasiyaları + `legacy_repair_current_period --period "2025/2026 Yaz"` (`REHEARSAL_FRESH_RESULT.md`) |
| P1-6 | `birth_date`/`gender`/`student_group_number` köçürülməyib (mənbədə var) | PHASE1 | FIXED (klon): `legacy_repair_demographics --from-source` → birth_date 2,175, gender 1,693; `student_group_number` 7,703 |
| P1-7 | Tələbə siyahısını yükləmək üçün heyət yolu yoxdur (`import_users_from_excel` komandası prod-da söndürülüb; RİM mərkəzində «yarat/idxal» yoxdur) | PHASE1 provisioning | FIXED (klon): `user.import` icazəsi (RİM/HR) + «Tələbə idxalı» bölməsi — xlsx şablon → dry-run → apply (User+Profile+Membership+SAR, sətir-sətir savepoint, placeholder e-poçt, birdəfəlik parol yalnız cavabda); 26 test; canlı 3 sətir (2 yaradıldı, 1 xəta), yeni tələbə giriş etdi. Komanda kill-switch-i dəyişməyib |
| P1-8 | 3,075 SAR plan sətri olmayan kurikuluma bağlı; 87 boş kurikulum | PHASE1 | DEFERRED (mənbədə plan yoxdur) |
| P1-9 | `FinalGrade.is_published` heç bir kod yolu ilə TRUE olmur (ölü sütun); əsl nəşr bayrağı `AssessmentScheme.is_published` (RİM jurnal bağlaması) | PHASE1 | WONTFIX-izah: tələbə UI-a təsiri yoxdur; sənədləşdirildi |
| P1-10 | dean/chair_head `org_admin` alias-ı alır → org-səviyyəli bloq moderasiyası sızması | PHASE2 | QİSMƏN: bloq moderasiyası fakültə əhatəsinə salınmadı; alias qaydası dəyişməyib (P2 → növbəti dalğa) |
| P1-11 | Kollokvium/apellyasiya idarəsi icazə açarı ilə yox, rol ADI ilə qapılır | PHASE2 | OPEN → 2-ci dalğa |
| P1-12 | `/accounts/send-otp/` və parol bərpası «done» səhifəsində hesab sadalama | PHASE23 | FIXED: vahid cavablar (mövcudluq sızmır); reset forması dəyər-əsaslı placeholder yoxlaması (PHASE27_FIXES R-8) |

## P2 — səhv funksionallıq / ciddi UX
| # | Problem | Mənbə | Status |
|---|---|---|---|
| P2-1 | Qruplar bölməsi hər açılışda org-səviyyəli tələbə checkbox siyahısı qururdu (813 ms) | PERF | FIXED — lazy `teacher_group_candidates` |
| P2-2 | `LegacyEntityMap.target_pk` indeksi yox (97.7 ms → 0.4 ms) | PERF | FIXED — `legacy_import/0007` |
| P2-3 | 2 istifadəçiyə görünən «İKT» mətni | scout | FIXED — «RİM rəhbəri» + 4 dil |
| P2-4 | Əks axtarış köməkçisi yox idi (koordinator/kafedra müdiri/dekan → vahid) | scout | FIXED — `apps/organizations/unit_heads.py` (18 test) |
| P2-5 | Tələbə kabinetinin başlığında «Join» düyməsi (köçürülmüş tələbə nəyə qoşulmalıdır?) | UI | OPEN → UX keçidi |
| P2-6 | 1,589 toqquşmada uduzan dəyər UI-da yox; `yekun`↔imtahan balı 884 sətirdə fərqli | PHASE1 | DEFERRED (BAL_PROBLEMLERI.md) |
| P2-7 | Provisioning canlı gedişi + `test_staged_portal_login.py` (6 test) hələ yaşıl təsdiqlənməyib | provisioning | FIXED: reqressiyada 6/6 yaşıl (PHASE27 axın 26) |
| P2-8 | Audit jurnalı admin-dən silinə bilir; `get_client_ip` XFF-in ən sol üzvünü oxuyur; base→production settings sürüşməsi; portal qapısı `POST /accounts/login/` ilə keçilir | PHASE23 | FIXED: audit silinməz, vahid XFF köməkçisi, production import siyahısı, portal qapısı |
| P2-9 | Yüklənmiş sənədlər (düzəliş PDF-ləri) icazə yoxlamalı serve view-suz `.url` ilə verilir | scout/security | FIXED: `core/media_policies.py` bütün şəxsi prefiksləri qapayır (P0-8) |

## UI QA + dashboard dalğası (PHASE21/22)
| # | Problem | Mənbə | Status |
|---|---|---|---|
| UI-1 | AZ tarix adları kataloqda korlanmışdı (16 msgid: `September`→«Hələ üzv əlavə olunmayıb.», `aug`→«əvvəl», `Sat`→«Status»…) → sentyabrda BÜTÜN tarixlər səhv | PHASE21 | FIXED (klon + kataloq) |
| UI-2 | `profile-info`-da xam `position` msgid (fuzzy) | PHASE21 | FIXED (4 dil) |
| UI-3 | Qrupsuz tələbələr «Müəllim cədvəli» kimi etiketlənirdi (`page_contexts.py:387`, klonda 102 real tələbə) | PHASE21 | FIXED + reqressiya testi |
| UI-4 | 768 px-də 200 px üfüqi sürüşmə (FA `.sr-only` absolute) | PHASE21 | FIXED (`ems_components.css`) |
| UI-5 | `.syl-chip__count` kontrast 4.34:1 | PHASE21 | FIXED → 6.92:1 |
| UI-6 | Heç bir rolda dashboard yox idi — hər kabinet `profile-info` ilə açılırdı | PHASE21/22 | FIXED: `dashboard` («Ana səhifə») bölməsi, 18 rol-şərtli vidcet, default landing, 15 test, sorğu büdcəsi ≤28 |
| UI-7 | 223 AZ `#, fuzzy` yazı səhv msgstr-lidir (`Sil`→`Dil`, `Blokla`→`Bloku aç`…) — hazırda zərərsiz, `--use-fuzzy`/un-fuzzy olsa fəlakət | PHASE21 | OPEN (əl ilə yenidən tərcümə lazımdır; §8 skript) |
| UI-8 | 7 bölmədə rol adları ingiliscə; `my-courses` etiketi «Təyin olunmuş fənlərim» amma kurs *yaradıcısıdır*; semestr/il defoltları cari dövrdən kənardır; `analytics` ~3 s | PHASE21 | OPEN (P2) |
| UI-9 | Off-canvas menyu tab sırasında; sidebar linklərində `:focus-visible` yoxdur (navbar.css ölçü-dondurulub) | PHASE21 | OPEN (P3) |
| UI-10 | Tələbə bölmə iç başlıqları qabıq başlığını təkrarlayırdı («Sillabuslar» ×2) | sahib | FIXED (sillabus, sillabus təsdiqi, cədvəl idarəetməsi, yük bölgüsü, dərs yüküm) |

## Reqressiya dalğası (PHASE27) — tapıntılar
| # | Problem | Mənbə | Status |
|---|---|---|---|
| R-8 | **Köçürülmüş heç bir istifadəçi giriş edə bilmirdi**: 8,543/8,568 hesabda parol yoxdur və reset forması onları süzürdü | PHASE27 | FIXED (klon): reset forması «giriş açıqdır» şərti ilə (staged/archived xaric), placeholder e-poçt → RİM yönləndirməsi (sadalama yox), OTP reset sonrası ilk-giriş qapısı təmizlənir; RİM per-user parol; `provision_student_credentials --group`; HANDOFF §8.9 cutover proseduru (SMTP şərti) |
| R-2 | Kafedra müdiri sillabusu heç vaxt görmürdü (`chair_unit` = ixtisas) | PHASE27 | FIXED (klon): `syllabus/services/units.py` — əcdad → müəllifin kafedra üzvlüyü → verilən vahid; `syllabus_repair_chair_units`. **Tenant tapıntısı:** 0/83 ixtisas və 0/766 qrupun kafedra əcdadı yoxdur (mənbədə `speciality.department_id` fakültəyə işarə edir). **SAHİBİN QƏRARI 2026-09-03: təsdiqçi KAFEDRA MÜDİRİDİR** — dekan `approve/revise/reject` açarlarını itirdi (`organizations/0035`), qərar əhatəsi kafedra səviyyəsinə daraldı (`covers_chair_unit`). Bax PHASE6_CHAIR_APPROVAL.md |
| R-1/R-4 | `my-schedule` yalnız bitmiş cari dövrü göstərirdi | PHASE27 | FIXED (klon): `resolve_display_period()` (?period → cari → ən yaxın gələcək slotlu → cari-dən köhnə olmayan son slotlu) + dövr seçicisi; canlı: koordinator 2026/2027 Payız slotu → müəllim və tələbə görür |
| R-9 | Bərpa hesablarının SAR-ı yoxdu | PHASE27 | FIXED (klon): `--with-sar` → SAR 7,703→7,799 (96/100; 4-ü mənbədə mövcud olmayan qrupa işarə edir — uydurulmadı) |
| R-5 | Klonda 0 `ExamRoom` | PHASE27 | FIXED (klon): `legacy_repair_rooms --from-source` (J10 fazasının öz məntiqi) → 158 otaq, 4 korpus; dərs modalı kaskadı işləyir |
| R-10 | `test_exam_eligibility_frozen` sətir-başına 2 sorğu gözləyirdi (köhnə N+1) | CI | FIXED: batching-dən sonra 0 kilidləndi |
| R-7 | İmtahan mərkəzi əməkdaşı başqa müəllimin sual bankını OXUYA bilir (A-31e) — PHASE23-də qəsdən saxlanıb | PHASE27 | **WONTFIX — sahibin qərarı 2026-09-03:** imtahan mərkəzi BAŞQA müəllimlərin sual bankını oxuya BİLƏR (mərkəz imtahan variantını qurmaq üçün bankı görməlidir; hər oxu audit olunur). Davranış dəyişmir, «boşluq» statusu bağlanır. |
| R-3 | PHASE23 «müsbət nəzarət» sillabusu bölməsiz idi (completion=100, 0 bölmə) — F7–F8 ilk əsl 100 % dövrüdür | PHASE27 | Qeyd |
| CI-1 | `rls-txn-pool` 9 fail + 28 error: `accounts/0018` xam-SQL cədvəli FK ilə flush-u bloklayırdı | CI | FIXED (`accounts/0019` state-only model; lokal 36/36) |
| CI-2 | pip-audit: pypdf 6.15.0 (CVE-2026-84309/10/11) | CI | FIXED → 6.16.1 |
| CI-3 | unit-tests-311: 108 fail + 105 error (əksəri TransactionTestCase flush kollateralı: consumers, seed, migration testləri, audit) | CI | Növbəti CI icrası ilə yoxlanılır |

## P3 — cilalama
| # | Problem | Mənbə | Status |
|---|---|---|---|
| P3-1 | Hər kabinet səhifəsində ~50–65 sorğuluq «profil qabığı vergisi» | PERF | OPEN (context_builder mərhələləri) |
| P3-2 | ~90 kod şərhində hələ «İKT» | scout | WONTFIX (kosmetik) |
| P3-3 | Kollokvium pəncərəsi view qatı üçün ayrıca test yoxdur | scout | OPEN |
| P3-4 | Host: repo iCloud-sinxron Desktop-dadır → pack fayl boşalması, `git diff` sınır; yenidən yükləmə `/private/tmp` scratchpad-ı sildi | infra | Qeyd: hesabatlar indi `docs/audits/2026-09-02/`-də saxlanır |

## Təhlükəsizlik dalğası 2 (PHASE23_SECURITY_WAVE2, 2026-09-03) — `a5d3ee9c..HEAD`
Tam hesabat: `PHASE23_SECURITY_WAVE2.md`. Aşağıda **AÇIQ** qalanlar; düzəldilənlər (P0 media,
P1 plan əhatəsi, P1 hadisə lenti trigger-i, P2 idxal qapısı) orada sənədləşdirilib.

| # | Problem | Mənbə | Status |
|---|---|---|---|
| S2-1 | `structure_tree_action` / `group_action` hədəf təşkilatı URL **slug**-ından, icazəni isə `request.org_permissions`-dan (**AKTİV** təşkilat) alır. A-da `unit.tree_manage`, B-də yalnız `unit.view` üzvlüyü olan aktor B-nin struktur ağacını dəyişə bilər. Tək tenantda latent. `apps/organizations/structure_actions.py:205`, `group_actions.py:271`, `views/shared/_helpers.py:68` | WAVE2 | OPEN (P2 — eyni naxış bütün `organizations/<slug>/…` səthindədir, ayrıca dilim kimi aparılmalıdır) |
| S2-2 | `TaskRowReview` «tarixçə» deyil: `update_or_create` koordinatorun əvvəlki vizasını üstündən yazır (`apps/workload/services/reviews.py:126`) | WAVE2 | OPEN (P3 — ya sənəd dili «cari viza»ya dəyişsin, ya append + `latest` güzgüsü) |
| S2-3 | `QuestionSubmissionEvent` DELETE qəsdən bloklanmır: `QuestionSubmission.delete()` (`submission_inbox.py:327`) FK CASCADE ilə bütün izi aparır. UPDATE artıq trigger ilə bağlıdır (`exams/0065`) | WAVE2 | OPEN (P3 — `on_delete=PROTECT` + göndərişin soft-delete-i təklif olunur; `core.audit` sətri qalır) |
| S2-4 | Qəbulun bir dəfəlik parol siyahısı (`credentials[]`) JSON cavabında qayıdır (`apps/accounts/services/intake/apply.py:246`) — saxlanılmır, amma brauzer tarixçəsinə/proxy loglarına düşə bilər | WAVE2 | OPEN (P3 — ayrıca `no-store` CSV/PDF endpoint-i) |

## QA dalğası 2 (PHASE21_UI_QA_WAVE2, 2026-09-03) — 13 rol × 456 bölmə açılışı, 0×500, 0 CSP
| # | Problem | Mənbə | Status |
|---|---|---|---|
| W2-1 | `EMSCore.getCsrfToken()` çərəz adını sabit yazırdı → `CSRF_COOKIE_NAME` fərqli olan mühitdə BÜTÜN `fetchJSON` yazıları 403 | WAVE2 | FIXED (`static/js/core/csrf.js` DOM/meta fallback, 997a4195) |
| W2-2 | Köhnə reviziyalı fakültə dilimi qərarı qəbul olunurdu → dekan superseded dilimi «təsdiqləyir», tapşırıq ilişib qalır (səssiz itən qərar) | WAVE2 | FIXED (`workload/services/workflow.py` 409 `stale_revision` + reqressiya testi) |
| W2-3 | 8 bölmədə qabıq başlığı ilə eyni `<h1>` təkrarı | WAVE2 | FIXED (8 şablon + 2 CSS, embed `h2`; 456/456 tək h1) |
| W2-4 | 13 yeni ekranın heç biri dashboard-a bağlı deyildi (TŞ rəhbəri kafedra bölgüsünə yönəlirdi, koordinatorda viza, dekanda təsdiq, rektorda baxış, tələbə xidmətlərində qəbul/reyestr yox) | WAVE2 P2-1 | FIXED (`staff.design_link_cards` — 12 rol-qapılı, sorğusuz keçid kartı; 4 yeni test; b7342a3a) |
| W2-5 | `teaching_office_staff` `semester.open` açarına sahibdir (açılış yarada bilir); `semester.lock/unlock` yoxdur. HANDOFF_FULL_PLAN §2/07 yalnız rəhbər+RİM deyir | WAVE2 P2-2 | OPEN — **sahib qərarı** (açılış ≠ kilid; bloklayıcı deyil) |
| W2-6 | Menyu səthi plandan genişdir: `exam_center`/`student_services` struktur ekranlarını, `program_coordinator` tədris planı/semestr açılışını OXUYUR (yazı endpoint-ləri ayrıca qapılıdır, sızma yoxdur) | WAVE2 P3-1 | OPEN (P3; P1-10 ailəsi — `org_admin` alias) |
| W2-7 | `curriculum-editor` (1) və `semester-opening` (2) cədvəllərində `aria-sort` yoxdur | WAVE2 P3-2 | OPEN (P3) |
| W2-8 | İcazəsiz bölməyə tam səhifə keçidi (`?section=workload-center`, tələbə) səssiz `profile-info`-ya düşür, mesaj yoxdur (AJAX ucu düzgün 403) | WAVE2 P3-3 | OPEN (P3, yalnız UX) |
| W2-9 | Fikstur: `qa.chair_head` və `qa.dean` fərqli fakültədədir — zənciri uçdan-uca sürmək üçün müvəqqəti üzvlük lazım oldu | WAVE2 | Qeyd (klon fiksturu; növbəti dalğada uyğunlaşdırılsın) |

