# EMSArena — Tam texniki audit və düzəliş hesabatı (Claude, 2026-09-13)

**Metod.** Bu audit `Develop` `96016cff` (CI yaşıl) vəziyyətindən başlayıb; 9 sahə üzrə oxu-yalnız auditor (imtahan, auth/RBAC/tenant, məlumat bütövlüyü, təhlükəsizlik, backend/biznes-məntiq, infrastruktur, testlər/akademik axınlar, frontend/a11y/i18n, performans) sübut topladı — hər tapıntı üçün `fayl:sətir`, endpoint, sandbox reproduksiya testi və ya QA klonunda `BEGIN…ROLLBACK` SQL. Sonra 7 düzəliş dalğası (imtahan, auth, RBAC, backend, data+security, infra, frontend, perf) tapıntıları bağladı; hər düzəlişin reqressiya testi var. Tam sübut faylları: `docs/audits/2026-09-13-claude/findings/<sahə>.md`. Codex-in 2026-09-12 hesabatı tarixi baza kimi istinad olunur.

**Məlumat qorunması.** Real baza (`localhost:5432`, `emsarena_db`) heç bir mərhələdə açılmayıb. Oxu QA klonunda (`127.0.0.1:55433`, `emsarena_rehearsal_a0d170000901`, 8 641 istifadəçi) `BEGIN…ROLLBACK` ilə; yazı yalnız agent sandbox bazalarında (`:55432`, `ems_<slug>`). Klonda yeganə dəyişiklik: kodun tələb etdiyi 6 sxem miqrasiyasının tətbiqi (`exams.0066`, `registrar.0071–0075`) — məlumat sətri dəyişdirilməyib. Parollar heç bir hesabata yazılmayıb (klon test hesabları `qa.<rol>` yalnız test məqsədlidir).

---

## 1. İcra xülasəsi

EMSArena-nın bünövrəsi möhkəmdir: modul monoliti sərhəd qapıları ilə (0 dövr, 0 xüsusi cross-app import), 487/487 FK bütövlüyü, 141/171 cədvəldə FORCE RLS, 60+ invariant trigger-i, atomik imtahan dərci, server-tərəfli deadline, OCC, kilidli qiymətləndirmə, 8 618 testlik PostgreSQL dəsti. Bu audit isə dərinlikdə **1 P0 və 12 P1** tapdı və hamısını kodda bağladı:

* **P0 — imtahan cavab açarı sızması:** tələbə imtahan gedərkən ikinci tabda nəticə URL-ini açıb düzgün variantları görüb geri qayıda bilirdi (`exams/views/student/results.py`). Düzəldildi + reqressiya testi.
* **P1 — imtahan:** final imtahanı kabinetdə görünən PIN ilə zal/bilet/nəzarətçi qapısından kənarda başladıla bilirdi; həmin endpoint-də PIN brute-force limiti yox idi; sual bankının məzmununu (cavab açarı daxil) sahibdən başqası dəyişə bilirdi.
* **P1 — icazələr:** superadmin girişi üçün brute-force sərhədi faktiki yox idi; imtahan mərkəzi rəhbəri müəllim/HR üzvlüyünü, dekan başqa fakültənin tələbəsini uzaqlaşdıra bilirdi (`member.remove` açarı kodda heç yerdə yoxlanmırdı); rol təyinatı audit-loglanmırdı.
* **P1 — məlumat:** superadmin «tam silmə» tələbənin akademik tarixçəsini (qeydiyyat, 40 763 dərs qiyməti, yekunlar) kaskadla aparırdı; `FinalGrade.exam_score` üçün DB diapazon yoxlaması yox idi (349 legacy sətir > 50).
* **P1 — infrastruktur:** final-mərkəz WebSocket consumer-ləri RLS-siz sorğu verirdi — NOBYPASSRLS tətbiq rolu (Codex P0-01 rollout-u) tətbiq olunan kimi bütün nəzarətçi monitorları 4403 alacaqdı; işləyən image 69 gün geridədir; alert kanalı işləmir (owner-only).
* **P1 — dərs yükü:** kafedra müdiri tədris şöbəsinin göndərilməmiş qaralamasını dekan təsdiqi olmadan bölüb açılış yaradırdı.
* **P1 — lokallaşdırma:** «Bağla» RU/TR-də «Aç», «Seçimi sıfırla» → «Sil», yoxlanmamış cəhdlərdə əsas əməl «Geri»; 613 `pgettext(_CTX, …)` sətri heç bir kataloqda yox idi (qapı kor nöqtə).

Ümumi texniki bal: **72,8 → 79,4/100**; istehsal hazırlığı **48/100** (bölmə 29–30). Kod istehsala yaxındır; işləyən mühitin maneələri (superuser DB rolu, köhnə image, alert kanalı, real backup restore) owner əməliyyatlarıdır və bu audit onları icra etməyib.

## 2. Claude-dan qalan yarımçıq işlər

Faza 1 yoxlaması (git vəziyyəti, Codex-in «açıq» siyahısı, kodda TODO/`NotImplemented`): 2026-09-12/13 remediasiya dalğasından yarımçıq iş qalmayıb — `96016cff`-də iş ağacı təmiz, CI 11/11 yaşıl. Tapılan qalıqlar və nəticəsi:

| Qalıq | Vəziyyət |
|---|---|
| Codex P2-06 i18n: `course_panel_tabs.js` türkcə mətn `gettext()`-də; `_import.html` təkrar «tələbə» msgid | ✅ tamamlandı (`7c5dc612`) |
| Codex P2-07 SQLite dəsti | ✅ əvvəl bağlanmışdı (8 206 keçir) |
| Codex P0-01 superuser DB rolu | ⏳ owner-only; bu audit onun gizli blokerini (WS consumer RLS) bağladı |
| Codex P1-07 image drift / P1-08 TLS bayraqları / P2-08 Redis maxmemory | ⏳ owner-only (bölmə 27) |
| Legacy reconciliation (1 374 364 sətir pending, 461 944 issue open) | ⏳ proses işi — bu audit yalnız ölçdü |

## 3. Məlumat bütövlüyü vəziyyəti

**Mövcud məlumat toxunulmaz qalıb.** Real bazaya qoşulma olmayıb; klonda yalnız sxem miqrasiyası. Klon üzərində ölçülənlər (`findings/data.md`, SQL `01–14`):

| Yoxlama | Nəticə |
|---|---|
| FK bütövlüyü (487 constraint) | 0 dangling; 0 `NOT VALID` |
| Tenant uyğunluğu (142 birbaşa + 39 çox-addımlı cüt) | 0 uyğunsuzluq (klonda 1 tenant — multi-org NOT TESTED) |
| Unikallıq: enrollment/final/mark/componentscore/attempt/SAR/FIN | 0 dublikat |
| Mojibake, mümkünsüz tarix, komponent balı > max, giriş balı > 50 | 0 |
| **`registrar_finalgrade.exam_score > 50`** | **349 sətir** (max 89) — mənbədən olduğu kimi; DB CHECK yox idi → indi `0..100 NOT VALID` CHECK + siyahı SQL-i (bölmə 26); 349 sətir İmtahan Mərkəzi qərarını gözləyir |
| Yumşaq dublikatlar | 1 ehtimal ikiqat tələbə (id 1030/3279), 7 dublikat qrup adı (15 orgunit), 9 fənn adı, specialty kodu `5555` ×24 |
| Tamlıq boşluqları (mənbə mənşəli) | 118 fənsiz kurikulum / 3 685 SAR; 1 172 müəllimsiz açılış (10,5 %); doğum tarixi 72,8 %, FIN 93 % boş; `admission_year=1950` 2 427 SAR; 2021/22 finalları 93 % boş |
| Legacy proses | reconciliation 0/1 374 364, issue review 0/461 944, 19 852 bağlanmayan fakt |
| RLS örtüyü | 141/171; org-sütunlu siyasətsiz: `accounts_userprofile` (bilinən), `registrar_guestrosterdocument` → **düzəldildi** (0074) + CI testi |
| Backup | gündəlik `pg_dump -Z6` + rotasiya + freshness metrikası; off-site/PITR/media backup yox; sintetik dump→restore məşqi tam paritet (172 cədvəl/210 trigger/142 siyasət/492 FK); **real ölçülü restore NOT TESTED** |
| Kaskad riski | `hard_delete_account` Django CASCADE ilə SAR/enrollment/mark/final-ı aparırdı; 875 tələbə `LegacyGradeFact PROTECT`-ə düşmür → **düzəldildi** (akademik tarixçəli hesab yalnız arxivlənir) |

Miqrasiya riskləri: MariaDB mənbəsi əlçatan olmadığından sahə-sahə müqayisə **ölçülməyib**; klon 2026-09-03 rehearsal run-udur (batch zənciri/digest 0 fərq, hədəf 0 itkin).

## 4. Kritik tapıntılar (P0)

| ID | Tapıntı | Yer | Vəziyyət |
|---|---|---|---|
| EX-01 | Bitməmiş (`in_progress`/`draft`) cəhdin nəticə səhifəsi düzgün variantları göstərir; tələbə ikinci tabda açıb geri qayıdıb cavabları düzəldir. Repro: status `in_progress` ikən 200 + `correct-option`, sonra `take_exam` 200. | `apps/exams/views/student/results.py::exam_result` — `attempt` yalnız `id/exam/user` ilə götürülürdü | ✅ `f5981b1a`: `expire_if_time_limit_reached()` + açıq cəhd → `take_exam`-a 302; test `InProgressResultPageTests` |

