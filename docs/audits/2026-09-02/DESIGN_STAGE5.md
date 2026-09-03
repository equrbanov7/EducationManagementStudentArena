# Dizayn Mərhələ 5 — Sillabus (ekran 18, 19, 20)

**Tarix:** 2026-09-03 · **Branch:** `audit/post-migration-qa-2026-09` (commit YOXDUR) ·
**Mənbə:** `docs/design/handoff_full/README.md` §5 (18–20), §6.4, §6.5, §8, §10 +
`docs/design/HANDOFF_FULL_PLAN.md` §2/18–20 + `docs/audits/2026-09-02/PHASE6_CHAIR_APPROVAL.md`

> **Plan nə deyirdi:** «Üçü də TAM — restyle». **Ölçmə nə göstərdi:** UI həqiqətən
> tamdır (5 KPI, filtrlər, cədvəl⇄kart, 10 bölmə, autosave, diff, audit timeline,
> qərar dialoqları — hamısı mövcuddur). Boşluqlar **qəbul qaydalarında** idi:
> §8/4 (çəkilər), §8/11 (kontakt saatları), §10.3 (avto-MAJOR), §10.4 (SLA
> siyasəti) və §6.5 (jurnal körpüsü). Bu iş məhz onları bağladı; `.syl-*` → `ems-*`
> kosmetik köçürməsi QƏSDƏN edilmədi (aşağıda «Edilməyənlər»).

---

## 1. Boşluq analizi — dizayn ↔ mövcud kod

### 18 · Müəllim — Sillabuslar (`syllabus-list`)

| Dizayn elementi | Vəziyyət | Nəticə |
| --- | --- | --- |
| 5 klik olunan KPI (`aria-pressed`) | ✅ `section.py::_kpis` + `_syllabus_list.html` | toxunulmadı |
| Filtrlər: axtarış (debounce) / il / semestr / kafedra | ✅ `section.py` + `syllabus_list.js` | toxunulmadı |
| 4 sıralama + Cədvəl⇄Kart açarı | ✅ `SORT_LABELS`, `_list_table/_list_cards` | toxunulmadı |
| 7 status + rəng tokenləri + «növbəti addım» mətnləri | ✅ `apps/syllabus/constants.py` | toxunulmadı |
| Əməllər: yarat (yalnız təyin olunmuş fənn) / davam / kiçik-böyük versiya / geri çağır | ✅ `rows.py::ACTIONS_BY_STATUS` | toxunulmadı |
| «Sillabussuz fənn» sətirləri + boş vəziyyət | ✅ `build_missing_row`, `_syllabus_list.html` | toxunulmadı |
| **«SLA-nı keçib» KPI-ı** | ❌ **yox idi** | **əlavə edildi** |
| **SLA həddi siyasətdən** | ❌ hardcode (`LATE_DAYS=10`, `WARN_DAYS=5`) | **`apps/syllabus/policy.py`-a köçürüldü** |
| «Geri çağır» səbəbi ≥20 simvol (§8/6) | ⚠️ 15 idi | **20-yə qaldırıldı** (server + JS + şablon) |

### 19 · Sillabus redaktoru (`syllabus-editor`)

