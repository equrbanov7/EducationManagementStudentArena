# FAZA 27 — Uçdan-uca reqressiya axınları (QA klonu)

**Tarix:** 2026-09-02 · **Branch:** `audit/post-migration-qa-2026-09` · **Commit edilməyib**
**Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (:55433, owner DSN) — prod `emsarena_db` (:5432)
**heç vaxt açılmadı**. Metod: Django test client, in-process (`config.settings.staging_inspect`,
`ALLOWED_HOSTS=["*"]`, `force_login`) — real URL-lər, real middleware, real servis qatı.
Ayrıca pytest icraları: **öz** bazalarımda (`ems_reg_rls_9x4k`, `ems_reg_prov_7q2`) — tam dəst
işlədilmədi (sahibin qaydası).

Aktorlar: `qa.student`, `qa.teacher`, `qa.chair_head`, `qa.program_coordinator`, `qa.dean`,
`qa.exam_center`, `qa.ikt_rehber` (RİM), `qa.rector`, `qa.sec.*` (PHASE23 fixture-ləri) və
köçürülmüş `myedu.student.7944…7948`, `myedu.worker.527`.

---

## 0. Yekun

| | say |
|---|---:|
| İcra edilən axın | **27** |
| Tam **KEÇDİ** | **24** |
| **ŞƏRTLİ** (məhsul məntiqi işləyir, konfiqurasiya bloklayır) | **2** (axın 5, 6) |
| **ƏHATƏ UYĞUNSUZLUĞU** (axın işləyir, amma nəzərdə tutulan rol ilə YOX) | **1** (axın 8) |
| Yeni tapıntı | **9** (R-1 … R-9; 1 P0-namizəd, 3 P1, 3 P2, 2 P3/info) |

**Ən kritik tapıntı — R-8:** köçürülmüş **8 543 hesabın HEÇ BİRİ bu gün sistemə girə bilmir**
(parol «unusable», parol bərpası isə belə hesabları qəsdən süzür → e-poçt göndərilmir).
Girə bilən 25 hesabın hamısı audit agentlərinin özlərinin qurduğu QA hesablarıdır.

---

## 1. Dəlil cədvəli — axın · addım · aktor · status · nəticə

### F1 · Tələbə qəbulu → hesab → giriş

| # | addım | aktor | status / id | nəticə |
|---|---|---|---|---|
| 1 | `GET /accounts/student-intake/template/` | `qa.ikt_rehber` | 200, `.xlsx` 5 561 bayt | ✅ |
| 1n | eyni ünvan | tələbə | **403** | ✅ (mənfi) |
| 2 | `POST /accounts/student-intake/preview/` (2 sətirlik xlsx) | `qa.ikt_rehber` | 200 · `{total:2, create:2, skip:0, error:0}` | ✅ |
| 3 | `POST /accounts/student-intake/apply/` | `qa.ikt_rehber` | 200 · `st.qareg0001`, `st.qareg0002` yaradıldı, birdəfəlik parol yalnız cavabda | ✅ |
| 4 | `POST /accounts/login/telebe/` (birdəfəlik parol) | `st.qareg0001` | 302 → `/accounts/kabinet/` | ✅ |
| 5 | `GET /accounts/profile/` | `st.qareg0001` | 302 → `/accounts/set-password/` (ilk-giriş kilidi) | ✅ |
| 6 | `POST /accounts/set-password/` `action=send_otp` | `st.qareg0001` | 200, OTP e-poçtu göndərildi | ✅ |
| 7 | `POST …` `action=set_password` + kod | `st.qareg0001` | `password_change_required=False`, `email_verified=True` | ✅ |
| 8 | yeni parolla giriş | `st.qareg0001` | 302→302→`/accounts/profile/` 200 | ✅ |
| 9 | `dashboard` · `my-subjects` · `my-schedule` · `my-journal` | `st.qareg0001` | 4×200 | ✅ |

> Nəticə: **PHASE1 §4 boşluğu bağlanıb** — heyət siyahı yükləyir → hesab yaranır → tələbə
> nəzərdə tutulan (OTP-li) axınla parolunu təyin edir → kabinetə girir. Sonda hər iki hesab silindi.

### F2–F3 · Kafedra müdiri yük bölgüsü → müəllim

