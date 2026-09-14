# Gecə dalğaları 2–4 (2026-09-14) — dəyişikliklərin faktiki siyahısı

Baza: `Develop` `ef612d58` (2026-09-14 00:02, CI yaşıl — audit hesabatının son commit-i).
Son: `931dff3e` (08:07). Aralıqda **24 commit**. Hər sətir bir commit; qruplaşdırma mövzu
üzrədir, commit mesajının məzmunu qısaldılıb. Sübut: `git log ef612d58..931dff3e`.
Audit tapıntı nömrələri (`P2-5`, `F-07`, `EX-12` …) `FINAL_REPORT_AZ.md` və
`findings/<sahə>.md` fayllarına istinad edir.

Dalğa 5 (bu sənəd + `w5left` qalıqları) hələ commit edilməyib — bura daxil deyil.

---

## 1. Dalğa 2 (02:46 – 04:12) — audit §27 «sonra düzəldilə bilər» maddələri

### Performans
| SHA | Dəyişiklik |
|---|---|
| `5c081c59` | RLS GUC yaddaşı sessiya səviyyəsində (perf F-07): eyni bağlantıda təkrar `set_config` / `current_setting` atlanır; kabinet səhifələrində −4…−6 sorğu (55→49, 61→55, 50→46) |
| `e3a1a73a` | `request.user` üçün `access_state` yoxlaması bir dəfə (perf F-08): middleware / view-as DB-yə getmir |
| `642cd110` | `/exams/groups/` və `create_student_group` namizədləri lazy (2,5 MB → 56 KB, 150 tələbədən asılı deyil); `registrar_lesson (org, date)` INCLUDE indeksi; 9 dublikat indeks `CONCURRENTLY` silindi (migr. `accounts 0023`, `appeals 0004`, `courses 0002`, `exams 0067`, `registrar 0076`); `exams_examanswer` RLS 500 × 40 ölçmə → 2,4 µs/sətir, denormalizasiya lazım deyil |
| `8206abdb` | Postgres `jit=off` (`POSTGRES_JIT`, EX-12: RLS planlarında JIT 2,7 → 158 ms) |

### İnfrastruktur / deploy
| SHA | Dəyişiklik |
|---|---|
| `972641c2` | Deploy SHA teqi + avtomatik rollback + deploy-öncəsi dump (P2-5); Redis parolu argv-dən konfiq şablonuna (P3-3); Alertmanager / Blackbox `render-template.sh` (P3-8/9); nginx `stub_status` healthcheck (P3-1, CI daxil); Daphne `--proxy-headers` (P3-12); `check --deploy` `WARNING` (P3-16); prod-smoke webhook + Redis argv yoxlaması |

### Təhlükəsizlik
| SHA | Dəyişiklik |
|---|---|
| `2376b41c` | Qalan 6 ixracda formula neytrallaşdırma + repo-boyu qoruyucu test (F-07); upload validator: 9 yeni block-list uzantısı, şəkil magic-bytes / markup rəddi, Pillow identifikasiyası, sənəd imza cədvəli (F-06); AI köməkçisi e-poçt maskası + log kəsmə + 90 gün retention (F-08); `.env.production.example` təhlükəsizlik parametrləri (F-09); XLSX vərəq adı təmizləmə |

### RBAC / backend
| SHA | Dəyişiklik |
|---|---|
| `8a442dac` | 13 qapısız reyestr açarı: 6-sı silindi (`org.delete`, `role.create/delete`, `grade.override`, `qa.*`) + data miqrasiyası `organizations 0051`; 5-i real qapıya bağlandı (`org.settings`/`org.edit`, `role.edit`, `audit.export`, `journal.view`, `analytics.view_own`); 11 çoxyazılı view `atomic`; qeyri-UUID pk → 400/404 (5 yer); davamiyyət həddi 6 səthdə tələbənin öz proqramından; bal/idxal endpoint-lərinə rate-limit `120/1m` (F-15); RİM rəhbərinə `final_score.entry` (sahibin qərarı, migr. `organizations 0052`) |
| `28d7bd04` | Şəxsi statistika CSV ixracı dashboard ilə eyni `analytics.view_own` qapısından keçir |