| Dizayn elementi | Vəziyyət | Nəticə |
| --- | --- | --- |
| 10 bölmə, dizayn `id`-ləri və sırası | ✅ `constants.SectionKey` | toxunulmadı |
| Addım naviqasiyası 3 vəziyyət, bölmə tamamlanma faizi | ✅ `completion.py` + `editor.py` | toxunulmadı |
| **Bir mövzu — növ üzrə saat** (§8/0) | ✅ **artıq belədir**: `week.rows[].{lecture,seminar,lab}` + `SyllabusVersion.plan_hours` | **sxem dəyişmədi → data migrasiyası lazım gəlmədi** |
| Sərbəst iş: yalnız `1×10` / `2×5` / `10×1`, `3×5` izahlı disabled kart | ✅ `SELFWORK_OPTIONS` / `SELFWORK_DISALLOWED` + save-time qapı | toxunulmadı |
| **Kilidli çəkilər 10/10/50 + müəllim 30-u bölür, cəm 100** | ⚠️ **yalnız UI-da** (slayder). Domen qatı `assess`-i HƏMİŞƏ «ödənilib» sayırdı; HTTP səthi ixtiyari JSON qəbul edirdi | **domen qaydası + server kilidi əlavə edildi** |
| **Kontakt saatı ↔ tədris planı (§8/11) təsdiqi bloklayır** | ⚠️ qayda var idi, **mənbə yox idi**: `api.py::_do_create` `plan_hours={}` ötürürdü → qayda heç vaxt işə düşmürdü | **`registrar.plan_hours` mənbəyi qoşuldu** |
| autosave + `revision` optimistik kilid → 409 müqayisə | ✅ `save_section` + `SectionConflict` + `saveState` bannerləri | **HTTP 409 testi əlavə edildi** (əvvəl yalnız servis testi vardı) |
| Təsdiq düyməsi tamamlanana qədər disabled | ✅ `can_submit` + `transition.incomplete` | toxunulmadı |
| **Versiya təsnifatı: struktur dəyişikliyi ⇒ MAJOR (§10.3)** | ❌ **yox idi** — müəllimin «kiçik» seçimi olduğu kimi qalırdı | **`services/versioning.py` + `submit` qapısı** |

### 20 · Kafedra müdiri — Sillabus təsdiqi (`syllabus-review`)

| Dizayn elementi | Vəziyyət | Nəticə |
| --- | --- | --- |
| Növbə + 4 KPI + filtrlər + sıralama | ✅ `review.py` | toxunulmadı |
| Bölmə-bölmə şərh, ümumi rəy | ✅ `SyllabusReview.section_comments` + `review_api._section_comments` | toxunulmadı |
| Diff kartı (əvvəlki təsdiqlənmiş ↔ yeni) | ✅ `queries.version_diff` + `review_panel.build_diffs` | toxunulmadı |
| Audit timeline | ✅ `version_timeline` + `build_timeline` | toxunulmadı |
| 3 qərar, səbəb ≥20 simvol | ✅ `MIN_DECISION_REASON = 20` | toxunulmadı |
| Təsdiq versiyanı kilidləyir, köhnəsi ARXİVLƏNİR | ✅ `workflow.approve` + `_archive_superseded` + DB constraint | toxunulmadı |
| Bildirişlər | ✅ `services/notifications.py` | toxunulmadı |
| `role=noscope` boş vəziyyəti (§8/8) | ✅ `coverage.has_review_scope` (fail-closed) | toxunulmadı |
| Dekan oxu/rəy, qərar YOX (PHASE6) | ✅ `_CHAIR_LEVEL_TRANSITIONS` + `read_only` qeydi | toxunulmadı |
| **«N gün gözləyir» SLA badge-i siyasətdən** | ⚠️ hardcode 10/5 | **siyasətə bağlandı + mətnə hədd yazıldı** |

### Jurnal körpüsü (§6.5 birinci sətir)

| Qayda | Vəziyyət | Nəticə |
| --- | --- | --- |
| «Təsdiqlənmiş sillabus → jurnal strukturu yaranır» | ❌ **POZULMUŞDU**: `journal_extras.lesson_topic_choices` mövzuları **LMS `courses.CourseTopic`-dən** oxuyurdu, sillabusdan yox | **düzəldildi** |
| Dərs növləri növ-üzrə saatdan gəlir (§8/0) | ❌ yox idi | **`kinds` əlavə edildi** (mövzu hansı növlərə aiddir) |
| Asılılıq istiqaməti | ✅ `registrar → syllabus` onsuz da mövcuddur (`syllabus_views.py`, `public.py`); əks kənar açılmadı (`scripts/module_deps.py` ✅) | — |

---

## 2. Edilən dəyişikliklər

### 2.1 Siyasət — `apps/syllabus/policy.py` (YENİ, 118 sətir)

