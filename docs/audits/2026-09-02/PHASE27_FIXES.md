# FAZA 27 → düzəlişlər — R-8 (P0), R-2, R-1/R-4

**Tarix:** 2026-09-02 · **Branch:** `audit/post-migration-qa-2026-09` · **Commit edilməyib**
**Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (:55433) — prod `emsarena_db` (:5432)
**heç vaxt açılmadı**. pytest: **öz** bazam `ems_prf_k7x2` (:55432); tam dəst işlədilmədi
(sahibin qaydası). Hər defekt üçün **əvvəlcə qırmızı test**, sonra düzəliş, sonra klonda
canlı təsdiq.

---

## 0. Yekun

| # | tapıntı | vəziyyət | qırmızı→yaşıl test | klonda canlı təsdiq |
|---|---|---|---|---|
| **R-8** | Köçürülmüş 8 328 hesab nə girə, nə bərpa edə bilirdi (P0) | ✅ **DÜZƏLDİ** | `apps/accounts/tests/test_migrated_password_reset.py` (4) | `myedu.student.9` bərpa → **giriş** → `/accounts/kabinet/` |
| **R-2** | Kafedra müdiri sillabusu heç vaxt görmürdü | ✅ **DÜZƏLDİ** (+ struktur kəşfi) | `apps/syllabus/tests/test_chair_unit_resolution.py` (7) | real ucdan yaradılan qaralama → `chair_unit` = **kafedra**, `qa.chair_head` görür |
| **R-1/R-4** | Bitmiş `is_current` dövr cədvəli görünməz edirdi | ✅ **DÜZƏLDİ** | `apps/registrar/tests/test_schedule_period_selection.py` (6) | koordinator 2026/2027 Payıza slot yazdı → müəllim + tələbə **gördü** (`is_current` toxunulmadı) |

Əlavə: `provision_student_credentials`-a **`--group`** filtri (parol siyahısı praktikada
qrup-qrup çap olunur) + 2 test. Cutover addımları `docs/migration/HANDOFF_2026_08_27.md`
**§8.9 «Girişin açılması»**-dadır (§8.8 adı artıq tutulduğu üçün 8.9).

---

## 1. R-8 — köçürülmüş hesab girişi (P0)

### Kök səbəb
Django-nun `PasswordResetForm.get_users()` `has_usable_password()` olmayan hesabı
QƏSDƏN süzür (LDAP/sistem hesabları üçün doğru defolt). Köçürmə isə kredensialları
qəsdən gətirmir (`services/rim/credentials.py`), yəni **hədəf qrupun HAMISI** məhz belə
görünür. Nəticə: səhifə «göndərildi» deyir, `outbox` boşdur. İkinci kilid: OTP-ni
qəbul edən forma da (`OTPPasswordResetCodeForm.clean`) `has_usable_password()` tələb
edirdi — yəni poçt getsəydi də bərpa tamamlanmazdı.

### Düzəliş
| fayl | dəyişiklik |
|---|---|
| `apps/accounts/identity.py` | `PLACEHOLDER_EMAIL_DOMAIN` + `email_is_placeholder()` — yer-tutucu e-poçtun TƏK mənbəyi (bazaya sorğu YOX → enumerasiya sızmır) |
| `apps/accounts/forms/auth/login.py` | `get_users()` tam override: meyar **girişin açıq olması** (`is_active` + `access_state` ∉ {`staged`,`archived`}), parolun mövcudluğu deyil; uyğunluq DB-nin kanonik (NFKC+trim+lower) ifadə indeksləri ilə eyni formadadır (`canonical_identity_queryset`) — Django-nun `iexact`-i NFKC normallaşdırmır. `clean_email()` yer-tutucu domendə RİM göstərişi verir |
| `apps/accounts/forms/otp.py` | `has_usable_password()` şərti çıxarıldı (bu formanın İŞİ ilk parolu qoymaqdır; e-poçt sahibliyini OTP sübut edir) + `mark_self_service_password_set()`: bərpadan sonra `password_change_required=False`, `email_verified=True` |

