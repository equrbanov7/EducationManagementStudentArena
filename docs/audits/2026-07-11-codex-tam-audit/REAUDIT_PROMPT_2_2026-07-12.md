# Codex üçün 2-ci yenidən-audit tapşırığı — sequence dalğasının verifikasiyası + tapdığın buqları ÖZÜN DÜZƏLT

**Bu sənəd Codex-ə verilir.** Məqsəd: 1-ci re-auditdən (REAUDIT_REPORT_AZ_2026-07-11.md)
sonra icra edilən **tövsiyə olunan sequence dalğasını** müstəqil təsdiqləmək,
regresiya axtarmaq, performansı yoxlamaq və — ƏSAS FƏRQ — **tapdığın hər real
buqu özün düzəldib, test + CI ilə doğrulayıb push etmək**. Yalnız hesabat yazıb
dayanma; aşağıdakı C bölməsindəki qaydalarla düzəlişi özün tamamla.

- Baxılacaq diapazon: `0699b8db..8ec54317` (branch: **Develop**, tip: `8ec54317`)
- Əvvəlki hesabat: [REAUDIT_REPORT_AZ_2026-07-11.md](./REAUDIT_REPORT_AZ_2026-07-11.md)
- İcra statusu (iddia): [INFRA_HANDOFF.md](./INFRA_HANDOFF.md) §9
- Prinsip: **iddiaya inanma, koddan və icradan yoxla.** Hər iddia üçün bypass
  ssenarisi qur; keçirsə buq say və DÜZƏLT.

---

## A. Bu dalğada edildiyi iddia olunanlar — TƏSDİQLƏ və SINDIRMAĞA ÇALIŞ

Hər sətir üçün: (1) kodu oxu, (2) testləri işə sal, (3) bypass cəhdi et.
Bypass keçirsə → C bölməsi ilə özün düzəlt.

| # | İddia | Commit | Verifikasiya nöqtəsi | Bypass cəhdi |
|---|---|---|---|---|
| 1 | Appeal 3-günlük pəncərə UX: bağlananda read-only nəticə/appeal baxışı + xəbərdarlıq; servisdə defense-in-depth invariant | `ea020c6e` | `apps/appeals/views/student/endpoints.py::_render_appeal_window_closed`, `services/creation.py::create_appeal`, `test_window.py` | `finished_at` 4 gün əvvəl olan attempt üçün appeal_create-ə BİRBAŞA POST göndər (formu bypass et) → ValidationError olmalı; səhifə read-only olmalı, form render olunmamalı |
| 2 | Grade-event append-only ledger + orijinal grader identity | `25eaeb9b` (mig exams `0048`, org `0022` RLS) | `ExamGradeEvent`, `graded_by`, `_attempt_views.py` grading POST, appeals `_is_conflicted_reviewer` | Qiyməti 2 dəfə dəyiş → 2 ledger sətri (old/new düzgün); ledger sətrini UPDATE/DELETE et → mümkün olmamalı (RLS/append-only); İLK grader appeal-i öz-özünə review edə bilməməli |
| 3 | Tam delivered snapshot v2 + snapshot-only render: nəticə və appeal səhifələri dondurulmuş mətn/variant/media/düzgün-cavabdan render olunur | `f28dec9e`, `e42c38ed` | `services/question_snapshot.py` (`build_question_snapshot`, `delivered_question_render`), `views/student/results.py`, `appeals/.../endpoints.py`, `exam_result.html`, `appeal_create.html` | Submit-dən SONRA sual mətnini/variant mətnini/düzgün variantı dəyiş → nəticə səhifəsi + appeal səhifəsi KÖHNƏ (çatdırılan) görünüşü göstərməli; snapshotsuz köhnə attempt canlıya düşməli (500 yox) |
| 4 | Autosave OCC: stale tab yazısı 409 ilə rədd olunur | `2e4ee612` (mig `0049`) | `_helpers.py::autosave_occ_conflict_response/bump_autosave_revision`, `draft.js` 409 handler, `take_exam.html` hidden field | Köhnə `autosave_revision` ilə autosave POST → 409 `{conflict, server_revision}`; revision-suz POST → köhnə davranış (yazır); 409-dan sonra client revision yeniləyib davam edir |
| 5 | Access-code bazada Fernet-at-rest (müəllim-görünən sirr, hash YOX) | `ee75309d` (mig `0050`) | `services/access_code_crypto.py`, `domain/fields.py::EncryptedAccessCodeField`, `test_access_code_encryption.py` | DB-dən raw SELECT → şifr-mətn olmalı (açıq kod YOX); Python-da `exam.access_code` xam olmalı; köhnə (miqrasiyasız) xam sətir oxunmalı; giriş axışı (kod yoxlama) işləməli |
| 6 | Atomik publish/unpublish + publish qapısı + audit log | `a8e8de41` | `services/lifecycle.py`, `views/teacher/exams/actions.py`, `teacher_exam_detail.html` `desired_state`, `test_lifecycle.py` | Sualsız imtahana publish POST → qaralama qalmalı + xəta toast; eyni `desired_state=1`-i 2 dəfə göndər (stale tab) → deaktiv OLMAMALI; publish/unpublish → `AuditLog` sətri |
| 7 | Server-authoritative per-question timer: ilk göstərilmə serverdə, müddəti keçmiş yazı atılır | `8ec54317` (mig `0051`) | `services/question_timer.py`, `views/student/question_timer.py` (question-seen endpoint), save loop skip (`attempts.py`), `timers.js` server sync, `test_question_timer.py` | question-seen-i başqa istifadəçinin attempt-inə/başqa imtahanın sualına POST et → 404; started_at-ı köhnəldib (limit+grace keçmiş) cavab POST et → yazı DÜŞMƏLİ (selected_options boş); limitsiz sual/siqnalsız köhnə client → bloklanmamalı |
| 8 | Əvvəlki re-audit düzəlişləri yerindədir: cross-FK M2M RLS (`org 0020`), audit attribution lock (`org 0021`), active-attempt guard, lab clamp, CF real-ip, DOM textContent, CI fail-closed | `0699b8db` | müvafiq migration/test-lər | Regresiya: bu dalğanın dəyişiklikləri bunları pozmayıb? Xüsusilə `attempts.py` refaktorları guard-ları saxlayıb? |

