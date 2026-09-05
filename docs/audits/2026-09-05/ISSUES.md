# Tam QA auditi 2026-09-05 — mərkəzi problem siyahısı

Status: OPEN · IN-PROGRESS · FIXED (klonda yoxlanıb) · DEFERRED (sahib qərarı) · WONTFIX (qəsdən belədir)
Baza: QA klonu `emsarena_rehearsal_a0d170000901` (:8100), branch `audit/full-qa-2026-09-05`.
Sübut qovluğu: `~/EMSArena-backups/qa-2026-09-05/` (crawl JSON, ekran görüntüləri, sorğu profili).

## P0 — sistem / data / təhlükəsizlik
| # | Modul | Səhifə | Rol | Problem | Kök səbəb | Status |
|---|---|---|---|---|---|---|

## P1 — əsas funksiya sınıq
| # | Modul | Səhifə | Rol | Problem | Kök səbəb | Status |
|---|---|---|---|---|---|---|
| P1-2 | accounts/people | `people-students`, `people-teachers` → şəxs detalı | dekan, RİM, rektor, kafedra müdiri, koordinator | Ada klik → modal yalnız ad + «Profil səhifəsi» linki göstərir (İSTİFADƏÇİ ŞİKAYƏTİ). Backend `/accounts/people/person/<id>/` tam JSON qaytarır (üzvlüklər, akademik sətirlər, tədris, əlaqə, əməllər), amma JS render stub-dur. ESC bağlamır, fokus tələsi yoxdur, «Bağla» düyməsi modaldan kənarda (səhifənin sağ-yuxarısında) çıxır. | `apps/accounts/static/accounts/js/profile/people_directory.js:349-382` (`openDetail` yalnız h3 + link yaradır); `_people_directory.html:275-279` (`people__modal` — ems_ui `_drawer` komponenti işlədilmir); CSS `people__modal-close` yerləşməsi | FIXED (kod): `people_detail.js` (ems_ui drawer, tam kart, əməllər, i18n 4 dil), `serialize_memberships` vahidsiz üzvlükləri saxlayır; testlər `test_people_detail_drawer.py` (4). Canlı re-test restart-dan sonra |
| P1-1 | accounts (qabıq) | `role-assignment`, `publish-notification`, `superadmin-contact-messages` (bütün TAM-SƏHİFƏ açılan bölmələr) | superadmin, rektor, prorektor, RİM | Konsol: `window.EMSReady is not a function` / `Cannot read properties of undefined (reading 'on')` → bölmənin JS-i heç vaxt bağlanmır (rol təyinatı təsdiq modalı, bildiriş hədəf seçimi, «kimdən» seçici ölüdür). AJAX yolu ilə açılanda işləyir, ona görə əvvəlki auditlərdə görünməyib. | `templates/base.html`: bölmə `<script src>`-ləri `{% block content %}` (sətir 127) içindədir, `ems_ajax_init.js` isə sətir 156-da (content-dən SONRA) yüklənir → tam səhifə render-də `EMSReady`/`EMSDelegate` hələ təyin olunmayıb. | FIXED (kod): `static/js/ems_early.js` növbə stub-u <head>-də + `ems_ajax_init.js` növbəni boşaldır + 21 partial-da 32 `<script src>`-ə `defer`; test `apps/accounts/tests/test_shell_script_order.py` (3 qat). Canlı re-test restart-dan sonra |

## P2 — funksional / vacib UX
| # | Modul | Səhifə | Rol | Problem | Kök səbəb | Status |
|---|---|---|---|---|---|---|
| P2-1 | accounts (qabıq) | hər bölmə, 375 px | hamı | Tam səhifə naviqasiyasında (`?section=`) mobil görünüşdə sidebar AÇIQ gəlir və məzmunu tam örtür; istifadəçi əvvəl menyunu bağlamalıdır. AJAX swap-dan sonra `setSidebarCollapsed(true)` çağırılır, ilk yükləmədə yox. | `profile/ui.js:364` — ilkin vəziyyət yalnız localStorage-a baxırdı | FIXED (kod): `ui.js` init-də `isMobileViewport()` → `collapsed` (localStorage-a yazılmır). Canlı re-test restart-dan sonra |
| P2-2 | accounts | `analytics` | rektor, RİM, imtahan mərkəzi, TŞ, HR, superadmin | 2.8–3.7 s tam səhifə, AJAX 3.5–8.2 s (superadmin). Bilinən (2026-09-02 U-13), reqressiya deyil, amma hələ açıqdır. | aqreqasiya sorğuları, keş yoxdur | OPEN |
| P2-3 | organizations | `chair-profile` | kafedra müdiri | 425 SQL sorğusu / 368 ms (in-process profil) — N+1 | `query_profile.json` | OPEN |
| P2-4 | accounts | `academic-records` | kafedra müdiri, imtahan mərkəzi, RİM, rektor | Səhifə HTTP 60–85 ms-də gəlir, amma bölmənin JS-i sonradan XHR çağırır və brauzerdə 10–35 s gözləyir (chair_head: `net::ERR_TIMED_OUT`). | `academic_records.js` → records overview endpoint-ləri (ölçülür) | OPEN |
| P2-5 | exams | `exam-score-entry` | imtahan mərkəzi, rektor, superadmin | 460–466 SQL sorğusu (227 dublikat), brauzerdə 9.6 s | `query_profile.json` — N+1 | OPEN |
| P2-6 | applications | `applications` | hamı | 80 sorğu / 38 dublikat hər açılışda | N+1 (agent araşdırır) | OPEN |
| P2-8 | registrar (data) | `people-students`, `groups-registry`, struktur ağacı | hamı | Klonda 72 «Level …» qrupu (dil-kurs kohortları: «Level 2025-2026», «Level - FT Beginner 1» — 239 SAR) və 2 «Xaric olunanlar» psevdo-qrupu (31 SAR): tələbə statusu (xaric) qrup ADI ilə ifadə olunub; UI-da «Level 2025-2026» əsl akademik qrup kimi görünür, ağacda ixtisas altında sıralanır. | legacy köçürmə: mənbədə status-konteyner qruplar; `StudentMovement`/status sahəsinə çevrilməyib | OPEN (sahib qərarı: `legacy_repair_*` ilə statusa çevirmək / qrupları «xidməti» kimi işarələmək) |
| P2-7 | accounts | `org-members` (imtahan mərkəzi 9 s), `student-organization-management` (RİM 1.3 s / dekan 3.5 s), `my-exams` (3 s), `student-admission` (3–9 s) | müxtəlif | Yavaş bölmələr (brauzer ölçüsü, yük altında) | ölçülür | OPEN |

