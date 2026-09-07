# QA audit P2-8 — «Level …» və «Xaric olunanlar» psevdo-qruplar (2026-09-05)

**Hədəf.** Buraxılış şərti #4: köçürülmüş tenant datasında akademik QRUP kimi
görünən, lakin mənbədə status/kurs-koqortu kodlaşdıran `OrgUnit` sətirləri —
say, naxış, tələbə təsiri.

**Mühit.** Yalnız oxu — QA klonu
`127.0.0.1:55433/emsarena_rehearsal_a0d170000901` (tenant `myedu-univ`,
`MyEdu Universiteti (rehearsal)`). Real baza `emsarena_db` açılmayıb.
Sorğular `manage.py shell --settings config.settings.staging_inspect` və
birbaşa `psql` ilə aparılıb; heç bir yazı əməliyyatı yoxdur.

---

## 0. Bir abzasda

Dəqiq **72 «Level …»** və **2 «Xaric ол(un)anlar»** = **74 psevdo-qrup**
(`organizations_orgunit.unit_type='group'`) tapıldı — sahibin təsvir etdiyi
sayla tam üst-üstə düşür. Onlara bağlı **270 `StudentAcademicRecord`** sətri
var (239 «Level» + 31 «Xaric olanlar»), amma bunların için 70-i (74-dən) **0
tələbə qeydi olan boş konteynerdir** — yalnız **4 psevdo-qrupda real, canlı
tələbə var**. Bu 4-ü ÖZLƏRİ DƏ bir-birindən köklü şəkildə fərqlənir (aşağıda
5 naxış). Ən önəmli tapıntı: **bütün 270 sətrin statusu `enrolled`-dur** —
«Xaric olanlar» qrupundakı 31 nəfər də daxil olmaqla. Yəni mənbədəki xaric
statusu YALNIZ konteyner üzvlüyü ilə kodlaşdırılıb, `status` sahəsinə heç vaxt
yazılmayıb — bu, sadəcə görünüş qüsuru deyil, **davam edən giriş/hesab
qüsurudur** (bax §4).

---

## 1. Say və mənbə

| Sorğu | Say |
|---|---|
| `unit_type='group' AND name ILIKE 'Level%'` | **72** |
| adı `Xaric olunanlar`/`Xaric olanlar` (unit_type='group') | **2** |
| **CƏMİ psevdo-qrup** | **74** |
| Bunlara bağlı `StudentAcademicRecord` sətri (cəmi) | **270** |
| — «Level» tərəfi | 239 |
| — «Xaric» tərəfi | 31 |
| Tenant | `myedu-univ` (`526cfa63-4f80-4bba-a7a7-61c8fbb3d918`), TƏK tenant — bütün 74 həmin təşkilata aiddir |

İkinci konteynerin adı sahibin təsvirindəki kimi **«Xaric olunanlar»** deyil,
**«Xaric olanlar»**dır (yazım fərqi — `un` yoxdur). SQL axtarışı bunu ILIKE
`%xar%olun%` genişləndirməsi ilə tapdı; dəqiq ad üzrə axtarış (`Xaric
olunanlar`) onu qaçırardı.

---

## 2. Struktur yeri

| Qrup adı naxışı | Say | Fakültə → İxtisas | Qeyd |
|---|---|---|---|
| `Level - BM/D/Ph/PH/SE/YT/Ks N`, `Level - Group N` (1-27), `Level 0` | 68 | **İngilis dili mərkəzi** → **«Level»** (özü də `unit_type='specialty'` psevdo-ixtisasdır, ona bağlı `Program.name='Level'` VAR) | Yalnız 2-si real tələbə daşıyır (§3, naxış B) |
| `Level - FT Beginner 1`, `Level - FT Elementary 2`, `Level -FT Elementary 1` | 3 | Filologiya və Tərcümə → **Azərbaycan dili və ədəbiyyatı** (REAL ixtisas) | Hamısı boş |
| `Level 2025-2026` | 1 | Dizayn → **Dizayn (Qrafik)** (REAL ixtisas) | 228 real tələbə (§3, naxış C) |
| `Xaric olunanlar 2023` | 1 | Dizayn → **Dizayn (Qrafik)** (REAL ixtisas) | Boş |
| `Xaric olanlar` | 1 | Filologiya və Tərcümə → **Tərcümə** (REAL ixtisas) | 31 real tələbə (§3, naxış E) |