Tapşırıq ili qəsdən **2029/2030** seçildi ki, real data toxunulmasın.

| # | addım | aktor | status / id | nəticə |
|---|---|---|---|---|
| 2a | `POST /ders-yuku/tapsiriq/` | `qa.chair_head` | 200 · `created=true`, status `draft` | ✅ |
| 2b | `POST /ders-yuku/setir/yadda-saxla/` (mühazirə 30 s + seminar 15 s) | `qa.chair_head` | 200 · sətir yarandı, 2 balans xəbərdarlığı | ✅ |
| 2c | `GET /ders-yuku/muellimler/` | `qa.chair_head` | 200 · 50 müəllimlik hovuz, `qa.teacher` var | ✅ |
| 2d | `POST /ders-yuku/bolgu/` `activity=lecture, hours=30` | `qa.chair_head` | 200 · bölgü id | ✅ |
| 2d₂ | `POST /ders-yuku/bolgu/` `activity=seminar, hours=15` | `qa.chair_head` | 200 | ✅ |
| — | natamam bölgü ilə təsdiq cəhdi | `qa.chair_head` | **403 `workload.distribution_incomplete`** | ✅ (doğru davranış) |
| 2e | `POST /ders-yuku/bolgu/tesdiq/` | `qa.chair_head` | 200 · `distributed`, `notified=1`, `sync.skipped=1` (R-6) | ✅ |
| 3a | müəllim bildirişi | `qa.teacher` | 1→2 · «Dərs yükü təyin edildi … 45 saat» | ✅ |
| 3b | `GET /ders-yuku/mene/setirler/?year=2029/2030` | `qa.teacher` | 200 · 1 sətir, 45 saat | ✅ |
| 3c | bölmə `my-workload` | `qa.teacher` | 200 | ✅ |

### F4–F6 · Cədvəl: koordinator → müəllim → tələbə

`qa.chair_head` və `qa.program_coordinator` **artıq `scope_unit` daşıyır** (PHASE21-dəki fixture
boşluğu aradan qalxıb): kafedra «Proqramlaşdırma və informasiya təhlükəsizliyi», ixtisas
«Dizayn (Qrafik)». **Klonda dəyişiklik etməyə ehtiyac olmadı.**

| # | addım | aktor | status | nəticə |
|---|---|---|---|---|
| 4a | bölmə `schedule-manage` | `qa.program_coordinator` | 200 | ✅ |
| 4b | `POST /accounts/schedule-manage/check/` | `qa.program_coordinator` | 200 · `{ok:true, conflict:null}` | ✅ |
| 4c | `POST /accounts/schedule-manage/action/` `action=add` | `qa.program_coordinator` | 200 · slot (Çərşənbə 10:00–11:20, otaq «QA-REG 101») | ✅ |
| 4d | **CARİ dövrə** (2025/2026 Yaz) slot cəhdi | `qa.program_coordinator` | **400 · «Bu semestr bitib — cədvəl slotu əlavə edilə bilməz»** | ⚠️ **R-1** |
| 6b | bildiriş: müəllim + qrupun tələbələri | — | müəllim 3→4, tələbə 0→1 (tək toplu insert) | ✅ |
| 5 | `my-schedule` — müəllim | `qa.teacher` | 200, slot **görünmür** (cari dövr ≠ slotun dövrü) | ⚠️ **R-1** |
| 6a | `my-schedule` — tələbə | `myedu.student.7944` | 200, slot **görünmür** | ⚠️ **R-1** |
| 5′ | cari dövr müvəqqəti 2026/2027 Payıza keçirildikdə | `qa.teacher` | 200, **«QA-REG 101» göründü** | ✅ |
| 6a′ | eyni şərtdə | `myedu.student.7944` | 200, **göründü** | ✅ |

> Yəni **məhzul məntiqi tamdır**; blokator yalnız `AcademicPeriod.is_current` göstəricisidir (R-1).
> Dövr dərhal geri qaytarıldı (`2025/2026 Yaz`).

### F7–F8 · Sillabus: yaratma → təqdim → düzəliş → təsdiq