README §10-un dörd açıq qərarının **yeganə oxu nöqtəsi**. Saxlama: mövcud
`Organization.settings` JSON (`"syllabus"` açarı) — **yeni cədvəl və migration YOX**.

| Açar | Default | Mənbə |
| --- | --- | --- |
| `sla_days` | **5** | §10.4 (sahib qərarı) |
| `escalation_days` | **10** | §10.4 — «10 gündən çox» eskalasiya həddi; SLA-dan kiçik ola bilmir (normallaşdırılır) |
| `second_approval_enabled` | **False** | §10.2 — dekanın ikinci təsdiqi SÖNDÜRÜLÜ |
| `assessment` | `{attendance:10, selfwork:10, final:50}` | §8/4; `flex` **saxlanılmır**, `100 − kilidli cəm` kimi hesablanır |

Pozuq dəyər (mətn, mənfi) susdurulmuş şəkildə default-a düşür — səth heç vaxt
istisna atmır.

### 2.2 §8/4 — qiymətləndirmə çəkiləri domen qaydası oldu

* `completion._check_assess`: `midterm + project == flex`, hər ikisi ≥ 0.
  `assess` artıq **avtomatik «ödənilib» sayılmır** — bölünməmiş bal cəmi 100-dən
  aşağı salır, ona görə təsdiqə göndərməni bloklayır.
* `drafts.save_section`: `assess` bölməsi üçün **server kilidi** —
  birləşdirilmiş nəticə siyasətə uyğun deyilsə `assess.split_mismatch` (403).
  Yoxlama BİRLƏŞMİŞ dəyər üzərindədir, yəni kliyent tək açar göndərəndə digəri
  sətirdən gəlir.
* `drafts.default_assess_data`: yeni qaralama **etibarlı bölgü ilə** açılır
  (15/15), 0/0 ilə yox.
* `drafts._inherited_data`: köçürülmüş (legacy) `{"midterm":0,"project":0}`
  bölgüsü yeni versiyaya **irs alınmır**, başlanğıc bölgüsü ilə əvəzlənir —
  **yalnız bu iki açar**; `note`, `exam_questions` və s. toxunulmur (R-1 data
  itkisi dərsi).
* **Migration `0003_normalize_open_assessment_split`** (data-only): artıq AÇIQ
  (draft/revision) qaralamalarda bölünməmiş bölgünü normallaşdırır.
  `approved`/`archived`/`submitted`/`review`/`rejected` **toxunulmur** (§8/1).

### 2.3 §8/11 — kontakt saatlarının mənbəyi

* **`apps/registrar/plan_hours.py` (YENİ)** — `plan_hours_for_subject/offering`:
  yalnız `Curriculum.status == APPROVED` sətirlərindən oxuyur; ixtisas
  (`Program.specialty_unit` ↔ qrupun valideyni) uyğun gələn plana üstünlük
  verir, tapılmasa ən yeni qəbul ilinə düşür. Sıfır saatlı növlər **atılır** ki,
  yalnız real bölgü məhdudiyyət yaratsın. Tapılmasa `{}` → «plan yoxdursa
  məhdudiyyət də yoxdur».
* `api.py::_do_create` artıq `plan_hours=plan_hours_for_offering(offering)` və
  `program=program_for_offering(offering)` ötürür (əvvəl hər ikisi boş idi).
* **`services.set_plan_hours`** — plan sonradan bağlananda bölgünü redaktəyə
  AÇIQ versiyaya yazır və tamamlanmanı yenidən hesablayır; kilidli versiyaya
  **heç vaxt** yazmır (§8/1).

### 2.4 §10.3 — avtomatik MAJOR

**`apps/syllabus/services/versioning.py` (YENİ)**

* `STRUCTURAL_SECTIONS = (week, assess, self)` — jurnal strukturunun mənbəyi.
* `structural_changes(version)` — baza: `source_version`, yoxdursa dosyenin
  təsdiqlənmiş versiyası. Baza yoxdursa qayda **şamil edilmir** (ilk versiya).