`mark_self_service_password_set` niyə doğrudur: ilk-giriş səhifəsinin tələb etdiyi İKİ
şey (öz e-poçtunu OTP ilə təsdiqlə + öz parolunu qur) bərpa axınında onsuz da baş verir.
**RİM-in verdiyi müvəqqəti parol yolu TOXUNULMUR** — orada parolu operator qoyur,
e-poçt sahibliyi sübut olunmur, bayraq qalxıq qalır.

### Qırmızı → yaşıl
Qırmızıda: `outbox 0 != 1`, yer-tutucu e-poçt 302 (səssiz «done»). Yaşılda 4 test:
aktiv+real e-poçt → poçt gedir və **bərpadan sonra giriş işləyir + kabinet açılır**;
`staged`/`archived` → heç nə; yer-tutucu → göstəriş, poçt yox; **hesabı olmayan**
yer-tutucu ünvan da eyni cavabı alır (enumerasiya sızmır).

### Klonda canlı (in-process, `locmem` outbox — real poçt GETMƏDİ)
```
target: myedu.student.9 (gmail.com, unusable)
reset POST → 302, outbox 1 ✓   OTP ilə tamamlama → 302 ✓   has_usable_password → True ✓
portal login → 302 → /accounts/kabinet/ ✓   profile 200 ✓   my-schedule 200 ✓
archived myedu.student.141 → outbox 0 ✓
placeholder myedu.student.37 → 200 + «RİM-ə müraciət» ✓ outbox 0 ✓
RİM (qa.ikt_rehber) → set_password myedu.student.11 → 200, 12 simvol bir dəfə, giriş ✓
provision_student_credentials --group "634 Qrafik" --generate --dry-run → 26 tələbə ✓
provision_student_credentials --org myedu-univ --generate --dry-run → 7 602 tələbə ✓
TƏMİZLİK: parol/bayraqlar/OTP sətirləri bərpa olundu (yoxlanıldı)
```
⚠️ **Prod ön şərti:** işlək SMTP. `EMAIL_BACKEND` konsol qalarsa A qapısı səssizcə sınır.
⚠️ Kütləvi əmr prod-da `ProductionCommandSafetyMixin` ilə **bloklanıb** (qəsdən) —
runbook A + C qapıları üzərində qurulub (bax §8.9).

---

## 2. R-2 — sillabusun kafedra bağı

### Düzəliş
`apps/syllabus/services/units.py` (yeni): `resolve_chair_unit()` bölmədən yuxarı
`chair`/`department` tipli ilk əcdadı tapır (gəzişmə `apps.organizations.unit_heads.
resolve_ancestor`-dadır — yeni scope məntiqi icad edilmir); tapılmasa dəyər QALIR.
Normallaşdırma `create_draft`-in İÇİNDƏDİR — hər yeni çağıran səth qaydanı təkrar
yazmır. `syllabus_repair_chair_units` (dry-run defolt, `--apply`, auditli, idempotent)
mövcud sətirləri düzəldir.

### ⚠️ Klonda ölçülmüş STRUKTUR kəşfi — kod tək kifayət etmirdi
```
ixtisas → əcdadda kafedra: 0/83   (83 ixtisasın parent-i FAKÜLTƏdir)
qrup    → əcdadda kafedra: 0/766
18 kafedranın övlad sayı: 0
mənbə (myedudb): speciality.department_id → 80 sətir type=3 (fakültə), 3 sətir type=0
```
Yəni **mənbə datasının özündə ixtisas↔kafedra tili yoxdur** — ağac gəzişməsi bu
tenant-da heç vaxt kafedra tapa bilməz. Amma müəllimin özü kafedraya bağlıdır:
**702 aktiv `teacher` üzvlüyünün `scope_unit`-i `chair` tipindədir.**

