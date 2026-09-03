# Dizayn Mərhələ 6 — ekran 21 «Keçilmiş dərslər» + ekran 10 «Tələbə kabineti»

**Tarix:** 2026-09-03 · **Budaq:** `audit/post-migration-qa-2026-09` (commit YOX — sahibin tələbi)
**Mənbə:** `docs/design/HANDOFF_FULL_PLAN.md` §2/10, §2/21 · `docs/design/handoff_full/README.md` §5 (10, 21), §6.5, §8, §10.1
**Prototiplər:** `design/21 Muellim - Kecilmish dersler.dc.html`, `design/10 Telebe kabineti.dc.html`
**Əhatə:** 21 (YENİ bölmə) · 10 (mövcud bölmələrin fərqləri) · README §8/2 jurnal siyasəti
**Ekran 11 (Müraciətlər)** artıq bitmişdi — burada yalnız **bir parametr** əlavə olundu (aşağı, §4).

---

## 0. Bir baxışda

| İş | Nəticə |
| --- | --- |
| Ekran 21 `lessons-log` bölməsi | **YENİ** — oxu-only, model dəyişikliyi YOX, migration YOX |
| Ekran 10 fərqləri | müəllim adı · APPROVED sillabus keçidi · qiymətləndirmə çəkiləri · transkript sorğusu CTA · «bu gün / növbəti dərslər» |
| README §8/2 (sillabussuz jurnal bloklanır) | **siyasət açarı** `journal.require_approved_syllabus`, **default SÖNDÜRÜLÜ** |
| Migration | **YOX** (siyasət mövcud `Organization.settings` JSON-undadır) |
| Testlər | 26 yeni test (17 + 9), fokuslu reqressiya **102/102** |
| Qapılar | black / isort / flake8 / modul ölçüsü / modul sərhədi / worker-atomic / `makemigrations --check` — **hamısı ✅** |
| i18n | **97 yeni msgid, 8 kontekst** → `DESIGN_STAGE6_MSGIDS.txt`; `.po` fayllarına **TOXUNULMADI** |

---

## 1. Ekran 21 — `lessons-log` «Keçilmiş dərslər»

Kabinet bölməsidir (`/accounts/profile/?section=lessons-log`): sol sidebar qalır,
panel sağda açılır; `<h1>` şablonda yazılmır (qabıq verir — canlıda `h1` sayı = 1).

### 1.1 Fayllar

| Fayl | Rol |
| --- | --- |
| `apps/registrar/lessons_log.py` (**yeni**) | domen servisi: əhatə, dövr, qeyd statusu, KPI aqreqatları, sətirlər, sillabus əhatəsi, CSV sətirləri |
| `apps/registrar/lessons_log_views.py` (**yeni**) | `registrar:lessons_log_csv` — CSV ixracı (eyni əhatə qaydası) |
| `apps/accounts/views/profile/_sections/lessons_log.py` (**yeni**) | GLUE: kontekst yığımı (KPI kartları, filtr sahələri, gün qruplaşdırması) |
| `apps/accounts/templates/accounts/profile/sections/_lessons_log.html` (+ `_lessons_log_actions.html`) | panel + başlıq əməlləri |
| `apps/accounts/static/accounts/css/profile/sections/lessons_log.css` | **yalnız düzüm** — kart/cədvəl/badge/KPI/filtr `ems_ui` qatındandır |

Qeydiyyat (5 yer, `test_section_registry_consistency` kilidləyir): `sections_api.SECTION_PARTIALS`
+ `AJAX_SAFE_SECTIONS` · `profile.html` `data-ajax-sections` · `_section_dispatch.html` ·
`_sections/labels.py` · `_sidebar_university.html`. Kontekst dispatch-i
`context_builder/_teaching_office.py` cədvəlinə düşdü (aktiv bölmə deyilsə HEÇ BİR sorğu işləmir).

### 1.2 Rol / əhatə (README §8/8)

* **Müəllim** — bölməni görür (`rbac_university_sections`), sorğu
  `instructor=user` VƏ YA `instructor IS NULL AND offering.instructor=user` ilə daralır.
  «Müəllim» filtri ONA AÇILMIR və CSV-də `ll_teacher` parametri **403** verir
  (səssiz «öz datası»na düşmək əvəzinə: parametr qəsdən yazılıb).
* **Nəzarətçi** — `journal.roster` (mövcud açar, YENİ açar yaradılmadı) →
  `rbac_sections.can_supervise_lessons`. Struktur alt-ağacı + «Müəllim» filtri.
  **Fail-closed:** açar var, amma `scope_unit` əhatəsi yoxdursa nəzarət görünüşü
  AÇILMIR (aşağıda canlı sübut: `qa.chair_head`).
