# Starosta — təyinat + kabinet bölməsi (2026-10-13, gecə)

Sahibin sözləri: «qrupa starosta əlavə etmək yerinə yenidən bax, problem olan hissəni dəyiş»; «starosta kabinetdə
əsas üstünlüyü o olmalıdır ki, seçmə fənn ya da başqa qrupun nə işi olarsa görünsün»; «Qrupum yerinə Starosta
bilinsin».

## 1. Təyinat — tapılan problemlər

| Yol | Problem | Həll |
|---|---|---|
| «Rol təyin et» (`role_assignment`, `update_member`) | Tələbənin YEGANƏ üzvlüyünün rolu yerində `lead_student` olurdu, `scope_unit` boş qalırdı → bölmə açılmırdı (QA hesabı); `student` rolu itirdi | `lead_student` rədd olunur (409, «Qruplar» reyestrinə yönləndirmə) — `_resolvers.py` |
| «Rolları idarə et» (`grant_role`) | İstənilən `scope_unit` (fakültə, başqa qrup); qrupa 2 starosta; tələbə yoxlaması yox | `lead_student` rədd olunur — `_multi_role.py` |
| Köhnə checkbox (`_sync_user_role_memberships`) | `scope_unit=None` ilə yaradır, qrupa bağlı sətri səssiz söndürürdü | `LEAD_STUDENT` redaktə dəstindən çıxarıldı — `membership.py` |
| Heç bir yol | Audit/bildiriş yox, reyestrdə görünmür, dəyiş/götür yox | Yeni xidmət + UI (aşağıda) |
| Bölmə qapısı | Köçürülmüş/xaric starosta köhnə qrupu görürdü | Qapı baxanın HƏMİN qrupda qeydiyyatlı tələbə olmasını tələb edir — `rbac_my_group.py` |

## 2. Yeni axın

* Xidmət `apps/accounts/services/group_lead.py`: `assign_group_lead` / `remove_group_lead` / `group_lead_map`.
  Qaydalar: yalnız qrupun aktiv+qeydiyyatlı tələbəsi; bir qrupda bir starosta (yeni təyinat köhnəni götürür,
  qrup sətri `SELECT … FOR UPDATE`); üzvlük ƏLAVƏDİR (`student` toxunulmur), götürmə deaktiv edir (silmir);
  tələbənin başqa əhatəli köhnə starosta sətirləri söndürülür; audit (`log_action`, `event` = assigned /
  replaced / removed); bildiriş (commit-dən sonra) təyin olunana və götürülənə; `UserProfile.role` sinxronu.
* Endpoint `POST /accounts/groups/lead/` (`accounts:group_lead_action`) — qapı: `unit.group_manage` VƏ YA
  `role.assign` + hədəf qrup həmin açarın əhatəsində (kənar → 404).
* UI: «Qruplar» reyestrində yeni **Starosta** sütunu (ad / «qrupda deyil» / «bir neçə starosta» xəbərdarlığı);
  tələbə çekmecəsində starosta paneli + «Starosta təyin et / Starostanı dəyiş / Götür» dialoqları; seçim
  yalnız açıq qrupun qeydiyyatlı tələbələri (çekmecənin artıq yüklədiyi siyahıdan, styled bootstrap select +
  axtarış); çekmecə sətirində «Starosta» nişanı.
* Ops: `manage.py repair_group_leads --org <slug>` (defolt quru qaçış; `--apply` konservativ düzəliş:
  əhatəsiz/qrup olmayan əhatəli sətir → tələbənin tək qrupuna bağlanır, həmin qrupda etibarlı starosta yoxdursa;
  qrupda olmayan starosta → deaktiv; dublikat → əl ilə).

## 3. «Starosta» bölməsi (açar `my-group` saxlanılıb)

Tab-lar (ortaq `ems_ui/nav.js`): **Fənlər** (məcburi/seçmə, müəllim, «kimlərlə», qrupdan neçə nəfər) ·
**Seçmə fənlər** (blok adı, götürənlərin ADLARI) · **Birləşmiş dərslər** (başqa qrupun jurnalı, jurnala başqa
qrupdan əlavə, alt qruplar/ana qrup) · **Cədvəl** (gün kartları, axın mühazirəsində birgə qruplar, «qrupdan N
tələbə») · **İmtahanlar** (90 gün, qrupa/ana qrupa təyin və ya qrup açılışlarının kursu) · **Elanlar** (qrupa /
ixtisasa / fakültəyə ünvanlanmış tələbə elanları; təşkilat-geniş elanlar «Elanlar» bölməsindədir) ·
**Qrup yoldaşları** (ad + nömrə) · **Davamiyyətim** (yalnız özü).

Məxfilik (sahib qərarı qüvvədədir): yoldaşların balı/qayıbı yoxdur; **təkrar (retake) qeydiyyatlar** qrup
mənzərəsinə düşmür (kimin fənni təkrar götürdüyü şəxsi məlumatdır); başqa qrupların fənləri yalnız qrup
tələbəsi orada oxuyursa görünür.

Modullar: `apps/registrar/group_academic.py`, `apps/registrar/group_timetable.py`,
`apps/announcements/services/group_feed.py` (public: `group_announcements`), tag-lar
`registrar_my_group.my_group_academic`, `my_group_tags.my_group_announcements`. Sorğu sayı tələbə/fənn sayından
asılı deyil (~11 sorğu, yalnız starosta üçün).

Ad: sidebar, bölmə başlığı (`labels.py`), AI köməkçi linki — «Starosta».

## 4. Yoxlama

* Testlər: `apps/accounts/tests/test_starosta_2026_10_13.py` (17 test: təyin/dəyiş/götür, yalnız qrup tələbəsi,
  əhatə 404/403, `role.assign`, sınıq sətrin bərpası, köçürülmüş starosta, `grant_role` rəddi, reyestr sütunu,
  repair əmri, bölmə məzmunu: seçmə + adlar, birləşmiş + alt qrup, cədvəl/imtahan/elan, məxfilik);
  köhnə `test_role_audit_b_lead_2026_10_13.py` (12) keçir.
* Qapılar: black/isort/flake8, `check_inline_assets`, `check_module_size --check`, `public_api_boundaries`,
  `module_deps`, `context_map`, `check_worker_atomic_coverage`, `check_i18n_catalogs`,
  `makemigrations --check` — hamısı yaşıl. Miqrasiya YOXDUR.
* i18n: `scripts/i18n_fill_starosta_2026_10_13.py` (az/en/ru/tr, 90 giriş).
* A11y (WCAG 2.1 AA öz-auditi): seçicidə `aria-required` + `aria-describedby`, xəta `role="alert"`,
  ikonlar `aria-hidden`, cədvəllərdə `caption`, toxunma ekranında `summary` ≥44px, mobil tab zolağı üfüqi
  sürüşür (səhifə sürüşmür).

## 5. Səhər üçün

1. Deploydan sonra prod-da: `manage.py repair_group_leads --org qku` (quru) → nəticəyə bax → `--apply`.
2. Mövcud starostalar əvvəlki axınla verilibsə (`scope_unit` boş), repair-dən sonra bölmə açılacaq.
3. RİM/koordinator: «Qruplar» → qrup → «Tələbələr» → «Starosta təyin et».
