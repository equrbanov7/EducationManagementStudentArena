# AUDIT — Tətbiq təhlükəsizliyi (OWASP) · Upload · Asılılıqlar · Sirlər · Məxfilik — slug `security`

Tarix: 2026-09-13 · Baza: Develop `96016cff` · Auditor: read-only (ikinci buraxılış; birinci buraxılışın probe artefaktları `probes/` altında).
Metod: grep/AST inventarlar (`probes/*.py`), settings oxunuşu, sandbox pytest (`ems_audit_security`). Dev-clone brauzer probe-u bu buraxılışda işlədilmədi (bax §10 NOT TESTED). Real DB-yə və klona toxunulmayıb.

Status legend: PASS / FAIL / PARTIAL / NOT TESTED / N/A. Severity: P0–P3.

## 0. Xülasə
- Bütün 9 checklist sahəsi işlənib; 2 FAIL (F-01 LLM→innerHTML, F-02 qeydiyyatsız media prefiksi), 1 konfiqurasiya sızması (F-03 klon DB parolları), qalan sahələr PASS.
- 2026-09-02 tapıntılarının statusu: P0-1 media (bağlı, reyestr), P1-3 audit silinməsi (bağlı), P2-4 alertmanager (bağlı), P2-5 rate-limit (bağlı — boot validasiyası + fail-closed), P2-6 XFF (bağlı — tək `get_client_ip`), «carried» enumerasiya (bağlı — sessiya-bağlı resend).
- Raw SQL 27 sayt / 0 injection; `|safe` 3 / 0 risk; `csrf_exempt` 1 / əsaslı; DOM sink 524 / 1 P2; upload sahələri 33 + 3 ad-hoc yol / 3 qeydiyyatsız; audit-log 18/18 əməl.
- Sübut faylları: `probes/dom_sinks.json`, `probes/secret_scan_out.txt` (dəyərsiz), `probes/osv_result.json`, `repro/test_media_unregistered_prefixes.py` (sandbox `ems_audit_security`, 4 passed).

## 1. Injection
### 1.1 Raw SQL inventarı — **PASS**
Grep: `\.raw\(|RawSQL\(|\.extra\(|cursor\.execute\(` (apps/core/config, testlər/migrasiyalar xaric) → **27 çağırış, 0 `.raw()`/`RawSQL`/`.extra()`**.

| Fayl:sətir | Nə | Parametrləşmə | Sorğu mənbəyi | Hökm |
|---|---|---|---|---|
| `core/rls.py:72,100,108` | `set_config`/`current_setting` | `%s` bound; f-string yalnız developer-in `set_config(%s,%s,%s)` siyahısı (`", ".join([...]*len)`) | GUC adları kod sabitləri | safe |
| `apps/accounts/services/identity_{access,reinstate,archive}.py` (9) | `set_config('app.current_user_id')` + `SELECT public.accounts_*_identity(%s…)` | bound | actor.pk / uuid | safe |
| `apps/registrar/reference_identity.py:169,193,235` | `set_config` siyahısı (`_TRANSFER_GUCS` sabiti) + `registrar_*_group_transfer(%s…)` | bound | sabit / pk | safe |
| `apps/legacy_import/services/{repair_support,ledger_locks,rehearsal_target_guard}.py` | `current_setting(%s)`, `pg_try_advisory_xact_lock(%s)`, `pg_roles`, `django_migrations` | bound / sabit | sabit | safe (operator-only) |
| `apps/legacy_import/services/mariadb_source.py:296-411` | MariaDB SELECT-lər (`_execute`, `_open_stream`) | dəyərlər bound; identifikatorlar `source_extraction.py:200` backtick, `field_contracts._identifier_tokens` ilə validasiya | plan/kontrakt sabitləri (request yox) | safe (operator-only, read-only sessiya) |
| `apps/exams/services/bank_fingerprint.py:28` | `MD5(GROUP_CONCAT(...)) FROM (<ORM compiler SQL>)` | ORM `as_sql()` + params | ORM | safe (yalnız sqlite yolu) |
| `apps/organizations/checks.py:38`, `core/views.py:92` | `pg_roles`, `SELECT %s` | sabit / bound | — | safe |

Heç bir request-dən gələn dəyər SQL mətninə düşmür. 2026-09-02 «22 sayt» nəticəsi ilə uyğundur (say artıb: identity/registrar DB-funksiya səthləri əlavə olunub, hamısı bound).
### 1.2 Template injection — **PASS**
- `|safe`: yalnız `templates/partials/_bootstrap_select_field.html:24,32,40` (`field_extra_attrs`, `option.attrs`, `field_hint_attrs`). Bütün 8 çağırış (`blog/post_form.html:47,49`, `accounts/.../_create_post.html:38,40`, `_post_edit_modal.html:42,44`) template-də **literal** string ötürür; `option.attrs` yalnız `apps/blog/selectors.py:265,274` (`""` və ya `data-parent-id="{int pk}"`) və `blog/profile_sections.py:45` (`""`) tərəfindən yaradılır → istifadəçi məlumatı yoxdur. Eyni partial-da `option.value/label` autoescape-dən keçir.
- `mark_safe(`: **0** (apps/core, test xaric). `autoescape off`: **0**. `format_html`: 17 çağırış, hamısı `apps/contact/admin.py`, `apps/trial_exams/admin.py` — f-string/`%`/`.format` misuse **0**.
- `<script type="application/json">` blokları: 56 `json_script` + 20 əl ilə yazılmış blok. Əl ilə yazılanlarda hər `{{ }}` ya `|escapejs` / `{% filter escapejs %}`, ya tam ədəd (`.id`, `|length`, `*_count|default:0`) — skript `probes/`-də (inline python) → **0 escape-siz string**. `escapejs` `<`→`\u003C` verir, `</script>` qaçışı mümkün deyil.
- `|escapejs` ümumi 211 istifadə; `<script>` daxilində `|safe` **0**.
### 1.3 JS DOM sink-ləri — **PASS (1 × P2 istisna)**
Inventar `probes/dom_sinks.json`: 524 sink (`innerHTML`/`insertAdjacentHTML`/`outerHTML`; `document.write`/`eval`/`new Function` **0**). 466 «dyn» (dəyişən/serverdən gələn HTML), 58 template-literal interpolyasiyalı; escape sarğısız interpolyasiya 51. Hər 51-i və 170 birləşdirmə/dəyişən RHS-i əl ilə təsnif etdim:

| Sinif | Say | Nümunə | Hökm |
|---|---|---|---|
| i18n sabiti / ikon class / emoji kataloqu | 38 | `I18N.noGroup`, `ICON_CLASS_BY_TYPE[..]`, `REACTION_EMOJI` (server `constants.py:150` sabit) | safe |
| Server-render HTML (`data.html`, `payload.html`) | ~60 | Django autoescape-dən keçmiş partial | safe |
| Live-exam nickname/qrup adı | 20+ | `podium.js:108`, `lobby.js:46`, `player/render.js:420,534` hamısı `esc()` | safe |
| Öz girişi (self-XSS) | 2 | `live_exam/join.js:84` (`nickname` preview), `exams/testQuestionBank.js:37` (`fileName`) | P3 gigiyena |
| Server sabit mesajı, escape-siz | 3 | `assignment_modal.js:206,243` (`data.error`/`err.message`), `courses/notifications.js:62` (`message`) — bütün cari mənbələr sabit/i18n (`assignments/views/**` grep) | P3 latent |
| LLM çıxışı → HTML | 3 | `static/js/ai_assistant.js:255` (escape ✔), `accounts/.../statistics/utils.js:57` (escape ✔), `exams/.../exam_center_stats_charts.js:31` (escape ✔), **`exams/static/exams/js/teacher_exam_statistics_charts.js:201-214` (escape ✘)** | **P2 — bax F-01** |
| Markdown link | 1 | `ai_assistant.js:265-271` yalnız `/`,`http(s)://` prefiksinə icazə (javascript: blok) | safe |

Stored-XSS probe (dev clone): `teacher_exam_statistics_charts.js` üçün payload sual mətni → Gemini çıxışı olduğundan deterministik deyil; kod oxunuşu ilə FAIL kimi qeyd edildi (sibling fayl escape edir → aydın drift).

## 2. CSRF / CORS / CSP / başlıqlar — **PASS**