| # | addım | aktor | status | nəticə |
|---|---|---|---|---|
| 7a | `POST /accounts/profile/syllabus/action/` `action=create` | `qa.teacher` | 200 · v1.0 `draft` | ✅ |
| 7a′ | yaranan `chair_unit` | — | **`specialty` «Dizayn (Qrafik)»** — kafedra DEYİL | ⚠️ **R-2** |
| 7b | 8 bölmənin hamısı real `…/section/` ucundan dolduruldu | `qa.teacher` | tamamlanma **100 %** | ✅ |
| 7c | `action=submit` | `qa.teacher` | 200 · `submitted` | ✅ |
| 7d | təsdiqçiyə bildiriş | `qa.dean` | 0→1 «Sillabus təsdiqə göndərildi» | ✅ |
| 8a | `syllabus-review` növbəsi | `qa.dean` | 200, sillabus siyahıda | ✅ |
| 8a′ | eyni növbə | **`qa.chair_head`** | 200, **sillabus YOXDUR** | ❌ **R-2** |
| 8b | `decision` `action=revise` + səbəb + şərh | `qa.dean` | 200 · `revision` | ✅ |
| 8c | müəllifə bildiriş | `qa.teacher` | 4→5 | ✅ |
| 8d | müəllif yenidən göndərir | `qa.teacher` | 200 · `submitted` | ✅ |
| 8e | `action=approve` | `qa.dean` | 200 · **`approved` + kilidləndi** | ✅ |
| 8f | təsdiq bildirişi | `qa.teacher` | 5→6 «Sillabus təsdiqləndi» | ✅ |
| — | `qa.chair_head` eyni versiyaya qərar cəhdi | `qa.chair_head` | **404 «əhatənizdə deyil»** | ❌ **R-2** |

> Bu, sistemdə **ilk dəfə real məzmunlu** (8 bölmə, 16 həftə, 100 %) uçdan-uca sillabus dövrəsidir —
> PHASE23-ün 19b «müsbət nəzarəti» süni fixture üzərində idi (bax R-3).

### F9–F12 · Jurnal: dərs → davamiyyət → bal → tələbə görünüşü

| # | addım | aktor | status | nəticə |
|---|---|---|---|---|
| 9a | `GET /jurnal/<off>/` | `qa.teacher` | 200 | ✅ |
| 9b | `GET /jurnal/<off>/sillabus.json` → 1-ci həftənin mövzusu | `qa.teacher` | 200 · «Mövzu 1» | ✅ |
| 9c | `POST … action=add_lesson` (mövzu + standart saat + otaq) | `qa.teacher` | dərs yarandı: `topic='Mövzu 1'`, `room='QA-REG 305'` | ✅ |
| 11–12 | `action=save_marks` (`att__`/`score__`) — 1 qayıb + 2×8 bal | `qa.teacher` | 3 `LessonMark` | ✅ |
| 10 | tələbənin fənn detalı (`my-journal?period=…&subject=<enrollment>`) | `myedu.student.7944` | **mövzu ✓ · otaq ✓ · «QAYIB 2 saat» ✓** | ✅ |
| 10′ | başqa tələbənin adı / daxili sahə sızması | `myedu.student.7944` | sıfır sızma (`created_by`, `instructor_id`, digər tələbələr yoxdur) | ✅ |

> Qeyd: dərs elə həmin gün açılıbsa tələbəyə **«Bu günün dərs qeydləri sabah görünəcək»** yazılır —
> qəsdən gecikmədir. Dərsin tarixi 1 gün geri çəkiləndə mövzu/otaq/davamiyyət dərhal göründü.
> Ayrıca: klonda **0 `exams.ExamRoom`** var (R-5) — otaq seçicisi tam tenant boyu boşdur.

### F13–F15 · Kollokvium pəncərəsi

| # | addım | aktor | status | nəticə |
|---|---|---|---|---|
| 13a | `GET /accounts/kollokvium-windows/` | `qa.exam_center` | 200 | ✅ |
| 13b | `action=save_window` (K1, dünəndən +7 günə) | `qa.exam_center` | pəncərə yarandı, defolt **qeyri-aktiv** | ✅ |
| 13c | `action=toggle_window_active` | `qa.exam_center` | `is_active=true`; müəllimə bildiriş 8→9 | ✅ |
| 14 | `POST /jurnal/<off>/kollokvium/` `kscore__<K1>__<enr>=7` | `qa.teacher` | 3 `ComponentScore` = 7.00 | ✅ |
| 15a | pəncərə bağlandı | `qa.exam_center` | `is_active=false`, «bağlandı» bildirişi | ✅ |
| 15b | müəllim `3` yazmağa cəhd edir | `qa.teacher` | **ballar 7.00 olaraq qalır** + «pəncərə açıq deyil» xəbərdarlığı | ✅ |
| 20n | koordinatorun pəncərə yaratma cəhdi | `qa.program_coordinator` | **403** | ✅ |