## 5. Yüksək prioritetli tapıntılar (P1)

| ID | Sahə | Tapıntı | Yer | Vəziyyət |
|---|---|---|---|---|
| EX-02 | İmtahan | `/exams/code-check/` kabinetdə görünən PIN ilə FINAL imtahanı zal IP qapısı, bilet, gözləmə otağı, nəzarətçi start-ı olmadan başladır (`FINAL_EXAM_ALLOWED_IPS` dolu ikən 127.0.0.1-dən attempt, `room_id=None`) | `views/shared/access.py::exam_code_check` | ✅ final yalnız `/exams/final/`; test `CodeCheckFinalGateTests` |
| EX-03 | İmtahan | Həmin endpoint-də PIN brute-force limiti yox (30 səhv → 30×400, hər biri PBKDF2) | eyni | ✅ `/exams/final/` ilə eyni istifadəçi-adı limiteri, 429 |
| EX-10 | İmtahan | `bank_question_add/edit/bulk_add/ai_generate` yalnız OXU görünürlüyü ilə yazır — mərkəz rəhbəri yad paylaşılmamış bankın sualını, müəllim paylaşılan bankın sualını auditsiz dəyişir (09-02 P0-2 düzəlişi natamam idi) | `views/teacher/question_library/questions.py` | ✅ `_ensure_bank_mutation_allowed` 4 view-da (deny audit + 403); test `BankQuestionWriteOwnershipTests` |
| ACC-F01 | Auth | Superadmin üçün login limiti dolanda hər cəhd yenə `authenticate()`-dən keçir, düz parolda 302 → brute-force sərhədsiz | `accounts/views/auth/login.py:222-236` | ✅ `9d18aa07`: ayrıca `superadmin_escape` vedrəsi (3/1h İP+ad), uğursuz cəhdlər sayılır; 4 test |
| ACC-F03 | RBAC | İmtahan mərkəzi rəhbəri (85, `member.remove` YOX) müəllim və HR üzvlüyünü deaktiv edir — qapı `level ≥ 65` idi | `organization/_management_flow/_members.py` | ✅ `140d2772`: `member.remove` + `get_permission_scope` əhatəsi; UI düyməsi də eyni qayda (`2e569180`) |
| ACC-F04 | RBAC | Dekan öz fakültəsindən kənar tələbəni uzaqlaşdırır (unit scope yoxlanmır) | eyni | ✅ hədəfin bütün aktiv üzvlükləri aktor alt-ağacında olmalıdır (fail-closed) |
| BE-F02 | Audit-log | Rol təyinatı/silinməsi heç bir audit izi yaratmır | `accounts/views/_helpers/membership.py::_sync_user_role_memberships` | ✅ `2c0411a6`: `AuditLog` old/new rol dəsti, added/removed |
| DATA-F2 | Məlumat | `hard_delete_account` akademik tarixçəni kaskadla silir | `accounts/services/account_deletion.py` | ✅ `28417a1d`: `AccountDeletionError("hard_delete_academic_history")` + UI mesajı |
| DATA-F1 | Məlumat | `FinalGrade.exam_score` diapazonu sxemdə yoxdur (349 sətir > 50) | `registrar/models/grading.py` | ✅ CHECK `0..100 NOT VALID` (0075). Qərar: 50 deyil 100 — legacy J-V2 qaydası (>50 dəyəri saxla + `above_scheme` bayrağı) qorunur; yeni yazı yolu onsuz da 50-yə clamp edir |
| INF-P1-1 | WS/RLS | Final-mərkəz consumer-ləri `bypass_rls()`-siz — NOBYPASSRLS rolunda 4403 (P0-01 rollout-un gizli blokeri) | `apps/exams/consumers.py` | ✅ `a9b2a7fe`: `database_sync_to_async_rls` (`rls_worker_atomic`+`bypass_rls`); `rls_app_role` ilə test |
| INF-P1-2 | Infra | İşləyən image 2026-07-06 build-dir (Django 5.2.15, pypdf/sqlparse CVE-li), 9 servis yoxdur, Redis maxmemory 0 | işləyən mühit | ⏳ owner-only (bölmə 27) |
| INF-P1-3 | Monitorinq | Alert kanalı faktiki işləmir: Brevo «525 Unauthorized IP», alertmanager/prometheus/nginx `Exited (127)` 5+ gün, self-monitoring yox | lokal prod-like stack | ✅ repo tərəfi `39e9de4e`: `Watchdog` (həmişə yanan) + `AlertmanagerNotificationsFailing` (critical) qaydaları, `heartbeat` receiver-i, sənəd (Brevo «Authorised IPs»); `promtool`/`amtool` yoxlaması SUCCESS. **Çatdırılma özü owner-only** (bölmə 27) |
| WL-FT1 | Dərs yükü | Kafedra müdiri TŞ-nin göndərilməmiş qaralamasını dekan təsdiqi/koordinator vizası olmadan bölüb `distributed` edir, `sync_offerings` açılış yaradır | `workload/services/workflow.py::ensure_distribution_stage` (yalnız `submitted_at`-a baxırdı) | ✅ `afcc9935`: istisna yalnız kafedranın özü yaratdığı qaralama üçün; `confirm_distribution` eyni qapı; 4 test |
| FE-F1..F4 | i18n | «Bağla»→RU «открыть»/TR «açık»; «Seçimi sıfırla»→«Удалить/Silmek»; `action_check`→«Geri/Back» (4 dil); 613 `pgettext(_CTX, …)` sətri kataloqsuz (skaner modul sabitini görmür) | `locale/*`, `scripts/i18n_source_scan.py` | ✅ `4e110172`: 31 msgstr yerində düzəldildi; `i18n_source_scan.py` modul-sabit kontekstləri həll edir (2 685/2 690 çağırış), dəqiq boşluq **564 django + 17 djangojs** msgid → doldurulub, qapı yaşıl; `core/tests/test_i18n_source_scan.py` (11 test) |

## 6. Orta prioritetli tapıntılar (P2)

Ümumi: **48 P2** tapıldı, **36 bağlandı**, 12 açıq (əksəri owner/proses qərarı).