### Kağız imtahan balı (sahibin 2026-09-14 tələbi)
| SHA | Dəyişiklik |
|---|---|
| `6340394b` | Sual-sual ballar S1…Sn (hər biri ≤ 10, cəm ≤ sxem imtahan maksimumu, giriş + imtahan ≤ 100); vərəqdə imtahan növü (yazılı / praktiki) + növ filtri; müəllim seçici / tələbə axtarışı / vəziyyət çipləri; «Dəyişən nəticələr» görünüşü (apellyasiya növü, filtrlər, tarixçə, CSV); idxalda S1…Sn; imtahan mərkəzi statistikasında kağız imtahan KPI-ları; migr. `registrar 0077` |

### Dalğa 2b — testlər, i18n, a11y, reqressiya
| SHA | Dəyişiklik |
|---|---|
| `fdcffe64` | Reqressiya düzəlişləri: permission-editor testləri `role.edit` daşıyır, guest-add ikinci POST təzə fayl, `statistics_export` `login_required` bərpa, RLS həcm testi sanity həddi 5 s |
| `6e5fec84` | EN/RU/TR-də ~230 real məna defekti (447 msgstr) + identity ratchet 68/18/223; AZ kataloqunda 22 səhv msgstr + placeholder uyğunluğu 4 dildə; icazə/rol sənədləri koddan yenidən törədildi |
| `9006a515` | Coverage boşluqları: imtahan dublikasiyası (16), qiymətləndirmə mixin-i (16), media checker-ləri (22), final-mərkəz qapıları (14), view-as paneli (8), migrasiya tək-yarpaq testi (4); CI-də tesseract OCR testləri; `requires_*` markerləri; `check_venv_sync` skripti |
| `e6e45657` | A11y: 24 px hədəflər, auth xəta bloklarında `role=alert` + `aria-invalid/describedby`, mobil sidebar fokus idarəsi, 18 ikon düyməyə `aria-label`, jd2 fokus konturu, 33 native `confirm()` → `EMSConfirm`, `create_combo` qorunması; qoruyucu testlər (13) |
| `cad42d84` | Dərs yükü düzəliş sənədinin adı təsadüfiləşdirilir (uzun ad → `DataError` 500); `requires_tesseract` / `requires_rehearsal_guc` markerləri tətbiq edildi |

## 2. Dalğa 3 (04:39 – 05:49) — sahibin brauzer rəyi, sual idxalı, süpürgə

### Kağız imtahan balı — sahibin rəyi
| SHA | Dəyişiklik |
|---|---|
| `b7acc5e2` | Yoxlayan / nəzarətçi axtarışlı müəllim seçicisi (`invigilator` FK, migr. `registrar 0078`); sual balları select (0…max, tənbəl enhance, klaviatura); təsdiq modalı (ad · giriş · imtahan · yekun · hərf, kəsilənlər qırmızı); bölmə AJAX-safe siyahısına əlavə edildi (filtrlər / çiplər səssiz işləmirdi); brauzerdə `qa.ikt_rehber` ilə tam axın |
| `deda4b73` | Sahibin qaydası: bir sualın maksimum balı 10-dan yuxarı qaldırıla bilməz (server + xana); sual sayı / maksimum cütünün 1000 px düzülüşü |
| `408c8e52` | Kağız bal cədvəlinin tənbəl-qoşulan seçiciləri native-select qoruyucusunda işarələndi |

### «İmtahanlarım» və sual idxalı
| SHA | Dəyişiklik |
|---|---|
| `6f2ce971` | İmtahan sehrbazı modalının iç-içə scroll bağı (tək qat `.ew-pane-body`, 390–1280 px); zibil qutusu sayğaclı ikon-düymə + «Aktiv / Zibil qutusu» alt-görünüşü (bərpa, birdəfəlik silmə `EMSConfirm`, boş vəziyyət, toast) |
| `576821c5` | Sual idxalı: DOCX (OMML düstur → LaTeX, şəkillər sual / varianta bağlanır, zip-bomb / VBA / xarici əlaqə qoruması, Pillow normalizasiya); LaTeX mətn kimi saxlanır + KaTeX 0.16.47 vendor render (CSP-safe, `trust:false`, server qadağan siyahısı, 2 000 simvol); ön-baxışda etibarlılıq nişanları / süzgəclər; PDF math regionları qorunur; `import_media` / `bulk_workbench` 600 sətir üçün bölündü |

### Brauzer süpürgəsi (rol × səhifə)
| SHA | Dəyişiklik |
|---|---|
| `8e7aa995` | AJAX-safe olmayan bölmələrdə səhifələmə / filtr klikləri səssiz udulurdu (tam-səhifə fallback + reyestr skaneri); jurnal bağlama əhatə parametrləri; cavab rejimi native select → komponent; sınaq cəhdində apellyasiya bloklandı; «Nəticələrim» xam status; bank boş vəziyyəti; pending-work kataloq korlanması; PIN axtarışı pəncərə / statusu |

