# FAZA 21 — Canlı UI / UX QA (rol-rol kabinet süpürgəsi)

**Tarix:** 2026-09-02 · **Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (:55433)
**Server:** `http://127.0.0.1:8100` · **Dil:** Azərbaycan · **Viewport:** 1280×900 (+375 / 768)
**Rollar:** `qa.student`, `myedu.student.5925` (Pünhan Kərimli — cari dövrdə 9 yazılış),
`qa.teacher`, `myedu.worker.459` (Ülkər Hüseynova — cari dövrdə 21 açılış),
`qa.chair_head`, `qa.program_coordinator`, `qa.dean`, `qa.exam_center`,
`qa.ikt_rehber` (RİM), `qa.rector`.

Köçürülmüş iki hesabın paroluna YALNIZ KLONDA `QaAudit2026!` təyin edildi
(`access_state=active`, `password_change_required=False`).

---

## 1. Rol × bölmə matrisi — yüklənmə

Metodika: hər rol ÖZ portalından real login etdi (tələbələr `/accounts/login/telebe/`,
qalanları `/accounts/login/muellim/`), profil qabığı yükləndi, sol menyudan çıxarılan
HƏR bölmə açarı əvvəlcə AJAX fraqment ucundan
(`/accounts/profile/api/sections/<sec>/`), 403 qaytaranlar isə tam səhifədən
(`/accounts/profile/?section=<sec>`) açıldı.

> **403 ≠ defekt.** `AJAX_SAFE_SECTIONS`-da olmayan (form/admin) bölmələr fraqment
> ucundan QƏSDƏN 403 verir (`sections_api.py:227`) və tam səhifə ilə yüklənir.
> Aşağıdakı «tam səhifə» sütunu məhz onlardır — hamısı **200**.

| rol | bölmə | AJAX 200 | tam səhifə 200 | **500 / istisna** | konsol xətası | ən yavaş bölmə |
|---|---:|---:|---:|---:|---|---:|
| `qa.student` | 16 | 14 | 2 | **0** | yoxdur | 106 ms |
| `myedu.student.5925` | 16 | 14 | 2 | **0** | yoxdur | 268 ms |
| `qa.teacher` | 18 | 15 | 3 | **0** | yoxdur | 111 ms |
| `myedu.worker.459` | 18 | 15 | 3 | **0** | yoxdur | 180 ms |
| `qa.chair_head` | 32 | 24 | 8 | **0** | yoxdur | 174 ms |
| `qa.program_coordinator` | 13 | 11 | 2 | **0** | yoxdur | 174 ms |
| `qa.dean` | 31 | 23 | 8 | **0** | yoxdur | 303 ms |
| `qa.exam_center` | 27 | 17 | 10 | **0** | yoxdur | **3 043 ms** (`analytics`) |
| `qa.ikt_rehber` | 44 | 29 | 15 | **0** | yoxdur | **3 052 ms** (`analytics`) |
| `qa.rector` | 37 | 27 | 10 | **0** | yoxdur | **2 878 ms** (`analytics`) |

**Cəmi 252 bölmə açılışı — 500/istisna YOXDUR.**

Konsol: hər rolda `console.error` / `onerror` / `unhandledrejection` hook-lanaraq
bölmələr bir-bir açıldı — **məhsul mənşəli konsol xətası aşkarlanmadı**.
(Loqdakı yeganə `405` mənim `GET /accounts/logout/` yoxlama sorğumdur.)

### `docs/ROL_MATRISI.md`-dən sonrakı YENİ bölmələr

| bölmə | etiket | görən rollar | status |
|---|---|---|---|
| `applications` | Müraciətlərim | **hamısı** (10/10) | 200 |
| `schedule-manage` | Cədvəl idarəetməsi | chair_head · coordinator · dean · RİM · rector | 200 |
| `my-workload` | Dərs yüküm | teacher · chair_head · coordinator · dean · RİM · rector | 200 |
| `workload-distribution` | Yük bölgüsü | chair_head · RİM · rector | 200 |
| `legacy-grade-review` | Köçürülmüş nəticələr | exam_center · RİM · rector | 200 |
| `student-intake` | (tələbə qəbulu) | RİM · rector | 200 |