* `escalate_if_structural` — müəllim MINOR seçib, amma struktur dəyişibsə
  versiya `v(N+1).0`-a **yenidən nömrələnir**, `change_kind=major` olur və audit
  jurnalına `version.structural_change_requires_major` səbəbi ilə yazılır.
* Çağırış yeri **`workflow.submit`** — yəni qayda HTTP səthindən asılı deyil.
  Nəticə `version.escalated_sections`-da qayıdır və API cavabındakı mesaja
  əlavə olunur (istifadəçi səssiz öyrənmir).

### 2.5 §10.4 — SLA siyasətə bağlandı

* `review_rows`: `thresholds(organization)`, `wait_text(days, sla=…)`,
  `wait_tone(days, warn=…, late=…)`, `build_queue_row(..., warn, late)`;
  sətirdə yeni `sla_breached` bayrağı. Mətn artıq **rəqəmi də göstərir**
  («7 gündür gözləyir — SLA 5 gün») — a11y §7: status yalnız rənglə verilmir.
* `review.py`: KPI-lar `thresholds(organization)` ilə hesablanır; bölmə
  kontekstinə `policy: {sla_days, escalation_days}` əlavə olundu.
* `section.py` (18-ci ekran): **6-cı KPI kartı «SLA-nı keçib»** + `status=sla`
  virtual filtri (`overdue_syllabus_ids`). «sla» REAL status olmadığı üçün
  domen sorğusuna ötürülmür.
* `LATE_DAYS`/`WARN_DAYS` sabitləri **yalnız fallback** kimi qaldı.

### 2.6 §6.5 — jurnal körpüsü

**`apps/registrar/journal_topics.py` (YENİ; `journal_extras.py`-dan ayrıldı ki,
o fayl 600 sətirlik büdcədə qalsın — davranış dəyişmədi, adlar yenə oradan da
import olunur.)**

* `syllabus_topic_rows(offering)` — **yalnız APPROVED** versiyanın `week`
  bölməsindən `[{title, kinds}]`; mövzu bir dəfə, `kinds` isə saatı olan
  növlərdir.
* `lesson_topic_choices` mənbə sırası: **təsdiqlənmiş sillabus → LMS kursu →
  boş** (şablon sərbəst mətnə keçir).
* `lesson_topic_meta` sətirləri `kinds`, `kinds_attr`, `covered_kinds` daşıyır;
  `_jd_lesson_modal.html` opsiyaya `data-kinds` və görünən nişan yazır
  («Mövzu 3 · mühazirə, seminar, laboratoriya»).

---

## 3. Testlər

| Fayl | Say | Nəyi kilidləyir |
| --- | --- | --- |
| `apps/syllabus/tests/test_policy_and_versioning.py` (YENİ) | 18 | siyasət default/override/fallback, `flex` törəməsi, `assess` server kilidi (tam və qismən yük), bölünməmiş bölgünün təsdiqi bloklaması, kontakt saatı uyğunsuzluğu, `set_plan_hours` (kilidli versiyaya yazmır), avto-MAJOR (week/assess/self), müəllimin seçdiyi MAJOR-un yenidən nömrələnməməsi, bazasız ilk versiya |
| `apps/accounts/tests/test_syllabus_sla_and_autosave.py` (YENİ) | 8 | 18-ci ekranın SLA KPI-ı (hədd siyasətdən, org override mətndə də görünür), `status=sla` filtri, **autosave 409** (`code`, serverdəki `revision`), uğurlu autosave sayğacı, endpoint-in siyasətdən kənar bölgünü rədd etməsi |
| `apps/registrar/tests/test_journal_topic_source.py` (YENİ) | 11 | qaralama sillabusun jurnala **sızmaması**, təsdiqlənmiş həftəlik planın mövzu siyahısına çevrilməsi, mövzu başına `kinds`, `covered/covered_kinds`, təsdiqlənmiş plandan saat bölgüsü (qaralama plan mənbə DEYİL), sıfır saatlı növün atılması, ixtisasın qrupdan həlli |
| `apps/syllabus/tests/test_completion.py` (YENİLƏNDİ) | +1 | boş sillabusda `assess` artıq ödənilmiş sayılmır; `flex` tam paylanmalıdır |
| `apps/syllabus/tests/test_workflow.py` (YENİLƏNDİ) | — | köçürmə irsi testi: `note`/`exam_questions` qorunur, ETİBARSIZ bölgü normallaşır |