Yəni psevdo-qruplar təkcə öz «Level» psevdo-ixtisasının altında deyil — **3
real ixtisasın öz qrup siyahısını da çirkləndirir** (Azərbaycan dili və
ədəbiyyatı, Dizayn (Qrafik), Tərcümə).

---

## 3. Naxışlar (datadan çıxarılıb, fərziyyədən yox)

### Naxış A — Boş, tarixi «Level» konteynerləri (69 ədəd, 0 tələbə)

66 qrup «Level» psevdo-ixtisası altında (BM/D/Ph/SE/YT/Ks/Group N adlanma
sxemi — İngilis dili kurs-səviyyəsi koqortları) + 3 qrup real «Azərbaycan
dili və ədəbiyyatı» ixtisası altında (`Level - FT Beginner 1`,
`Level - FT Elementary 2`, `Level -FT Elementary 1`). Heç birində
`StudentAcademicRecord` yoxdur. **Risk: sıfır** — silinmə deyil, sadəcə
gizlətmə təklif olunur; toxunacaq tələbə qeydi yoxdur.

### Naxış B — Canlı İngilis-kursu koqortları (2 ədəd, 11 tələbə)

`Level - Group 2` (4 nəfər) və `Level - Group 3` (7 nəfər) — «Level» psevdo-
ixtisası altında, amma bu 11 nəfərin HAMISININ real `Enrollment` sətri var
(kurs qeydiyyatı aparılıb). Bunlar mənbədə İngilis dili hazırlıq kursunun
davam edən iştirakçılarıdır. **Risk: aşağı** — status dəyişmir, sadəcə
seçicidən/ağacdan gizlədilir; mövcud `group_id` istinadı toxunulmur.

### Naxış C — Bölüşdürülməmiş qəbul-ili «tutucu qrup» (1 ədəd, 228 tələbə) ⚠️ SAHIB QƏRARI TƏLƏB EDİR

`Level 2025-2026` — **real** `Dizayn (Qrafik)` ixtisası altında, `admission_
year=2025`, `sector=en`, 228 `StudentAcademicRecord` (ixtisasın CƏMİ 320
sətrinin 71%-i!). Bunların **HEÇ BİRİNDƏ** `Enrollment` sətri YOXDUR (0/228) —
yəni bunlar kurs qeydiyyatına düşməmiş, real akademik qruplara
bölüşdürülməmiş 2025 qəbulu tələbələridir.

**Bu naxış sahibin təsvirinə TAM uyğun gəlmir.** «Level» sözü burada dil-
kursu səviyyəsini yox, çox güman ki, mənbə sistemində «hələ qrupa
bölüşdürülməyib» statusunu kodlaşdırır (legacy `groups.id=758`,
`speciality_id=56` — məhz Dizayn (Qrafik)-in legacy ID-si). Say böyükdür və
tələbələr HƏQİQƏTƏN aktivdir (görünür yeni qəbul, semestr hələ başlamayıb).
Bu qrupu sadəcə «xidmət bölməsi» kimi gizlətmək **problemi HƏLL ETMİR** — 228
tələbə hələ də real qrupa bölünməlidir. Əmr onu texniki olaraq gizlədə bilər
(seçicidən itməsi əslində düzgündür — bu ad heç vaxt real qrup adı olmayıb),
AMMA **bu, dekanlığın əl işini əvəz etmir**. Tövsiyə: `--apply` bu qrupu
DEFAULT olaraq daxil etsə də, operator əvvəlcə bu 228 nəfərin real qrup
bölgüsü planını görməlidir (əmrin cədvəli bunu aydın işarələyir, bax §5).

### Naxış D — Boş status-konteyner (1 ədəd, 0 tələbə)

`Xaric olunanlar 2023` — real `Dizayn (Qrafik)` ixtisası altında, 0 tələbə
qeydi. Konteyner mənbədən köçüb, amma ona bağlı heç bir tələbə tenant-a
uyğunlaşmayıb (və ya artıq başqa yerə köçürülüb). **Risk: sıfır**.