* **Tələbə** — bölmə YOXDUR; fraqment endpoint-i **403** qaytarır.

### 1.3 Məzmun (prototipə uyğun)

* **5 KPI:** Keçilmiş dərs · Auditoriya saatı · Orta iştirak · Jurnalı boş dərs · Gec yazılan qeyd.
* **Qeyd statusu 3 vəziyyət** (`core/ui/status_catalog.py::journal_note`, hazır idi):
  `Vaxtında yazılıb` / `Gec yazılıb` / `Jurnal boşdur`.
  «Gec» tərifi: dərsin İLK xanası dərs tarixindən **48 saat** sonra yazılıb
  (`LessonMark.created_at` ↔ `Lesson.date`) — **model dəyişikliyi tələb etmir**.
* **Gün-gün qruplaşdırma** (tarix + həftə günü + gün cəmi), sətirdə saat/müəllim/fənn+qrup/
  mövzu/tip/iştirak/saat/jurnal qeydi; otaq+korpus `Lesson.room`-dan.
* **Sillabus mövzu əhatəsi** zolağı — açılış üzrə `covered / planned` + faiz.
  Planlaşdırılan mövzular **YALNIZ APPROVED versiyanın** `week` bölməsindən gəlir (§8/9);
  təsdiqlənmiş sillabus yoxdursa «Təsdiqlənmiş sillabus yoxdur» yazılır.
* **Sürətli əməllər** mövcud jurnal endpoint-lərini təkrar istifadə edir
  («Jurnalı aç» / «Dərs əlavə et»). Siyasət açıq və sillabus yoxdursa
  «Dərs əlavə et» **kilid + səbəb + sillabusa CTA** ilə əvəz olunur (§8/2).
* **Filtrlər** (draft ≠ applied, `EMSFilterBar`): axtarış · dövr · fənn · qrup ·
  dərs tipi · semestr · (nəzarətçidə) müəllim. **CSV ixracı** cari filtrlə.
* Sətir tavanı 90 (dizaynla eyni) + «cəmi N qeyd var» lenti.

### 1.4 Sorğu büdcəsi

Dövr üzrə **4 sorğu** (aqreqat sətirlər · davamiyyət aqreqatı · səhifə sətirləri ·
səhifənin xana aqreqatı) + filtr seçiciləri. Sillabus əhatəsi ən çox dərsi olan
**4 açılışla** məhdudlaşır (`COVERAGE_CAP`). Aqreqat rəqəmlər **SAXLANILMIR** (§8/13).

> Test `test_query_count_does_not_grow_with_the_number_of_lessons` **invariantı**
> yoxlayır: sətir sayı 2 → 14 olanda sorğu sayı ARTMIR. Mütləq rəqəm qabığın özündən
> (sidebar + badge + icazə) asılıdır və sabit deyil; ona görə hədd əvəzinə invariant kilidləndi.

---

## 2. README §8/2 — «jurnal təsdiqlənmiş sillabus olmadan bloklanır»

**Kodda yox idi.** Mövcud davranış (`apps/registrar/syllabus_notice.py`, 2026-08) yalnız
XƏBƏRDARLIQ banneri idi: sillabusu olmayan müəllim dərsi sərbəst mətn mövzusu ilə açırdı.

**Qaydanı qeyd-şərtsiz qoşmaq mümkün deyil:** köçürülmüş bazada açılışların böyük
əksəriyyətinin təsdiqlənmiş sillabusu YOXDUR — universitet cari semestrdə jurnal yaza bilməzdi.

**Həll — org siyasət açarı** (`apps/registrar/journal_policy.py`, **yeni**):

```
Organization.settings = {"journal": {"require_approved_syllabus": true}}
```

* **DEFAULT SÖNDÜRÜLÜ** (`DEFAULT_REQUIRE_APPROVED_SYLLABUS = False`) — köçürülmüş data
  qorunur, davranış dəyişmir.
* **AÇIQ** olduqda:
  * servis qapısı — `gradebook.create_lesson` → `SyllabusGateError(reason_code="no_approved_syllabus")`
    (yəni seed/komanda/ayrı çağıran da keçə bilmir);
  * HTTP — jurnalın `action=add_lesson` POST-u **403 + gövdədə səbəb kodu**;
  * görünüş — `can_edit=False` → jurnal **read-only**, üstündə kilid banneri + «Sillabusa keç» CTA
    (`_jd_syllabus_notice.html`-in sonuna əlavə blok).