### F16 · RİM sənədli düzəlişi

| # | addım | aktor | status | nəticə |
|---|---|---|---|---|
| 16a | `GET /jurnal/<off>/?correct=1` | `qa.ikt_rehber` | 200 · düzəliş rejimi | ✅ |
| 16b | `POST /jurnal/duzelis/<off>/tetbiq/` (`field=attendance`, `reason=official`, `note`, **PDF**) | `qa.ikt_rehber` | xana `absent → present`, `JournalCorrection` + sənəd yazıldı | ✅ |
| 16c | tələbəyə bildiriş | `myedu.student.7944` | 5→6 | ✅ |
| 16d | tələbə tərəfdə tarixçə nişanı | `myedu.student.7944` | «Bu qeydə rəsmi düzəliş edilib — nişana klikləyib tarixçəyə baxın» | ✅ |
| 7n/8n | `journal.correct`-siz müəllimin eyni ucları | `qa.teacher` | 404 (PHASE23 A-7/A-8 təkrarı) | ✅ |

### F17–F23 · Müraciətlər (ESD)

| # | addım | aktor | status | nəticə |
|---|---|---|---|---|
| 17 | tələbə «Dərs cədvəli» müraciəti | `myedu.student.7944` | 200 · MR-000006 → vahid **koordinator** | ✅ |
| 18 | `GET /muracietler/api/list/?tab=inbox` | `qa.program_coordinator` | 200, müraciət qutuda | ✅ |
| 19 | `mark_seen` → `forward` `target_unit=rim` | `qa.program_coordinator` | 200 · `forwarded` | ✅ |
| 20a | RİM qutusu | `qa.ikt_rehber` | 200, müraciət var | ✅ |
| 20b | `resolve` + səbəb | `qa.ikt_rehber` | 200 · `resolved` | ✅ |
| 20c | göndərənə bildiriş | `myedu.student.7944` | 9→10 | ✅ |
| 21a | tam tarixçə | `myedu.student.7944` | 4 hadisə: `submitted → seen → forwarded → resolved` | ✅ |
| 21b | `close` | `myedu.student.7944` | 200 · `closed` | ✅ |
| 22 | müəllim «Təqdimat» → kafedra | `qa.teacher` → `qa.chair_head` | vahid `kafedra`, müdir qutusunda, `resolve` 200, müəllimə bildiriş 13→14 | ✅ |
| 22′ | müəllim «Kadr məsələsi» | `qa.teacher` | vahid **`kadrlar`** (org əhatəsi) — kafedra müdiri GÖRMÜR | ✅ (marşrut kataloqu belədir, defekt deyil) |
| 23 | dekan «Texniki» → RİM | `qa.dean` → `qa.ikt_rehber` | vahid `rim`, RİM qutusunda, `resolve` 200 | ✅ |
| 24n | tələbə `tab=inbox` | `myedu.student.7944` | 200, **0 sətir** (yalnız öz müraciətləri) | ✅ |
| 24n | tələbə yad müraciəti `resolve` edir | `myedu.student.7944` | **404** | ✅ |

### F24 · İcazə mənfi testləri (PHASE23 §A yenidən yoxlaması)