İcazə uyğunluğu (rol matrisi ilə tutuşdurma):
* **✅ `schedule-manage` müəllimdə YOXDUR** — P0-4-ün gözlənilən nəticəsi.
* **⚠️ `my-workload` («Dərs yüküm» — MÜƏLLİMİN öz yükü) dean / coordinator / rector-a
  da açıqdır** və onlarda həmişə boş (4 826 bayt eyni gövdə). Tədris aparmayan
  rollar üçün menyu səs-küyüdür. → P3, `apps/workload` (toxunulmadı).
* **⚠️ `workload-distribution` proqram koordinatorunda YOXDUR** — koordinator cədvəli
  və qrupları idarə edir; yük bölgüsünə buraxılıb-buraxılmaması **sahib qərarıdır**.

---

## 2. Uçdan-uca axınlar

| axın | nəticə | dəlil |
|---|---|---|
| Tələbə portalı → kabinet | ✅ | `POST /accounts/login/telebe/` → `/accounts/profile/` 200 |
| Heyət portalı → kabinet | ✅ | `POST /accounts/login/muellim/` → 200; səhifə tam AZ (bax §6 skrinşot qeydi) |
| Köçürülmüş tələbə (5925) tam kabinet | ✅ | 16 bölmə, 500 yox, ən yavaz 268 ms |
| Köçürülmüş müəllim (459) tam kabinet | ✅ | 18 bölmə, 500 yox, `my-workload` 0 saat |
| Müəllim `my-workload` | ✅ | `qa.teacher`: 3 sətir / 60 saat / doluluq 12 %; boş-hal bloku sətir olanda **düzgün gizlədilir** (DOM-da var, `offsetParent=null`) |
| Kafedra müdiri `workload-distribution` | ✅ yüklənir | kafedra «Proqramlaşdırma və informasiya təhlükəsizliyi» tanınır; «Bu il üçün tapşırıq yoxdur» + izahlı boş-hal |
| Sillabus növbəsi (chair_head) | ⚠️ | `syllabus-review`: «Növbədə gözləyən **1**» — AMMA `qa.chair_head` **bildirişləri BOŞDUR** («Hazırda bildiriş yoxdur») |
| `schedule-manage` slot əlavə/sil | ⛔ **icra edilə bilmədi** | `qa.chair_head` üzvlüyündə **`scope_unit` yoxdur** → «Səlahiyyət sahənizdə qrup yoxdur» (fixture boşluğu, məhsul defekti deyil) |
| Kollokvium pəncərəsi → müəllim K balı | ⛔ icra edilmədi | eyni fixture boşluğu + budcə |
| RİM `?correct=1` düzəliş axını | ⛔ icra edilmədi | budcə |
| Başlıqdakı «Qoşul» düyməsi (P2-5) | ✅ **cavablandırıldı** | bax aşağıda |

### «Qoşul» düyməsi — P2-5-ə cavab

Tələbə kabinetində `button.blog-header__create-toggle` **tək bəndlik** açılan menyudur:

```html
<a href="/live/" class="blog-header__create-item">
  <span class="…item-title">Canlı imtahan</span>
  <span class="…item-desc">PIN ilə canlı imtahana daxil ol</span>
</a>
```

Yəni **mənasız deyil** — canlı (aralıq/test) imtahana PIN girişidir. Amma:
* Yekun imtahan bu yolla AÇILMIR (`project_final_cabinet_pin_only` — giriş
  `/exams/final/` + bilet PIN-i ilədir), ona görə köçürülmüş tələbənin çox halda
  qoşulacağı heç nə olmur;
* tək bəndlik açılan menyu düymə kimi davranmır (istifadəçi 2 klik edir).

**Tövsiyə (fix DEYİL, sahib qərarı):** düyməni yalnız tələbənin qoşula biləcəyi
canlı imtahan olanda göstərmək, olduqda isə birbaşa `/live/`-a keçid etmək.

---

## 3. Kabinet ana-səhifə (dashboard) boşluqları