| Sahə | ID | Tapıntı (qısa) | Vəziyyət |
|---|---|---|---|
| İmtahan | EX-04 | Bilet yolu deaktiv/arxiv imtahana və limiti dolmuş tələbəyə cəhd yaradır | ✅ |
| İmtahan | EX-05 | Deadline anındakı avtomatik «finish» POST-u atılır — son cavablar itir | ✅ 15 s grace |
| İmtahan | EX-06 | `/exams/final/` fərdi-PIN yolu IP limiterini yan keçir | ✅ |
| İmtahan | EX-07 | Rədd edilən fayl yükləməsi əvvəlki faylları silir | ✅ |
| İmtahan | EX-08 | `draft` statusu unikal məhdudiyyətdən kənarda | ✅ migr. 0066 |
| İmtahan | EX-09 | Autosave kilidi `exams_exam` sətrini də tutur (bir imtahanın bütün tələbələri serializasiya) | ✅ `FOR UPDATE OF` |
| Auth | ACC-F02 | OTP API hesab enumerasiyası (`password_reset` 202/404, `signup` 409/404) | ✅ neytral 202 |
| Tenant | ACC-F05 | `registrar_guestrosterdocument` RLS-siz | ✅ 0074 + CI testi |
| RBAC | ACC-F06 | 16 reyestr açarı kodda yoxlanmır (icazə redaktoru «yalançı» düymələr) | ◐ `member.remove` bağlandı; 13 açar ratchet-də, qapısız |
| Məlumat | D-L1..L3 | Reconciliation 0/1,37 M, issue review 0/462 k, 19 852 bağlanmayan fakt | ⏳ proses (review UI/CLI işə salınmalı) |
| Məlumat | D-L6/L7 | 118 boş kurikulum / 3 685 SAR; 1 172 müəllimsiz açılış | ⏳ TŞ/İMT qərarı |
| Məlumat | D-dup | 1 ehtimal ikiqat tələbə (1030/3279), 7 dublikat qrup adı | ⏳ dedupe → unikal indeks DDL hazır |
| Məlumat | D-RLS | `accounts_userprofile` RLS-siz | ⏳ giriş-öncəsi oxunuşlar `bypass_rls`-ə alınmalıdır (riskli, ayrıca iş) |
| Məlumat | D-demo | Doğum tarixi 72,8 % / FIN 93 % boş, `admission_year=1950` ×2 427 | ⏳ mənbə mənşəli |
| Təhlükəsizlik | SEC-F01 | LLM çıxışı escape-siz `innerHTML` | ✅ |
| Təhlükəsizlik | SEC-F02 | `assignments/submissions/`, `notifications/files\|images/` media checker-siz (fail-closed 404) | ✅ checker + test |
| Təhlükəsizlik | SEC-F03 | Klon/staging DB parolları 8 tracked faylda | ✅ env fayllarına; gitleaks qaydası; **rotasiya owner-only** |
| Backend | BE-F01 | Qeyri-UUID/int pk → 500 (workload assign/row_save, cədvəl slotu, superadmin org) | ✅ `core/http_ids.py`; 5 yer qalır (P3) |
| Backend | BE-F03 | Əlavə cəhd qrantı audit-siz + istənilən `User.id` | ✅ audit + aktiv üzvlük |
| Backend | BE-F04 | Org approve/suspend/reactivate və GPA şkalası audit-siz | ✅ |
| Backend | BE-F05 | ÜOMG iki düstur, eyni etiket (transkript 100-bal vs statistika 4.0) | ✅ etiketlər ayrıldı («Orta GPA (4.0)») |
| Backend | BE-F06 | Davamiyyət həddi iki mənbə (qapı 25 vs kabinet 10) | ✅ `registrar/absence_limit.py`; finals/qrid P3 |
| Backend | BE-F07 | 31 çoxyazılı view `atomic`-siz | ◐ 8 ən riskli sarıldı; qalanı P3 siyahısında |
| Backend | BE-F08 | `journal_sync` səssiz istisna → jurnal körpüsü kəsilir, log yox | ✅ `logger.exception` + metrik |
| İnfra | INF-P2-1 | Alertmanager webhook prod konfiqində 400/301 | ✅ nginx daxili location + test |
| İnfra | INF-P2-2 | Prometheus 8 replikanı tək nginx hədəfi ilə qarışdırır | ✅ `dns_sd_configs` |
| İnfra | INF-P2-3 | `stop_grace_period` yoxdur (10 s SIGKILL) | ✅ app 130/worker 300/heavy 900/pg 60 s |
| İnfra | INF-P2-4 | arp-agent gateway pin-lənməyib → imtahan qapısı fail-closed riski | ✅ IPAM 172.18.0.0/16 + healthcheck |
| İnfra | INF-P2-5 | Deploy rollback / SHA teqi yoxdur | ⏳ təklif diff hesabatda (rehearsal-sız tətbiq edilmədi) |
| İnfra | INF-P2-6 | `sweep_overdue_attempts` kilidsiz kor yazı (`submitted` → `expired`) | ✅ `sweep_guard.py` sətir kilidi + CAS + race testi |
| İnfra | INF-P2-7 | Backup: off-site/şifrələmə/media/PITR yox | ⏳ owner |
| İnfra | INF-P2-8 | Heavy növbəsi/worker monitorinqsiz | ✅ metrik + `CeleryHeavyWorkerDown` |
| İnfra | INF-P2-9 | `prometheus.depends_on app healthy` | ✅ |
| İnfra | INF-P2-10 | İşləyən Redis `maxmemory 0` | ⏳ owner |
| Testlər | F-T2 | Xaric edilmiş tələbə öz qrupuna bərpa oluna bilmir | ✅ |
| Testlər | F-T4 | QA klon sxemi koddan geridə (exam-score-entry 500) | ✅ klon miqrasiya edildi |
| Testlər | F-T5 | Paralel agentlər eyni nömrəli migrasiya yaratdı (proses) | ⏳ tək-yarpaq testi təklifi |
| Frontend | FE-F5 | AJAX bölmə keçidindən sonra fokus `body`-də | ✅ başlığa fokus + aria-live |
| Frontend | FE-F6 | `--ems-neutral-400` (2,56:1) 63 mətn qaydasında | ✅ 56 qayda token dəyişdi |
| Frontend | FE-F7 | Dərs yükü JS-i i18n-siz (18 literal) | ✅ |
| Frontend | FE-F8/F9 | «March»→«Search»; «Dublikatlar» kartı «Mövzu» | ✅ |
| Perf | PF-F01/02/04 | N+1: qrup tələbələri, qrup forması prefetch, `syllabus_for_offering` ×12 | ✅ |
| Perf | PF-F05 | Finish +1 sorğu/sual | ✅ 112 → 42 |
| Perf | PF-F10 | `/exams/groups/` tam səhifəsi 2 008 ms / 2,5 MB | ⏳ kabinet bölməsi sahib qərarı ilə silindiyi üçün yönləndirmə mümkün olmadı; JS lazy namizəd yükləməsi lazımdır |
| Perf | PF-F12 | Sillabus siyahısı 4 926 sətir Python-da | ✅ 1 076 → 87 ms |
| Perf | PF-F13 | Lessons-log KPI 509 833 qeyd keşsiz | ✅ SQL + 300 s keş (949 → 245 ms) |
| Perf | PF-F14 | `/jurnal/` org-geniş aqreqat paginasiyadan əvvəl | ✅ 365 → 95 ms |

## 7. Aşağı prioritetli tapıntılar (P3)

Ümumi: **~75 P3** (sahələr üzrə: imtahan 3+4 qeyd, auth/RBAC 7, məlumat 12, təhlükəsizlik 8, backend 7, infra 18, testlər 7, frontend 13, perf 8). Bağlananlar: BE-F10 (8 «200-on-failure» → düzgün status), BE-F14 (`console.log`), SEC-F04/F05 (self-XSS sink-lər), SEC-F07 (CSV/XLSX formula, 5 ixrac), SEC-F11 (imtahan bal dəyişikliyi `AuditLog`-a), ACC-F07 (yad tenant struktur səhifəsi 302), ACC-F10 (qrant tenant), ACC-F12 (`assignment.edit`), ACC-F13 (`RLS_BYPASS_AUDIT` skriptlə 156/65 + `rows` 403), INF-P3-7/P3-14/P3-15, FE-F10/F12/F13/F14/F20/F22, PF-F03/F06/F11, WL «rows» 403. Açıq qalanların tam siyahısı `findings/*.md`-dədir; ən mənalıları:

| Sahə | Açıq P3 |
|---|---|
| İmtahan | `exams_examanswer` RLS siyasəti sətir-başına subplan (böyük finalda ölçülməli — `organization_id` denormalizasiyası); `ERROR_LOCKED` mesajı bilet mövcudluğunu açır; PIN girişi tam platform sessiyası; `reissue/revoke_student_pin` müstəqil audit; Redis kəsintisində kapasite qapısı fail-open |
| Auth/RBAC | `login` OTP məqsədində gövdə-səviyyəli fərq (`expires_in`) — mövcud UI müqaviləsi; 13 qapısız reyestr açarı; icazə matrisi sənədləri (`permission-matrix.md`) köhnə |
| Məlumat | 9 dublikat indeks + `lessonmark` org indeksləri ~85–100 MB; `registrar_lesson (organization_id, date)` indeksi; fənn/proqram/specialty-kod dublikatları; 228 dövr-kənar dərs; 371 qeydiyyatsız SAR |
| Təhlükəsizlik | Upload MIME müştəri başlığına etibar, `.xhtml/.mjs/.svgz` block-list-də yox, Pillow `verify()` yox; AI assistant PII + prompt retention; `google-generativeai` deprecated; 6 ixrac view-u hələ `safe_csv_writer`-siz; `.env.production.example` 24 env sənədsiz |
| Backend | `on_commit`-siz `.delay` (blog siqnalı, extract_jobs); güzgü implementasiyalar parity-testsiz; 23 modul 590–600 sətir; bal/idxal endpoint-lərində rate-limit yox; 23 atomic-siz view; 5 qeyri-UUID pk yeri |
| İnfra | nginx/app healthcheck dəqiqliyi; Redis parolu argv-də; `/health/` build sha sızması; image digest pin; nginx 1.28/Loki 3.5; Alertmanager `sed` render (`\|`/`&` parol); Blackbox host git-də; Daphne `--proxy-headers`; deploy `check --deploy` WARNING səviyyəsi |
| Testlər | venv-də `pytest-cov`/`pytest-timeout` yoxdur; 4 test heç yerdə işləmir (tesseract, `rehearsal_target`); migrasiya testləri 25 CPU-dəq; fixture dublikasiyası; `freezegun` yoxdur |
| Frontend | 13–18 px hədəflər; login xətası `role=alert`-siz; mobil sidebar fokus; 18 ikon-only düymə adsız; `jd2.css` outline; 22 native `confirm()`; `create_combo.js` `closest` qorumasız |
| Perf | RLS `set_config` 5–17/səhifə; `access_state` ×3; membership ×3–5; `people/analytics` planner təxmini; 259–711 KB HTML səhifələr; `create_student_group` eyni 2,5 MB profili |

## 8. Arxitektura qiymətləndirilməsi

**Backend.** Django 5.2 modul monoliti; `scripts/module_deps.py` (0 dövr), `scripts/public_api_boundaries.py` (0 xüsusi cross-app import), 600-sətir modul qapısı — hamısı yaşıl. 946 route / 250 JSON endpoint inventarı (`findings/backend.md` §4). Zəif tərəflər: 23 modul 590–600 sətirdə (qapıya «sığdırma»), 446 geniş `except` bloku (şərh edilib: əksəri fail-soft, 3-ü səssiz idi → düzəldildi), `ATOMIC_REQUESTS=False` ikən 31 çoxyazılı view atomic-siz idi (8-i düzəldildi, qalanı P3 siyahısında). Güzgü implementasiyalar (cəhd limiti ×3, ÜOMG 2 düstur, davamiyyət həddi 2 mənbə) — davamiyyət həddi vahidləşdirildi, ÜOMG etiketləri ayrıldı.