### Naxış E — Canlı status-konteyner: statusu YAZILMAMIŞ xaric edilənlər (1 ədəd, 31 tələbə) — bu əmrin ƏSAS hədəfi

`Xaric olanlar` — real `Tərcümə` ixtisası altında, **31** `StudentAcademicRecord`,
**hamısının statusu `enrolled`** (default!), 84 real `Enrollment` sətri (tarixi
kurs fəaliyyəti göstərir ki, bunlar həqiqətən keçmiş tələbələr olub), 0 imtahan
cəhdi. Konteynerin adı («xaric olanlar») ilə sətrin faktiki akademik statusu
(«enrolled») **ziddiyyət təşkil edir** — köçürmə statusu tapşırıqdan tələbənin
konteyner üzvlüyünə köçürüb, `status` sahəsinə YAZMAYIB.

**Canlı təsir.** `apps.registrar.movements._sync_access_state` yalnız
`status ∈ {expelled, graduated}` olduqda `UserProfile.access_state`-i
`ARCHIVED`-ə keçirir və portal girişini bağlayır. Bu 31 nəfərin statusu
`enrolled` olduğu üçün **girişləri bağlı deyil** — «xaric edilmiş» tələbə
kabinetə normal aktiv tələbə kimi daxil ola bilər (eyni sinif problem, bax
layihə yaddaşı «Prod ops … access_state» qeydləri). Bu, sadəcə struktur
kosmetikası deyil, **təhlükəsizlik/əməliyyat qüsurudur**.

---

## 4. Status/fəaliyyət cədvəli (bütün 74 psevdo-qrup üzrə)

| Metrik | Dəyər |
|---|---|
| `StudentAcademicRecord.status` paylanması (270 sətir) | `enrolled`: **270**, digər: 0 |
| `is_active` (OrgUnit özü) | 74/74 = `true` (heç biri arxivlənməyib) |
| Tələbəsi olan psevdo-qrup sayı | 4 / 74 (`Level 2025-2026`, `Xaric olanlar`, `Level - Group 3`, `Level - Group 2`) |
| Tələbəsi olan qruplardakı `Enrollment` (kurs qeydiyyatı) | `Level 2025-2026`: 0; `Xaric olanlar`: 84 (31 tələbənin hamısında); `Level - Group 2/3`: hamısında (11/11) |
| `ExamAttempt` (imtahan cəhdi) | 0 — heç bir psevdo-qrup tələbəsinin imtahan cəhdi yoxdur |

---

## 5. Əlaqəli, LAKİN bu əmrin ƏHATƏSİNDƏN KƏNAR tapıntı (sahib üçün ayrıca qeyd)

«Level» psevdo-ixtisasının (`unit_type='specialty'`, `6d78c15a-…`) özü də
şübhəlidir — ona bağlı **real bir `Program` sətri var** (`Program.name='Level'`,
`specialty_unit=<bu OrgUnit>`), və onun altında 72 «Level …» qrupundan başqa
daha **5 real-görünüşlü qrup** da var:

| Ad | Tələbə sayı |
|---|---|
| `Silinmelidir` («silinməlidir» — hərfi mənada!) | 7 |
| `İnternational - az` | 54 |
| `İnternational - eng` | 8 |
| `İnternational - rus` | 14 |
| `international - turk` | 2 |

Bu 5 qrup adı naxışı («Level …» / «Xaric ол(un)anlar») ilə üst-üstə düşmür,
ona görə audit əhatəsinə DAXİL EDİLMƏYİB və əmr onlara TOXUNMUR. Amma
`Silinmelidir` adının hərfi mənası («bu silinməlidir») və bütün budağın
(«İngilis dili mərkəzi» → «Level») strukturunun academik ixtisas kimi deyil,
DİL MƏRKƏZİ kimi modelləşdirilməli ola biləcəyi göz önündədir. **Tövsiyə:**
sahib bunu ayrıca bir P2 maddəsi kimi nəzərdən keçirsin — bu sənəd və əmr
onu HƏLL ETMİR.

---

## 6. Nəticə — sahib qərarı tələb edən maddələr

1. **`Level 2025-2026`** (228 tələbə, naxış C) — «Level» adı ilə uyğun gəlmir,
   böyük ehtimalla bölüşdürülməmiş 2025 qəbulu tutucu qrupudur. Gizlətmək
   düzgündür (real qrup adı deyil), amma **228 tələbənin real qrup bölgüsü
   ayrıca əməliyyat işidir** — bu əmrin əhatəsi xaricindədir.