| # | hal | aktor | əvvəl | indi | nəticə |
|---|---|---|---|---|---|
| A-27 | org rol/icazə matrisi | `qa.sec.dean_b` | **200 FAIL** | **302** | ✅ DÜZƏLİB |
| A-31e | yad bankı OXUMAQ | `qa.sec.exam_center_staff` | **200 FAIL** | **200** | ⚠️ **R-7** (PHASE23 §2-də qəsdən saxlanıb) |
| A-31f | yad bankda **toplu silmə** | `qa.sec.exam_center_staff` | **302 + sətir silindi** | **403, sətir sayı dəyişməz** | ✅ DÜZƏLİB |
| A-39 | imtahan mərkəzi səhifəsi | `qa.sec.student_b` | **200 FAIL** | **403** | ✅ DÜZƏLİB |
| A-46 | yad sillabusu klonlamaq | `qa.sec.teacher_b` | **200 + klon yarandı** | **404, sillabus sayı 4→4** | ✅ DÜZƏLİB |
| A-10 | tələbə imtahan yaradır | `qa.sec.student_b` | 403 | 403 | ✅ |
| A-20 | koordinator kollokvium pəncərəsi | `qa.program_coordinator` | 403 | 403 | ✅ |
| A-22 | kafedra müdiri jurnal bağlayır | `qa.chair_head` | 403 | 403 | ✅ |
| A-30 | kafedra müdiri apellyasiya idarəsi | `qa.chair_head` | 403 | 403 | ✅ |
| A-38 | müəllim `manage-roles` | `qa.teacher` | 302 | 302 | ✅ |
| A-44 | müəllim registrar konsolu | `qa.teacher` | 404 | 404 | ✅ |
| N-1 | müəllim `schedule-manage/action/` | `qa.teacher` | — | **403** | ✅ |
| N-1′ | müəllim `POST /jurnal/cedvel/` | `qa.teacher` | — | **403** | ✅ |
| N-1″ | müəllim `schedule-manage` bölməsi | `qa.teacher` | — | **403** | ✅ |
| N-2 | tələbə `student-intake/apply/` | tələbə | — | **403** | ✅ |
| N-3a | tələbə `workload-distribution` bölməsi | tələbə | — | **403** | ✅ |
| N-3b | tələbə `GET /ders-yuku/setirler/` | tələbə | — | 200, amma `{task:null, rows:[]}` (data sızmır) | ⚠️ zəif siqnal |

**5 FAIL-dan 4-ü bağlanıb; 1-i (A-31e) sənədləşdirilmiş qəsdli qərardır.**

### F25 · Tenant izolyasiyası (NOBYPASSRLS rolu `emsarena_ci_rls`)

```
apps/organizations/tests/test_rls.py  apps/registrar/tests/test_rls.py
apps/applications/tests/test_rls.py   apps/workload/tests/test_rls.py
→ 82 passed, 0 failed (38.5 s)
```
Baza: `ems_reg_rls_9x4k` @ :55432, `RLS_TRANSACTION_SCOPED=True`. **Regresiya yoxdur.**

### F26 · Provisioning testləri

`apps/accounts/tests/test_staged_portal_login.py` → **6 passed** (baza `ems_reg_prov_7q2`).
→ **ISSUES P2-7 bağlana bilər.**

### F27 · Performans — 4 keçmiş P1 səhifəsinin yenidən ölçülməsi

`CaptureQueriesContext` + `perf_counter`, isti keş, klon datası.

| səhifə | PHASE24 (sonra) | indi | dəyişiklik |
|---|---|---|---|
| `journal_detail` (555 yazılış × 226 dərs, `f82a7ec4…`) | 102 sorğu · 477 ms SQL · 7 202 ms wall | **104 sorğu · 309 ms SQL · 5 089 ms wall** (42.7 MB cavab) | ✅ regresiya yox |
| tələbə `my-results` (`myedu.student.200`, 59 yazılış) | 68 sorğu · 47 ms · 96 ms | **72 sorğu · 69 ms · 130 ms** | ✅ (+4 sorğu — FAZA 22 kabinet qabığı) |
| tələbə `overall-academic` | 64 sorğu · 48 ms · 104 ms | **64 sorğu · 68 ms · 135 ms** | ✅ eyni |
| heyət `groups` bölməsi | 61 sorğu · 46 ms · 90 ms | **63 sorğu · 68 ms · 113 ms** | ✅ |

> `journal_detail`-in 5 saniyəlik wall-u sorğudan deyil, **42.7 MB HTML render-indən** gəlir
> (SQL cəmi 309 ms). Növbəti optimallaşdırma addımı səhifələmə/virtuallaşdırmadır, sorğu deyil.

---

## 2. Yeni tapıntılar