**Frontend.** Django şablonları + vanilla JS (343 fayl / 66 446 sətir), nonce-lu CSP (inline yox), `EMSReady`/`EMSDelegate` AJAX-safety, `ems_ui` komponent qatı, dizayn tokenləri. 7 rol × dashboard + 8–45 bölmə brauzerdə: **0 CSP pozuntusu, 0 JS xətası, 0 4xx**. Qalıq: 5 paralel BEM sistemi (~950 class) + 1 194 legacy `card`; 4 geri-sayım faylında swap-dan sonra sızan `setInterval`.

**İnfrastruktur.** Docker Compose prod stack (nginx + Daphne ×N + Celery worker/beat/heavy + Postgres/PgBouncer + Redis + Prometheus/Alertmanager/Grafana/Loki + backup sidecar), CI 11 qapı (lint, 3.11/3.12 unit, RLS txn-pool, security, gitleaks, docker build, Trivy, prod-smoke, e2e-smoke) hamısı fail-closed. Mənbə sağlamdır; işləyən mühit mənbədən 69 gün geridədir.

## 9. Məlumat bazası qiymətləndirilməsi

Sxem: UUID PK, hər FK indeksli, 111 unikal + 236 CHECK, 60+ same-org/immutable/append-only trigger, RLS 141/171 FORCE. Zəif: kaskad yalnız ORM-də (DB FK-lar NO ACTION) — hard-delete qapısı ilə örtüldü; qrup adı/kod unikallığı yoxdur (7 dublikat qrup adı; DDL təklifi `findings/data.md` §6, dedupe-dən sonra); 9 dublikat indeks + `lessonmark` üzərində ~85 MB sıfır-seçicilikli org indeksləri (P3).

Sorğu davranışı (klonda EXPLAIN ANALYZE, ORM-dən tutulmuş 9 isti sorğu): hamısı indeks yolu, 1–5 ms; tək isti nöqtə üzv reyestri (8 679 sətir × auth_user, 23 ms, 26 k buffer). Seq scan yalnız `registrar_lesson` tarix aralığında → indeks təklifi `(organization_id, date) INCLUDE (offering_id, hours)` (icra edilməyib). `exams_examanswer` RLS siyasəti sətir-başına 3-cədvəlli korrelyasiyalı subplan (P3; klonda cəhd cədvəli boş → real təsir ölçülməyib).

## 10. Legacy miqrasiya qiymətləndirilməsi

Transform sadiqdir və sübut zənciri bütövdür (batch/chain/digest 0 fərq, hədəf 0 itkin, klon = 2026-09-03 rehearsal). Amma proses yarımçıqdır: `reconciliation_status` bütün 1 374 364 sətirdə `pending`, 461 944 issue hamısı `open`, 19 852 bağlanmayan fakt, linked faktlarda 5 719 `exam_entry_exit` + 300 `summary` FinalGrade-siz, 888 summary bal fərqi. Mənbə boşluqları hədəfə köçüb (yuxarıda). **Etibarlılıq: orta (66/100)** — tamlıq yalnız hədəf tərəfdən qiymətləndirilə bilir; MariaDB ilə müqayisə **ölçülməyib**.

## 11. Təhlükəsizlik qiymətləndirilməsi (OWASP)

| Sahə | Nəticə |
|---|---|
| Injection | 27 `cursor.execute` hamısı bound-parametrli, 0 `.raw/RawSQL/.extra`; `\|safe` 3 sabit sayt, `mark_safe` 0, `autoescape off` 0 — PASS |
| XSS (DOM) | 524 sink inventarı; real risk 1: LLM çıxışı escape-siz `innerHTML` (`teacher_exam_statistics_charts.js`) → ✅ escape; self-XSS 4 sink → ✅ `textContent` |
| CSRF/CSP/başlıqlar | nonce CSP, `csrf_exempt` 1 (bearer-qorunmalı webhook), HSTS/secure cookie fail-safe (TLS bayraqları olmadan prod açılmır), XFF overwrite + tək `get_client_ip` — PASS |
| Media/IDOR | 33 model prefiksi checker reyestrində; `assignments/submissions/`, `notifications/files\|images/` qeydiyyatsız (fail-closed 404) → ✅ checker-lər əlavə edildi + test |
| Upload | uzantı allow/block-list, uuid ad, traversal/overwrite/zip-bomb qorunur; MIME müştəri başlığına etibar edir, `.xhtml/.mjs/.svgz` block-list-də yox (P3, açıq) |
| Sirlər | QA klon/staging DB parolları 8 tracked faylda idi → ✅ hamısı gitignore-lanmış `.claude/*.env`-ə köçürüldü, gitleaks DSN qaydası; **parol rotasiyası owner-only** (git tarixində qalır) |
| Asılılıqlar | OSV: yalnız lokal venv `setuptools 65.5.0` (prod image `>=78.1.1`); Django 5.2.17 təmiz; `google-generativeai` deprecated (P3) |
| Export | CSV/XLSX formula inyeksiyası neytrallaşdırılmırdı → ✅ `core/export_safety.py` 5 ixracda; 6 ixrac view-u qalır (P3) |
| Logging/məxfilik | sirr/OTP log-a düşmür; Clarity kabinetdə söndürülüb; AI assistant ad+e-mail+ballar göndərir, prompt limitsiz saxlanır (P3, açıq) |
| WebSocket | `AllowedHostsOriginValidator` + auth, obyekt icazəsi hər consumer-də, imzalı token, rate-limit — PASS; RLS blokeri ✅ düzəldildi |

## 12. Rollar / icazələr / multi-tenancy

**Autentifikasiya (checklist A1–A13):** portal qapısı, OTP (HMAC hash, 5 cəhd, vaxt, təkrar), CSRF/cookie bayraqları, open-redirect (7 variant), şifrə dəyişəndə digər sessiyaların ləğvi, arxiv/inactive bloku, rate-limit fail-closed — PASS. FAIL/PARTIAL → düzəldildi: superadmin qaçış vedrəsi (P1), OTP API enumerasiyası (`password_reset`/`signup` neytral 202), ilk-giriş yad e-poçta OTP + IntegrityError 500, OTP/parol-bərpa İP limiti (40/10m, 100/10m), suspended-org istifadəçisinin org-suz sessiyası (hard logout).

**RBAC yazma matrisi:** 17 yüksək riskli əməl × 4–7 yanlış rol → hamısı 403/404, DB dəyişmədi; obyekt-id və payload `organization_id` manipulyasiyası nəticəsiz. İki real dəlik (üzv uzaqlaşdırma) bağlandı. Kataloq drift-i: 13 reyestr açarı kodda heç yerdə yoxlanmır (`grade.override`, `org.settings`, `role.edit` …) — `member.remove` real qapıya bağlandı, qalanı ratchet testi ilə pinləndi (icazə redaktorunda «yalançı» düymələr olduğu sənədləşdirilib); `assignment.edit` reyestrə + müəllim şablonuna əlavə edildi.

**Tenant izolyasiyası:** 14 resurs sinfi, 40+ cross-tenant zond (RLS söndürülmüş sandboxda belə) → 403/404; keş açarları org/scope id ilə; WS qrupları icazədən sonra; media prefiksləri checker-li. Yad tenantın slug-lu struktur səhifəsi 200 boş qabıq idi → 302. `bypass_rls()` 156 çağırış / 65 fayl (skriptlə inventar, `docs/audits/RLS_BYPASS_AUDIT.md` yeniləndi). View-as 2026-09-12 düzəlişindən sonra 8 zondda tutdu.

## 13. İmtahan sistemi

State-machine (`findings/exams.md` §1): Exam `draft→published→…` atomik publish/unpublish qapısı (sualsız dərc yoxdur), soft-delete/restore; ExamAttempt `draft/in_progress/submitted/expired` + DB unikal açıq cəhd (indi `draft` daxil); bilet `WAITING/READY/ACTIVE/…` və otaq oturumu `ENTRY_OPEN/ACTIVE/…`. 164 endpoint inventarı (129 exams + 9 appeals + 26 live_exam) auth/rol/tenant sütunları ilə.

| Yoxlama | Əvvəl | Sonra |
|---|---|---|
| Lifecycle | PARTIAL (bilet yolu siyasəti, draft constraint) | PASS — bilet yolu deaktiv/arxiv/limit yoxlayır (EX-04), constraint draft-ı əhatə edir (EX-08, migr. 0066) |
| PIN / giriş | FAIL (EX-02/03/06) | PASS — final yalnız mərkəz axını, limitlər hər iki yolda |
| Taymer / submit | PARTIAL (deadline-anı POST itkisi) | PASS — `EXAM_SUBMIT_GRACE_SECONDS=15` pəncərəsi, cavablar saxlanır, status `expired` |
| Məxfilik | FAIL (EX-01) | PASS — take_exam HTML/JSON-da açar yoxdur, nəticə yalnız bitmiş cəhdə |
| Paralellik | PARTIAL (valideyn sətir kilidi, draft) | PASS — `FOR UPDATE OF exams_examattempt`; 20 tələbə × start/autosave/finish sandbox-da itkisiz (perf auditi) |
| Tenant/rol | PARTIAL (bank yazısı) | PASS |
| Audit log | PASS | PASS (+ bal dəyişikliyi `AuditLog`-a, əlavə cəhd qrantı audit + tenant üzvlüyü) |
| Performans | PARTIAL | start/take/autosave/result 43/28/27/33 sorğu (sual sayından asılı deyil); finish +1 sorğu/sual → ✅ toplu yazı: finish 25 sual **112 → 42** sorğu (sual sayından asılı deyil) |