* Saxlama yeri mövcud JSON sahəsidir → **migration YOXDUR**; naxış `apps/syllabus/policy.py` ilə eynidir.
* Modul sərhədi: `apps.organizations` import EDİLMİR — yalnız ötürülən obyektin
  `settings` atributu oxunur (ördək tipi).

Hər iki rejim testlə və canlı klonda yoxlandı (§5).

---

## 3. Ekran 10 — tələbə kabinetinin fərqləri

Mövcud bölmələr TAM idi; prototipdən ÇATIŞMAYANLAR əlavə olundu (heç bir mövcud test sınmadı).

| Fərq | Harada | Qeyd |
| --- | --- | --- |
| **Müəllim adı** fənn kartında | `_my_subjects.html` + `services.get_student_cabinet_data` | `offering__instructor` `select_related`-a əlavə olundu (N+1 yox) |
| **«Sillabus (təsdiqlənmiş)» keçidi** | `_my_subjects.html` + `cabinet_policy.approved_syllabus_offerings` | **YALNIZ APPROVED** (§8/9); TOPLU (tək sorğu) — sətir-sətir yoxlama N+1 idi |
| **Qiymətləndirmə strukturu** 10/10/30/50 = 100 | `_my_subjects.html` + `cabinet_policy.assessment_weights_view` | §8/4; dəyər **kodda hardcode DEYİL** — `apps.syllabus.policy` org səviyyəsindən oxuyur |
| **Transkript sorğusu CTA** | `_my_results.html` + `context_builder/_stage4._transcript_request_cta` | §10.1 default `request`; **sənəd linki YOX**, yalnız Müraciətlər panelinə keçid (3 iş günü) |
| **«Bu gün / növbəti dərslər»** | `dashboard_widgets.student_today` + yeni `upcoming_slots` | bu gün dərs yoxdursa kart boş qalmır — həftənin növbəti dərsli günü (ƏLAVƏ SORĞU YOX) |
| Davamiyyət / qayıb limiti / komponentlər | **artıq var idi** | dəyişdirilmədi |

**⚠️ Tapıntı — «Transkript» bölməsi tələbədə ONSUZ DA BAĞLIDIR.**
`rbac.py:399` bayraq bağlı ikən `my-transcript`-i `allowed_sections`-a ƏLAVƏ ETMİR
(sidebar + fraqment + birbaşa URL — hamısı bağlı). Yəni bölmənin daxilindəki
«PDF yüklə» düyməsi heç vaxt göstərilmirdi. Ona görə:

* CTA **`my-results`** bölməsinə qoyuldu (tələbənin GÖRDÜYÜ səth);
* `_my_transcript.html` yenə də siyasətə görə budaqlanır (`sec.self_service`) — sahib
  `download`-a keçəndə bölmə açılan kimi düzgün davranır, əlavə iş lazım deyil.

`STUDENT_TRANSCRIPT_SELF_SERVICE=False` semantikası **dəyişmədi**; PDF endpoint-i
əvvəlki kimi 404 verir (`test_transcript_pdf` yaşıl).

---

## 4. Ekran 11 — bir parametr (öncədən seçilmiş müraciət növü)

`?section=applications&new_kind=<kod>` — panel «Yeni müraciət» dialoqunu həmin növ
seçilmiş halda açır. Dəyişiklik minimaldır və **backend-ə toxunmur**:

* `_applications.html` → `data-new-kind="{{ request.GET.new_kind }}"`;
* `applications_dialogs.js::openCreate(mode, app, presetKind)` — üçüncü opsional arqument;
* `applications.js` → kataloq gəldikdən SONRA `openPresetKind(root)`; **naməlum kod səssizcə atılır**
  (server tərəfdə növ yenə fail-closed yoxlanılır).

Transkript CTA-sı məhz bu parametri işlədir.

---

## 5. Canlı yoxlama (QA klonu, `http://127.0.0.1:8100`)

Klon miqrasiya olundu (`staging_inspect.sh migrate`). Yeni miqrasiya YOXDUR.

### 5.1 Müəllim — `qa.teacher`
* «Keçilmiş dərslər» bölməsi sidebar-da göründü; panel 200.
* Jurnaldan **dərs əlavə edildi** (`action=add_lesson`, 2027-07-05, seminar,
  «DS6 QA — sintaksis təhlili») → **logda göründü**, statusu `Jurnal boşdur`
  (xana yazılmayıb — doğru), «Sillabus mövzu əhatəsi» zolağı çıxdı.