## 3. Dalğa 4 (06:07 – 08:07) — nəzarət rejimi, sehrbaz, PDF şəkillər, CI

| SHA | Dəyişiklik |
|---|---|
| `ee1cd0cf` | Zibil qutusunda native `confirm` fallback silindi (a11y qoruyucusu); vərəq sorğu-büdcəsi testi soyuq keşlə |
| `36b32754` | Nəzarət rejimi status sorğusu WS-first (15 s heartbeat / 2–10 s backoff, ETag 304, 15/10 s rate-limit, 3 → 1 sorğu); fərdi PIN girişi oturum tarixçəsində (audit + KPI); sual göndərişi parseri (boş sətirdən sonra «N.», sonluq `*`); PDF-dən raster şəkillərin sual / varianta bağlanması |
| `3b0721a5` | İmtahan sehrbazında reyestr qrupları (`OrgUnit` GROUP) təyinatı: `Exam.allowed_units` (migr. `exams 0068` + RLS `0069`); giriş siyasəti / tələbə siyahıları / təyin olunmuş tapşırıqlar / PIN provizionu / bildiriş alıcıları / dublikat tək mənbədən (`StudentAcademicRecord.group`); namizəd axtarışı əhatə ilə; köhnə kohortlar ikinci dərəcəli; addım 2 klient validasiyası + server `step`/`field`; «Aktiv et» naviqasiya parametrlərini saxlayır; dublikat / şans toast-ları; brauzerdə tələbə axını |
| `931dff3e` | KaTeX CSS-dən vendorlanmayan `.woff` / `.ttf` fallback istinadları silindi (CI docker-build `collectstatic MissingFileError`); vərəq büdcə testi `AuditLog` introspeksiyasını əvvəlcədən isidir (xdist sıra asılılığı) |

---

## 4. Yeni testlər

`git diff --stat ef612d58..931dff3e -- '*test_w*'`: **46 yeni fayl, 8 599 sətir**
(hamısı əlavə; dəyişdirilən köhnə test faylları bura daxil deyil). `def test_` sayı
(subtest-lər sayılmır):

| Dalğa | Fayl | Test funksiyası | Əsas fayllar |
|---|---|---|---|
| 2 | 32 | 278 | `test_w2_exam_score_entry_section` (25), `test_w2_exam_score_questions` (30), `test_w2_rbac_catalog`, `test_w2_atomic` × 7 app, `test_w2_export_formula` × 3, `test_w2_media_checkers`, `test_w2_grading_mixin`, `test_w2_duplication`, `test_w2_deploy_rollback`, `test_w2_a11y_guards`, `test_w2_examanswer_rls_scale`, `test_w2_upload_security`, `test_w2_write_rate_limit`, `test_w2_rls_session_memo` … |
| 3 | 9 | 67 | `test_w3_import_docx` (18), `test_w3_import_omml` (19), `test_w3_katex_assets` (6), `test_w3_my_exams`, `test_w3_sweep_*` × 5 |
| 4 | 5 | 53 | `test_w4_wizard_units` (23), `test_w4_pdf_images` (10), `test_w4_supervision_status`, `test_w4_final_history_pin_entry`, `test_w4_parser_blocks` (9) |
| **Cəmi** | **46** | **398** | |

Digər: `apps/ai_assistant/test_w2_privacy.py` (161 sətir) və `tests/test_w2_deploy_rollback.py`
(277 sətir) app `tests/` qovluğundan kənardadır, saya daxildir.

i18n: 11 fill skripti (`scripts/i18n_fill_*_2026_09_14.py`) orkestrator tərəfindən
işlədilib, kataloqlar müvafiq commit-lərdə yenilənib.

---

## 5. Hələ açıq qalanlar

Mənbə: agent hesabatlarının «Edilməyən / yarımçıq / orkestrator üçün» bölmələri
(`scratchpad/audit/w2_*_report.md`, `w3_w3sweep_report.md`, `w3_w3import_report.md`,
`w4_w4wizard_report.md`, `w4_w4superv_report.md`). Sonradan bağlananlar çıxarılıb
(məs. `statistics_export` qapısı → `28d7bd04`; XLSX vərəq adı → `2376b41c`; CI nginx
`stub_status` → `docker/nginx/nginx.ci.conf`; dərs yükü fayl adı → `cad42d84`;
PDF raster şəkillər → `36b32754`; `jit=off` → `8206abdb`).