## P3 — cilalama
| # | Modul | Səhifə | Rol | Problem | Kök səbəb | Status |
|---|---|---|---|---|---|---|
| P3-1 | ai_assistant | `superadmin-ai` | superadmin | Konsol: `The specified value "5,00" cannot be parsed` — `<input type=number>` dəyəri AZ lokalında vergüllə render olunur → sahə boş görünür | şablon `{{ value }}` `USE_L10N` ilə `5,00`; `|unlocalize` və ya `stringformat` lazımdır | OPEN |
| P3-2 | accounts | dashboard, profil | hamı | Rol etiketi ingiliscə (`Teacher`, `Dean`…) — bilinən (PHASE21 U-2) | rol `display_name` klon datasında ingiliscə; UI tərcümə xəritəsi yoxdur | OPEN |
| P3-4 | accounts (qabıq) | bütün bölmələr | hamı | `<title>` həmişə «Profil - <istifadəçi adı> - Qərbi Kaspi Universiteti» — bölmə adı brauzer tab-ında/tarixçədə/ekran oxuyucuda görünmür (645 açılışın hamısında eyni). | `profile.html` `{% block title %}` bölmə başlığını daxil etmir; AJAX swap `document.title`-ı yeniləmir | FIXED (kod): title bölmə adı ilə başlayır; `ui.js` swap-da `document.title` yeniləyir (`data-title-suffix`); test `DocumentTitleTest` |
| P3-5 | accounts (qabıq) | `my-results`, `my-appeals`, `my-journal` | heyət rolları | Bölmə `allowed_sections`-da var (birbaşa URL ilə açılır, boş), amma menyuda yoxdur — capability ↔ sidebar uyğunsuzluğu; heyət üçün mənasız «Nəticələrim/Jurnalım» səhifəsi | `rbac.py` allowed_sections tələbə bölmələrini heyətə də verir | OPEN |
| P3-3 | accounts (test) | `apps/accounts/tests/test_people_directory.py::RowShapeTest` | — | sqlite-də 2 test HEAD-də də (adb7e07f) düşür (`faculty_name '' != 'Fakültə A'`); Postgres CI-də yaşıldırsa backend-asılı test, deyilsə real reqressiya | yoxlanılır | OPEN |

## Təhlükəsizlik matrisi (scripts/qa_live/security_matrix.py, 14 hesab × menyuda olmayan bütün bölmələr)
- **Bölmə səviyyəsində sızma YOXDUR.** 75 «şübhə»nin 55-i `qa.sec.hr`-dən idi: hesab əvvəlki agent dalğasında `password_change_required=True` vəziyyətində qalmışdı (first-login testinin qalığı) → fraqment 200 ilə «İlk giriş — parol təyini» səhifəsini qaytarırdı, bölmə məzmunu yox. Bayraq sıfırlandı, hesab yenidən normaldır.
- Qalan 20: `my-results` (11 rol), `my-appeals` (7), `my-journal` (5) — `allowed_sections`-da var, sidebar-da yoxdur; yalnız istifadəçinin ÖZ datası (heyət üçün boş). Sızma deyil, menyu↔capability uyğunsuzluğu (P3-5).
- Başlıqlar: CSP (`script-src 'self' 'nonce-…'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` var; HSTS dev-də yoxdur (prod nginx-də olmalıdır — yoxlanılmalı). Cookie: `sessionid` HttpOnly+Lax, `csrftoken` Lax; `Secure` dev-də bağlıdır (gözlənilən).

## Qeyd — yalançı-müsbətlər (süpürgə evristikası)
- `academic-records` «icazəniz yoxdur» — JSON i18n lüğətindəki mətn idi, real inkar deyil (AJAX 403 qəsdli: bölmə `AJAX_SAFE_SECTIONS`-da deyil).
- inline `<script>` sayları — `nonce` daşıyan və `application/json` blokları idi; evristika düzəldildi.