* CSV: `Yığın və növbə strukturları` var, başqa müəllimin mövzusu **YOXDUR**;
  `ll_teacher` ilə sorğu → **403 `teacher_filter_forbidden`**.

### 5.2 Köçürülmüş müəllim — `myedu.worker.459` (klonda parol quruldu)
10 açılış, 3–36 dərs. Dövr `2022-09-15 — 2023-01-31`: sətirlər göründü,
statuslar **«Gec yazılıb»** (köçürmə xanaları dərsdən çox sonra yazıb — gözlənilən),
əhatə zolağında «Təsdiqlənmiş sillabus yoxdur».

### 5.3 Nəzarətçi
| Hesab | Nəticə |
| --- | --- |
| `qa.ikt_rehber` (RİM) | nəzarət görünüşü **AÇIQ** — «Kafedranın müəllimləri…» mətni, «Müəllim» filtri, sətirlər |
| `qa.chair_head` | nəzarət görünüşü **BAĞLI** — rol sətrində `journal.roster` YOXDUR (`has_structure_access=False`) → müəllim görünüşünə düşür (**fail-closed, doğru**) |
| `qa.student` | fraqment **403** `forbidden_or_unknown_section` |

> **Klon qeydi:** `qa.chair_head` rolunda `journal.roster` yoxdur, çünki klonun rol
> sətirləri `sync_journal_permissions` komandasından ƏVVƏLdir. Prod-da kafedra müdirində
> açar var (`default_roles_university.py`). Klonda nəzarət görünüşünü sınamaq üçün
> həmin komandanı işlətmək lazımdır — **kod problemi deyil**.

### 5.4 Siyasət açarı — canlı, HƏR İKİ rejim
| Rejim | POST `add_lesson` | Jurnal GET |
| --- | --- | --- |
| SÖNDÜRÜLÜ (default) | **200** — dərs yaradıldı | redaktə açıq |
| AÇIQ | **403 `no_approved_syllabus`** | 200, **kilid banneri** + «Yeni dərs əlavə et» YOXDUR (read-only) |

Yoxlamadan sonra klon **default vəziyyətə qaytarıldı** (`settings["journal"]` silindi).

### 5.5 Tələbə kabineti — `myedu.student.5925` (39 yazılış)
* `dashboard`: «Bu gün / növbəti dərslər» ✔, «Müraciətlər» ✔
* `my-subjects`: «Qiymətləndirmə strukturu» (Davamiyyət 10 · Sərbəst iş 10 · Cari 30 · Yekun 50 · Cəmi 100) ✔;
  «Sillabus (təsdiqlənmiş)» **YOXDUR** — klonda təsdiqlənmiş sillabus yoxdur (§8/9 üzrə doğru)
* `my-results`: «Transkript sorğusu göndər» ✔ + «qeyri-rəsmi baxış nüsxəsidir» qeydi ✔ + `new_kind=transkript` ✔
* `applications`: `data-new-kind` çəngəli ✔
* `qa.student` (akademik qeydi yoxdur) → boş vəziyyətlər, xəta yox.

### 5.6 Responsiv / konsol
* **1280×1500:** content header + 5 KPI + filtr paneli + boş vəziyyət düzgün; sidebar solda qalır.
* **375×812:** `scrollWidth == clientWidth == 375` (üfüqi sürüşmə **0**), `h1` sayı **1**,
  KPI **1 sütun**, cədvəl öz konteynerində sürüşür.
* `performance.getEntriesByType('resource')` üzrə **≥400 statuslu sorğu = 0**.
  (Konsol tarixçəsindəki 405/404 yazıları paylaşılan brauzer tabındakı ƏVVƏLKİ
  naviqasiyalardandır — cari səhifə yükündə deyil.)

---

## 6. Testlər

`apps/accounts/tests/test_lessons_log_section.py` — **17 test**
(rol qapısı 200/403 · əhatə · `ll_teacher` filtrinin müəllimə təsir etməməsi + CSV 403 ·
CSV məzmunu · `on_time`/`late`/`empty` riyaziyyatı · KPI aqreqatları · əhatə faizi ·
siyasətin hər iki rejimi: servis istisnası, HTTP 403 + səbəb kodu, read-only görünüş ·
N+1 invariantı).

`apps/accounts/tests/test_student_cabinet_stage6.py` — **9 test**
(transkript siyasətinin hər iki dəyəri · «transkript» növünün kataloqda olması ·
kilidli çəkilər 10/10/30/50=100 · toplu sillabus yoxlamasının boş halı ·
`upcoming_slots` · şablon müqavilələri).