Qalan (P3): `exams_examanswer` RLS subplan (böyük finalda ölçülməli), `ERROR_LOCKED` mesajı bilet mövcudluğunu açır, PIN girişi tam platform sessiyası verir, `reissue/revoke_student_pin` müstəqil audit yazmır, Redis kəsintisində kapasite qapısı fail-open. Klonda cəhd cədvəli boş olduğundan real həcmdə EXPLAIN **ölçülməyib**.

## 14. Elektron jurnal

HTTP E2E (istehsal rol kataloqu, real PG trigger-lər): sahib-yalnız yazı (yad müəllim/tələbə 404), 0–10 tam ədəd, gündəlik pəncərə, dublikat dərs rədd, semestr sonu, RİM bağlama → yazı rədd, düzəliş səbəb+sənəd tələb edir, audit sətirləri — PASS. Codex §14 yarış düzəlişləri (offering→enrollment→xana kilid sırası) yerindədir. Davamiyyət həddi iki mənbədən (imtahan qapısı açılış qrupunun ilk qeydindən, kabinet tələbənin öz proqramından — repro: gate=25, cabinet=10) → tək mənbə `registrar/absence_limit.py` (qonaq tələbə üçün gate == cabinet). Qalan: `finals.compute_final_result`/`journal_extras`/müəllim qridi hələ açılış-səviyyəli həddi işlədir (P3); jurnal detalında 12 dublikat `syllabus_for_offering` sorğusu → ✅ tək sorğu (12 → 4).

## 15. Tədris yükü

Zəncir TŞ → dekan → koordinator vizası → kafedra bölgüsü → `sync_offerings` HTTP-də işləyir: dublikat sətir atomik rədd, saat həddi, natamam bölgü bloku, yad kafedra 403. P1 (göndərilməmiş qaralamanın bölünməsi) düzəldildi. Qalan: dərs yükü paneli JS-i i18n-siz (18 AZ literal) → ✅ `gettext()` (20 literal, djangojs kataloqu); `workload:rows?chair=<yad>` 200 boş → 403.

## 16. Dərs cədvəli

Qrup/müəllim/otaq/qismən/tək-cüt həftə toqquşmaları, dublikat, tərs saat, keçmiş semestr, koordinator əhatəsi (yalnız öz ixtisası), tələbə/müəllim read-only görünüş, ICS ixracı, soft-delete — PASS (17 addım). Qeyd: `ScheduleSlot`-da dərc/qaralama sahəsi yoxdur (slot yaradılan an tələbəyə görünür), DB səviyyəsində exclusion constraint yoxdur (P3). Qeyri-UUID `offering_id` 500 verirdi → 404.

## 17. Sillabus axını

Tam zəncir HTTP-də PASS: natamam göndərmə 409, biznes qaydaları server tərəfdən (`MIN_GOAL_CHARS=60`), göndərilmiş/təsdiqlənmiş versiya `version.locked` 403, icazəsiz təsdiq 403/404 (mövcudluq sızmır), səbəbsiz düzəliş 400, tələbə yalnız təsdiqlənmişi görür, rəy tarixçəsi tam. Qalan: `copy_into_existing`/`duplication.py` 0 % coverage; sillabus siyahısı org-geniş rolda 4 926 sətri Python-da paginasiya edir → ✅ SQL paginasiya, klon rektor **1 076 → 87 ms**.

## 18. Tələbə idarəetməsi

Sənədli köçürmə (əmr, tarix, ≥20 simvol səbəb), DB trigger çılpaq qrup yazısını bloklayır, hərəkət tarixçəsi + audit, xaric etmə → giriş arxivi → bərpa açır — PASS. Düzəldildi: xaric edilmiş tələbənin öz qrupuna bərpası `same_group` 409 verirdi (F-T2); `hard_delete` akademik tarixçəni aparırdı (DATA-F2). Qalan: 1 ehtimal ikiqat tələbə, 371 qeydiyyatsız SAR («Level» pseudo-qrupları), demoqrafiya boşluqları — mənbə mənşəli, İmtahan Mərkəzi/TŞ qərarı.

## 19. Frontend və UX/UI

Brauzer sınağı (dev klonu, 7 rol × dashboard + 8–45 bölmə, 375/768/1024 px): **0 CSP pozuntusu, 0 JS xətası, 0 4xx**; bölmə swap-ları 0,86–1,25 s, ən ağır (analytics/lessons-log/syllabus-list) 2,0–2,9 s → lessons-log və syllabus-list perf düzəlişləri ilə 245 ms / 87 ms. Üfüqi daşma yoxdur, cədvəllər scroll sarğısında, sticky başlıqlar, mobil sidebar off-canvas + ESC.

JS keyfiyyəti (343 fayl): AJAX-safety praktiki tam, CSRF bütün POST-larda; düzəldildi — 4 geri-sayım faylında swap-dan sonra sızan `setInterval`, `console.log` qalıqları, `rim-center` client/server AJAX siyahı drift-i (+ test hər iki istiqaməti yoxlayır). UX: `ems_ui` hakimdir, amma 5 paralel BEM sistemi (~950 class) + 1 194 legacy `card`; native `<select>` yalnız 2 çox-seçimli listbox; təhlükəli əməllər təsdiqlidir (22-si native `confirm()` — P3). Əlçatanlıq: skip link, tək `h1`, `aria-current`, `aria-modal` + fokus tələsi, reduced-motion PASS; düzəldildi — AJAX keçidindən sonra fokus başlığa + `aria-live` elanı, `--ems-neutral-400` (2,56:1) və 500/600 tonlu status rəngləri mətndən çıxarıldı (56 qayda), iç-içə `<main>`. Açıq: 13–18 px hədəflər, ikon-only düymələr, login xətası `role=alert` (P3). Ölçülməyib: ekran görüntüsü (Browser pane bu sessiyada gizli idi), «ilk resize» keçidi, jurnal qridi (klonda 0 offering), imtahan sihirbazı modalı, HR rolu.

## 20. Lokallaşdırma

Yerdəyişənlər (`%(name)s`) 4 dildə 100 % uyğun; qapı `check_i18n_catalogs` yaşıl idi — amma **kor nöqtə ilə**: `pgettext(_CTX, …)` (modul sabiti kontekst) çağırışlarını skaner görmürdü → **564 django + 17 djangojs msgid** heç bir kataloqda yox idi (audit-log, groups-registry, org-members, registry, teacher-intake, exam_score_import, semester-opening EN/RU/TR-də qarışıq dilli). Düzəldildi: skaner (`ast` ilə modul sabitləri), fill skripti, `compilemessages`, 11 skaner testi. Semantik qüsurlar (P1) düzəldildi: `action_close` RU «открыть»/TR «açık» → «Закрыть»/«Kapat»; `action_deselect_all` «Удалить/Silmek» → «Снять выделение/Seçimi temizle»; `action_check` «Geri/Back» → «Yoxla/Check/Проверить/Kontrol et»; «March» → «March/Март/Mart»; `stat_duplicates` «Mövzu» → «Dublikatlar»; `aria_close` RU sən-forması; `supervision.enabled` etiketi. Dərs yükü paneli 20 JS literalı `gettext()`-ə keçdi. Codex P2-06 qalıqları da bağlandı. Qalan: EN/RU/TR üçün insan baxışı yoxdur (identity ratchet: EN 69, RU 19, TR 225 «eyni» tərcümə).

## 21. Performans

**Sorğu büdcəsi** (sandbox, 62 endpoint × 2 miqyas: 2 tələbə vs 150 tələbə / 12 açılış / 40 sual): 58-i miqyasdan asılı deyil; 4 N+1 tapıldı və bağlandı (`group_students` 16→39, `teacher_group_list` 38→48, `group_individual_plan` 19→65, `appeal_stats_data` 19→27 — hamısı sabit); jurnal detalında 12 dublikat `syllabus_for_offering` → 4; imtahan finish 5/25 sual 52/112 → 42/42. Kabinet qabığı memoizasiyası (Codex §14/§21, −17 sorğu/səhifə) yerindədir.

**Yük sınağı** (dev klonu :8011, `DEBUG=False`, tək `runserver --noreload` prosesi, klon DB; 5 → 20 → 50 VU × 30 s, qarışıq GET axını): xəta 0; p50 70–86 ms; p95 200 / 420 / 410 ms; p99 230 / 670 / 490 ms; 26 RPS; dayanma şərti heç bir mərhələdə işləmədi; darboğaz app prosesi (GIL, tək nüvə ~60 %), DB boş (≤4 aktiv bağlantı). Bu istehsal throughput-u deyil (Daphne 12 thread ≈ 30–45 RPS/replika); 5 000 tələbənin 10 dəqiqəlik login pəncərəsi (320 ms hash) ≥ 3 replika tələb edir — `APP_REPLICAS` defoltu 1.

**Ağır səhifələr** (klon, org-geniş rol, tək istifadəçi): `/exams/groups/` 2 008 ms / 2,5 MB (⏳ açıq — bölmə 27), sillabus siyahısı 1 244 → 87 ms, lessons-log 1 038 → 711 (keşsiz) / 245 ms (keş), `/jurnal/` rektor 426–472 → 95 ms.