**Nəticələr** (private DB `ems_ds5_7f3a91`, `emsarena_agent`):

```
apps/syllabus            214 passed
apps/registrar/tests    1420 passed  (+ yeni 11; mövcud test_journal_syllabus_bridge.py 18-i toxunulmazdır)
apps/accounts/tests     1395 passed, 1 skipped, 1 failed  ← ƏCNƏBİ (aşağı bax)
```

⚠️ **`test_account_archive_postgres.py::…_opens_the_registrar_guard_…` — bu işə
AİD DEYİL.** Səbəb: `63007671` (Mərhələ 2/3) `registrar_studentacademicrecord`-a
NOT NULL `admission_exam_type` əlavə edib, testin xam SQL INSERT-i isə sütunu
yazmır. Ayrıca task kimi qeyd olundu.

---

## 4. Canlı QA (klon `emsarena_rehearsal_a0d170000901`, server `:8100`)

Migrasiya tətbiq olundu (`syllabus.0003` daxil), server yenidən başladıldı.

| Addım | Nəticə |
| --- | --- |
| `qa.teacher` → «Sillabuslar» | 6 KPI (o cümlədən **«SLA-NI KEÇİB · 5 gündən çox kafedra növbəsindədir»**), 2 «Sillabus yoxdur» sətri; şəkil 1280 |
| Təyin olunmuş fənnə (MYEDU-L1001) qaralama | v1.0; **`plan_hours` təsdiqlənmiş plandan gəldi: 30/16/14** |
| 10 bölmə QƏSDƏN səhv saatla dolduruldu | **88 %**, redaktorda: «Mühazirə saatı tədris planındakı 30 saatla uyğun gəlmir (hazırda 28)», «Növ üzrə bölgü **28/30 · 14/16 · 14/14**» qırmızı, addım 4 «2 xəta», **«Təsdiqə göndər» disabled** |
| Saatlar düzəldildi | 100 % → `submitted` |
| `qa.chair_head` baxışa götürdü, bölmə şərhi ilə düzəliş istədi | `revision`, səbəb + `section_comments` yazıldı |
| Müəllim ədəbiyyatı yenilədi → yenidən göndərdi → müdir təsdiqlədi | `approved`, `locked_at` dolu, `approved_by = qa.chair_head`, dosyenin `approved_version` göstəricisi keçdi |
| **Jurnal dərs modalı** | 14 mövzu **təsdiqlənmiş sillabusdan**: «QA-DS5 mövzu 1 · mühazirə, seminar, laboratoriya», `data-kinds="lecture seminar lab"` |
| **Avto-MAJOR canlı** | müəllim **MINOR** seçdi (v1.1) → həftəlik mövzu dəyişdi → göndərişdə **v2.0 / major**, `escalated=('week',)` |
| **20-ci ekran** (`qa.chair_head`) | KPI: «Növbədə gözləyən 2 · Eskalasiya həddini keçib 0 (10 gündən çox gözləyir) · Çatışmayan bölməsi var 1 · Orta gözləmə 4 gün (hədəf: SLA çərçivəsində)»; sətir: **«7 gündür gözləyir — SLA 5 gün»** sarı tonda, «100 %», «v2.0 · v1.0 aktivdir», risk çipi «böyük dəyişiklik». Qərar paneli: 3 düymə + «Sillabus bölmələri / Dəyişikliklər / Audit tarixçəsi» tabları + «Düzəliş tələb olunan bölmələr» |
| Mobil 375 | sillabus paneli 343 px (üfüqi sürüşmə yaratmır), `h1` sayı 1. Səhifə səviyyəsindəki 1024 px `scrollWidth` **qabığın** bağlı `mobile-nav-panel` off-canvas elementindəndir — sillabus bölməsindən deyil (mövcud davranış, bu işin əhatəsindən kənar) |
| Konsol | Sillabus səhifələrinin yüklənməsində **0 uğursuz resurs** (`performance` ölçmə). Buferdə qalan 405/404 mənim səhv naviqasiyalarımdandır (`GET /accounts/logout/`, mövcud olmayan `/accounts/login/teacher/`) |
| Təmizlik | `QA-DS5` sillabus + 2 versiya + 20 bölmə + 6 baxış qeydi silindi; müvəqqəti plan sətrinin saatları və plan adı **əvvəlki vəziyyətinə qaytarıldı**; `QA-DS5` qalıq: **0** |

