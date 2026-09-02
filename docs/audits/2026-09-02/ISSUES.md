# Mərkəzi problem / tapşırıq siyahısı — köçürmədən sonrakı audit (2026-09-02)

Status: OPEN · IN-PROGRESS · FIXED (klonda yoxlanıb) · DEFERRED (sahib qərarı) · WONTFIX (qəsdən belədir)

## P0 — data / təhlükəsizlik / autentifikasiya / icazə
| # | Problem | Mənbə | Status |
|---|---|---|---|
| P0-1 | 2,291 cari tələbə səhvən `archived`+`alumni` (qrupun `start_year='0000'`, 248 qrup) → giriş bağlı | PHASE1 data audit | FIXED (klon): `rehearsal_sar_phase._decide` yalnız `azadedildi=1` ilə arxivləyir; `legacy_repair_archive_status --apply` → archived 2,490→199, active 5,948→8,239, 2,291 audit sətri, 2-ci icra 0; `accounts/0018_account_restore_evidence` |
| P0-2 | 100 tələbə + 14 işçi hesabsız (14 e-poçt toqquşması karantin, 86 etibarsız e-poçt); 12 karantinli işçiyə 62 jurnal bağlıdır | PHASE1 | FIXED (klon): identity fazası placeholder e-poçt; `legacy_repair_missing_accounts --from-source --apply` → 114 yaradıldı (tələbə 7,716→7,816, işçi 715→729), 45 açılış müəllim aldı (müəllimsiz 1,203→1,168), 2-ci icra 0. Demoqrafiya: birth_date 0→2,175, gender 0→1,693 |
| P0-3 | Hədəfdə cari akademik dövr yoxdur (mənbədə `semestr_jurnal.id=13 is_current=1`), 2026/2027 yaradılmayıb → «Fənlərim» boş | PHASE1 | FIXED (klon): `legacy_repair_current_period` → 2025/2026 Yaz cari (1,212 açılış), 2026/2027 yaradıldı (0 açılış) |
| P0-4 | Cədvəli açılışın istənilən müəllimi dəyişə bilirdi; icazə açarı, koordinator/RİM yolu, audit, bildiriş yox idi | PHASE2 rol matrisi | IN-PROGRESS — `schedule.manage` + «Cədvəl idarəetməsi» bölməsi (cədvəl agenti) |
| P0-5 | Dərs yükü axını mövcud deyildi (`apps/workload` yox) | PHASE2 | FIXED (klon): `apps/workload` F0+F3+F4 — 5 model + RLS/saat-balans/append-only trigger, `workload.*` icazə ailəsi, 14 JSON endpoint, «Yük bölgüsü» + «Dərs yüküm» bölmələri, offering sinxronu; 71 test; canlı: kafedra müdiri 3 sətir/6 bölgü → 3 açılış + 2 bildiriş; audit branch-ına birləşdirildi (d32e3d37). Qalan: F1 tədris şöbəsi redaktoru, F2 dekanlıq təsdiqi, F5 hesabat/amendment UI |
| P0-6 | Müraciətlər / ESD modulu yox idi | tapşırıq | FIXED (klon): `apps/applications` (152 test) + kabinet bölməsi «Müraciətlərim» (9 test); canlı: tələbə→koordinator→RİM→həll→bağla, 0 konsol/CSP xətası, 375 px slide-over |
| P0-4 (yenilənmə) | Cədvəl | — | FIXED (klon): `schedule.manage`, «Cədvəl idarəetməsi», müəllim 403, 26 yeni test |
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
| P1-5 | 12,457 bal + 19,116 qayıb xanası dərs sətirsiz (J12 `journal_lesson_recovery` fazası işlədilməyib) | PHASE1 | OPEN — hədəfə tətbiq üçün dəstəklənən hədəfli yol yoxdur (ledger `transform_version` konflikti); təzə tam repetisiya tələb edir |
| P1-6 | `birth_date`/`gender`/`student_group_number` köçürülməyib (mənbədə var) | PHASE1 | IN-PROGRESS — `legacy_repair_demographics` |
| P1-7 | Tələbə siyahısını yükləmək üçün heyət yolu yoxdur (`import_users_from_excel` komandası prod-da söndürülüb; RİM mərkəzində «yarat/idxal» yoxdur) | PHASE1 provisioning | FIXED (klon): `user.import` icazəsi (RİM/HR) + «Tələbə idxalı» bölməsi — xlsx şablon → dry-run → apply (User+Profile+Membership+SAR, sətir-sətir savepoint, placeholder e-poçt, birdəfəlik parol yalnız cavabda); 26 test; canlı 3 sətir (2 yaradıldı, 1 xəta), yeni tələbə giriş etdi. Komanda kill-switch-i dəyişməyib |
| P1-8 | 3,075 SAR plan sətri olmayan kurikuluma bağlı; 87 boş kurikulum | PHASE1 | DEFERRED (mənbədə plan yoxdur) |
| P1-9 | `FinalGrade.is_published` heç bir kod yolu ilə TRUE olmur (ölü sütun); əsl nəşr bayrağı `AssessmentScheme.is_published` (RİM jurnal bağlaması) | PHASE1 | WONTFIX-izah: tələbə UI-a təsiri yoxdur; sənədləşdirildi |
| P1-10 | dean/chair_head `org_admin` alias-ı alır → org-səviyyəli bloq moderasiyası sızması | PHASE2 | OPEN → düzəliş keçidi |
| P1-11 | Kollokvium/apellyasiya idarəsi icazə açarı ilə yox, rol ADI ilə qapılır | PHASE2 | OPEN → 2-ci dalğa |
| P1-12 | `/accounts/send-otp/` və parol bərpası «done» səhifəsində hesab sadalama | PHASE23 | OPEN → düzəliş keçidi |