Auditin gözlədiyi vidcetlərlə müqayisə. **Heç bir rolda ayrıca «dashboard» səhifəsi
yoxdur** — kabinet açılanda ilk bölmə `profile-info`-dur (şəxsi məlumat kartı).
Yəni aşağıdakıların HAMISI çatışmır:

| rol | gözlənilən | mövcud |
|---|---|---|
| müəllim | bugünkü dərslər · təyin fənlər · gözləyən sillabus · son müraciətlər | ❌ heç biri — `profile-info` açılır |
| tələbə | bugünkü dərslər · son qiymətlər · davamiyyət · müraciətlər · elanlar | ❌ heç biri |
| kafedra müdiri | yük statusu · sillabus təsdiqləri · gözləyən müraciətlər | ❌ heç biri |
| koordinator | cədvəl · qruplar · müraciətlər | ❌ heç biri |
| RİM | növbələr · düzəlişlər · müraciətlər | ❌ heç biri |
| imtahan mərkəzi | qiymətləndirmə pəncərələri · imtahanlar · sorğular | ❌ heç biri |

**Kiçik vidcet ƏLAVƏ EDİLMƏDİ.** Səbəb: hazır helper (`apps.applications.public`)
mövcud olsa da, kabinetdə vidcet yerləşdirəcək **ana-səhifə bölməsi yoxdur** —
`profile-info` şəxsiyyət kartıdır, ora sayğac kartı qoymaq redizayn olardı.
Doğru həll: yeni `dashboard` bölməsi (öz partial + `SECTION_PARTIALS` +
`AJAX_SAFE_SECTIONS` + `data-ajax-sections` + `rbac_sections`) — ayrıca iş elementi.

Müsbət: **bildiriş zəngi (`badges_api`) və `notifications` bölməsi işləyir**
(`qa.student`-də 8 oxunmamış), yəni «son hadisələr» üçün data qatı hazırdır.

---

## 4. Tətbiq edilən düzəlişlər

### 4.1 🔴 AZ tarix adları KORLANMIŞDI (bütün tətbiq boyu)

`locale/az/LC_MESSAGES/django.po` Django-nun ÖZ tarix msgid-lərini kölgələyir və
10-unun tərcüməsi başqa (əlaqəsiz) sətirdən sürüşmüşdü. Nəticə: **UI-dakı HƏR tarix
səhv ay/gün adı ilə render olunurdu.** Sentyabr ayında olduğumuz üçün bu, canlı
sistemdə **hər tarixdə** görünürdü.

`locale/az/LC_MESSAGES/django.po`:

| msgid | əvvəl | sonra |
|---|---|---|
| `September` | **`Hələ üzv əlavə olunmayıb.`** | `Sentyabr` |
| `January` | `manual` | `Yanvar` |
| `March` | `Axtar` | `Mart` |
| `November` | `Üzv` | `Noyabr` |
| `December` | `Üzv` | `Dekabr` |
| `jul` | `https://example.com/...` | `iyl` |
| `aug` | **`əvvəl`** | `avq` |
| `oct` | `Bloqa keçid` | `okt` |
| `Sat` | `Status` | `Şnb` |
| `Sun` | `Tələbə` | `Bzr` |

Dəyərlər Django-nun öz `az` kataloqundan (`django/conf/locale/az`) götürülüb.
Bu 10 msgid-in layihə kodunda **heç bir istifadəsi yoxdur** (yoxlanıldı:
`grep -r 'trans "January"' apps/ config/ templates/ static/` → 0) — yalnız Django-nun
tarix adlarını kölgələyirdilər.

**Brauzerdə təsdiq:** `profile-info` → «QOŞULMA TARİXİ» `27 Əvvəl 2026` → **`27 Avq 2026`**.

### 4.2 🟠 `profile-info`-da xam msgid sızması: «position»

`#, fuzzy` işarəsi `msgfmt`-in girişi `.mo`-ya salmasının qarşısını alırdı, ona görə
UI xam msgid göstərirdi. **Dörd kataloqda da** düzəldildi (fuzzy silindi):