2. **`Silinmelidir` + 4 «İnternational -…» qrupu** (§5, 85 tələbə) — audit
   adı-naxışına uyğun gəlmədiyi üçün toxunulmayıb, amma «İngilis dili
   mərkəzi» → «Level» budağının bütövlükdə akademik strukturmu, yoxsa
   xidmət mərkəzimi olduğu ayrıca aydınlaşdırılmalıdır.
3. Qalan 72-dən **69-u tamamilə boş** (naxış A+D) və **3-ü aktiv, lakin kiçik**
   (naxış B, 11 nəfər) — bunlar üçün «xidmət bölməsi» işarəsi risk daşımır.
4. **`Xaric olanlar`dakı 31 nəfər** (naxış E) — status düzəlişi (`enrolled` →
   `expelled`) TƏLƏB OLUNUR; bu, kosmetik deyil, giriş nəzarəti qüsurudur.

---

## 7. Əmr

Aşağıdakı əməllər `apps/legacy_import/management/commands
/legacy_repair_pseudo_groups.py` ilə (dry-run default, `--apply` yazır):

* **`mark_service`** — hədəf `OrgUnit.is_service_unit=True` təyin edir (yeni
  sahə, bax §8) → akademik qrup seçicisi (`apps.accounts.services
  .student_groups.groups_under`) və struktur ağacı
  (`apps.organizations.structure_views.tree`) bunu artıq göstərmir. Mövcud
  `StudentAcademicRecord.group` istinadı TOXUNULMUR — tarixi məlumat qalır.
* **`expel`** — `Xaric olanlar`/`Xaric olunanlar 2023` konteynerindəki
  `status='enrolled'` (və ya `academic_leave`) sətirləri
  `apps.registrar.movements.create_movement(kind=EXPULSION)` ilə
  `status='expelled'`-ə keçirir (rəsmi hərəkət ledger sətri + audit + giriş
  bağlanması `_sync_access_state` vasitəsilə avtomatik). Xam `UPDATE` YOXDUR.

Default hədəf dəsti dəqiq bu sənəddəki 74 vahiddir (ad naxışı: `Level%` +
literal `Xaric olunanlar 2023` / `Xaric olanlar`, `unit_type='group'`) —
`--include-level-2025-2026` bayrağı verilmədikdə `Level 2025-2026` `mark_
service`-dən İSTİSNA olunur (naxış C-nin ölçüsü/riski görə, bax §3);
`--i-know-this-is-production` olmadan repetisiya markeri olmayan bazada
YAZMIR.

---

## 8. Sxem — `OrgUnit.is_service_unit`

Kodda mövcud `OrgUnit.is_active=False` («arxiv») fərqli semantika daşıyır:
`apps.organizations.group_actions._archive` **aktiv tələbəsi olan qrupu
arxivləməyi rədd edir** («Tələbəsi olan qrup arxivlənmir»). Bizim 4 psevdo-
qrupumuzun (naxış B/C/E) məhz aktiv tələbəsi var — `is_active=False` işlətmək
bu invariantı pozardı və UI-da «arxivlənmiş» kimi fərqli, səhv mənalı
görünərdi. Ona görə **yeni, ortoqonal sahə** əlavə olundu:

```python
is_service_unit = models.BooleanField(default=False, db_index=True)
```

Miqrasiya: `apps/organizations/migrations/0043_org_unit_is_service_unit.py`
(sadə, geri-dönən `AddField`). İstehlakçılar:

* `apps/accounts/services/student_groups.py::groups_under()` — akademik qrup
  seçicisi, `is_service_unit=False` filtri əlavə olundu;
* `apps/organizations/structure_views/tree.py::build_structure_tree_context()`
  — struktur ağacının kök sorğusuna `is_service_unit=False` əlavə olundu
  (paylaşılan `_visible_units_queryset` DƏYİŞDİRİLMƏDİ ki, qrup reyestri və
  struktur əməlləri kimi digər səthlər xidmət bölməsini hələ də tapıb idarə
  edə bilsin — bir-tərəfli «itmiş» vahid olmasın).