Ona görə həll iki pilləlidir (`resolve_syllabus_chair_unit`):
**struktur əcdadı → müəllifin aktiv kafedra üzvlüyü → verilən dəyər (fail-soft)**.
Sıra qəsdlidir: ağacda kafedra varsa həqiqətin özü odur; yoxdursa müəllifin üzvlüyü
yeganə real bağdır; heç nə yoxdursa köhnə dəyər saxlanılır (sahibsiz sillabus olmur).

### Klonda canlı
```
qa.teacher → POST /accounts/profile/syllabus/action/ {action:create} → 200
chair_unit = «Proqramlaşdırma və informasiya təhlükəsizliyi» (chair) ✓
qa.chair_head: has_review_scope True · can_view True ✓
syllabus_repair_chair_units (quru) → 0 sətir (mövcud 3 sillabus onsuz da kafedradadır)
TƏMİZLİK: yaradılan sillabus + 10 bölmə + 1 versiya silindi (sillabus sayı 3 → 3)
```
Testlər: `apps/syllabus/tests` (89) + `apps/accounts/tests/test_syllabus_review_section.py`
(19) + `apps/registrar/tests/test_journal_syllabus_bridge.py` (18) → **218 passed**.

> **Sahib qərarı hələ də lazımdır** (R-2-nin sənədləşdirilmiş sualı): sillabusu kafedra
> müdiri, yoxsa dekan təsdiqləyir? Kod indi hər ikisini mümkün edir (kafedra müdiri
> əhatəni müəllif üzvlüyündən alır, dekan org səviyyəsindən). Struktur həll (ixtisasları
> öz kafedralarına bağlamaq) **mənbədə data olmadığı üçün** ayrıca qərar tələb edir.

---

## 3. R-1/R-4 — cədvəldə dövr seçimi

### Düzəliş
`apps/registrar/schedule.py` → `resolve_display_period(organization, requested=…)`:
1. açıq `?period=<id>`;
2. cari dövr — **ƏGƏR bu gün onun tarixləri arasındadırsa**;
3. slotu olan ən yaxın GƏLƏCƏK dövr (`start_date ≥ bugün`);
4. slotu olan ən son dövr — **amma cari dövrdən geri getmədən**;
5. köhnə davranış (cari / ən son).

4-cü pillənin şərti canlı datadan gəldi: klonda 2022/2023 semestrindən qalma tək slot
«ən son slotlu dövr» kimi seçilirdi və istifadəçiyə **4 il köhnə** cədvəl göstərirdi.
Bu hal ayrıca testlə kilidlənib.

Seçici (R-4): `_schedule_content.html`-də jurnaldakı ilə **eyni `?period=` müqaviləsi** —
tədris ili + yarım il, `bootstrap-select` sarğısı, `sgx-term` ad məkanında öz CSS-i;
JS `schedule_grid.js`-də (delegated, profil SPA-sında `js-profile-section-link` ilə
shell içində qalır). Seçilmiş dövr həftə pillələrində İTMİR (`schedule_nav_prefix`-ə
`period=` əlavə olunur). Seçici yalnız MƏNALI dövrləri göstərir: slotu olanlar + cari +
seçilmiş. `schedule_manage`-in «bitmiş semestrə yazmaq olmaz» qaydası **toxunulmadı**.

CLAUDE.md: inline CSS/JS YOXDUR — dinamik dəyərlər `data-base-url` /
`data-selected-period` / `data-year` atributları ilə ötürülür.

### Klonda canlı
```
qa.program_coordinator → /accounts/schedule-manage/action/ {add, 2026/2027 Payız} → 200
myedu.worker.616 (müəllim) my-schedule → 200, «QA-PRF 707» GÖRÜNÜR, seçici var
myedu.student.7223      my-schedule → 200, «QA-PRF 707» GÖRÜNÜR, seçici var
seçici → ?period=<2025/2026 Yaz> → 200, slot gizlənir ✓
`is_current` DƏYİŞDİRİLMƏDİ (2025/2026 Yaz olaraq qaldı)
TƏMİZLİK: slot + açılış + 28 bildiriş silindi; iki hesabın ilk-giriş bayraqları bərpa olundu
```