**Paralellik** (sandbox thread-lər): eyni imtahanda 20 tələbə start → 3×autosave → finish — itən yeniləmə yox, dublikat cəhd yox; eyni tələbədən 5 paralel start → 1 cəhd. PASS.

**EXPLAIN (klon):** seq scan yalnız `registrar_lesson` tarix aralığında → indeks təklifi (icra edilməyib); `exams_examattempt` klonda 0 sətir → imtahan yolları real həcmdə **ölçülməyib**. Keş: DB ayrımı + `noeviction` + tenant-namespaced açarlar düzgün; statistika/analitika yalnız TTL; stampede qorunması yox. Statik: 44 fayl / 709 KB xam / 165 KB gzip + FA font 146 KB; `/jsi18n/` 83 KB dinamik → indi `Cache-Control: private` + `Vary`. Çərçivə yükü: hər səhifədə 10–15 təkrar sorğu (RLS `set_config` ×4–12, `access_state` ×3, membership ×3–5) — P3, açıq.

## 22. İnfrastruktur / DevOps

**Mənbə** (`docker-compose.prod.yml`, `docker/**`, `remote_deploy.sh`, CI): restart siyasətləri, resurs limitləri, healthcheck-lər (Celery worker/beat daxil — Codex remediasiyası təsdiqləndi), non-root image, `preflight_django_deploy_check`, build-sha yoxlaması, PgBouncer + `RLS_TRANSACTION_SCOPED`, TLS fail-closed. Bu auditdə əlavə edildi: `stop_grace_period` (app 130 s ≥ `DAPHNE_APPLICATION_CLOSE_TIMEOUT`, worker 300 s, heavy 900 s, postgres 60 s — invariant testləri), şəbəkə IPAM pin (`172.18.0.0/16`, gateway = `ARP_AGENT_BIND` = `EXAM_ARP_AGENT_URL` — test) + arp-agent logging/limits/healthcheck, `prometheus.depends_on app` silindi, `.trivyignore` baxış tarixi (CVE-2025-47273 girişi hələ lazımdır — `pip 26.2` vendor `setuptools 70.3.0` elan edir), CI `safety … || true` yanıltıcı addımı silindi.

**Celery:** tasklar idempotent + time-limit; `sweep_overdue_attempts`/`sweep_expired_resume_windows` indi hər cəhd üçün `select_for_update(of=self, skip_locked)` + status təkrar yoxlaması (tələbənin `submitted`-i heç vaxt `expired`-ə yazılmır — race testi) + 55 s overlap kilidi. `on_commit`-siz `.delay` 2 yerdə qalır (P3).

**İşləyən mühit (owner-only, dəyişməyib):** image `emsarena-prod:latest` 2026-07-06 build (Django 5.2.15, `sqlparse 0.5.4`, `pypdf 6.13.3` məlum CVE-lər), heavy worker/9 servis yoxdur, Redis `maxmemory 0` / 512 MiB limit drift-i, DB rolu superuser (Codex P0-01 — WS blokeri artıq bağlanıb, rollout mümkündür). Deploy rollback / SHA teqi yoxdur — təklif diff `docs/audits/2026-09-13-claude/findings/infra.md` §9 P2-5 və fixinfra hesabatında.

**Backup/DR:** gündəlik `pg_dump -Z6` + rotasiya + `BackupTooOld` alerti; sintetik restore PASS (data auditoru); real ölçülü restore, off-site, şifrələmə, media backup, PITR **yoxdur / NOT TESTED**. RPO 24 saat.

## 23. Monitorinq

Prometheus 11 scrape job, 31 → 35 alert qaydası, Loki/Promtail, blackbox ×3, `core/health*` + `build_info`. Tapıntılar: lokal prod-like stack-də alertmanager/prometheus/nginx 2026-09-07-dən `Exited (127)`, Alertmanager logunda Brevo «525 5.7.1 Unauthorized IP address» → **alert çatdırılması heç bir şəraitdə sübut olunmayıb** (P1); webhook `http://app:8000/…` düzgün prod konfiqində 400/301 alırdı (P2); app scrape tək `nginx:80` hədəfi ilə 8 replikanın sayğaclarını qarışdırırdı (P2); heavy növbəsi ölçülmürdü (P2). Repo tərəfi düzəldildi: `Watchdog: vector(1)` (deadman) + `AlertmanagerNotificationsFailing` (critical) + `heartbeat` receiver, webhook nginx daxili `location =` (172.16.0.0/12) + `url: http://nginx/…`, `dns_sd_configs app:8000` + `http_headers`, `emsarena_celery_queue_length{queue}` (celery|heavy) + `emsarena_celery_queue_workers{queue}` + `CeleryHeavyWorkerDown`; monitorinq paneli `sum()` ilə; `promtool check rules` 35 SUCCESS, `amtool check-config` SUCCESS; `SISTEM_MONITORINQI.md` §8.1 (Brevo «Authorised IPs», `amtool` smoke, deadman). **Owner-only:** Brevo IP ağ siyahısı və işləyən stack-in yenidən qaldırılması; sonra Watchdog-un xarici heartbeat-ə çatdığını sübut etmək.

## 24. Avtomatik testlər

Tam PostgreSQL dəsti (audit sandbox, `-n 6`, coverage ilə): **8 618 passed · 15 skipped · 1 failed** (mühit — paralel agentin dəstin ortasında əlavə etdiyi migrasiya) · 15 dəq 31 san. Coverage: apps+core statement 78,76 % / branch 66,54 %; kritik modul dəsti (28 405 stmt) 85,88 % / 72,69 %. Boşluqlar: `exams/services/duplication.py` 0 %, `exams/domain/grading.py` 22 %, `exams/services/journal_sync.py` 34 %, media checker-lərinin yarısı, final mərkəzi 3 icazə qapısı, `view_as.actor_can_use_view_as` 0 %. Skip inventarı: 16 — hamısı mühit/dizayn, xətanı gizlədən yoxdur; 4 test heç bir mühitdə işləmir (tesseract, `rehearsal_target` GUC). Gigiyena: venv-də `pytest-cov`/`pytest-timeout` yoxdur (requirements-də pinlənib), 4 migrasiya-test faylı ≈ 25 CPU-dəq, 280 fayl öz org-unu qurur (`_make_org` 11 kopya), `freezegun` yoxdur.

Bu auditin əlavə etdiyi reqressiya testləri: 203 test / 28 fayl (hamısı `test_audit_2026_09_13_*.py` adı ilə). Yekun reqressiya: tam PostgreSQL dəsti (`apps core tests`, sandbox `ems_regress`, `-n 6`, `--create-db`): **8 820 passed · 226 skipped · 0 failed · 1 402 subtests** — 9 dəq 26 san (2026-09-13). Bundan əlavə bütün gate-lər yaşıl: black/isort/flake8, `check_module_size`, `module_deps` (0 dövr), `public_api_boundaries`, `check_i18n_catalogs` (564+17 yeni msgid daxil), `makemigrations --check`, `promtool`/`amtool`, `docker compose config`.

## 25. Kod keyfiyyəti

black/isort/flake8 + 4 struktur qapısı yaşıl; 23 «ölü kod» namizədi yalan-pozitiv (test sinifləri); `print`/`console.log` qalıqları (4) silindi; TODO/FIXME inventarı `findings/backend.md` §1. Zəif: 23 modul qapının kənarında, 446 geniş `except`, güzgü implementasiyalar parity-testsiz (cəhd limiti ×3), README↔kod sillabus qapısı (org siyasəti default söndürülü). Test-suite gigiyenası yuxarıda.

## 26. İcra edilən düzəlişlər

