# FAZA 23 — CodeQL xəbərdarlıqlarının bağlanması (PR #119)

Mənbə: `code-scanning/alerts?ref=refs/pull/119/merge` + analiz SARIF-i
(`analyses/1713691059`) — hər xəbərdarlığın DATA-AXIN yolu oxundu, təxminlə
düzəldilmədi.

## Düzəldilən 12 xəbərdarlıq

| # | Qayda | Yer | Düzəliş |
|---|-------|-----|---------|
| 1134 | `py/clear-text-logging-sensitive-data` (HIGH) | `core/rate_limit.py:119` | Spesifikasiya dəyəri (`RIM_PASSWORD_RESET_RATE_LIMIT`-dən gəlir) log-dan çıxarıldı; yalnız **scope adı** loglanır. |
| 1133 | `py/log-injection` | `apps/accounts/views/people/actions.py:105` | `safe_log_value(action)` |
| 1127 | `py/log-injection` | `apps/accounts/views/rim/actions.py:140` | `safe_log_value(action)` |
| 1117 | `py/log-injection` | `apps/accounts/views/profile/sections_api.py:335` | `safe_log_value(section)` |
| 1115 | `py/log-injection` | `core/cache.py:64` | `safe_log_value(key)` |
| 1116 | `py/log-injection` | `core/cache.py:327` | `safe_log_value(key)` |
| 1132 | `py/stack-trace-exposure` | `apps/accounts/views/legacy_review/actions.py:39` | `PermissionDenied` mətni klientə qaytarılmır: sabit tərcümə + `logger.warning(..., exc_info=True)`. |
| 1125, 1091 | `py/stack-trace-exposure` | `apps/registrar/correction_views.py:225, :203` | `str(exc)` fallback-i silindi (`ValidationError` HƏMİŞƏ `.messages` daşıyır → ölü kod idi); `_user_facing_validation_message()` + server tərəfdə `exc_info=True` log. |
| 1131, 1130 | `py/url-redirection` | `apps/accounts/views/exam_score_entry.py:86, :93` | Bax aşağıda. |
| 1128, 1129 | `py/url-redirection` | `apps/accounts/views/journal_close.py:86, :95` | Bax aşağıda. |

### Yeni ortaq helper — `core/logging_utils.py`

`safe_log_value(value, *, limit=120)`: idarəedici simvolları + `\r\n`-i silir və
dəyəri kəsir. Mövcud `core/logging_filters.SensitiveDataFilter` SİRLƏRİ
maskalayır, log-injection-ı yox — ona görə ayrı helper.

### Açıq-yönləndirmə: kök səbəb keyword arqument idi

`_resolve_next_url` / `_safe_same_origin_redirect_path` (`apps/accounts/views/_helpers/redirects.py`)
ONSUZ DA `url_has_allowed_host_and_scheme` ilə yoxlayırdı — yəni real open-redirect
YOX idi. Lakin çağırış `url=next_url` **keyword** formasında idi və CodeQL
sanitizer-i yalnız **pozisiya** arqumentində tanıyır (müq.: `apps/registrar/schedule_views.py::_redirect_after_schedule`
pozisiya işlədir və heç bir xəbərdarlıq vermir). Düzəliş:

1. helper-də arqument pozisiyaya keçirildi (bu, `exam_chance`, `kollokvium_windows`,
   `superadmin/exam_rooms` kimi DİGƏR çağıranların eyni tipli xəbərdarlıqlarını da bağlayır);
2. `exam_score_entry` və `journal_close` view-larında yoxlama redirect nöqtəsinin
   ÖZ funksiyasında da təkrarlanır (davranış dəyişmir — `fallback_next` `reverse()`-dəndir).

## Reqressiya testləri

- `core/tests/test_logging_utils.py` — `\n` ilə saxta log sətri uydurula bilmir, kəsilmə, idarəedici simvollar.
- `core/tests/test_rate_limit_config.py::test_failure_log_does_not_echo_the_spec_value`.
- `apps/accounts/tests/test_journal_close_section.py` + `test_exam_score_entry_section.py` — `next=//evil.example.com` rədd edilir, daxili `next` saxlanılır.
- `apps/accounts/tests/test_legacy_review_action_errors.py` — 403 cavabında `PermissionDenied` mətni yoxdur.
- `apps/registrar/tests/test_correction_error_payload.py` — `{'document': [...]}` quruluşu sızmır.

Nəticə: `core/tests/{test_logging_utils,test_rate_limit_config,test_cache}` +
`apps/accounts/tests/{test_legacy_review_action_errors,test_journal_close_section,test_exam_score_entry_section,test_rim_center,test_people_directory,test_profile_section_fragment}` +
`apps/registrar/tests/{test_correction_error_payload,test_correction_reversal}` — **hamısı yaşıl** (161 test).
Qapılar: black / isort / flake8 / `check_module_size.py --check` / `module_deps.py --check` / `check_i18n_catalogs.py` — yaşıl.

## TOXUNULMAYANLAR (pre-existing, bu PR-ın kodu deyil)

- `py/clear-text-logging-sensitive-data`: `scripts/prod_ops/exam_day_probe.py:35`, `scripts/prod_ops/exam_day_verify_login.py:38` (#1111, #1112)
- `py/redos`: `scripts/i18n_repair_corrupt_msgctxt.py:48` (#1114)
- `py/bad-tag-filter`: `apps/accounts/tests/test_profile_i18n_role_matrix.py:65` (#1113), `apps/accounts/tests/test_rim_center.py:747` (#1126) — test-lərdəki regex assertion-ları
- Digər köhnə `py/url-redirection` / `py/log-injection` xəbərdarlıqları (`apps/exams/**`, `apps/monitoring/**`, `apps/labs/**`) — helper-dəki pozisiya düzəlişi `apps/accounts` çağıranlarını bağlayır, `apps/exams/views/teacher/groups.py::_resolve_next_url` isə eyni keyword tələsini daşıyır və AYRI iş kimi qalır.

## Qeyd

`apps/registrar/tests/test_corrections_bridge.py::CorrectionMediaAccessTest::test_pdf_denied_to_unrelated_user_allowed_to_owner`
bu düzəlişlərdən ƏVVƏL də qırıqdır (`core.media_views._check_journal_correction_access`
mövcud deyil) — CodeQL işi ilə əlaqəsi yoxdur.

## Əlavə — PR #120 (dalğa 2, 2026-09-03)

CodeQL PR yoxlaması 22 «yeni» xəbərdarlıq göstərdi; Develop ref-i ilə müqayisədə **yalnız 2-si həqiqətən yenidir** (qalan 20-si diff böyük olduğu üçün köhnə alertlərin yenidən sayılmasıdır — Develop-da da açıqdır, ayrıca dilim).

| Alert | Qayda | Yer | Düzəliş |
|---|---|---|---|
| 1138 | `py/stack-trace-exposure` | `apps/registrar/catalog_actions.py:139` | geniş `except Exception` + `str(exc)` əvəzinə `except ValidationError` + `.messages` (yalnız öz doğrulama mətnimiz). |
| 1139 | `py/stack-trace-exposure` | `apps/accounts/views/student_intake.py:194` | `ValueError` kodu yalnız bilinən siyahıdan keçir, qalanı `invalid` + generik mesaj. |