## P2 — səhv funksionallıq / ciddi UX
| # | Problem | Mənbə | Status |
|---|---|---|---|
| P2-1 | Qruplar bölməsi hər açılışda org-səviyyəli tələbə checkbox siyahısı qururdu (813 ms) | PERF | FIXED — lazy `teacher_group_candidates` |
| P2-2 | `LegacyEntityMap.target_pk` indeksi yox (97.7 ms → 0.4 ms) | PERF | FIXED — `legacy_import/0007` |
| P2-3 | 2 istifadəçiyə görünən «İKT» mətni | scout | FIXED — «RİM rəhbəri» + 4 dil |
| P2-4 | Əks axtarış köməkçisi yox idi (koordinator/kafedra müdiri/dekan → vahid) | scout | FIXED — `apps/organizations/unit_heads.py` (18 test) |
| P2-5 | Tələbə kabinetinin başlığında «Join» düyməsi (köçürülmüş tələbə nəyə qoşulmalıdır?) | UI | OPEN → UX keçidi |
| P2-6 | 1,589 toqquşmada uduzan dəyər UI-da yox; `yekun`↔imtahan balı 884 sətirdə fərqli | PHASE1 | DEFERRED (BAL_PROBLEMLERI.md) |
| P2-7 | Provisioning canlı gedişi + `test_staged_portal_login.py` (6 test) hələ yaşıl təsdiqlənməyib | provisioning | OPEN → reqressiya dalğası |
| P2-8 | Audit jurnalı admin-dən silinə bilir; `get_client_ip` XFF-in ən sol üzvünü oxuyur; base→production settings sürüşməsi; portal qapısı `POST /accounts/login/` ilə keçilir | PHASE23 | OPEN → düzəliş keçidi |
| P2-9 | Yüklənmiş sənədlər (düzəliş PDF-ləri) icazə yoxlamalı serve view-suz `.url` ilə verilir | scout/security | OPEN — `applications` üçün qapılı download view yazılıb; köhnə modullara tətbiq 2-ci dalğa |

## P3 — cilalama
| # | Problem | Mənbə | Status |
|---|---|---|---|
| P3-1 | Hər kabinet səhifəsində ~50–65 sorğuluq «profil qabığı vergisi» | PERF | OPEN (context_builder mərhələləri) |
| P3-2 | ~90 kod şərhində hələ «İKT» | scout | WONTFIX (kosmetik) |
| P3-3 | Kollokvium pəncərəsi view qatı üçün ayrıca test yoxdur | scout | OPEN |
| P3-4 | Host: repo iCloud-sinxron Desktop-dadır → pack fayl boşalması, `git diff` sınır; yenidən yükləmə `/private/tmp` scratchpad-ı sildi | infra | Qeyd: hesabatlar indi `docs/audits/2026-09-02/`-də saxlanır |