| Problem | Ciddilik | Fayl/Modul | Düzəliş | Yoxlama |
|---|---|---|---|---|
| Açıq cəhdin nəticə səhifəsi cavab açarını göstərir | P0 | `exams/views/student/results.py` | vaxtı bitmiş cəhd bağlanır, açıq cəhd `take_exam`-a 302 | `test_audit_2026_09_13_exam_integrity.py::InProgressResultPageTests` (2) |
| Final imtahanı kabinet PIN-i ilə zal qapısından kənarda başlayır; PIN brute-force limiti yox | P1 | `exams/views/shared/access.py` | final yalnız `/exams/final/`; istifadəçi-adı limiteri, 429 | `CodeCheckFinalGateTests` (2) |
| Bank sualı yazıları yalnız oxu görünürlüyü ilə | P1 | `question_library/{_shared,questions,crud}.py` | `_ensure_bank_mutation_allowed` 4 view-da (deny audit + 403) | `BankQuestionWriteOwnershipTests` (4) |
| Bilet yolu siyasəti, deadline grace, IP limiter bypass, fayl silinməsi, draft constraint, valideyn sətir kilidi | P2 ×6 | `services/final_center/tickets.py`, `views/student/attempts.py`, `_answer_writes.py`, `final_center.py`, `domain/attempts.py`, migr. `0066` | bölmə 6 | 11 test |
| Superadmin login qaçış yolu limitsiz | P1 | `accounts/views/auth/{login,_shared,constants}.py`, `admin_ratelimit.py` | ayrıca vedrə 3/1h (İP+ad), uğursuz cəhdlər sayılır | `test_audit_2026_09_13_auth.py::SuperadminEscapeBucketTest` (4) |
| OTP API enumerasiyası; ilk-giriş yad e-poçt + 500; OTP/parol-bərpa İP limiti; suspended org sessiyası | P2/P3 | `otp_api.py`, `first_login.py`, `organizations/middleware.py` | neytral 202; canonical e-poçt yoxlaması + `IntegrityError`; 40/10m, 100/10m; hard logout | 19 test |
| Üzv uzaqlaşdırma `member.remove`-siz və əhatəsiz | P1 ×2 | `organization/_management_flow/_members.py`, `org_sections/management.py` | açar + `get_permission_scope` (UNIT → alt-ağac), `member.student_manage` yalnız tələbə; UI düyməsi eyni qayda | `test_audit_2026_09_13_rbac.py` (18) |
| `guestrosterdocument` RLS-siz; kataloq drift; yad tenant struktur 200; `assignment.edit`; `rows` 403; `RLS_BYPASS_AUDIT` | P2/P3 | `registrar/migrations/0074`, `core/tests/…rls_coverage`, `organizations/{permissions,default_roles*}.py`, `views/shared/_helpers.py`, `workload/views/distribution_api.py`, `scripts/rls_bypass_inventory.py` | bölmə 12 | 21 test |
| Rol sinxronu audit-siz | P1 | `accounts/views/_helpers/membership.py` | `AuditLog` old/new rol dəsti | `RoleSyncAuditTest` (3) |
| Qeyri-UUID pk 500; qrant audit + tenant; org status/şkala audit; davamiyyət həddi; atomic; journal_sync; JSON statusları; GPA etiketləri | P2/P3 | `core/http_ids.py`, `attempt_grants.py`, `superadmin/endpoints.py`, `registrar/absence_limit.py`, `exam_bridge.py`, `journal_sync.py`, 8 view | bölmə 6 | 7 fayl, 49 test |
| `hard_delete` akademik tarixçəni silir; `exam_score` diapazonu | P1 ×2 | `account_deletion.py`, `registrar/models/grading.py`, migr. `0075` | `hard_delete_academic_history`; CHECK `0..100 NOT VALID` | 7 test |
| LLM `innerHTML`; media prefiksləri; DSN sızması; self-XSS; CSV/XLSX formula; imtahan bal audit | P2/P3 | `teacher_exam_statistics_charts.js`, `core/media_policies.py`, `.gitleaks.toml`, `core/export_safety.py`, `manual_grading.py` | bölmə 11 | 21 test |
| Final-mərkəz WS consumer-ləri RLS-siz | P1 | `apps/exams/consumers.py` | `database_sync_to_async_rls` | `test_audit_2026_09_13_ws_consumer_rls.py` (1, `rls_app_role`) |
| Göndərilməmiş TŞ qaralamasının bölgüsü | P1 | `workload/services/{workflow,distribution}.py` | yaradanın `workload.distribute` əhatəsi; `confirm_distribution` eyni qapı | 4 test |
| Bərpa eyni qrupa 409 | P2 | `registrar/movements.py` | `REINSTATEMENT` istisnası | 1 test |
| Alert qaydaları, webhook location, dns_sd, stop_grace, IPAM, sweep CAS, heavy metrik | P1/P2 | `docker/**`, `docker-compose.prod.yml`, `exams/services/sweep_guard.py`, `monitoring/collectors.py` | bölmə 22–23 | 3 fayl, 29 test |
| i18n əks-mənalı tərcümələr + 581 kataloqsuz sətir; fokus; kontrast; JS i18n; interval sızması | P1/P2 | `locale/**`, `scripts/i18n_source_scan.py`, `section_loader.js`, 37 CSS, `workload_*.js` | bölmə 19–20 | 23 test |
| N+1 ×4, `syllabus_for_offering`, finish toplu yazı, sillabus siyahısı, lessons-log, `/jurnal/`, `/jsi18n/` | P2/P3 | 10 fayl (bölmə 21) | SQL paginasiya/aqreqat, prefetch, bulk | 6 fayl, 25 büdcə testi |
| «Sillabussuz» çipi bütün açılışları göstərir | P2 | `accounts/views/syllabus/section.py` | virtual status domen sorğusuna ötürülmür | 1 test |
| Codex i18n qalıqları; klon/staging parolları tracked fayllarda | P2/P3 | `course_panel_tabs.js`, `_import.html`, 8 skript/sənəd, `.claude/launch.json` | env fayllarına (`.claude/*.env`, gitignore) | gate |

## 27. Qalan problemlər

**İstehsala qədər MÜTLƏQ (owner əməliyyatları — bu audit icra etməyib):**
1. DB tətbiq rolunu superuser-dən NOBYPASSRLS rola keçirmək (Codex P0-01; `scripts/provision-app-db-role.sh` → `.env` → `EMS_DB_ROLE_ENFORCE=error`), əvvəlcə staging klonunda final-mərkəz WS + `-m postgres` dəsti ilə — bu auditin `a9b2a7fe` düzəlişi ön şərtdir.
2. İşləyən image-i yenidən build/deploy etmək (Django 5.2.17 və CVE düzəlişləri, healthcheck-lər, stop_grace, IPAM); deploy-dan əvvəl `docker network inspect` subnet 172.18.0.0/16 təsdiqi.
3. Prod `.env`: TLS bayraqları (`INSECURE_TRANSPORT_OK` yox), `ALLOWED_HOSTS`-a `localhost` (webhook), Redis `maxmemory 3gb`/`noeviction` drift-i.
4. Alert çatdırılması: Brevo «Authorised IPs», stack-in qaldırılması, Watchdog heartbeat-in xarici tərəfdə göründüyünü sübut etmək.
5. Parol rotasiyası: klon/staging DB parolları git tarixində qalır (`ALTER ROLE emsarena_staging/emsarena_app`); əlavə olaraq yeni gitleaks DSN qaydası 2026-02-02 tarixli `b09cb19d` commit-ində səhvən yığılmış lokal `.env`-i (dev docker DB parolu + 4 sirr sətri) aşkarladı — həmin dəyərlər hər hansı real mühitdə işlədilirsə dəyişdirilməlidir; fingerprint-lər `.gitleaksignore`-da pinlənib ki, yeni sızma CI-ni qırsın.
6. Real ölçülü backup restore məşqi + off-site nüsxə; RPO qərarı.
7. 349 `exam_score > 50` sətri və 1 ehtimal ikiqat tələbə üçün İmtahan Mərkəzi/TŞ qərarı; legacy reconciliation/review prosesinin işə salınması.

**Sonra düzəldilə bilər (kod, P2/P3 açıq):** `/exams/groups/` tam səhifəsi (lazy namizəd yükləməsi), `accounts_userprofile` RLS, 13 qapısız reyestr açarı, 23 atomic-siz view, 5 qeyri-UUID pk yeri, finals/qrid davamiyyət həddi, `exams_examanswer` RLS subplan (böyük finalda ölçmə), deploy rollback/SHA teqi, 6 ixracda formula neytrallaşdırma, upload MIME sniffing, AI PII/retention, dublikat indekslər + `registrar_lesson (org, date)` indeksi, qrup adı unikal indeksi (dedupe-dən sonra), a11y hədəf ölçüləri/ikon düymələr, 22 native `confirm()`, EN/RU/TR insan baxışı, çərçivə sorğuları (RLS `set_config`, `access_state`, membership), `pytest-cov/timeout` venv-də, migrasiya tək-yarpaq testi.

## 28. Bal kartı

Bal — sübuta əsaslanan mühəndis qiymətidir (0–100). «Əvvəl» = `96016cff`-də bu auditin gördüyü vəziyyət (Codex-in 2026-09-12 «Sonra» sütunu ilə müqayisə oluna bilər — fərqlər bu auditin daha dərin tapıntılarından gəlir, məs. İmtahan 84 → 58); «Sonra» = düzəlişlərdən sonra.