**Fokuslu reqressiya:** 102/102 keçdi (`test_cabinet_ui`, `test_transcript`,
`test_transcript_pdf`, `test_dashboard_section`, `test_sidebar_role_matrix`,
`test_section_registry_consistency`, `test_journal_syllabus_bridge` daxil).

**Geniş süpürgə** (`apps/registrar/tests` + `apps/accounts/tests`): **2 815 keçdi, 1 skip, 1 uğursuz.**
Uğursuz olan `test_account_archive_postgres.py::test_archiving_opens_the_registrar_guard_without_opening_the_login`
— **bu işə aid DEYİL**: xam SQL INSERT-i Mərhələ 2/3-ün əlavə etdiyi
`registrar_studentacademicrecord.admission_exam_type` NOT NULL sütununu göndərmir
(`63007671` commit-i). Düzəlişi həmin sahənin sahibinə aiddir.

---

## 7. Qapılar

| Qapı | Nəticə |
| --- | --- |
| `black` / `isort` / `flake8` (yalnız bu işin faylları) | ✅ təmiz |
| `scripts/check_module_size.py --check` | ✅ (`registrar/public.py` 663 → **594**; iki köməkçi `registrar/cabinet_policy.py`-yə çıxarıldı) |
| `scripts/module_deps.py --check` | ✅ yeni dövr yoxdur — `registrar` `organizations`-u statik import ETMİR |
| `scripts/check_worker_atomic_coverage.py --check` | ✅ 46/46 |
| `makemigrations --check` (sqlite) | ✅ «No changes detected» |
| `scripts/check_i18n_catalogs.py` | `.po`-ya toxunulmadı; yeni msgid-lər ayrıca fayldadır (§8) |

---

## 8. i18n

`docs/audits/2026-09-02/DESIGN_STAGE6_MSGIDS.txt` — **97 msgid, 8 kontekst**
(HEAD ilə fərqdən çıxarılıb, yəni yalnız bu mərhələnin yazıları):

| Kontekst | Say |
| --- | --- |
| `accounts.lessons_log` | 54 |
| `registrar.lessons_log` | 25 |
| `profile.subjects` | 7 |
| `profile.results` | 3 |
| `profile.transcript` | 3 |
| `registrar.journal_policy` | 3 |
| `profile.sidebar` | 1 (Keçilmiş dərslər) |
| `accounts.dashboard` | 1 (Bu gün / növbəti dərslər) |

`.po` fayllarına **TOXUNULMADI** (paralel i18n agenti doldurur).
Həftə günü adları modul səviyyəsində DEYİL, funksiya içində hesablanır
(layihə yaddaşı: modul-səviyyəli `pgettext` i18n qapısı üçün görünməzdir).

---

## 9. Sahib qərarı gözləyənlər / təxirə salınanlar

1. **`journal.require_approved_syllabus` nə vaxt açılsın.** Hazırda SÖNDÜRÜLÜ.
   Açılmazdan əvvəl cari semestrin açılışları üçün sillabus əhatəsi ≈100% olmalıdır —
   əks halda müəllimlər jurnal yaza bilməyəcək. Ekran 21-in «Sillabus mövzu əhatəsi»
   zolağı bu hazırlığı ölçmək üçün istifadə oluna bilər.
2. **Nəzarət görünüşünün açarı** `journal.roster` seçildi (yeni açar yaratmadıq).
   Sahib istəsə ayrıca `journal.lessons_watch` açarı verilə bilər — dəyişiklik
   `rbac_sections.py`-də bir sətirdir.
3. **`qa.chair_head` klonda `journal.roster` daşımır** — klonda
   `manage.py sync_journal_permissions` işlədilməlidir (prod rol şablonunda açar var).
4. **Semestr filtri** artıq YALNIZ istənildikdə tətbiq olunur (canlı QA-da tapıldı:
   «Seçilmiş aralıq» dövründə gizli semestr filtri istifadəçiyə boş ekran verirdi).
   «Semestr» dövrü isə onsuz da semestrin tarixlərindən doğur.
5. **QA klonunda qalan artefaktlar:** `qa.teacher`-in `MYEDU-L1001` açılışında
   2 sınaq dərsi (Yay 2027 — gələcək dövr, zərərsiz) və `myedu.worker.459` /
   `myedu.student.5925` hesablarına qoyulmuş `QaAudit2026!` parolu. **Yalnız klonda.**