## B. Regresiya + performans süpürgəsi

1. **Tam suite**: postgres konteyneri ilə `-m postgres` RLS testləri DAXİL
   (sqlite onları görünməz keçir — bilinən tələ) + tam sqlite run.
2. **Yeni migrasiyalar** (`exams 0048–0051`, `organizations 0020–0022`) təmiz
   postgres-də sıfırdan `migrate` ilə keçməli; `makemigrations --check` boş.
3. **Performans**: `exam_result` səhifəsində snapshot render N+1 gətirmirmi
   (`delivered_question_render` prefetch olunmuş `question__options` istifadə
   etməlidir); autosave yolunda əlavə sorğu sayı; `question-seen` endpoint-i
   attempt başına 1 kiçik UPDATE-dən artıq iş görməməlidir.
4. **Təhlükəsizlik**: yeni endpoint (`question-seen`) auth/tenant/attempt-owner
   guard-ları; OCC 409 cavabında məlumat sızıntısı yoxdur; access-code açarı
   `SECRET_KEY`-dən törəyir — log-larda xam kod görünmür.

## C. TAPDIĞIN BUQLARI ÖZÜN DÜZƏLT — qaydalar

Hesabatla dayanma. Hər təsdiqlənmiş buq üçün bu dövrəni tam icra et:

1. **Reproduksiya testi yaz** (əvvəl qırmızı) — buqu sübut edən test.
2. **Düzəlt** — minimal, mövcud pattern-lərə uyğun (şərti-UPDATE, snapshot
   fallback, `_helpers` extraksiyası və s.).
3. **Geriyə-uyğunluğu qoru** — bunlar QIRILA BİLMƏZ: snapshotsuz köhnə
   attempt-lər; base-revision-suz autosave; xam (miqrasiyasız) access-code
   sətirləri; question-seen siqnalı göndərməyən köhnə client; parametrsiz
   toggle formaları.
4. **Bütün gate-lər**: `black`/`isort`/`flake8`; `python
   scripts/check_module_size.py --check` (YENİ fayl 600 sətri keçməməli —
   keçirsə helper-ləri çıxar); `manage.py makemigrations --check`; tam pytest
   (sqlite) + postgres konteynerində `-m postgres`.
5. **Commit + push**: hər buq ayrıca commit — `audit-fix(EXAM-XXX): <izah>`;
   Develop-a push; **CI Pipeline tam yaşıl olana qədər bitmiş sayma**
   (yalnız tip commit-in run-u sayılır; cancelled = köhnə push, xəta deyil).
6. **Toxunma — yalnız hesabatda qeyd et**: PIN one-use/rotation (məhsul
   qərarı — finals reconnect-i poza bilər); draft→review→approved iş axını
   (yeni məhsul funksiyası); prod DB rol provisioning / backup / load test
   (operator işi, INFRA_HANDOFF-da).

### Bilinən tələlər (vaxt itirmə)

- RLS testləri sqlite-da GÖRÜNMƏZ keçir → real postgres konteyneri işlət.
- CI `check --fail-level WARNING` superuser postgres-də W011 verir →
  testlərdə `EMS_DB_ROLE_ENFORCE=off` artıq qoyulub, söndürmə.
- Django messages toast-ları `data-auto-hide="3000"` — browser yoxlamasında
  mesajı redirect CAVABININ HTML-ində axtar, gecikmiş DOM-da yox.
- Audit trigger (org 0019/0021) content-UPDATE-i bloklayır, FK→NULL-a icazə
  verir — user/org silmə testlərində bunu nəzərə al.
- macOS-da `" 2"` suffiksli duplikat migration faylları qrafı sındırır — görsən sil.
- Ardıcıl sürətli push-lar bir-birinin CI-ını cancel edir — batch-lə, tək push.

## D. Hesabat formatı

`REAUDIT_REPORT_2_AZ_<tarix>.md` bu qovluqda:

- Hər A-bəndi üçün: TƏSDİQ / BUQ TAPILDI→DÜZƏLDİLDİ (commit hash) / AÇIQ (səbəb).
- Yeni tapıntılar: ID + severity + reproduksiya + düzəliş commit-i.
- Performans ölçmələri (sorğu sayları, əvvəl/sonra).
- Toxunulmayan məhsul-qərarı bəndləri ayrıca siyahıda.
- Yekun qiymət: imtahan modulu /100, layihə /100, GO/NO-GO.