| fayl | əvvəl | sonra |
|---|---|---|
| `locale/az/LC_MESSAGES/django.po:11751` | `#, fuzzy` → UI-da `position` | `Vəzifə` |
| `locale/en/LC_MESSAGES/django.po:11749` | `#, fuzzy` + səhv `Section` | `Position` |
| `locale/ru/LC_MESSAGES/django.po:11764` | `#, fuzzy` → `position` | `Должность` |
| `locale/tr/LC_MESSAGES/django.po:11723` | `#, fuzzy` → `position` | `Pozisyon` |

**Brauzerdə təsdiq:** `POSİTİON` → **`VƏZİFƏ`**.

### 4.3 🟠 Qrupsuz TƏLƏBƏ «Müəllim cədvəli» görürdü (klonda 102 hesab)

`apps/registrar/page_contexts.py:387` — `schedule_context` İKİLİ idi: akademik
qeyd/qrup yoxdursa `role = "teacher"` verilirdi, `_schedule_content.html:21`
isə `role == 'student'` olmayanda başlığa **«Müəllim cədvəli»** yazırdı.
`qa.student`-də canlı təsdiqləndi: `Q QA Student · Müəllim cədvəli · Yaz`.

Ölçü: aktiv `student` üzvlüyü 7 606, akademik qeyd+qrupu olan 7 504 →
**102 real tələbə** bu ekranı görürdü.

* `apps/registrar/page_contexts.py:359-368` — yeni `_has_active_student_membership()`
  (`django_apps.get_model("organizations", "Membership")` — `module_deps` qapısına
  görə statik import YOX).
* `apps/registrar/page_contexts.py:398-404` — yeni `elif` qolu: aktiv `student`
  üzvlüyü varsa `role = "student"`, `slots = []` (boş-hal mesajı çıxır).
* Reqressiya testi: `apps/registrar/tests/test_schedule_views.py:117-140`
  `test_groupless_student_is_not_labelled_a_teacher`.

### 4.4 🟠 768 px-də səhifə 200 px ÜFÜQİ sürüşürdü

Kök səbəb (ölçülüb, təxmin deyil): Font Awesome vendor CSS-i `.sr-only`-ni
`position: absolute` verir, amma `left/top` TƏYİN ETMİR → element statik mövqeyində
qalır. Geniş (`overflow-x: auto` içində sürüşən) cədvəlin `<th>`-indəki
`<span class="sr-only">Əməllər</span>` beləcə `left: 975.6px`-ə düşür və
`documentElement.scrollWidth`-i şişirdirdi.

* `static/css/ems_components.css:155-170` — vendor faylına toxunmadan override:
  `.sr-only:not(:focus) { left: 0; top: 0; }` (`:focus` variantı toxunulmaz).

**Ölçülmüş nəticə (`syllabus-list`, 768 px):**
`scrollWidth 975 → 768` · `window.scrollX 200 → 0` · `hScroll true → false`.
375 və 1280-də reqressiya yoxdur; `.sr-only` hələ də 1×1 və `clip: rect(0,0,0,0)`.

### 4.5 🟡 WCAG AA kontrast — sillabus sayğac çipi

