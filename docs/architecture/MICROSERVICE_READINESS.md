# Mikroservisə çıxış hazırlığı — kontekst xəritəsi və e-jurnal planı

Sahib 2026-09-21: «Bundan sonra mikroservisə çıxmaq lazım gələrsə (məs. e-jurnal)
rahatlıqla çıxmaq alınsın.» Bu sənəd (1) bugünkü sərhədləri, (2) çıxarılma
üçün lazım olan şərtləri və (3) e-jurnal üçün konkret addımları verir.
Xəritə avtomatik çıxarılır: `python scripts/context_map.py`.

## 1. Bugünkü vəziyyət — modul monolit

| Sərhəd | Necə qorunur (CI qapısı) |
|---|---|
| App-lar arası import dövrü yoxdur (20 app, 0 dövr) | `scripts/module_deps.py --check` |
| App-lar arası import yalnız `apps/<app>/public.py` üzərindən | `scripts/public_api_boundaries.py --check` |
| Fayl həcmi ≤ 600 sətir (köhnə borc dondurulub, yalnız kiçilə bilər) | `scripts/check_module_size.py --check` |
| Jurnal/reyestr modellərinə birbaşa import artmır (ratchet) | `scripts/context_map.py --check` (2026-09-21) |
| CSP: inline `<script>`/`<style>` yoxdur, JS/CSS xarici fayldadır | CLAUDE.md qaydası + `grep` yoxlaması |

### Məhdud kontekstlər (bounded contexts)

| Kontekst | App / modullar | Qeyd |
|---|---|---|
| identity_tenant | `accounts`, `organizations` | istifadəçi, üzvlük, rol, təşkilat, struktur (OrgUnit), akademik dövr |
| academic_registry | `registrar` (27 modul: catalog, curriculum, plan_*, movements, transfer, transcript, guest_*, semester_*) | fənn kataloqu, tədris planı, tələbə akademik qeydi, qrup hərəkəti |
| **e_journal** | `registrar` (73 modul: attendance, gradebook*, lessons_log*, finals*, corrections*, exam_score_*, journal_*, kollokvium_*, analytics*) | dərs, qiymət, davamiyyət, yekun, düzəliş, bağlanma |
| schedule | `registrar` (11 modul: schedule_*, ical, lesson_rooms, calendar_context) | dərs cədvəli |
| syllabus | `syllabus` | sillabus dosyesi/versiya/təsdiq |
| workload | `workload` | kafedra tapşırığı, dərs yükü bölgüsü |
| exams | `exams`, `live_exam`, `appeals`, `trial_exams` | imtahan, canlı imtahan, apellyasiya |
| learning_tasks | `courses`, `assignments`, `labs`, `projects`, `task_submission_core` | tapşırıq/lab/layihə |
| platform | `notifications`, `audit`, `monitoring`, `ai_assistant`, `blog`, `contact`, `applications` | kəsişən xidmətlər |
| legacy_import | `legacy_import` | köhnə sistemdən köçürmə (müvəqqəti) |

`registrar` üç konteksti bir app-da saxlayır — bu, mikroservisə çıxışın əsas
maneəsidir və aşağıdakı planın 1-ci addımıdır.

### Verilənlər bazası əlaqələri (FK) — kim kimə bağlıdır

* `registrar` → `organizations.Organization` (hər model), `organizations.OrgUnit`
  (qrup), `organizations.AcademicPeriod`, `AUTH_USER_MODEL` (tələbə/müəllim).
* `syllabus` → `registrar.Subject`, `registrar.CourseOffering`, `registrar.Program`.
* `workload` → `registrar.Subject`.
* `exams` → registrar modellərinə FK **yoxdur**; uyğunluq/qiymət `registrar.public`
  funksiyaları ilə oxunur (`eligibility_rules`, `exam_score_*`).
* RLS: hər cədvəldə `organization_id` + Postgres siyasətləri (bax `organizations/0003_rls_policies`).

### Daxil olan (inbound) müqavilə istifadəsi

`apps/registrar/public.py`-dən 131 import sətri: `accounts` 48 fayl (profil
bölmələri: jurnal siyahısı, imtahan balı, cədvəl, təhvil, transkript, analitika),
`exams` 9, `workload` 2, `legacy_import` 1. Bundan əlavə 63 faylda
`apps.registrar.models`-ə **birbaşa** import var (18-i jurnal modellərinə —
`context_map.py` siyahılayır). Bunlar çıxışdan əvvəl `public` müqaviləsinə
köçürülməlidir; ratchet qapısı yenilərinin yaranmasını dayandırır.

## 2. Çıxarılma şərtləri (hər servis üçün)