---

## 4. Dəyişən fayllar

**Kod:** `apps/accounts/identity.py` · `apps/accounts/forms/auth/login.py` ·
`apps/accounts/forms/otp.py` · `apps/accounts/management/commands/provision_student_credentials.py` ·
`apps/syllabus/services/units.py` (yeni) · `apps/syllabus/services/drafts.py` ·
`apps/syllabus/management/commands/syllabus_repair_chair_units.py` (yeni) ·
`apps/registrar/schedule.py` · `apps/registrar/page_contexts.py`

**Frontend:** `registrar/partials/_schedule_content.html` · `registrar/css/schedule.css` ·
`registrar/js/schedule_grid.js`

**Testlər (yeni):** `apps/accounts/tests/test_migrated_password_reset.py` ·
`apps/syllabus/tests/test_chair_unit_resolution.py` ·
`apps/registrar/tests/test_schedule_period_selection.py` ·
(+ `test_provision_student_credentials.py`-a 2 test)

**Sənəd:** `docs/migration/HANDOFF_2026_08_27.md` §8.9 · bu fayl ·
`locale/{az,en,ru,tr}/LC_MESSAGES/django.{po,mo}` (3 yeni msgid × 4 dil)

---

## 5. Qapılar

```
black / isort / flake8 (dəyişən fayllar)      ✅
scripts/check_module_size.py --check          ✅ (SOFT_CAP=600; page_contexts 561, schedule 422)
scripts/module_deps.py --check                ✅ yeni dövr yoxdur
scripts/check_i18n_catalogs.py                ✅ (3 msgid 4 kataloqa əlavə + compilemessages)
makemigrations --check (sqlite)               ✅ No changes detected
pytest (hədəflənmiş modullar, baza ems_prf_k7x2)
  accounts auth/identity/otp/provision        114 passed, 1 skipped
  syllabus + review section + journal bridge  218 passed
  schedule (view/manage/period) + registrar   62 passed
```

### Bu düzəlişlərdən ƏVVƏL də qırmızı olan (mənə aid DEYİL)
* `apps/registrar/tests/test_corrections_bridge.py::CorrectionMediaAccessTest::test_pdf_denied_to_unrelated_user_allowed_to_owner`
  → `ImportError: _check_journal_correction_access` (`core/media_views.py` — bu işdə
  toxunulmayıb, son dəyişiklik `2e294a83` audit commit-indədir);
* `apps/registrar/tests/test_exam_eligibility_frozen.py::FrozenLookupIsBatched::…`
  → sorğu-sayı evristikası (`0.0 != 2`).

---

## 6. Klonda qalıq

**Sıfır.** Yaradılan hər obyekt (sillabus kaskadı, cədvəl slotu + açılış, 28 bildiriş)
silindi; dəyişdirilən hər hesab sahəsi (parol, `password_change_required`,
`email_verified`) və OTP sətirləri bərpa olundu — hər addımda yoxlama çap edilib.
`AcademicPeriod.is_current` **heç vaxt dəyişdirilmədi** (R-1 düzəlişinin mahiyyəti
məhz odur ki, buna ehtiyac qalmır).

> Qeyd: klonda **mənə aid olmayan** iki qalıq var — 2022/2023 semestrinə bağlı tək
> cədvəl slotu (`qa.sec.teacher_b`, PHASE23 fixture-i) və `myedu.student.4` üçün
> 18:26-da yaradılmış istifadə olunmamış `password_reset` OTP sətri (FAZA 27
> ölçmələrindən). Toxunmadım; ikisi də zərərsizdir, amma R-1-in «geriyə zaman
> səyahəti» pilləsini məhz o slot üzə çıxardı.