| # | ağırlıq | tapıntı | sübut | təklif |
|---|---|---|---|---|
| **R-1** | **P1** | `AcademicPeriod.is_current` = **2025/2026 Yaz**, bitmə tarixi **2026-06-30** — yəni bu gün (2026-09-02) *keçmiş* semestrdir. `my-schedule` YALNIZ cari dövrü göstərir (`page_contexts.schedule_context:374`), `schedule_manage` isə bitmiş dövrə yazmağı **rədd edir** (`schedule_manage.period_window_error`). Nəticə: koordinatorun yarada bildiyi hər slot görünməz, görünən hər dövrə isə slot yazıla bilmir — **cədvəl axını bu gün uçdan-uca işləmir**. | axın 4d (400 «Bu semestr bitib») + 5/6 (slot görünmür) + 5′/6′ (dövr düzəldiləndə **görünür**) | tədris ili açılanda `is_current`-i **2026/2027 Payıza** keçirin; paralel olaraq `my-schedule`-ə dövr seçicisi əlavə edin (bax R-4) |
| **R-2** | **P1** | Müəllim UI-dan yaradılan sillabusun `chair_unit`-i `offering.group.parent` təyin olunur (`views/syllabus/api.py:158`). Köçürülmüş strukturda **766 qrupun 766-sının valideyni `specialty`-dir; heç bir kafedranın qrup övladı yoxdur**. Yəni `chair_unit` HEÇ VAXT kafedra olmur → kafedra əhatəli `chair_head` sillabusu nə növbədə görür, nə də qərar verə bilir (404). Faktiki təsdiqçi **fakültə dekanıdır**. | 8a (dean 200 / chair_head sillabusu görmür) + `decision` 404 + `SELECT parent__unit_type … GROUP BY` → `specialty: 766` | ya `chair_unit`-i fənn/kafedra bağından həll edin (məs. `Subject`→kafedra), ya da `covers_unit` qaydasını «ixtisasın kafedrası» ilə genişləndirin. **Sahib qərarı tələb edir: sillabusu kafedra müdiri, yoxsa dekan təsdiqləyir?** |
| **R-3** | **P2** | PHASE23-ün fixture sillabusları `completion_percent=100` daşıyır, amma **0 `SyllabusSection` sətri var**. İlk real keçid faizi 100 → 12-yə salır və müəllif «göndər»i itirir. Yəni **19b «müsbət nəzarəti» heç nə sübut etmirdi** və `İstehlak…` sillabusu heç vaxt real təqdim edilməmişdi. | `SyllabusSection.objects.filter(version=…)` → 0; `revise`-dən sonra `completion 100→12` | fixture-ləri `complete_section_data()` ilə qurun (mən elə etdim); FAZA 27-nin F7–F8 dövrəsi indi əsl müsbət nəzarətdir |
| **R-4** | **P2** | `my-journal`-da tədris ili + semestr seçicisi **var**, `my-schedule`-də **yoxdur** — buna görə R-1 kosmetik deyil, ölümcül olur. | bölmə HTML-ləri (`sjx-term` seçicisi yalnız jurnalda) | `my-schedule`-ə eyni `?period=` müqaviləsini verin |
| **R-5** | **P3** | Klonda **0 `exams.ExamRoom`** sətri var → dərs modalının otaq siyahısı bütün tenant boyu boşdur; ISSUES P1-3 («tələbə jurnalında otaq görünsün») yalnız otaqlar seed olunandan sonra istifadə edilə bilər. Otaq yaradıldıqda axın **işlədi**. | `ExamRoom.objects.count() == 0`; QA otağı yaradıldıqdan sonra `room='QA-REG 305'` tələbə görünüşündə çıxdı | otaq reyestrini köçürmə/seed dilimi kimi planlaşdırın (mənbədə `rooms` cədvəli **var**) |
| **R-6** | info | `confirm_distribution` açılış sinxronunda `sync.skipped=1` verdi: sətrin semestri (2025/2026 Yaz) tapşırığın tədris ili (2029/2030) ilə uyğun gəlmir. Qəsdli qorumadır, defekt deyil. | axın 2e cavabı | sənədləşdirin: sətrin semestri tapşırığın ilinə aid olmalıdır |
| **R-7** | P2 | İmtahan mərkəzi işçisi **hələ də** yad müəllimin sual bankını oxuya bilir (200). PHASE23 §2 bunu qəsdən saxlayıb, amma auditin gözləntisi 403 idi. | A-31e | sahib qərarı: ya oxu əhatəsini daraldın, ya da ISSUES-də WONTFIX kimi bağlayın |
| **R-8** | **P0 namizədi** | **Köçürülmüş 8 543 hesabın parolu «unusable»-dir** (`!`-prefiksli). `CustomPasswordResetForm` Django-nun `get_users()`-una söykənir, o isə `has_usable_password()` olmayanları **süzür** → `/accounts/password-reset/` sükutla «done» səhifəsinə aparır, **e-poçt göndərmir**. Yəni köçürülmüş istifadəçi nə parolla girə bilir, nə də özü bərpa edə bilir. Girə bilən 25 hesabın hamısı audit agentlərinin yaratdığıdır. | `myedu.student.5` → reset POST 302, **outbox 0**; `myedu.worker.19` → **outbox 0**; `SELECT … password NOT LIKE '!%'` → 25 | canlıya çıxışdan ƏVVƏL toplu parol buraxılışı yolu lazımdır (RİM mərkəzində «parol sıfırla» tək-tək işləyir; toplu CSV yoxdur). Alternativ: `get_users()`-u override edib `access_state=active` + doğrulanmış e-poçtu olan hesablara da icazə vermək |
| **R-9** | **P1** | `legacy_repair_missing_accounts` ilə yaradılan **100 tələbənin `StudentAcademicRecord`-u yoxdur** (7 816 hesab, 7 703 SAR, fərq 113 = 100 bərpa + 13 staged). Qrupu/proqramı/kurikulumu olmayan tələbə boş kabinet görür və PHASE21 §4.3-dəki «qrupsuz tələbə» kohortudur. | `students_without_sar=113`, `of_them_active=100`, `of_them_staged=13` | bərpa əmrinə SAR mərhələsi əlavə edin (mənbədə `students.group_id`/`speciality_id` var) |