| Yoxlama | Sübut | Status |
|---|---|---|
| CSP `script-src` | `config/settings/components/csp.py:40-44` `SELF + NONCE + Clarity` — `unsafe-inline`/`unsafe-eval` yox; `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`; prod `production.py:546-556` eyni + `img-src https:` | PASS |
| CSP `style-src-attr 'unsafe-inline'` | sənədləşdirilmiş müvəqqəti istisna (CLAUDE.md); inline `style=` 20→4 (`--pct`) azaldılıb | PASS (izlənir) |
| CSP `connect-src` base-də `ws://127.0.0.1:8000` və s. | yalnız base (dev); prod `_csp_connect_sources(SITE_URL, LIVE_EXAM_PUBLIC_HOST)` → `https://`/`wss://` (`production.py:200-224`) | PASS |
| CORS | `corsheaders` yoxdur (requirements/config grep = 0) → same-origin | N/A |
| `csrf_exempt` inventarı | **1** — `apps/monitoring/views.py:351 alertmanager_webhook`: `require_POST`, yalnız `Authorization: Bearer` (`_bearer_token`) + `hmac.compare_digest`, boş token → 403; `?token=` yolu 2026-09-12 silinib. Əsaslandırılıb | PASS |
| Clickjacking | `X_FRAME_OPTIONS="DENY"` (security.py:127, production.py:338) + `XFrameOptionsMiddleware` + CSP `frame-ancestors 'none'` | PASS |
| HSTS / secure cookie | `production.py:329-381`: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` default True; `INSECURE_TRANSPORT_OK` olmadan hər üçü False olarsa `ImproperlyConfigured` (355-360); HSTS 31536000 + subdomains + preload | PASS |
| `SECURE_PROXY_SSL_HEADER` vs edge | `production.py:332` `X-Forwarded-Proto`; `docker/nginx/nginx.conf:131,187` `$scheme`, `/metrics` üçün sabit `https` (daxili); compose: yalnız nginx 80/443 açıqdır (`docker-compose.prod.yml:21,370`), app portu publik deyil → başlıq saxtalaşdırıla bilməz | PASS |
| `X-Forwarded-For` | nginx **overwrite** (`$remote_addr`, `nginx.conf:129,161,186`; CI conf `$proxy_add_x_forwarded_for` — yalnız CI). Tək mənbə `core/utils.py:166-191 get_client_ip` sağdan `TRUSTED_PROXY_HOPS`; `HTTP_X_FORWARDED_FOR` başqa yerdə parse olunmur (grep = 1 sayt). 2026-09-02 P2-6 **bağlanıb** | PASS |
| Referrer / Permissions / COOP / CORP | `security.py:128-149` `strict-origin-when-cross-origin`, `camera=(), geolocation=(), microphone=()`, `same-origin`, `same-origin`; `core/middleware.py:357 SecurityHeadersMiddleware` `setdefault` | PASS |
| nosniff | `SECURE_CONTENT_TYPE_NOSNIFF=True`; `protected_media` hər cavabda `X-Content-Type-Options: nosniff` (`core/media_views.py:548,558,577`). **Qeyd:** nginx-in birbaşa verdiyi `/media/post_images/`, `/media/course_covers/` və `/static/` cavablarında nosniff **yoxdur** (`nginx.conf:104-113`) — uzantı allow-list (jpg/png/gif/webp) + brauzerlərin image/* → HTML sniff etməməsi səbəbindən istismar olunmur; P3 sərtləşdirmə | PASS (P3 qeyd) |
| Cookie atributları | `SESSION_COOKIE_HTTPONLY`, `SameSite=Lax`, `CSRF_COOKIE_HTTPONLY=False` (JS oxuyur — məqbul), `LANGUAGE_COOKIE_HTTPONLY` | PASS |
| Admin | `ADMIN_URL_PREFIX` prod-da `admin` qadağan (`production.py:281-283`), `AdminSecurityMiddleware` IP allow-list, `AdminOTPGateMiddleware` 2FA qapısı | PASS |
| Monitoring portları | alertmanager/prometheus/grafana `127.0.0.1:` bind (`docker-compose.prod.yml:635,689,729`) | PASS |

## 3. Giriş nəzarəti — media / export / hesabat / AI / bildiriş — **PARTIAL**

| Sahə | Sübut | Status |
|---|---|---|
| Media prefiks əhatəsi | 33 model sahəsi + 3 `default_storage.save` yolu → 4.1 cədvəli. `_PUBLIC_PREFIXES` = `post_images/ course_covers/ org_logos/`. Bütün model `upload_to` prefiksləri `_ACCESS_CHECKERS` (11) + `media_policies.ACCESS_CHECKERS` (12) reyestrindədir. **İstisna:** `assignments/submissions/`, `notifications/files/`, `notifications/images/` — reyestrdə yoxdur → deny-by-default (sandbox test `repro/test_media_unregistered_prefixes.py`: auth istifadəçi 404, ictimai kontrol 200) | **FAIL — funksional, fail-closed (F-02, P2)** |
| Media traversal / klassifikasiya | `normpath` + `safe_join` + `..` rədd; 403 əvəzinə 404 (mövcudluq sızmır) | PASS |
| Avatar | `_check_avatar_access` → istənilən auth istifadəçi (tenant-arası) — dizayn qərarı, aşağı risk | PASS (qeyd) |
| Export scope | `apps/audit/views.py:1006` `_run_scoped(is_superadmin…)` + `log_action(EXPORT)`; `student_registry.py:184` registry scope; `journal_export.py`/`lessons_log_views.py` registrar scope — scope məntiqi `access` auditorunun sahəsidir | NOT TESTED (access) |
| CSV/XLSX formula neytrallaşdırma | Export tərəfdə **heç bir** `=`/`+`/`-`/`@` prefiks qorunması yoxdur (grep: 0 helper; import tərəfdə `registrar/exam_score_import_safety.py:20` var). openpyxl `"=…"` sətrini **formula** (`data_type='f'`) kimi yazır — yerli sınaq: `ws.append(["=1+1"])` → `'f'`. İstifadəçi mətnli sütunlar: ad/soyad (admin təyin edir), audit `reason` (müəllim/əməkdaş yazır → `audit/views.py:947 _csv_row`), qrup adı, incident meta (`xlsx_build.py:101` — `key: value` prefiksli, formula deyil) | **P3 (F-07)** |
| AI assistant kontekst | `apps/ai_assistant/context_builder.py:21-58`: yalnız `request.organization` + öz kursları/cəhdləri (`Exam.objects.filter(organization=…, author=user)`, `ExamAttempt.filter(user=user, exam__organization=…)`), naviqasiya icazə siyahısı ilə; `security.py` giriş regex + çıxış redaksiyası (ikincil) | PASS |
| AI-ya göndərilən PII | `_user_identity_section` (`context_builder.py:207-209`) **ad + e-mail** + imtahan balları hər sorğuda Gemini-yə gedir; `AIAssistantLog.prompt` tam mətn saxlanır (`models.py:36`). Statistik xülasə: sual mətnləri + qrup adları; AI qiymətləndirmə: tələbə cavabı + şəkil | **P3 məxfilik (F-08)** |
| AI prompt-injection | `ai_grading.py:317-345` tələbə cavabı delimitersiz prompt-a daxil olur; nəticə yalnız **təklif**dir (müəllim `feedbackInput.value`/`textContent`, `teacher_check_attempt.js:438,464`) | P3 (F-08) |
| Bildiriş hədəfləri | `access` auditoru | NOT TESTED |

## 4. Fayl yükləmələri — **PARTIAL** (1 × P2 funksional, 2 × P3)

### 4.1 Upload sahələri inventarı (33 `FileField/ImageField`, test/migrasiya xaric)

| Model sahəsi | `upload_to` prefiksi | Model validator | View/form allow-list | Media checker |
|---|---|---|---|---|
| `organizations.Organization.logo` | `org_logos/` | — (yalnız admin ImageField→Pillow) | admin | PUBLIC |
| `blog.Post.image` | `post_images/` | — | `blog/forms.py:239`, `views/author/posts.py:224` IMAGE ext | PUBLIC (nginx birbaşa) |
| `courses.Course.cover_image` | `course_covers/` | — | `courses/forms.py:137` IMAGE ext | PUBLIC (nginx birbaşa) |
| `accounts.User.avatar` | `avatars/` | — | `profile_actions.py:54` `PROFILE_AVATAR_ALLOWED_EXTENSIONS` | `_check_avatar_access` (hər auth istifadəçi) |
| `courses.CourseResource.file` | `course_resources/` | — | `courses/forms.py:285` pdf/zip/rar/7z/txt/doc(x)/xls… | `_check_course_resource_access` (org üzvü) |
| `labs.*` (4 sahə) | `labs/{submissions,answers,teacher_files,questions}/` | `FileUploadValidator()` ×3 (submission_file — yox) | `labs/views/shared/_helpers.py:50` `DEFAULT_LAB_ALLOWED_EXTENSIONS` | `_check_lab_file_access` (4 alt-prefiks) |
| `projects.Submission.file` | `projects/submissions/` | `FileUploadValidator()` | `projects/forms.py:81` allow-list | `_check_project_submission_access` |
| `assignments` (JSON `files`) | **`assignments/submissions/`** (`assignments/models.py:355` `default_storage.save`) | — | `assignments/forms.py:76` allow-list | **QEYDİYYATSIZ → hər kəsə 404 (F-02)** |
| `exams.ExamAnswerFile.file` | `exam_uploads/` | `validate_file_extension/size/zip_contents` | `views/student/attempts.py:156` `EXAM_ALLOWED_EXTENSIONS` | `_check_exam_upload_access` |
| `exams.ExamAnswer.paint_image` | `exam_paints/` | — (server base64→PNG, `services/utils.py:46-73`, regex `data:image/png`, 1.5M simvol limit) | — | `_check_exam_paint_access` |
| `exams.*Question/Option.image/video` (6) | `question_media/`, `bank_media/` | video: `FileExtensionValidator(mp4/webm/mov)` | `forms/question.py:323,333`, `forms/bank_question.py:156,165` IMAGE ext / video | `_check_question_media_access`, `_check_bank_media_access` |
| `exams.TextExtractionJob.file/result_file` | `import_jobs/%Y/%m/` | — (yalnız ölçü, `extract_jobs.py:143`; uzantı yoxlaması task-da `pipeline.py:59-173`) | — | `_check_import_job_access` (**yalnız sahibi**) → P3 |
| `registrar.*` (10 sahə) | `journal_*_corrections/`, `exam_score_entries/`, `exam_score_sheets/`, `legacy_excuse_documents/`, `student_movements/`, `guest_roster_documents/` | `FileUploadValidator(allowed_extensions=…, max_size_mb=…)` | — | `core/media_policies.py:441-454` hamısı qeydiyyatlı |
| `applications.ApplicationAttachment.file` | `applications/<org>/<app>/` | `FileUploadValidator(ALLOWED_ATTACHMENT_EXTENSIONS, 10MB)` + `validate_zip_archive` (`services/submit.py:82`) | — | `check_application_attachment_access` + ayrıca `views/downloads.py` |
| `workload.Amendment.document` | `workload_amendments/` | `FileUploadValidator({".pdf"},10)` | — | `check_workload_amendment_access` |
| `trial_exams.TrialExamRequest.questions_file` | `trial_exams/` | `FileUploadValidator({".pdf"})` | `trial_exams/forms.py:121` | `_check_trial_exam_access` |
| bildiriş qoşmaları (model yox) | **`notifications/files/`, `notifications/images/`** (`profile_actions.py:198,259`) | — | `profile_actions.py:187,249` allow-list | **QEYDİYYATSIZ → hər kəsə 404 (F-02)** |

`_PUBLIC_PREFIXES` = `post_images/`, `course_covers/`, `org_logos/` (`core/media_views.py:68-72`); `_is_private` ağ-siyahı məntiqi (hər şey privat, yalnız bu üçü ictimai). Naməlum privat prefiks → **deny** (`media_views.py:518`). nginx də yalnız `post_images/`, `course_covers/` birbaşa verir (`org_logos/` Django üzərindən keçir — uyğunsuzluq yalnız performans).

### 4.2 Validator (`core/upload_security.py`) qiymətləndirməsi
| Yoxlama | Nəticə |
|---|---|
| Uzantı block-list (`.exe .php* .html .htm .svg .js .sh …`, 25 ədəd) + ikiqat uzantı (`shell.php.jpg`) | PASS; **boşluq:** `.xhtml`, `.mjs`, `.xml`+`.xsl`, `.svgz`, `.shtml`, `.mht` block-list-də yoxdur. Latent — bütün çatan yükləmə yolları allow-list verir (bax 4.1), yalnız `import_jobs/` (sahibinə) və model-səviyyə `FileUploadValidator()` (labs/projects — view allow-list ilə örtülü) default-a düşür → **P3 (F-06)** |
| MIME | `_resolve_mime_type` (128-133) **müştərinin `content_type`-ına etibar edir**; magic-bytes yalnız `MZ`/`<?php` (119-125). Şəkillərdə Pillow `verify()` yalnız import_media-da; avatar/post/question şəkli üçün yoxdur. İstismar: `.png` içində HTML — brauzer `image/*`-i HTML kimi sniff etmir + `nosniff` → XSS olmur; polyglot yalnız disk yeri. **P3 (F-06)** |
| Ölçü | default 25 MB, sahə-səviyyə 10 MB (PDF), exam `EXAM_ANSWER_FILE_MAX_SIZE_MB`, extraction `MAX_UPLOAD_BYTES`; bildiriş `_NOTIFICATION_FILE_MAX_MB` | PASS |
| SVG/HTML şəkil kimi | `.svg/.html/.htm` blok; `IMAGE_ALLOWED_EXTENSIONS` = jpg/jpeg/jfif/png/gif/webp | PASS |
| Path traversal | `randomize_uploaded_filename` (uuid ad) 14 saytda; Django `FileField.generate_filename → validate_file_name`; `protected_media` `posixpath.normpath` + `safe_join` + `..` rədd (`media_views.py:530-537`) | PASS |
| Overwrite | Django `Storage.get_available_name` (suffix) — heç yerdə `os.remove`/`overwrite` yoxdur | PASS |
| ZIP bomb | `validate_zip_archive` (1000 fayl, 100 MB, dərinlik 3, nisbət) — exam uploads (`exams/validators.py:71`), applications, exam-score import. Labs/course_resources/projects ZIP-ləri server tərəfində **açılmır** (`extractall` grep = 0) → yalnız saxlanılır | PASS |
| Private vs public | bax 4.1; korreksiya/sübut PDF-ləri (2026-09-02 P0-1) indi `media_policies` reyestrində | PASS |
| İcra olunan məzmun | `.php/.sh/.exe` blok, MZ imzası; nginx `location /media/` → Django/`internal` alias (icra yoxdur) | PASS |

## 5. Auth-ə yaxın — **PASS**

| Yoxlama | Sübut | Status |
|---|---|---|
| OTP entropiyası | `core/utils.py:15-19` `secrets.choice(digits)` ×6; saxlama `salted_hmac(SECRET_KEY)` (`otp_models.py:70-76`); 300 s ömür, 5 cəhd (`exam.py:165-167`), saat-başı göndərmə limiti (`services/auth.py:203-209`), köhnə pending-lər invalidasiya | PASS |
| Reset token | Django `default_token_generator` (`urls.py:56 reset/<uidb64>/<token>/`) + OTP; `PASSWORD_RESET_TIMEOUT`=300 s | PASS |
| OTP/parol/token log-da | grep `logger.*(otp|code|token|password)` → yalnız `user %s not found` (`core/email_tasks.py:117,183`), token dəyəri heç yerdə; `core/logging_filters.py:36-57` sanitizer | PASS |
| Sessiya | `cached_db`, `HttpOnly`, `Lax`, prod 24 h / 8 h hərəkətsizlik (`production.py:365-367`), `SessionTimeoutMiddleware` | PASS |
| Admin | `ADMIN_URL_PREFIX≠admin` prod-da məcburi, IP allow-list, `AdminOTPGateMiddleware` 2FA | PASS |
| XFF bypass | bax §2 — tək `get_client_ip`, sağdan, nginx overwrite | PASS |
| Open redirect | `_safe_same_origin_redirect_path` (`core/helpers.py:55`) və `url_has_allowed_host_and_scheme` — `next`/`return_to`/`referer` istifadə edən **13** sayt hamısı yoxlanır (`selection.py:117`, `labs`, `assignments/projects endpoints.py:124`, `schedule_views.py:59`, `blog/moderator/posts.py:90`, `courses/crud.py:205`, `exam_score_entry.py:103`, `journal_close.py:89`, `account_management.py:350`, `middleware.py:396`); `LOGIN_REDIRECT_URL` fallback | PASS |
| Logout CSRF | `register.py:368-378` yalnız POST (405) + CsrfViewMiddleware | PASS |
| Hesab enumerasiyası (2026-09-02 «carried») | `resend_code_view` e-mail-i **sessiyadan** oxuyur (`register.py:288`), kənar e-mail sorğulana bilmir; reset formu Django `get_users` semantikası (həmişə «done») | PASS |

## 6. Sirlər və konfiqurasiya — **PARTIAL** (1 × P2)

Skan: `probes/secret_scan.py` (gitleaks-üslublu 9 qayda, yalnız `git ls-files`, `.env*` xaric; çıxış `probes/secret_scan_out.txt` — **dəyərlər çap olunmur**). 419 xam uyğunluq: 387 `generic_assign` (hamısı test fixture / CI placeholder / audit sübut log-ları), 3 `google_api_key` (`.gitleaks.toml:44` allow-list-dəki saxta fixture + `ai_assistant/tests.py:30,191` eyni fixture), 29 `url_creds`.

| Yoxlama | Sübut | Status |
|---|---|---|
| Tracked fayllarda **işlək** DB parolları | `url_creds` hit-lərinin təsnifatı (yalnız SHA-256 prefiksi ilə müqayisə, `probes/`): **iki fərqli literal parol** (`emsarena_app`, sha8 `c58d0355`; `emsarena_staging`, sha8 `c55cb02e`) QA klonu `127.0.0.1:55433` üçün **`.claude/launch.json:46`** (tracked!), **`docs/ROL_MATRISI.md:13`**, **`scripts/qa_live/query_profile.py:7`**, `docs/audits/2026-09-02/REHEARSAL_FRESH_2026_09_03.md:13-14`-də. Klon 8 644 real istifadəçi ilə real məlumatın kopyasıdır. `.gitleaks.toml` bunları allow-list etmir, amma gitleaks default qaydaları `postgres://user:pass@host` formasını tutmur → CI keçir | **FAIL — P2 (F-03)** |
| Digər `url_creds` | `.github/workflows/*` CI placeholder (`security_user`, `test_user`), `README.md:231` nümunə, `docs/operations/CLAUDE_POSTGRES_SANDBOX.md:42,48` agent sandbox (`emsarena_agent`, sha8 `c186a9e6` — audit brifində açıq verilən sandbox parolu), `scripts/dev-daphne.sh:100` `$CLONE_PASSWORD` dəyişəni | PASS |
| `.env` | `.gitignore:6 *.env`, `git ls-files .env` boş; `.env.example` (75 sətir), `.env.production.example` | PASS |
| `SECRET_KEY` | prod `os.environ["SECRET_KEY"]` (`production.py:238`); local boşdursa `ImproperlyConfigured` (`local.py:206-218`); test random | PASS |
| `DEBUG` | prod `False` sabit (`production.py:246`); test `False`; `handler403/404/500` `core/views` (`config/urls.py:21-23`) | PASS |
| `ALLOWED_HOSTS` | boşdursa `ImproperlyConfigured` (`production.py:299-301`) | PASS |
| Sentry PII | `send_default_pii=False` (`production.py:532`) | PASS |
| `.env.production.example` əhatəsi | 165 settings env-var vs 60 nümunə; təhlükəsizlik-əlaqəli çatışmayanlar: `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_*`, `INSECURE_TRANSPORT_OK`, `ADMIN_*_RATE_LIMIT`, `FINAL_EXAM_ALLOWED_IPS`, `CODING_PISTON_AUTH_TOKEN`, `EMAIL_HOST_PASSWORD`, `PASSWORD_RESET_TIMEOUT` (hamısının təhlükəsiz default-u var) | P3 (F-09) |
| Docker | `Dockerfile.prod:71,108` `appuser` (non-root), base image sha-pinned; compose sirrləri yalnız `${VAR}` interpolyasiyası (literal 0); Redis parol məcburi (`:?`) | PASS |
| Alertmanager token (2026-09-02 P2-4) | `.env.production.example:47` var; `production.py` import siyahısında — Codex remediasiyası ilə bağlanıb (bearer) | PASS |

## 7. Asılılıqlar — **PASS** (1 × P3)

Mənbə: `probes/osv_result.json` (OSV batch, 64 paket — `requirements/base.txt` + `production.txt` + venv-dən götürülən köməkçi paketlər). `pip-audit`/`safety` şəbəkə alətləri ayrıca işlədilmədi (OSV nəticəsi mövcud olduğundan).

| Paket | Quraşdırılmış (pin) | Advisory | Fixed-in | Şiddət | Burada istismar? |
|---|---|---|---|---|---|
| Django | 5.2.17 | yox (5.2.17 = 2026-08-04 security release) | — | — | — |
| sqlparse | 0.6.0 | yox | — | — | — |
| pillow | 12.3.0 | yox | — | — | — |
| cryptography / pyOpenSSL / Twisted | 50.0.0 / 26.4.0 / 26.4.0 | yox | — | — | — |
| urllib3 / requests / certifi | 2.7.0 / 2.33.0 / 2026.1.4 | yox | — | — | — |
| celery / redis / channels / channels_redis / daphne | 5.5.2 / 7.1.0 / 4.3.2 / 4.3.0 / 4.2.2 | yox | — | — | — |
| pypdf / PyMuPDF / lxml / python-docx / openpyxl | 6.16.1 / 1.24.14 / 6.1.0 / 1.2.0 / 3.1.5 | yox (pypdf 6.16.1 CVE-2026-84309/10/11 bağlı) | — | — | — |
| psycopg2 / sentry-sdk / django-csp / django-ratelimit | 2.9.9 / 2.52.0 / 4.0 / 4.1.0 | yox | — | — | — |
| **setuptools** | **venv 65.5.0** (requirements `>=78.1.1`, `Dockerfile.prod:79` `--upgrade setuptools`) | PYSEC-2022-43012 (CVE-2022-40897 ReDoS), PYSEC-2025-49 (CVE-2025-47273 path traversal), GHSA-5rjg-fvgr-3xxf, GHSA-cx63-2mw6-8hw5, GHSA-h35f-9h28-mq5c, GHSA-r9hx-vwmv-q579, PYSEC-2026-1918, PYSEC-2026-3447 | 78.1.1+ | orta | **Xeyr** — yalnız lokal venv; prod image yenilənir (Codex P2-10 bağlı). Lokal: `venv/bin/pip install -U setuptools` |
| google-generativeai | 0.8.6 | yox; paket **deprecated** (Google → `google-genai`) | — | — | P3 texniki borc (F-10) |

Frontend vendor (`static/vendor`): Bootstrap **5.3.0** (cari 5.3.x-də düzəlişlər; 5.3.0 üçün məlum XSS advisory yoxdur — CVE-2024-6531 4.x Carousel), Tooltip/Popover **istifadə olunmur** (grep 0); Chart.js 4.4.7; FontAwesome 6.4.0; CodeMirror 5.65.21 (5.x son). `package.json` yoxdur; CDN skript yoxdur (CSP `script-src 'self'`). → PASS, Bootstrap yeniləməsi P3 gigiyena.

## 8. Logging / məxfilik / audit-log əhatəsi — **PASS** (2 × P3)

| Yoxlama | Sübut | Status |
|---|---|---|
| Parol/OTP/token log-da | grep → 0 dəyər; yalnız e-mail ünvanları `services/auth.py:259`, `core/email_tasks.py:151`, `core/mailing.py:146` — prod-da `SensitiveDataFilter` (`core/logging_filters.py:18 _EMAIL_RE`, `production.py:481-496` bütün handler-lərdə) maskalayır | PASS |
| Tələbə cavabı/bal log-da | grep `answer_text|student_answer|score=` → 0 | PASS |
| Clarity | `core/context_processors.py:176-181`: yalnız anonim səhifələr, kabinet üçün `MICROSOFT_CLARITY_AUTHENTICATED` bayrağı (default False); formalar `data-clarity-mask` — Codex §11 bağlı | PASS |
| PII → 3-cü tərəf (Gemini) | bax §3 F-08 (ad + e-mail + ballar; `AIAssistantLog.prompt` tam saxlanır, saxlama müddəti yoxdur) | P3 |
| Export-da artıq PII | `student_registry.py` CSV: kod, ad, ixtisas, qrup, kurs, il, forma, təhsil haqqı, status — məqsədə uyğun; audit CSV `IP ünvanı` + `Sorğu ID` daxildir (yalnız superadmin/scope) | PASS |
| Audit jurnalı append-only (2026-09-02 P1-3) | `apps/audit/admin.py:64-66` `has_delete_permission` → heç kim | PASS |

### 8.1 Yüksək riskli əməllər → audit yazısı

| Əməl | Yazı yolu | Audit | Sübut |
|---|---|---|---|
| Jurnal balı (dərs/kollokvium/sərbəst iş/kurs işi) | `registrar/gradebook.py:118 save_marks`, `gradebook_components.py:345` | ✅ | `grade_audit.log_grade_changes` (`gradebook.py:239`, `grade_audit.py:88-91 AuditLog.objects.create`) + DB immutability trigger (`migrations/0024`) |
| Final/yekun bal | `registrar/finals.py:288,323,359` | ✅ | `log_grade_changes` |
| Sənədli düzəliş (correction) | `registrar/corrections.py:186,200,376,383,440,447` | ✅ | `log_grade_changes` + `log_action` |
| İmtahan balı daxil etmə / import | `registrar/exam_score_entry.py record_exam_score` (import → `save_roster_scores` eyni yol, `exam_score_import.py:12`) | ✅ | `log_action` ×1 + sübut/səbəb məcburi (`:304 _require_justification`) |
| İmtahan cavabının müəllim balı (result modification) | `exams/services/manual_grading.py:78-88` | ✅ | `ExamGradeEvent` (old/new/grader) — `AuditLog`-a deyil, ayrıca hadisə cədvəlinə |
| Apellyasiya qərarı / bal düzəlişi | `appeals/services/decisions.py:47-86` | ✅ | `log_action` ×2 |
| Rol təyini / dəyişməsi | `accounts/views/roles/_assignment_flow/flow.py:244` | ✅ | `create_audit_log` |
| İcazə matrisi redaktəsi | `accounts/views/roles/permissions.py:210-215` | ✅ | `create_audit_log(action="update", resource_type="role")` |
| Müəllim rolu ver/al, hesab status | `accounts/services/people/actions.py:134,280,356` | ✅ | `log_action` ×3 |
| Üzv çıxarma / arxiv | `identity_archive.py:144`, `people/actions.py:347` (`set_teacher_role(grant=False)` → `:356`) | ✅ | `log_action` |
| İmtahan aktivləşdirmə / dayandırma / silmə / bərpa | `exams/views/teacher/exams/actions.py:138-141,213-216,268-271,338`; `services/lifecycle.py:34-45` | ✅ | `log_action` |
| Sual bankı toplu silmə (2026-09-02 P0-2) | `exams/views/teacher/question_library/crud.py` | ✅ | `log_action` ×3 |
| Sillabus təsdiqi / rədd | `syllabus/services/workflow.py:104-119 _audit` | ✅ | `log_action` |
| Qrup köçürmə | `registrar/transfer.py:44` + DB evidence funksiyası (`reference_identity.py:184-229`) | ✅ | `log_action` + `GroupTransferEvidence` |
| Jurnal bağlama | `registrar/journal_close.py:129` | ✅ | `log_action` |
| Dəvət silmə (`invite_membership.delete()`) | `accounts/views/organization/invitations.py:172`, `_management_flow/_invites.py:152` | ✅ | həmin fayllarda `log_action` ×2 |
| View-as | `accounts/services/view_as.py` | ✅ | `log_action` ×2 |
| Export | `audit/views.py:992` | ✅ | `log_action(EXPORT)` |

Boşluq tapılmadı; yeganə qeyd — imtahan cavab balı `AuditLog` əvəzinə `ExamGradeEvent`-də (ayrıca cədvəl; audit ekranında görünmür) → P3 (F-11).

## 9. WebSocket / ASGI — **PASS**

| Yoxlama | Sübut | Status |
|---|---|---|
| Origin / auth stack | `config/asgi.py`: `AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(...)))` | PASS |
| Auth on connect | `exams/consumers.py`: 3 consumer hər biri `is_authenticated` (4401) + obyekt icazəsi (`_can_observe_attempt` — yalnız cəhd sahibi/müəllif; `_can_supervise`; `_authorize` ticket) (4403); `live_exam/consumers.py:84-97` `authorize_socket_connection(pin, user_id, token)` — imzalı `signing.loads(salt=PLAYER_TOKEN_SALT, max_age=PLAYER_TOKEN_MAX_AGE)` (`live_exam/auth.py:17-19`), token-də `pin` uyğunluğu (`auth.py:100-101`) | PASS |
| Qrup adlandırma | `exam_supervision_{attempt_id}`, `staff_group(session_id)`, ticket qrupları; live: host və oyunçu ayrı qruplar (`consumers.py:209`) — tenant sızması üçün cross-pin qoşulma yoxdur | PASS |
| Mesaj validasiyası | `ExamSupervisionConsumer` `receive_json` yoxdur (yalnız server→client); `FinalExamRoomConsumer` yalnız `ping`; `LivePlayConsumer` `parse_answer_submission` (`transport.py:100-111`: `int()`, `option_ids` ≤ 50, `isdigit`) | PASS |
| Rate limiting | live: connect (`_get_connect_rate_identity`, token/cookie/user əsaslı), ümumi mesaj və cavab limitləri (`consumers.py:225-260`, `logger "live_exam.ws.rate_limit"`) | PASS |
| RLS konteksti | `rls_worker_atomic()` + `bypass_rls()` yalnız PIN/token axtarışı üçün (`consumers.py:95-97`) — `access` auditoru bypass_rls saytlarını izləyir | PASS (qeyd) |

## 10. Tapıntılar (P0–P3) və minimal düzəlişlər

**P0: 0 · P1: 0 · P2: 3 · P3: 8**

| ID | Sev | Tapıntı | Sübut | Minimal təhlükəsiz düzəliş |
|---|---|---|---|---|
| F-01 | **P2** | LLM çıxışı escape-siz `innerHTML`-ə yazılır (müəllim imtahan statistikası AI xülasəsi). Prompt-a sual mətnləri + qrup adları daxil olur (`views/teacher/statistics.py:356-404`); paylaşılan bank sualı və ya qrup adı vasitəsilə dolayı prompt-injection → müəllim brauzerində XSS mümkündür (CSP inline-i bloklayır, amma `<img onerror>`-suz `<a href>`/DOM manipulyasiyası və `'self'` skriptləri açıqdır). Sibling fayl `exam_center_stats_charts.js:31` escape edir — aydın drift | `apps/exams/static/exams/js/teacher_exam_statistics_charts.js:188,201-214` | `formatMarkdown` başlanğıcında `escapeHtml(text)` tətbiq et (eyni faylda helper yoxdursa `exam_center_stats_charts.js:20-28`-dəki `escapeHtml`-i köçür); ideal — üç markdown renderer-i `static/js/ems_ui/markdown.js`-də birləşdir |
| F-02 | **P2** (funksional, fail-closed) | `assignments/submissions/`, `notifications/files/`, `notifications/images/` prefiksləri `default_storage.save` ilə yazılır, amma media checker reyestrində yoxdur → `/media/…` linkləri **superadmin-dən başqa hər kəsə 404** (qiymətləndirmə növbəsi `/media/assignments/submissions/…` linki göstərir — `test_profile_views.py:4509`; bildiriş qoşması `default_storage.url` — `profile_actions.py:200`). Sandbox: `repro/test_media_unregistered_prefixes.py` 4/4 (auth 404, ictimai kontrol 200) | `apps/assignments/models.py:355`; `apps/accounts/services/profile_actions.py:198,259`; `core/media_views.py:456-471,518` | `core/media_policies.py`-də `assignments/submissions/` üçün checker (submission sahibi / kurs müəllimi — `AssignmentSubmission.files[].path` üzrə `JSONField` axtarışı) və `notifications/` üçün checker (bildirişin hədəf org üzvü) əlavə et; `PRIVATE_PREFIXES`-ə qeyd et. Regressiya testi: `core/tests/test_media_views.py`-ə hər prefiks üçün müsbət/mənfi hal |
| F-03 | **P2** | QA klon DB-nin (real istifadəçi məlumatının kopyası) **iki işlək parolu** tracked fayllardadır: `.claude/launch.json:46` (`emsarena_app`), `docs/ROL_MATRISI.md:13`, `scripts/qa_live/query_profile.py:7`, `docs/audits/2026-09-02/REHEARSAL_FRESH_2026_09_03.md:13-14` (`emsarena_staging`). gitleaks default qaydası DSN-i tutmur | `probes/secret_scan_out.txt` (`url_creds`), sha-müqayisə | Parolları rotasiya et (`scripts/provision-app-db-role.sh` / klon `ALTER ROLE`); fayllarda `${CLONE_PASSWORD}` / `<password>` placeholder; `.gitleaks.toml`-a `postgres(ql)?://[^:]+:[^@]{8,}@` qaydası əlavə et; `.claude/launch.json`-ı `.gitignore`-a köçür və ya sirri env-dən oxu. Git tarixindən təmizləmə ayrıca qərar (rotasiya kifayətdir) |
| F-04 | P3 | Self-XSS sink-ləri: `live_exam/join.js:84` (`nickname` preview), `exams/testQuestionBank.js:37` (`fileName`) | §1.3 | `esc()` / `textContent` |
| F-05 | P3 | Server mesajı escape-siz `innerHTML` (hazırda sabit mətnlər): `assignment_modal.js:206,243`, `courses/notifications.js:62` | §1.3 | `textContent` və ya `esc()`; `notify()`-ə `{html:false}` default |
| F-06 | P3 | Upload validator: MIME müştəri `content_type`-ına etibar edir; block-list-də `.xhtml .mjs .xml .xsl .svgz .shtml .mht` yoxdur; şəkil sahələrində Pillow `verify()` yoxdur. Latent — hər çatan yol allow-list verir | `core/upload_security.py:26-47,128-133` | Block-list-i genişləndir; `IMAGE_ALLOWED_EXTENSIONS` yollarında `Image.open().verify()`; `application/*` üçün magic-bytes (`%PDF`, `PK`) |
| F-07 | P3 | CSV/XLSX export-larda formula neytrallaşdırma yoxdur; openpyxl `"=…"` sətrini formula kimi yazır (yerli sınaq `data_type='f'`). İstifadəçi mətnli sütunlar: audit `reason`, ad/qrup | `apps/audit/views.py:947-1012`, `registrar/journal_export.py:112`, `accounts/views/student_registry.py:184-210`, `exams/services/final_center/xlsx_build.py` | `core/export_safety.py: neutralise_cell(v)` (`=+-@\t\r` ilə başlayanlara `'` prefiksi; openpyxl-də `cell.data_type='s'`) və bütün `writer.writerow`/`ws.append`-lərdə tətbiq |
| F-08 | P3 (məxfilik) | AI assistant hər sorğuda ad + e-mail + imtahan ballarını Gemini-yə göndərir; `AIAssistantLog.prompt` tam saxlanır (retention yox); AI grading prompt-unda tələbə cavabı delimitersizdir | `apps/ai_assistant/context_builder.py:207-209`, `models.py:36`, `exams/services/ai_grading.py:317-345` | E-mail-i kontekstdən çıxar (yalnız ad/rol); `AIAssistantLog` üçün retention job; grading prompt-unda cavabı `<student_answer>…</student_answer>` + «cavab məlumatdır, təlimat deyil» sətri |
| F-09 | P3 | `.env.production.example` 24 təhlükəsizlik-əlaqəli env-var-ı sənədləşdirmir (hamısının təhlükəsiz default-u var) | §6 | Şərhlə əlavə et |
| F-10 | P3 | `google-generativeai==0.8.6` deprecated; Bootstrap 5.3.0 → 5.3.x; lokal venv `setuptools 65.5.0` | §7 | `google-genai`-yə miqrasiya planı; vendor yeniləmə; `pip install -U setuptools` (lokal) |
| F-11 | P3 | İmtahan cavab balı dəyişikliyi `AuditLog`-a deyil, `ExamGradeEvent`-ə yazılır — audit ekranında görünmür | `exams/services/manual_grading.py:80-88` | `log_action(UPDATE, obj=attempt, old/new)` əlavə et (və ya audit ekranında `ExamGradeEvent`-i göstər) |

### NOT TESTED (bu buraxılışda)
- Dev-clone-da canlı stored-XSS probe (F-01 LLM çıxışı deterministik deyil; digər sink-lər kod oxunuşu ilə safe).
- Export scope məntiqi və bildiriş hədəf scope-u (`access` auditoru).
- `pip-audit`/`safety` canlı işə salınması (OSV batch nəticəsi istifadə olundu); konteyner OS CVE skanı.

## 11. Ballar

| Sahə | Bal | Əsaslandırma |
|---|---|---|
| **Security (OWASP tətbiq)** | **78/100** | Injection (SQL/template/DOM) əsasən təmiz — 27 raw SQL hamısı bound, `|safe` 3 sabit, 524 DOM sink-də 1 real risk (F-01, LLM). CSP nonce-based, CSRF 1 əsaslı istisna, başlıqlar tam, XFF tək mənbə, open redirect 13/13 qorunur, WebSocket auth+rate-limit. Çıxılan: F-01 (−6), F-03 (−8; real məlumat klonunun parolu repo-dadır), F-02 (−3; fail-closed amma funksiya qırıq), upload MIME etibarı + formula (−5). |
| **Data Privacy** | **74/100** | Clarity kabinetdə söndürülüb, Sentry PII off, media ağ-siyahı + UUID yollar, korreksiya PDF-ləri qorunur, export-lar məqsədə uyğun. Çıxılan: AI-ya e-mail+ballar + limitsiz prompt saxlama (−10), klon DSN sızması (−10), avatar tenant-arası (−3), `.env` nümunə boşluğu (−3). |
| **Logging** | **86/100** | Sirr/OTP log-a düşmür, prod-da e-mail/telefon maskası, JSON + request-id, 18/18 yüksək riskli əməl audit olunur, audit append-only. Çıxılan: `ExamGradeEvent` audit ekranından kənar (−7), `INFO` səviyyəsində e-mail ünvanı (maska ilə) (−4), 2026-09-02 P2-5 (səssiz rate-limit söndürmə) **bağlıdır** — `core/rate_limit.py:75 ImproperlyConfigured` boot-da + `:124` fail-closed (`True, 60`); qalan çıxılma: `RATELIMIT_ENABLE=False` qlobal keçidi log-suzdur (−4). |
