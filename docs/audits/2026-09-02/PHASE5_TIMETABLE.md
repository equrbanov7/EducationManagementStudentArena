# FAZA 5 — Dərs cədvəli (timetable) idarəetməsi

Branch `audit/post-migration-qa-2026-09` · 2026-09-02

## 1. İcazə modeli

Yeni kanonik açarlar — `apps/organizations/permissions.py`, kateqoriya `schedule`
(«Dərs cədvəli»), hər ikisinin AZ etiketi `PERMISSION_LABELS`-dədir:

| açar | mənası |
|---|---|
| `schedule.view` | cədvələ baxış (kataloq bütövlüyü) |
| `schedule.manage` | cədvəl slotu əlavəsi/silinməsi |

Default rollar (`apps/organizations/default_roles_university.py`):

| rol | əhatə |
|---|---|
| `program_coordinator` (lvl 45, UNIT) | öz ixtisasının alt-ağacı — cədvəlin **əsas sahibi** |
| `ikt_rehber` / RİM (lvl 88, ORGANIZATION) | org-wide |
| `dean` (lvl 80, UNIT) | öz fakültəsinin alt-ağacı |
| `chair_head` (lvl 70, UNIT) | öz kafedrasının alt-ağacı |
| `rector` / `vice_rector` / org sahibi / superuser | `*` ilə org-wide |

**`teacher` QƏSDƏN almır.** Açar permission-editordan istənilən rola verilə bilər
(qapı rol adına yox, açara baxır).

**Miqrasiya:** `apps/organizations/migrations/0033_schedule_manage_permission.py`
(`dependencies = [("organizations", "0032_seed_alumni_role")]`; idempotent forward,
reverse hər iki açarı bütün rollardan çıxarır; `*` daşıyan rollara toxunmur).
Uyğunluq testi: `apps/organizations/tests/test_permissions.py::
DefaultRolePermissionComplianceTest::test_default_roles_permissions_are_all_valid`
(mövcud test yeni açarları avtomatik əhatə edir — `validate_permissions` kataloqa baxır).

## 2. Server qapısı (əvvəl → indi)

Əvvəl `apps/registrar/schedule_views.py` yalnız `journal_access.is_direct_editor`-a
baxırdı (dərsi aparan müəllim / org sahibi / superuser). İndi:

* `apps/registrar/schedule_manage.py` — icazə + əhatə + validasiya (oxu qatı);
* `apps/registrar/schedule_manage_actions.py` — yazma + audit + bildiriş.

`_handle_add_slot` və `schedule_slot_delete` indi
`schedule_manage.can_manage_offering()` tələb edir: superuser / org sahibi VƏ YA
`schedule.manage` + açılışın **qrup OrgUnit-inin** aktorun alt-ağacında olması.
Uğursuzluqda **403** (`PermissionDenied`). Açılışın müəllimi olmaq artıq
səlahiyyət VERMİR.

**Modul sərhədi qorunub:** registrar `apps.organizations`-u statik import etmir —
`django_apps.get_model("organizations", "OrgUnit")` + mövcud
`OrgUnit.user_permission_scope` / `journal_scope.offering_in_actor_scope`
(`scripts/module_deps.py --check` yaşıl, yeni kənar yoxdur).