---

## 3. Klonda edilən müvəqqəti dəyişikliklər (hamısı geri qaytarıldı)

| dəyişiklik | səbəb | bərpa |
|---|---|---|
| `AcademicPeriod.is_current` → 2026/2027 Payız | R-1-i sübut/təkzib etmək | ✅ `2025/2026 Yaz`-a qaytarıldı (`finally` bloku) |
| 5 tələbədə `password_change_required=False` | bölmə GET-lərinin 302-yə düşməməsi | ✅ `True` + `email_verified=False` bərpa olundu |
| `myedu.worker.527` üçün eyni (yalnız ölçmə anında) | perf ölçməsi | ✅ dərhal bərpa olundu |
| PHASE23 fixture sillabusu `submitted → revision` | F8-in ilk cəhdi | ✅ `submitted`-ə qaytarıldı |

## 4. Təmizlik — yaradılan `QA-REG*` obyektlərin hamısı silindi

```
syllabus                     16 sətir (1 sillabus, 1 versiya, 10 bölmə, 4 rəy)
kollokvium window             1
schedule slot                 1
offering kaskadı             17 (1 açılış, 5 yazılış, 1 dərs, 3 LessonMark, 3 ComponentScore,
                                 1 AssessmentScheme, 3 AssessmentComponent)
subject QAREG-SUB             1
ExamRoom «QA-REG 305»         1
workload task 2029/2030       4 (1 tapşırıq, 1 sətir, 2 bölgü)
workload task 2025/2026       1 (boş — bu agentin təsadüfi yaratdığı)
applications MR-000003…9     23 (7 müraciət, 15 hadisə, 1 izləmə)
st.qareg0001 / st.qareg0002   5 (2 istifadəçi, 2 profil, 1 OTP) + SAR + üzvlük
bildirişlər                 268
```

**Qalıq: 0.** Yoxlama (təmizlikdən sonra): `QAREG` fənn 0 · `QAREG` açılış 0 · `st.qareg*` 0 ·
`QA-REG` müraciət 0 · `QA-REG` bildiriş 0 · 21:55-dən sonra yaranan bildiriş 0.
Klonun yekun ölçüləri PHASE31 hesabatındakı cədvəldədir və işə başlamazdan əvvəlki dəyərlərlə üst-üstə düşür.