`apps/accounts/static/accounts/css/profile/sections/syllabus_list.css:190-198`
`.syl-chip__count` 0.7 rem (kiçik mətn → ≥ 4.5:1 tələb olunur):
`--ems-neutral-500` (#64748b) / `--ems-neutral-100` (#f1f5f9) = **4.34:1 — KEÇMİR**.
→ `--ems-neutral-600` (#475569) = **6.92:1**.
Brauzerdə ölçüldü: 8 çipdən 7-si 4.34 → **6.92**, aktiv çip 6.7 (onsuz da keçirdi).

### Qapılar (dəyişdiyim fayllar üçün)

* `black` / `isort` / `flake8` — `apps/registrar/page_contexts.py` **təmiz**.
* `scripts/module_deps.py --check` — **✅ yeni dövr yoxdur**.
* `scripts/check_module_size.py --check` — dəyişdiyim fayllar **təmizdir**
  (qalan 2 xəbərdarlıq — `apps/legacy_import/models.py`, `apps/registrar/models/grading.py`
  — **başqa agentlərin** işidir, mənə aid deyil).
* `pytest` (özəl baza `ems_ui_*`, agent postgres :55432):
  `test_schedule_views.py` + `test_schedule.py` + `test_section_registry_consistency.py`
  → **22 passed**.
* `scripts/check_i18n_catalogs.py` — **budaqda ONSUZ DA qırmızıdır** (HEAD-də
  `source_missing 112`, paralel agentlərin `applications`/`workload` sətirləri).
  Mənim dəyişikliyim `az/source_missing`-i **112 → 4** azaldır; `tr/identity 270 → 280`
  artımı **mənim deyil** — `locale/tr` faylına başqa agent ~933 sətir
  (`msgctxt "applications"`, msgstr == msgid) əlavə edib.

---

## 5. DÜZƏLTMƏDİYİM problemlər

### P1

| # | problem | yer | niyə düzəltmədim |
|---|---|---|---|
| U-1 | **223 AZ kataloq girişi `#, fuzzy` və msgstr-i SƏHVDİR** — `msgmerge` başqa sətirdən uyğunlaşdırıb. Bu gün UI msgid-ə (əsasən düzgün AZ) düşür, amma kimsə `--use-fuzzy` ilə kompilyasiya etsə və ya tərcüməçi fuzzy-ni götürsə etiketlər **kütləvi şəkildə səhv** olur: `Sil`→**`Dil`**, `Blokla`→**`Bloku aç`**, `Jurnalları bağla`→**`Jurnallarım`**, `Tələbə balları`→**`Tələbə sayı`**, `Jurnaldan çıxar`→**`Kafedradan çıxar`** | `locale/az/LC_MESSAGES/django.po` (394 fuzzy, 223-ü zərərli) | 223 sətrin ƏLLƏ yenidən tərcüməsi lazımdır — redizayn həcmi. **Tam siyahı bu hesabatın §7-dədir.** |
| U-2 | **Rol adları İNGİLİSCƏ görünür** — `Teacher`, `Student`, `Department Chair`, `Exam Center`, `Exam Center Head`, `Exam Center Staff`, `Lead Student`, `Dean`, `Rector` + təsvirlər («Exam center managing exam lifecycle, monitoring, results and appeals»). Görünən bölmələr: `org-faculties`, `org-kafedras`, `org-members`, `org-roles`, `role-assignment`, `student-organization-management`, `applications` başlığı | `apps/organizations/default_roles_university.py:18,26,68,98,189,209,240,291,339,369,386` + KLONDAKI `Role.display_name` sətirləri | Data miqrasiyası + `.po` işi; fayl paralel agent tərəfindən redaktə olunur (P2-3 «RİM rəhbəri» düzəlişi). Konflikt riski. |
| U-3 | **Sillabus növbəsində 1 element var, amma kafedra müdirinin bildirişi YOXDUR** — P1-1-in (sillabus bildirişləri) real axında işlədiyi TƏSDİQLƏNMƏDİ | `apps/syllabus/services/notifications.py` | Növbədəki element düzəlişdən ƏVVƏL yaradılmış ola bilər; təsdiq üçün təzə submit lazımdır (fixture `scope_unit` boşluğu mane oldu). |

### P2

| # | problem | yer |
|---|---|---|
| U-4 | **`my-courses` etiketi məzmunu ilə ziddiyyətdədir.** Müəllimə «Təyin olunmuş fənlərim» yazılır, amma bölmə LMS **kurs yaradıcısıdır**: sayğac `my_created_courses_count`, düymə «Yeni kurs» → `courses:create_course`, boş-hal «Hazırda heç bir kurs yaratmamısınız. İlk kursu yarat». Kafedra müdirində eyni bölmə düzgün — «Yaratdığım kurslar». | `_my_courses.html:10`, `_sidebar.html:197,201` (`university_mode and role_capabilities.is_teacher` şərti) — düzgün etiket sahib qərarıdır (etiketi dəyişmək vs məzmunu «təyin fənlər»ə çevirmək) |
| U-5 | **Semestr/il defoltları cari dövrə uyğun deyil.** Cari dövr **2025/2026 Yaz**, amma `schedule-manage` defolt **«Payız semestri»**, `my-workload` defolt **2026/2027** seçir → istifadəçi boş ekrana düşür | `schedule-manage` bölməsi; `apps/workload` (toxunulmadı) |
| U-6 | **`my-workload` başlığı İKİQAT** («Dərs yüküm» qabıq başlığı + bölmənin öz `<h*>`-i) və **tədris ili idarəsi iki dəfə** (mətn input + select, hər ikisi `2026/2027`) | `apps/workload` (toxunulmadı) |
| U-7 | **Scope həlli modullar arasında ZİDDİYYƏTLİDİR.** `qa.chair_head`-də `syllabus-review` «Əhatə: 0 struktur bölmə», `schedule-manage` «Səlahiyyət sahənizdə qrup yoxdur» deyir, amma `workload-distribution` kafedranı («Proqramlaşdırma və informasiya təhlükəsizliyi») TANIYIR | `schedule_manage` / `syllabus-review` vs `apps/workload` |

### P3

| # | problem |
|---|---|
| U-8 | **Bağlı off-canvas menyu tab sırasında qalır** — `nav.mobile-nav-panel` `position: fixed; right: -300px; visibility: visible` → klaviatura ilə ekrandan kənar linklərə fokus düşür. Düzəliş bir qayda ilə mümkündür (`visibility: hidden` bağlı, `visible` `.is-open`-da + `transition: … visibility 0s linear .3s`), **AMMA** `static/css/navbar.css` `check_module_size.py`-da 983 sətirdə DONDURULUB, +7 sətir qapını qırır → geri qaytardım. Ayrıca fayl/budcə yeniləməsi lazımdır. |
| U-9 | **Sol menyu linklərində `:focus-visible` qaydası YOXDUR** (`apps/accounts/static/accounts/css/profile/sidebar.css` — `focus` sözü 0 dəfə); klaviatura fokus halqası UA defoltuna qalır. Qlobal fokus üslubu dizayn qərarıdır. |
| U-10 | **Handler rolları da sidebar-da «Müraciətlərim» görür** (chair_head/dean/RİM/rector/coordinator/exam_center) — onlar İCRAÇIDIR. PHASE18-də qəsdən belədir (panel içində «Mənə gələnlər» tabı var), amma menyu etiketi yanıldıcıdır. |
| U-11 | **İkonalar təkrarlanır:** `journal-close` = `change-password` (`lock`); `exam-center-pins` = `permission-editor` (`key`); `question-submissions` = `publish-notification` (`paper-plane`); `org-roles` = `question-bank` (`layer-group`); `exam-center-stats` = `analytics` (`chart-line`); tələbədə `my-subjects` = `my-journal` (`book-open`). |
| U-12 | **`Email` etiketi 30+ yerdə tərcümə edilmir** (`msgstr "Email"` az/en/ru/tr-də) — sistem mesajlarında isə «e-poçt» işlənir. Ardıcıllıq borcu; qəsdən seçim ola bilər, ona görə toxunmadım. |
| U-13 | **`analytics` bölməsi 2.9–3.1 s** (exam_center / RİM / rector). Skelet yükləyici var, amma 3 s AJAX gözləməsi çoxdur. |
| U-14 | **Login səhifəsində dil seçimi kəsilir** — «Azərbay…» (select çox dar). |
| U-15 | **`profile-info` avatar modalında `aria-label="Close"`** — ingiliscə qalıb. |

---

## 6. Metodika qeydləri (təkrar üçün)

* **Brauzer paneli skrinşotları oxunmur** — 1280×900 emulyasiyası 800×562-ə
  kiçildilir və mətn seçilmir; `zoom` region kırpması bu paneldə DƏSTƏKLƏNMİR.
  Ona görə mətn yoxlamaları `get_page_text` / `find` / `javascript_tool` ilə,
  ölçmələr isə birbaşa DOM-dan (`getBoundingClientRect`, `getComputedStyle`,
  `window.scrollX`) aparıldı — skrinşota göz ilə baxmaqdan daha etibarlıdır.
* **Paylaşılan brauzer:** iş vaxtı panelə başqa agentlər 3 `file://` tab açdı;
  öz işim `tab-2`-dədir.
* **QA serveri 2 dəfə qalxa bilmədi** (mənim səbəbimdən deyil):
  (1) `organizations.0034_seed_user_import_permission` klonda tətbiq olunmamışdı →
  `scripts/staging_inspect.sh migrate` ilə tətbiq etdim;
  (2) `apps/accounts/views/profile/context_builder/_stage3.py:412` paralel agentin
  yarımçıq redaktəsi ilə `SyntaxError: '(' was never closed` verirdi → gözlədim.

---

## 7. FAZA 32 — rol / funksiya matrisi (crna qaralama)

| Rol | Funksiya | UI testi | İcazə testi | Data testi | Nəticə |
|---|---|---|---|---|---|
| student | kabinet qabığı (16 bölmə) | ✅ 200, konsol təmiz | ✅ heyət bölmələri menyuda yoxdur | ✅ `qa.student` boş, `5925` 9 yazılış | **KEÇDİ** |
| student | `my-schedule` | ⚠️ qrupsuzda «Müəllim cədvəli» | ✅ | ✅ 102 hesab təsirlənirdi | **DÜZƏLDİ** (4.3) |
| student | `profile-info` | ⚠️ `position` xam msgid | — | ✅ | **DÜZƏLDİ** (4.2) |
| student | `my-journal` / `my-results` / `overall-academic` | ✅ 200, izahlı boş-hal | ✅ | ✅ | **KEÇDİ** |
| student | `applications` (Müraciətlərim) | ✅ panel kabinet içində, sidebar qalır | ✅ yalnız öz müraciətləri | ✅ MR-000002 bildirişi | **KEÇDİ** |
| student | başlıqdakı «Qoşul» | ⚠️ tək bəndlik menyu → `/live/` | ✅ | ⚠️ köçürülmüşdə boş | **AÇIQ** (P2-5) |
| teacher | kabinet qabığı (18 bölmə) | ✅ | ✅ `schedule-manage` YOXDUR | ✅ `459` 21 açılış | **KEÇDİ** |
| teacher | `my-workload` | ✅ 3 sətir / 60 saat, boş-hal düzgün gizlənir | ✅ | ✅ | **KEÇDİ** |
| teacher | `my-workload` il defoltu | ⚠️ 2026/2027 (cari 2025/2026) | — | ⚠️ | **AÇIQ** (U-5) |
| teacher | `syllabus-list` | ✅ 200, kontrast düzəldi | ✅ yalnız öz fənləri | ✅ 2 fənn | **DÜZƏLDİ** (4.5) |
| teacher | `my-courses` | ⚠️ etiket ≠ məzmun | ✅ | ✅ | **AÇIQ** (U-4) |
| teacher | `groups` / `pending-review` / `review-results` | ✅ 200, izahlı boş-hal | ✅ | ✅ | **KEÇDİ** |
| chair_head | kabinet qabığı (32 bölmə) | ✅ | ⚠️ dean ilə eyni 30 bölmə (P1-10) | ✅ | **KEÇDİ** |
| chair_head | `syllabus-review` növbəsi | ✅ «Növbədə 1» | ✅ yalnız öz kafedrası | ⚠️ bildiriş gəlmədi | **AÇIQ** (U-3) |
| chair_head | `schedule-manage` slot əlavə/sil | ⛔ `scope_unit` yoxdur | — | — | **İCRA EDİLMƏDİ** |
| chair_head | `workload-distribution` | ✅ kafedra tanınır, izahlı boş-hal | ✅ | ✅ | **KEÇDİ** |
| chair_head | yük sətri yarat/təsdiqlə → müəllim bildirişi | ⛔ | — | — | **İCRA EDİLMƏDİ** |
| coordinator | kabinet qabığı (13 bölmə) | ✅ | ✅ ən dar səth | ✅ | **KEÇDİ** |
| coordinator | `schedule-manage` | ✅ 200 | ✅ görür | ⛔ scope yoxdur | **QİSMƏN** |
| coordinator | `workload-distribution` | — | ⚠️ GÖRMÜR | — | **SAHİB QƏRARI** |
| dean | kabinet qabığı (31 bölmə) | ✅ | ⚠️ chair_head ilə eyni siyahı | ✅ | **KEÇDİ** |
| exam_center | 27 bölmə (PIN, stats, kollokvium, apellyasiya) | ✅ hamısı 200 | ✅ sillabus səthləri YOXDUR | ✅ | **KEÇDİ** |
| exam_center | `analytics` | ⚠️ 3 043 ms | ✅ | ✅ | **AÇIQ** (U-13) |
| exam_center | kollokvium pəncərəsi yarat → müəllim K balı | ⛔ | — | — | **İCRA EDİLMƏDİ** |
| RİM (`ikt_rehber`) | 44 bölmə — ən geniş səth | ✅ hamısı 200, konsol təmiz | ✅ `superadmin-exam-rooms` yalnız RİM-də | ✅ | **KEÇDİ** |
| RİM | `?correct=1` sənədli düzəliş + tarixçə | ⛔ | — | — | **İCRA EDİLMƏDİ** |
| rector | 37 bölmə | ✅ | ✅ `kollokvium-windows`/`exam-center-pins` YOXDUR | ✅ | **KEÇDİ** |
| **hamısı** | AZ tarix adları | ⚠️ 10 ay/gün adı korlanmışdı | — | ✅ tətbiq boyu | **DÜZƏLDİ** (4.1) |
| **hamısı** | responsiv 375 / 768 / 1280 | ⚠️ 768-də 200 px üfüqi sürüşmə | — | — | **DÜZƏLDİ** (4.4) |
| **hamısı** | sidebar 375-də yığılır | ✅ off-canvas, üfüqi sürüşmə yox | — | — | **KEÇDİ** |
| **hamısı** | klaviatura fokus halqası | ⚠️ sidebar-da `:focus-visible` yoxdur | — | — | **AÇIQ** (U-9) |
| **hamısı** | status çipləri kontrastı | ⚠️ `syl-chip__count` 4.34:1 | — | — | **DÜZƏLDİ** (4.5) |
| **hamısı** | rol adları AZ-dır? | ⚠️ İNGİLİSCƏ | — | ⚠️ klon datası | **AÇIQ** (U-2) |

---

## 8. Əlavə — U-1 (zərərli fuzzy) tam siyahısı

Yenidən yaratmaq üçün:

```bash
.venv/bin/python - <<'PY'
import re
s = open("locale/az/LC_MESSAGES/django.po").read()
for e in s.split("\n\n"):
    if "#, fuzzy" not in e: continue
    c = re.search(r'^msgctxt "([^"]*)"', e, re.M)
    i = re.search(r'^msgid "((?:[^"\\]|\\.)*)"', e, re.M)
    m = re.search(r'^msgstr "((?:[^"\\]|\\.)*)"', e, re.M)
    if not (i and m) or not i.group(1) or i.group(1) == m.group(1): continue
    print("%-34s %-48s => %s" % (c.group(1) if c else "", i.group(1)[:48], m.group(1)[:60]))
PY
```

Ən təhlükəli 10-u (etiket «sil»i «dil», «blokla»nı «bloku aç» edir):

| ctx | msgid | fuzzy msgstr (SƏHV) |
|---|---|---|
| `registrar.journal_close` | `Sil` | **`Dil`** |
| `profile.rim` | `Sil` | **`Dil`** |
| `profile.rim` | `Blokla` | **`Bloku aç`** |
| `profile.rim` | `Blokdan çıxar` | **`Kafedradan çıxar`** |
| `registrar.journal_close` | `Jurnalları bağla` | **`Jurnallarım`** |
| `registrar.exam_score_entry` | `Tələbə balları` | **`Tələbə sayı`** |
| `registrar.guest_roster` | `Jurnaldan çıxar` | **`Kafedradan çıxar`** |
| `registrar.guest_roster` | `Jurnala əlavə et` | **`Kalendara əlavə et`** |
| `accounts.people.academic` | `Tələbə idarəetməsi` | **`Dil idarəetməsi`** |
| `accounts.handover` | `Təhvil ver` | **`Təhvil verilib`** |