**Saxlama-öncəsi validasiya** (heç nə yazılmır — prevent, don't save):
weekday 1–7 · `end_time > start_time` · dövr bitibsə bloklanır (`period_window_error`) ·
eyni slotun təkrarı · `find_conflict` (qrup / müəllim / otaq) + səbəb etiketi
(«qrup» / «müəllim» / «auditoriya») və konflikt slotunun tam təsviri.

## 3. Kabinet bölməsi — «Cədvəl idarəetməsi»

Bölmə açarı `schedule-manage`, etiket `pgettext_lazy("profile.sidebar",
"Cədvəl idarəetməsi")` (az/en/ru/tr). Profil shell-inin İÇİNDƏ açılır — sol
sidebar qalır, panel sağdadır; AJAX-safe (`AJAX_SAFE_SECTIONS`).

Görünürlük: `apps/accounts/views/_helpers/rbac_sections.py` →
`can_manage_schedule = privileged or has_permission(permissions, "schedule.manage")`
(rol adı ilə DEYİL).

Panel məzmunu: tədris ili + semestr seçicisi (kollokvium panelinin qaydası) →
qrup seçicisi (bootstrap-select, axtarışlı, aktorun əhatəsi ilə məhdud; RİM hamısını
görür) → həftə grid-i (`_schedule_content.html` + `build_time_grid` yenidən
istifadə olunur, `role="manage"`) → slot cədvəli (silmə düyməsi + təsdiq modalı) →
«Slot əlavə et» forması (fənn/növ/gün/`STANDARD_LESSON_TIMES` + sərbəst vaxt /
otaq `<datalist>` = `exams.ExamRoom` adları / həftə tipi) + **«Konflikti yoxla»**
(AJAX, saxlamadan əvvəl) və inline sahə xətaları. «Müəllim cədvəli» toggle-ı
`get_teacher_schedule` ilə bir müəllimin həftəsini göstərir.

CSS/JS xarici fayllardadır (CSP), dinamik dəyərlər `data-*` atributları ilə;
JS `EMSDelegate` + `EMSCore.fetchJSON` işlədir. Hər fayl < 600 sətir
(`check_module_size.py --check` yaşıl).

JSON səthi: `accounts:schedule_manage_check` (POST, yalnız yoxlayır) və
`accounts:schedule_manage_action` (POST, `add`/`delete` allow-list-i).

## 4. Yayım (audit + bildiriş)

* **Audit:** `core.audit.log_action` — `AuditAction.CREATE` / `DELETE`,
  `resource_type="registrar.ScheduleSlot"`. **Yeni audit `action` növü LAZIM
  OLMADI** → əlavə miqrasiya yoxdur.
* **Bildiriş:** `apps/notifications/public.create_notification_for_users` —
  açılışın müəllimi + qrupun `ENROLLED` tələbələri, TƏK bulk insert,
  `transaction.on_commit` (rollback olarsa heç kim yalan xəbər almır; bildiriş
  nasazlığı əməli geri qaytarmır). Başlıq: «Dərs cədvəli dəyişdi: <fənn> <gün>
  <saat>», link → `?section=my-schedule` (org-scoped),
  `metadata={"event": "schedule_changed", ...}`.

## 5. Müəllim nə edə bilir / edə bilmir

| əməl | əvvəl | indi |
|---|---|---|
| öz həftəlik cədvəlinə baxmaq (`my-schedule`, `/jurnal/cedvel/`) | ✅ | ✅ dəyişməz |
| «Slot əlavə et» düyməsi | ✅ | ❌ render olunmur |
| «Slotu sil» düyməsi | ✅ | ❌ render olunmur |
| `POST /jurnal/cedvel/` (slot əlavəsi) | ✅ | ❌ **403** |
| `POST /jurnal/cedvel/slot/<id>/sil/` | ✅ | ❌ **403** |
| `accounts:schedule_manage_check` / `_action` | — | ❌ **403** |
| «Cədvəl idarəetməsi» bölməsi / sidebar sətri | — | ❌ 403 / görünmür |

Tələbə: `my-schedule` əvvəlki kimi qrup cədvəlini göstərir (yalnız-oxu).
Koordinator/RİM/dekan/kafedra müdiri idarəetməni YALNIZ yeni bölmədə görür.

## 6. Dəyişən / əlavə olunan fayllar

**Yeni**
- `apps/registrar/schedule_manage.py` (297 sətir)
- `apps/registrar/schedule_manage_actions.py` (231)
- `apps/accounts/views/schedule_manage.py` (149)
- `apps/accounts/views/profile/_sections/schedule_manage.py` (~235)
- `apps/accounts/templates/accounts/profile/sections/_schedule_manage.html` (285)
- `apps/accounts/static/accounts/css/schedule_manage.css` (336)
- `apps/accounts/static/accounts/js/schedule_manage.js` (261)
- `apps/organizations/migrations/0033_schedule_manage_permission.py`
- `apps/registrar/tests/test_schedule_manage.py` (418, 26 test)
- `scripts/i18n_fill_schedule_manage.py` (4 dil × 63 giriş)

**Dəyişən**
- `apps/organizations/permissions.py` — `schedule` kateqoriyası + etiketlər
- `apps/organizations/default_roles_university.py` — 4 rola açar
- `apps/registrar/schedule_views.py` — qapı `schedule.manage`-ə keçdi
- `apps/registrar/page_contexts.py` — `schedule_can_manage`, `schedule_next_url`
- `apps/registrar/templates/registrar/partials/_schedule_content.html`,
  `_schedule_row.html` — idarəetmə düymələri `schedule_can_manage` ilə qapılı,
  `role="manage"` görünüşü, inline `onsubmit="confirm(...)"` ÇIXARILDI (CSP)
- `apps/registrar/static/registrar/js/schedule_grid.js` — silmə təsdiqi xarici JS-də
- `apps/accounts/views/_helpers/rbac_sections.py` — `can_manage_schedule` qapısı
- `apps/accounts/views/profile/_sections/labels.py`, `sections_api.py`,
  `context_builder/_stage2..4.py`, `apps/accounts/urls.py`,
  `apps/accounts/views/__init__.py`,
  `templates/accounts/profile.html`, `profile/_sidebar_university.html`
- `apps/registrar/tests/test_schedule_views.py` — gözləntilər yeniləndi
- `locale/{az,en,ru,tr}/LC_MESSAGES/django.po` (+ `.mo`)

## 7. Testlər

`apps/registrar/tests/test_schedule_manage.py` — 4 sinif / 26 test:
icazə matrisi (koordinator daxil/xaric-əhatə, müəllim, RİM, helper-lər,
default rolların açarı), validasiya (tərs saat, səhv gün, təkrar slot, qrup
konflikti, otaq konflikti, bitmiş dövr, konfliktli slot HEÇ VAXT yazılmır,
müəllimə `check` 403), yayım (audit sətri + bildiriş alıcıları, `add`/`delete`,
müəllimə 403, naməlum `action` 400), bölmə görünürlüyü (koordinator/RİM 200,
müəllim/tələbə 403, `my-schedule` yalnız-oxu).

`apps/registrar/tests/test_schedule_views.py` yeniləndi:
`test_teacher_sees_own_schedule_read_only`, `test_teacher_cannot_add_slot` (403),
`test_permission_holder_adds_slot` (yeni `sv_manager` = RİM üzvlüyü), konflikt
testi səlahiyyətli aktora keçdi, fixture dövrü CARİ tarixlərə köçdü.

**Nəticə (private DB `ems_tt_1230527765`, agent postgres :55432):**

```
apps/registrar/tests/test_schedule_views.py ......        (6)
apps/registrar/tests/test_schedule_manage.py .......…..   (26)
================= 32 passed in 50.12s =================
```

* `apps/accounts/tests/test_sidebar_role_matrix.py` → **12 passed** (matris
  dəyişmədi: yeni bölmə icazə-qapılıdır, boş-permission test rollarına düşmür).
* `apps/registrar/tests/test_schedule.py` → **11 passed** (servis qatı toxunulmadı).

Aralıq qaçışlarda 3 uyğunsuzluq tutuldu və düzəldildi: 2 × bildiriş
`transaction.on_commit`-də olduğu üçün `TestCase`-də icra olunmurdu
(`captureOnCommitCallbacks(execute=True)`), 1 × `test_schedule_views` fixture
dövrü KEÇMİŞ tarixli idi (yeni dövr-pəncərəsi validasiyası onu haqlı bloklayırdı).

## 8. Canlı yoxlama (QA klonu `emsarena_rehearsal_a0d170000901`)

Miqrasiya tətbiq olundu:
`Applying organizations.0033_schedule_manage_permission... OK`

Rol sətirləri klonda (SQL): `chair_head|t · dean|t · ikt_rehber|t ·
program_coordinator|t · teacher|f`.

`qa.program_coordinator` üzvlüyündə `scope_unit = «Dizayn (Qrafik)»` (ixtisas)
ARTIQ var idi — əlavə təyinat lazım olmadı. Əhatə: `scope=unit`, **11 qrup**.
`qa.ikt_rehber` → `scope=org`. `qa.teacher` → `can_manage=False`.

Django test client (force_login, `active_organization=myedu-univ`):

| yoxlama | nəticə |
|---|---|
| `schedule-manage` fraqmenti — koordinator / RİM / dekan | **200 / 200 / 200** |
| `schedule-manage` fraqmenti — müəllim / tələbə | **403 / 403** |
| `check` — KÖÇÜRÜLMÜŞ (bitmiş) semestr | `ok:false`, `period: «Bu semestr bitib…»` |
| `check` — təmiz slot | `ok:true` |
| `add` (Cümə 16:55–18:25, otaq QA-901) | **200**, slot yaradıldı |
| `check` — eyni slot təkrar | `ok:false`, `time_slot: «Bu slot artıq cədvəldədir.»` |
| `check` — üst-üstə düşən vaxt | `ok:false`, `conflict: «…MYEDU-L4 ilə üst-üstə düşür (qrup)»` + konflikt slotu |
| `check` — `weekday=9` | `ok:false`, `weekday: «Həftənin günü 1–7 aralığında olmalıdır.»` |
| bildiriş / audit (add) | **+10 bildiriş** (müəllim + 9 tələbə), **+1 audit** |
| müəllim: `action` / `check` / registrar `slot/sil/` | **403 / 403 / 403** |
| tələbə `my-schedule` fraqmenti | **200** |
| koordinator paneli slotu göstərir | **200**, `QA-901` HTML-də var |
| `delete` | **200**, slot silindi |
| bildiriş / audit (yekun) | **+20 bildiriş**, **+2 audit** |

⚠️ **Tapıntı (kod problemi deyil):** klonda 2026-09-02 tarixini əhatə edən
akademik dövr YOXDUR — ən son «Yay 2025/2026» 2026-08-31-də bitib. Yəni real
datada cədvəl qurmaq üçün əvvəlcə **2026/2027 Payız semestri yaradılmalıdır**;
yeni dövr-pəncərəsi validasiyası bunu istifadəçiyə açıq mesajla göstərir.
Canlı axın üçün MÜVƏQQƏTİ QA dövrü + QA açılışı yaradıldı və sonda **SİLİNDİ**
(`CLEANUP: QA offering + period removed: True`) — köçürülmüş dataya toxunulmadı.

## 9. Qapılar

| qapı | nəticə |
|---|---|
| `black --check` (20 fayl) | ✅ |
| `isort --profile black --check-only` | ✅ |
| `flake8` | ✅ |
| `scripts/check_module_size.py --check` | ✅ |
| `scripts/module_deps.py --check` | ✅ (yeni dövr/kənar yoxdur) |
| `makemigrations --check --dry-run` (sqlite) | ✅ `No changes detected` |
| `scripts/i18n_fill_schedule_manage.py` | ✅ 4 dil × +63 giriş, `msgfmt` OK |
| `scripts/check_i18n_catalogs.py` | ⚠️ TAMAMLANMADI — bax §10 |

## 10. Qalan iş

1. `scripts/check_i18n_catalogs.py` son qaçışı təsdiqlənmədi: paralel işləyən
   başqa agent `compilemessages` icra edərkən qapı yarımçıq yazılmış `.mo` faylını
   oxuyub `struct.error: unpack requires a buffer of 4 bytes` ilə çökdü (host
   sonra yenidən başladı). Sətirlər `.po`-lara ƏLAVƏ OLUNUB və `msgfmt --check-format`
   dörd dildə də təmiz keçib; qapını `compilemessages` bitəndən sonra bir dəfə
   təkrar işlətmək lazımdır.
2. Brauzerdə vizual yoxlama (`http://127.0.0.1:8100`) edilmədi — host yenidən
   başladığı üçün QA serveri qaldırılmadı. Panel Django test client ilə tam
   yoxlanıb (yuxarıdakı cədvəl), amma CSS/JS-in real render-i gözlə görülməyib.
3. `schedule.view` açarı hazırda heç bir səthi qapıMIR (kataloq bütövlüyü üçün
   əlavə olunub) — istənilsə «cədvələ ümumi baxış» səthi ona bağlana bilər.
4. Otaq hələ də `CharField`-dir (`exams.ExamRoom` yalnız `<datalist>` təklifi kimi
   verilir). Room/Building vahidləşdirilməsi ayrıca iş olaraq qalır.