1. **Tək giriş qapısı.** Kontekstə hər müraciət `public.py`-dəki funksiyalarla
   olur; funksiyalar model obyekti yox, sadə dəyər/dict qaytarır (bu gün
   qismən belədir — `journal_scope`, `eligibility_rules`, `plan_hours_for_offering`).
   Model qaytaran funksiyalar (`syllabus_for_offering_obj` kimi) çıxışdan əvvəl
   DTO-ya çevrilir.
2. **Şəxsiyyət ID ilə, FK ilə yox.** Servis öz bazasında `organization_id`,
   `user_id`, `group_id`, `period_id`-ni UUID/int kimi saxlayır; adlar/etiketlər
   üçün *reference data* hadisə ilə (outbox → broker) surətlənir və ya sinxron
   oxunur. `organizations` və `accounts` **identity_tenant** servisi olaraq
   qalır (JWT/session token verir, RLS `organization_id`-ni ötürür).
3. **URL prefiksi.** Hər kontekstin öz prefiksi var (`/jurnal/` → registrar,
   `/exams/`, `/sillabus/` …), nginx səviyyəsində yönləndirmək mümkündür;
   şəbəkə zonası qaydası da artıq nginx-dədir (`geo $ems_zone`, bax
   `docs/ops/PUBLIC_DOMAIN_ROLLOUT.md`).
4. **Frontend ayrılığı.** Səhifə CSS/JS-i app-ın öz `static/<app>/` qovluğunda,
   inline kod yoxdur (CSP) — statik fayllar servislə birgə daşınır.
5. **Hadisə sərhədi.** Kontekstlər arası yazı (məs. imtahan balının jurnala
   düşməsi) sinxron funksiya çağırışından **domen hadisəsinə** çevrilir
   (`exam.score.finalized` → jurnal). Bu gün `exams → registrar.public`
   çağırışı ilə olur; outbox cədvəli + Celery/redis stream keçid mərhələsidir.

## 3. E-jurnalın çıxarılması — addım-addım (strangler)

| Addım | İş | Nəticə | Risk |
|---|---|---|---|
| 0 (indi) | Qapılar: `context_map.py --check` (yeni birbaşa model importu yoxdur), `public_api_boundaries`, `module_deps` | sərhəd pisləşmir | yox |
| 1 | `apps/registrar` → `apps/registrar` (reyestr) + `apps/journal` (dərs/qiymət/yekun/düzəliş/bağlanma/kollokvium/analitika) + `apps/schedule`; modellər `journal_*` cədvəllərinə köçür (`db_table` saxlanaraq migrasiya sıfır-hərəkət) | eyni monolit, təmiz app sərhədi | 73 modul, ~2 gün; testlər import yolu ilə |
| 2 | `accounts`-dakı 18 birbaşa jurnal model importu `journal.public` DTO funksiyalarına çevrilir; `dashboard_staff_widgets`, `academic_summary`, `statistics_metrics` sorğuları `journal.public.read_*` olur | jurnal modelini yalnız `apps/journal` görür | orta |
| 3 | Jurnala GİRİŞ hadisələri: `enrollment.changed`, `offering.created`, `exam.score.finalized`, `period.closed` — outbox cədvəli + consumer (Celery) | jurnal yazıları asinxron | orta (idempotent consumer lazımdır) |
| 4 | `apps/journal` ayrı Django prosesi kimi (eyni repo, `config/settings/journal.py`, öz `urls`, öz DB sxemi `journal` və ya ayrı DB); nginx `/jurnal/` → journal upstream; sessiya/JWT `accounts`-dan | fiziki ayrılma | yüksək — RLS və `organization_id` ötürülməsi, media faylları (`ImmutableCorrectionEvidence`) |
| 5 | Reference data surəti (`Subject`, `OrgUnit`, `AcademicPeriod`, `User` adı) hadisə ilə; FK-lar UUID-ə çevrilir | müstəqil deploy | yüksək |

**Nəyi çıxarmamalı:** `organizations`/`accounts` (identity) ilk servis
olmamalıdır — hamı ondan asılıdır; o, «platforma» olaraq qalır.

## 4. Gündəlik qaydalar (bu gündən)

* Yeni kodda `from apps.registrar.models import …` **yazma** — `apps.registrar.public`
  (və `public_services`) funksiyasından istifadə et; yoxdursa oraya əlavə et.
* Bir modul bir kontekstə aid olsun: jurnal məntiqi `journal_*`/`gradebook*`/
  `lessons_log*` adları ilə, cədvəl `schedule_*`, reyestr `catalog_*`/`curriculum_*`.
* Template/JS/CSS — app-ın öz `static/` qovluğunda; inline yoxdur.
* Böyük fayl (>600) yaratma — bölün (`check_module_size.py`).

Xəritəni yenilə: `python scripts/context_map.py` (hesabat), `--check` (qapı),
`--update` (baseline sıxma — yalnız import sayı azalanda).