### ⚠️ QA harness məhdudiyyəti (bütün agentlərə aiddir)

`config/settings/staging_inspect.py` CSRF cookie-sini `emsarena_staging_csrftoken`
adlandırır (`:8000` ilə toqquşmasın deyə), frontend JS isə `csrftoken` oxuyur →
**`:8100`-də hər AJAX yazısı 403 CSRF verir** («Sillabus yarat» dialoqu açılır,
təsdiq POST-u düşür). Ona görə yazı əməliyyatları **servis qatından** (UI-nin
çağırdığı eyni kod yolu) icra edildi, brauzer isə hər vəziyyətin RENDER-ini
yoxladı. Bu, məhsul deyil, **harness** qüsurudur — həlli sahibin qərarını
tələb edir (cookie adını geri qaytarmaq `:8000` sessiyasının CSRF cookie-sini
əvəz edər).

---

## 5. Qapılar

| Qapı | Nəticə |
| --- | --- |
| `black` / `isort` / `flake8` (bu işin 21 faylı) | ✅ təmiz |
| `scripts/check_module_size.py --check` | ✅ (`journal_extras.py` 590 → bölündü; `journal_topics.py` 129) |
| `scripts/module_deps.py --check` | ✅ yeni dövr yoxdur (`registrar → syllabus` onsuz da mövcud idi) |
| `makemigrations --check` (sqlite) | ✅ «No changes detected» (0003 data-only) |
| pytest | ✅ 214 + 1420 + 1395 (1 əcnəbi uğursuzluq — §3) |
| `.po` faylları | **TOXUNULMADI** — msgid-lər `DESIGN_STAGE5_MSGIDS.txt`-dədir |

---

## 6. Edilməyənlər (qəsdən) və qalan iş

1. **`.syl-*` → `ems-*` CSS köçürməsi edilmədi.** `HANDOFF_FULL_PLAN.md` §5.3
   bunu «Mərhələ 1+ konsolidasiya hədəfi» kimi qeyd edir; sillabus CSS dəsti
   artıq ≤600 sətirlik fayllara bölünüb və `syllabus_*.js` hook-ları həmin
   class adlarına bağlıdır. Davranış riski faydadan böyükdür — tapşırıq
   «yalnız ucuz köçürmə» deyirdi.
2. **`second_approval_enabled` yalnız oxunur.** Default `False` (§10.2), UI
   marşrutu uzatmır. Açılanda `workflow`-a ikinci pillə əlavə etmək lazımdır —
   bu, sahib qərarı gələnə qədər YAZILMADI (indi yazılsa ölü kod olardı).
3. **Kontakt saatı mənbəyi köhnə qaralamalarda boşdur.** `plan_hours` yalnız
   YENİ yaradılan qaralamalara yazılır; mövcud açıq qaralamalar üçün toplu
   `set_plan_hours` icrası ayrıca əməliyyatdır (canlı klonda təsdiqlənmiş plan
   sətirlərinin **heç birində saat yoxdur** — Mərhələ 2 planları saatsız
   köçürüb, ona görə hazırda heç bir sillabusa təsir etmir).
4. **20-ci ekranın brauzer içindən qərar axını** harness CSRF səbəbi ilə
   yoxlanmadı (render + servis qatı yoxlanıldı).