### Dalğa 5 `w5left` — BAĞLANDI (`b6285e1f`): 1–3 aşağıda tarixi qeyd kimi qalır
(yeni fayllar: `apps/exams/domain/unit_scope_filters.py`, `apps/exams/forms/exam_exclusions.py`,
`apps/exams/services/unit_pin_sync.py`, `apps/registrar/signals.py`; testlər
`apps/exams/tests/test_w5_unit_leftovers.py`, `apps/registrar/tests/test_w5_group_transfer_pins.py`;
yekun vəziyyət `w5left` hesabatında)
1. `allowed_groups` oxuyan yerlər reyestr qrupunu (`allowed_units`) hələ görmür: imtahan
   mərkəzi statistikası (qrup / fakültə filtri), `apps/appeals/views/teacher/statistics.py`,
   «Yenidən şans» bölməsi (`exam_chance.py`), müəllim nəticələrində qrup filtri
   (`results/_helpers.py`).
2. `ExamForm.clean()` `excluded_users`-i yalnız kohort üzvləri ilə süzür — reyestr qrupu ilə
   təyinatda «tələbəni istisna et» saxlanmır.
3. Tələbə qrup dəyişəndə (`StudentAcademicRecord.group` transferi) final PIN-ləri avtomatik
   yenilənmir (registrar tərəfində siqnal lazımdır).

### Kod — kiçik, sahibsiz qalanlar
4. Kağız bal idxalı: şablon endirmə view-u həmişə S1…S5 verir; quru icra planı vərəqin
   sual şəbəkəsini bilmir — dalğa 6 `w6paper` işində (bax commit tarixçəsi).
5. ~~`ExamScoreSheetKind` ixracı~~ — `48599f40`.
6. ~~`_searchable_multi_select.html`~~ — dalğa 6-da silindi (`1ffa623b`).
7. `ensure_can_manage_final_center` / `ensure_can_supervise_session` / `ensure_ticket_owner`
   / `ensure_can_manage_exam_rooms` / `actor_can_use_view_as` ixrac olunur, heç bir view
   çağırmır (`w2tests`).
8. `journal.view` açarı heç bir defolt rol şablonuna verilməyib (əlavə oxu yolu; sahib
   istəsə icazə redaktorundan verir) (`w2rbac`).
9. Kohort (`exams.StudentGroup`) səthi: dalğa 7-də (`4be82229`) kohortsuz tenantda əvəzlənmə kartı + köhnəlmə qeydi; model/data qalır (tam silmə — ayrıca miqrasiya qərarı).
10. Kabinet SPA-da `journal-close` / `kollokvium-windows` / `exam-center-stats` filtr
    panelləri də səssiz qala bilər (eyni kök səbəb, `8e7aa995` yalnız reyestr skaneri ilə
    örtür) — ayrıca yoxlama (`w2paper` 3-cü dövrə).
11. ~~Sual idxalı: pano ilə şəkil yapışdırma; DOCX brauzer QA~~ — dalğa 8-də bağlandı (pano/sürüklə-burax yapışdırma bank toplu əlavədə; DOCX yükləməsi brauzerdə uçdan-uca yoxlanıldı).
12. Audit P3 maddələri P3-4 / P3-5 / P3-6 / P3-10 / P3-11 / P3-17 / P3-18 heç bir briefdə
    olmayıb — toxunulmayıb (`w2infra`).

### Sahib əməliyyatları (kodla bağlanmır) — bax `deployment.md` §5.2
13. NOBYPASSRLS DB rolu rollout-u; yeni image deploy; prod `.env` TLS / `ALLOWED_HOSTS` /
    Redis; `docker network inspect`; Brevo IP ağ siyahısı + Watchdog sübutu; parol
    rotasiyası; real ölçülü restore məşqi; 349 `exam_score > 50` sətri üçün İmtahan Mərkəzi
    qərarı (audit §27 «MÜTLƏQ» 1–7).

### Sənədlər (dalğa 5 `w5docs`)
- `docs/features/kagiz_imtahan_bali.md`, `imtahan_sehrbazi_reyestr_qruplari.md`,
  `sual_idxali_dustur_sekil.md`; `docs/operations/deployment.md` §5.2 + `POSTGRES_JIT`;
  bu fayl.