| Sahə | Əvvəl | Sonra | Qeyd |
|---|---:|---:|---|
| Architecture | 80 | 80 | Modul monoliti, 0 dövr / 0 xüsusi import; 23 modul qapı kənarında |
| Backend | 76 | 82 | Audit-log boşluqları, 500-lər, atomic, tək mənbə davamiyyət həddi bağlandı |
| Frontend | 82 | 84 | 7 rolda 0 CSP/JS xətası; fokus, kontrast, interval sızması düzəldi |
| Database Design | 78 | 80 | exam_score CHECK, guestrosterdocument RLS; kaskad ORM-də, dublikat indekslər qalır |
| Database Integrity | 88 | 89 | 487/487 FK, 0 tenant uyğunsuzluğu; 349 legacy şkala-kənar bal, hard-delete qapısı |
| Legacy Data Migration | 66 | 66 | Transform sadiq, reconciliation 0 %, mənbə müqayisəsi mümkün deyil — dəyişməyib |
| Security | 78 | 84 | LLM→innerHTML, media prefiksləri, DSN sızması, formula, sinks bağlandı; MIME/AI PII açıq |
| Authentication | 72 | 84 | Superadmin qaçış vedrəsi, enumerasiya, İP limitləri, suspended hard logout |
| Authorization / RBAC | 66 | 80 | member.remove real qapı + əhatə, drift testi; 13 açar hələ qapısız |
| Multi-Tenancy Isolation | 78 | 84 | RLS 142/171 + CI testi, WS consumer bypass, attempt_grants tenant; userprofile RLS-siz |
| Exam System | 58 | 82 | P0 açar sızması, final zal qapısı, PIN limiti, bank yazısı, deadline grace, kilidlər; sweep CAS |
| Electronic Journal | 84 | 85 | E2E PASS; davamiyyət həddi tək mənbə (qapı + kabinet); finals/qrid hələ açılış-səviyyəli |
| Teaching Workload | 68 | 78 | Göndərilməmiş qaralama bölgüsü (P1) bağlandı; JS i18n; rows 403 |
| Schedule System | 80 | 80 | 17 addım PASS; dərc statusu/exclusion constraint yoxdur |
| Syllabus Workflow | 91 | 91 | Tam zəncir PASS; «Sillabussuz» çipi düzəldi; duplication.py 0 % coverage |
| Student Management | 73 | 77 | Bərpa eyni qrupa, hard-delete qapısı; legacy dublikat/boşluqlar qalır |
| API Design | 72 | 78 | Qeyri-UUID pk 400/404, 200-on-failure statusları; OpenAPI yoxdur |
| Performance | 72 | 78 | 4 N+1 + 4 ağır səhifə (2 008→? , 1 076→87, 949→245, 365→95 ms); finish 112→42 sorğu; /exams/groups/ açıq |
| Scalability | 64 | 65 | Tək Daphne prosesi/12 thread ≈ 30–45 RPS; APP_REPLICAS defolt 1; dns_sd scrape hazır |
| Reliability | 58 | 64 | stop_grace_period, IPAM pin, sweep kilidləri; rollback yolu yoxdur |
| Celery / Background Jobs | 70 | 76 | Sweep-lər sətir kilidi + overlap kilidi; heavy növbə metrik |
| Redis / Caching | 67 | 68 | Topologiya/açarlar düzgün; işləyən maxmemory 0 (owner), ağır hesablama keşi natamam |
| WebSocket / Realtime | 52 | 72 | NOBYPASSRLS blokeri bağlandı; auth/rate-limit PASS; geniş soket yükü ölçülməyib |
| DevOps | 62 | 66 | CI 11 qapı fail-closed; safety ||true silindi; image teq/rollback yoxdur |
| Deployment | 55 | 57 | İşləyən image 69 gün geridə (owner); deploy rollback təklifi hesabatda |
| Monitoring / Observability | 48 | 62 | Watchdog + notif-failed + heavy worker qaydaları, replika-düzgün scrape; alert çatdırılması sübutsuz |
| Logging | 76 | 82 | Rol sinxronu, qrantlar, org statusu, bal dəyişikliyi audit-də; sirr log-a düşmür |
| Automated Tests | 74 | 80 | 8 618 → 8 8xx test; 26 yeni reqressiya faylı; coverage boşluqları qalır |
| Code Quality | 78 | 79 | Gate-lər yaşıl; console.log silindi; geniş except-lər qalır |
| Maintainability | 74 | 76 | attempts.py/lessons_log bölündü; 23 modul qapı kənarında |
| UX/UI | 74 | 76 | ems_ui hakim; 5 BEM sistemi + native confirm() qalır |
| Accessibility | 67 | 73 | Fokus + aria-live, kontrast tokenləri; hədəf ölçüləri, ikon-only düymələr qalır |
| Localization | 56 | 74 | Əks-mənalı tərcümələr, 564+17 kataloqsuz sətir dolduruldu, skaner kor nöqtəsi; EN/RU/TR insan baxışı yoxdur |
| Documentation | 66 | 72 | Monitorinq/deploy sənədləri, RLS_BYPASS_AUDIT yenidən; icazə matrisi sənədləri köhnə |

## 29. Ümumi bal

| Kateqoriya | Çəki | Əvvəl | Sonra |
|---|---:|---:|---:|
| Təhlükəsizlik | 15% | 78.00 | 84.00 |
| Baza və məlumat bütövlüyü | 12% | 77.33 | 78.33 |
| Backend/biznes məntiqi | 12% | 76.00 | 82.00 |
| İmtahan | 10% | 58.00 | 82.00 |
| Arxitektura | 8% | 80.00 | 80.00 |
| Performans/miqyas | 8% | 68.00 | 71.50 |
| İcazələr/tenant | 8% | 72.00 | 82.00 |
| Frontend | 6% | 82.00 | 84.00 |
| Testlər | 6% | 74.00 | 80.00 |
| DevOps/etibarlılıq | 5% | 60.00 | 65.00 |
| Digər kateqoriyalar | 10% | 69.63 | 75.79 |

Texniki bal: **72,8 → 79,4 / 100** (`scorecard.json`). Kateqoriyalar prompt-dakı çəkilərlə; «Digər kateqoriyalar» qalan 19 sahənin sadə ortasıdır. Təhlükəsizlik və məlumat düzgünlüyü UI-dan ağır çəkilidir; heç bir bal «yoxlanmadı» əsasında yüksəldilməyib.

İstehsal hazırlığı (işləyən mühit, ayrıca): **48 / 100** — mənbə 79-a çatsa da, işləyən mühitdə superuser DB rolu, 69 günlük image drift-i, sübut olunmamış alert çatdırılması və real restore məşqinin olmaması qalır. Bunlar kod deyil, əməliyyat maneələridir və bölmə 27-də sadalanıb.

## 30. İstehsal qərarı

**PRODUCTION READY WITH CONDITIONS (kod: 79,4/100 → «istehsal hazır, vacib təkmilləşdirmələrlə»).**

Niyə bu, daha yuxarısı deyil: imtahan bütövlüyü (P0 açar sızması, final zal qapısı), tenant/icazə dəlikləri (üzv uzaqlaşdırma, bank yazısı) və məlumat kaskadı bu auditdə tapılıb **kodda bağlandı və reqressiya testləri ilə kilidləndi** — amma bunların hamısı bir gün əvvəlki «73,7» balın altında gizli idi, yəni əhatənin hələ də boşluqları ola bilər (imtahan yolları real həcmdə ölçülməyib, EN/RU/TR insan baxışı yoxdur, coverage boşluqları var). Niyə daha aşağısı deyil: sərt bütövlük tam, RBAC yazma matrisi 17 əməl × 7 rol sıfır sızma, tenant zondları sıfır sızma, 8 6xx test yaşıl, bütün P0/P1 kod tapıntıları bağlı.

**Şərtlər (bölmə 27, «MÜTLƏQ» siyahısı):** işləyən mühit yenilənmədən (NOBYPASSRLS rol, yeni image, TLS/Redis env, alert çatdırılması, parol rotasiyası, restore məşqi) ictimai istehsal təsdiqi verilmir — həmin vəziyyətdə mühit **48/100, NOT READY** sayılır. Şərtlər yerinə yetirildikdən sonra nəzarətli pilot (bir fakültə, bir imtahan sessiyası) tövsiyə olunur.

## 31. Tövsiyə olunan növbəti addımlar

**Dərhal (bu həftə):**
1. `Develop` → `main` merge və deploy: NOBYPASSRLS rol rollout-u (staging klonunda WS/RLS dəsti ilə), yeni image, prod `.env` TLS/Redis/`ALLOWED_HOSTS`, `docker network inspect`.
2. Alert kanalı: Brevo IP ağ siyahısı, stack-in qaldırılması, Watchdog heartbeat sübutu.
3. Parol rotasiyası (klon/staging), real ölçülü restore məşqi, off-site backup.
4. İmtahan Mərkəzi: 349 şkala-kənar bal siyahısı (SQL migr. 0075 docstring-də), sonra `VALIDATE CONSTRAINT`; 1 ikiqat tələbə qərarı.

**Qısa müddət (2–4 həftə):**
5. `/exams/groups/` lazy namizəd yükləməsi; `accounts_userprofile` RLS; 13 qapısız reyestr açarı → qapıya bağla və ya reyestrdən çıxar; 23 atomic-siz view; 6 ixrac formula neytrallaşdırma; upload MIME sniffing.
6. Deploy rollback/SHA teqi (təklif diff hazırdır) + deploy-öncəsi dump.
7. Böyük final rehearsal-ı: 500+ cəhdli sandbox ilə `exams_examanswer` RLS subplan və finish/autosave yükünü ölçmək; `APP_REPLICAS ≥ 3` ilə yük sınağı.
8. Legacy reconciliation/review prosesini işə salmaq (75 212 warning sinfi ilə başlayaraq), 19 852 bağlanmayan fakt.
9. EN/RU/TR kataloqlarına insan baxışı (identity ratchet EN 69 / RU 19 / TR 225).

**Sonra (opsional):**
10. Dublikat indekslər + `registrar_lesson (org, date)` indeksi (CONCURRENTLY); qrup/fənn unikal indeksləri.
11. Çərçivə sorğuları (RLS `set_config` dedup, `access_state`/membership request-keşi); statistika/analitika keşi + stampede qorunması.
12. A11y: hədəf ölçüləri, ikon-only düymələr, native `confirm()` → `EMSConfirm`; 5 BEM sisteminin `ems_ui`-yə köçürülməsi.
13. Test gigiyenası: `pytest-cov/timeout` venv-də, migrasiya testlərinin sürəti, `freezegun`, migrasiya tək-yarpaq testi; coverage boşluqları (`duplication.py`, `domain/grading.py`, media checker-ləri).
