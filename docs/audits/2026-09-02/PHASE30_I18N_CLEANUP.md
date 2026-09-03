# FAZA 30 — i18n/etiket təmizliyi (fuzzy kataloqlar + rol adları)

**Tarix:** 2026-09-03 · **Branch:** `audit/post-migration-qa-2026-09` · **Commit edilməyib**
**Mənbə:** `PHASE21_UI_QA.md` §8 (U-1, 223 zərərli fuzzy) + §5 (U-2 rol adları, U-4 my-courses, U-9 fokus halqası)

---

## 1. Fuzzy AZ/EN/RU/TR kataloqları (U-1)

### Kök səbəb

`msgmerge` mövcud olmayan yeni `msgid`-i ƏN OXŞAR köhnə girişə fuzzy-match edib,
onun `msgstr`-ini daşımışdı. AZ kataloqunda `msgid` layihə konvensiyasına görə
artıq Azərbaycanca mətndir, ona görə fuzzy-eşləşmə köhnə **başqa** sözün AZ
mətnini gətirmişdi (`Sil`→`Dil`, `Blokla`→`Bloku aç`, `rim_center`→`İmtahan
Mərkəzi` və s.). **Eyni kök səbəb EN/RU/TR-də də** eyni cütlərlə təkrarlanıb
(`Sil`→ingiliscə "Dil"in tərcüməsi yox, amma `Blokdan çıxar`→en "Remove from
department" kimi başqa sözün tərcüməsi) — yoxlama zamanı bu üst-üstə düşmə
təsdiqləndi.

### Metodika

1. `polib` ilə hər 4 lokal × 2 domendə (`django.po`, `djangojs.po`) bütün
   `#, fuzzy` girişlər toplandı.
2. **AZ:** `msgstr = msgid`, fuzzy bayrağı düşür — LAYİHƏ KONVENSİYASI (mənbə
   dili AZ-dır). İstisna: 2 həqiqi Django-daxili İngiliscə `msgid`
   (`"Please submit at least %(num)d form."`, `"%(total_count)s selected"` —
   formset plural mesajları) — bunlara əl ilə düzgün AZ tərcümə (plural
   formalarla) yazıldı.
3. **EN/RU/TR:** əvvəlcə eyni `msgid`-in HƏMİN kataloqda BAŞQA (fuzzy olmayan,
   boş olmayan) girişdə artıq düzgün tərcüməsi var-mı yoxlanıldı — varsa
   həmin tərcümə TƏKRAR İSTİFADƏ edildi (171/370 EN, 171/370 RU, 171/383 TR
   bu yolla avtomatik həll olundu). Qalan **201 unikal AZ mətn** üçün əl ilə
   EN/RU/TR tərcüməsi yazıldı (bax `apps/accounts` və digər app-lardakı
   mövcud oxşar tərcümələrlə üslub uyğunluğu saxlanıldı).
4. `djangojs.po` (bütün 4 lokal) — heç vaxt fərdiləşdirilməmiş
   `makemessages` boilerplate header (`msgid ""` bloku `#, fuzzy` daşıyırdı,
   `SOME DESCRIPTIVE TITLE` mətni ilə) — `django.po` üslubuna uyğunlaşdırıldı.
5. `django-admin compilemessages` — 4 lokal, 2 domen.

### Yoxlama

* `msgfmt --check` — 4 lokal × 2 domen — **TƏMİZ**.
* Fuzzy sayı (`grep -c '^#, fuzzy'`) — **0** bütün 8 fayl üzrə (əvvəl: az
  django.po 395, az djangojs.po 1(header), en django.po 370, en djangojs.po
  1, ru django.po 370, ru djangojs.po 1, tr django.po 383, tr djangojs.po 1
  — **cəmi 1518 giriş düzəldi**).
* 16 tarix `msgid`-i (`September`, `aug`, `Sat`, `Sun`, `alt. month`/
  `abbrev. month` variantları) — PHASE21 §6 metodika skripti ilə yenidən
  yoxlanıldı, **korlanma YOXDUR**.
* U-1-in "ən təhlükəli 10"u (`Sil`→`Dil`, `Blokla`→`Bloku aç`, `rim_center`→
  `İmtahan Mərkəzi` və s.) — hər 4 lokalda əl ilə birbaşa yoxlanıldı, hamısı
  düzgün (məs. `rim_center` indi AZ-da `RİM mərkəzi`, EN-də `Digital
  Development Centre (RİM)`, RU-da `Центр цифрового развития (RİM)`, TR-da
  `Dijital Gelişim Merkezi (RİM)`).

### Koordinator əlavəsi (FAZA 6 — kafedra təsdiqi paralel agent)

`docs/audits/2026-09-02/PHASE6_CHAIR_APPROVAL.md`-in bitməsindən sonra 6 yeni
`msgid` (ctx `accounts.syllabus` ×5, `syllabus.notify` ×1) — çoxsətirli/
dict-daxili `pgettext_lazy` çağırışları olduğu üçün `scripts/i18n_source_scan.py`
tərəfindən görünmürdü (AST skanerin bilinən kor nöqtəsi). `polib` ilə birbaşa
yoxlanıb TƏSDİQLƏNDİ ki, 4 kataloqun HEÇ BİRİNDƏ yoxdur; əl ilə (AZ=identity,
EN/RU/TR tərcümə) 4 kataloqa əlavə edildi, kompilyasiya təkrarlandı.

### Say hesabatı (`scripts/check_i18n_catalogs.py`, domen `django`)

| lokal | fuzzy əvvəl | fuzzy sonra | identity əvvəl | identity sonra | əsaslandırma |
|---|---|---|---|---|---|
| az | 395 | **0** | 0 | 0 | — |
| en | 370 | **0** | 235 | 235 | dəyişmədi |
| ru | 370 | **0** | 124 | **125** | `Email` (mövcud, toxunulmamış 30+ yerdəki U-12 konvensiyası ilə eyni) |
| tr | 383 | **0** | 290 | **306** | 16 TR=AZ leksik uyğun söz (`Sil`, `Blokla`, `Bağlı`, `Dekan`, `Laborant`, `Soyad`, `maksimum` və s. — Türk-Azərbaycan ortaq kökləri, tapşırıqda icazə verilib) |

`djangojs` domenində fuzzy 1→0 (hər lokal, header) dəyişdi; `identity`
dəyişmədi. Baseline (`scripts/i18n_baseline.json`) YALNIZ bu 2 əsaslandırılmış
sayğac üçün `--update` YOX, əl ilə dəqiq yeniləndi (digər sayğaclara toxunulmadı).

**Qeyd (mənə aid olmayan):** son `check_i18n_catalogs.py` işə salınmasında
`source_missing 0 → 32` görünür — bu, PARALEL agentin (imtahan sual-baxışı
"chair review" funksiyası, `apps/exams/services/question_chair_review.py` və
s., commit edilməmiş) yeni `exams.model.question_submission.*` mətnləridir.
Mənim işim yoxlanılanda (bu agentin dəyişikliyindən ƏVVƏL) qapı **tam yaşıl**
idi (`✅ i18n kataloq qapısı: yeni borc yoxdur`). Fuzzy sayı və mənim əlavə
etdiyim bütün girişlər (16 `roles.org_display_name` + 6 FAZA 6) hələ də
kataloqlarda saxlanılır — yoxlanıldı.

---

## 2. Rol adları İngiliscə görünürdü (U-2)

### Kök səbəb

`apps/organizations/default_roles_university.py` bir çox rolu İngiliscə
`display_name` ilə seed edir (`"Teacher"`, `"Dean"`, `"Department Chair"` və
s.). Bu fayl paralel agent tərəfindən redaktə olunurdu (FAZA 6 üçün) —
**toxunulmadı**. Data miqrasiyası da yazılmadı (0035/0036 sıra münaqişəsi
riski) — bunun ƏVƏZİNƏ **runtime etiket xəritəsi** seçildi (tapşırıqda icazə
verilən ikinci variant).

### Həll

* `core/roles.py` — `ORG_ROLE_DISPLAY_LABELS` (16 rol adı → `pgettext_lazy`
  AZ etiket, ctx `roles.org_display_name`) + `resolve_seeded_role_label
  (role_name, raw_display_name)`: `raw_display_name` HƏRFİ olaraq bilinən
  default İngiliscə seed dəyərlərindən biridirsə (`_SEEDED_ENGLISH_ROLE_
  DISPLAY_NAMES`, 16 hərfi mətn) xəritədəki AZ etiketlə əvəzlənir; admin
  fərqli bir ad yazıbsa (və ya heç nə verilməyibsə) TOXUNULMUR — heç nə
  uydurulmur.
* `core/staff_position.py` — `visible_role_label` indi `resolve_seeded_role_
  label`-i tətbiq edir (əvvəl callera buraxırdı).
* `apps/organizations/templatetags/org_tags.py` — yeni `localized_role_label`
  şablon süzgəci (`role_badge_label`-in yanında).
* `apps/organizations/models.py`-ə TOXUNULMADI (600 sətir SOFT_CAP-i keçirdi
  — süzgəc həlli seçildi, model deyil).
* Şablonlar — birbaşa `role.display_name` / `member.role.display_name`
  → `role|localized_role_label` / `member.role|localized_role_label`:
  `templates/organizations/partials/_kafedras_content.html` (2),
  `_members_content.html` (1), `_roles_content.html` (1),
  `apps/accounts/templates/accounts/partials/_role_assignment_content.html` (4).
* `apps/accounts/views/profile/_sections/applications.py::_role_label` —
  `resolve_seeded_role_label` çağırır (əvvəl xam `display_name`).
* `org-faculties`/`org-kafedras`-dakı `candidate.role_label` və
  `student-organization-management`-dəki `membership.management_role_label`
  artıq `core.staff_position.visible_role_label`-dən keçdiyi üçün MƏRKƏZİ
  düzəlişlə avtomatik düzəldi (əlavə fayl toxunmadı).

### Yoxlama

`manage.py shell` ilə real Django konteksində (`AZ` aktiv dil):

| rol adı | xam `display_name` | `localized_role_label` nəticəsi |
|---|---|---|
| `dean` | Dean | **Dekan** |
| `chair_head` | Department Chair | **Kafedra müdiri** |
| `teacher` | Teacher | **Müəllim** |
| `rector` | Rector | **Rektor** |
| `exam_center` | Exam Center | **İmtahan mərkəzi** |

4 lokalda (`resolve_seeded_role_label`) yoxlanıldı — `chair_head`: az
`Kafedra müdiri`, en `Department Head`, ru `Заведующий кафедрой`, tr
`Bölüm Başkanı`. Admin fərqli bir ad yazıbsa (məs. `"Baş Dekan"`)
TOXUNULMADIĞI ayrıca testlə (`test_role_badge_label.py::
test_customized_display_name_is_untouched`) kilidləndi.

**Diqqət:** `ikt_rehber` artıq düzgün seed edilib (`"Rəqəmsal İnkişaf
Mərkəzi (RİM) rəhbəri"`) — bilərəkdən `_SEEDED_ENGLISH_ROLE_DISPLAY_NAMES`-ə
DAXİL EDİLMƏDİ (toxunulmaz qalır).

---

## 3. `my-courses` etiketi (U-4)

**Problem:** müəllimə (universitet rejimində) sidebar-da və bölmə
başlığında hardcoded `"Təyin olunmuş fənlərim"` yazılırdı, amma bölmə
LMS **kurs yaradıcısıdır** (sayğac `my_created_courses_count`, düymə
→ `courses:create_course`). Kafedra müdirində EYNİ bölmə düzgün göstərilirdi
(`"Yaratdığım kurslar"`, mövcud `my_created_courses` `msgid`-i ilə).

**Düzəliş:** hardcoded mətn silindi, `courses` app-ın artıq işlətdiyi
`"Kurslarım"` termini (`msgid="my_courses"`, ctx `profile.section`/
`profile.sidebar` — mövcud, 4 kataloqda artıq tərcümə olunmuş) tətbiq edildi:

* `apps/accounts/templates/accounts/profile/_sidebar.html` — `data-title` +
  `<span>` mətni.
* `apps/accounts/templates/accounts/profile/sections/_my_courses.html` —
  bölmə başlığı.

Bölmə açarı (`my-courses`) DƏYİŞMƏDİ. Hardcoded mətn artıq heç yerdə yoxdur
(`grep -rl "Təyin olunmuş fənlərim"` — 0 nəticə).

---

## 4. Klaviatura fokus halqası (U-9)

`.sidebar-menu-link` (profil sol menyu, CSS ölçü budcəsi ilə DONDURULMUŞ
`profile/sidebar.css`-də deyil) və off-canvas bağlama düyməsi
(`.blog-header__toggle`, `navbar.css`-də — 983 sətir, DONDURULUB) üçün heç bir
`:focus-visible` qaydası yox idi (`grep focus` → 0). Dondurulmamış ortaq
`static/css/ems_components.css`-ə (169→182 sətir, limit daxilində) əlavə
edildi:

```css
.sidebar-menu-link:focus-visible,
.blog-header__toggle:focus-visible {
    outline: 2px solid var(--ems-primary-600);
    outline-offset: 2px;
}
```

`ems_components.css` `base.html`-də `navbar.css`-dən SONRA yüklənir və hər iki
hədəf selektorda əvvəllər `outline` sıfırlanmadığı üçün kaskad
münaqişəsi yoxdur. **Yoxlanıldı** — izolyasiya edilmiş statik səhifədə
(faktiki `design-tokens.css` + `ems_components.css` yükləyərək) Tab düyməsi
ilə hər iki elementə fokuslanıb mavi halqa + 2px offset vizual təsdiqləndi
(brauzer paneli, klaviatura hadisəsi — `element.focus()` deyil, çünki
`:focus-visible` skript-fokusda BƏZƏN tətbiq olunmur).

---

## 5. Testlər və qapılar

### Testlər (81 keçdi, 0 uğursuz — mənim dəyişikliyimə aid)

```
apps/accounts/tests/test_profile_i18n_role_matrix.py .......... 3 passed
apps/accounts/tests/test_sidebar_role_matrix.py ................ 13 passed
apps/accounts/tests/test_profile_refactor_characterization.py .. 23 passed
apps/accounts/tests/test_staff_position_labels.py .............. 17 passed
apps/notifications/tests/test_services_refactor_characterization.py . 20 passed
apps/organizations/tests/test_role_badge_label.py .............. 5 passed
```

İki mövcud test (`test_staff_position_labels.py::
test_visible_role_label_blanks_placeholder`,
`test_role_badge_label.py::test_real_role_renders_its_display_name` +
`test_template_usage_hides_empty_badge`) KÖHNƏ (xətalı) davranışı — xam
`"Dean"`/`"Teacher"` gözləyirdi; PHASE21 U-2-nin məhz bu bug-ı düzəltdiyi üçün
gözlənilən nəticələr `"Dekan"`/`"Müəllim"`-ə yeniləndi + admin-customization
qorunması üçün 1 yeni test əlavə edildi
(`test_customized_display_name_is_untouched`).

`apps/accounts/tests/test_profile_views.py::
test_superadmin_can_hard_delete_soft_deleted_pending_org_owner` — ilk işə
salınmada `exams_questionsubmission.chair_reviewer_id does not exist` ilə
uğursuz oldu; tamamilə TƏMİZ, ayrıca DB-də TƏKRAR işə salınanda KEÇDİ.
Kök səbəb: paralel agentin `apps/exams/models.py`-ə yeni sahə əlavə edib
migrasiyasını hələ yazmadığı an paylaşılan Postgres cluster-ə düşmək — mənim
dəyişikliyimlə ƏLAQƏSİ YOXDUR (fayl toxunulmayıb, davranış mənim işimdən
ƏVVƏLKİ commit-də də eynidir).

### Gate-lər

```
black --check ✓        (core/roles.py, core/staff_position.py, org_tags.py,
                         applications.py, 2 test faylı)
isort --check-only ✓
flake8 ✓
check_module_size.py --check ✓ (SOFT_CAP=600 — models.py-a əvəzinə
                                 org_tags.py-a süzgəc yazılaraq keçildi)
module_deps.py --check ✓ (0 yeni dövr)
check_i18n_catalogs.py ✓ (mənim işim yoxlanılanda — bax §1 qeydi)
msgfmt --check ✓ (4 lokal × 2 domen)
```

---

## 6. Toxunulmayan (paralel agent əhatəsi)

* `apps/syllabus/**`, `apps/organizations/default_roles_university.py`,
  `apps/organizations/migrations/0035_dean_syllabus_review_only.py`,
  sillabus review şablonları — FAZA 6 agentinə aiddir.
* `apps/exams/**` (chair review / question_submission) — başqa paralel
  agentə aiddir (son gate run-da görünən `source_missing` artımının mənbəyi).
* `apps/organizations/models.py` — 600 sətir SOFT_CAP-i keçməmək üçün
  bilərəkdən dəyişdirilmədi (əvəzinə `org_tags.py` süzgəci).

---

## 7. Fayllar

**Kataloqlar:** `locale/{az,en,ru,tr}/LC_MESSAGES/{django,djangojs}.{po,mo}`
(16 fayl) · `scripts/i18n_baseline.json`

**Rol etiketi:** `core/roles.py` · `core/staff_position.py` ·
`apps/organizations/templatetags/org_tags.py` ·
`apps/accounts/views/profile/_sections/applications.py` ·
`templates/organizations/partials/{_kafedras_content,_members_content,
_roles_content}.html` ·
`apps/accounts/templates/accounts/partials/_role_assignment_content.html`

**my-courses:** `apps/accounts/templates/accounts/profile/_sidebar.html` ·
`apps/accounts/templates/accounts/profile/sections/_my_courses.html`

**Fokus halqası:** `static/css/ems_components.css`

**Testlər:** `apps/accounts/tests/test_staff_position_labels.py` ·
`apps/organizations/tests/test_role_badge_label.py`
