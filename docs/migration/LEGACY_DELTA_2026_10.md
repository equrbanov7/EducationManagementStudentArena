# Köhnə sistemin deltası (myedu → EMS Arena) — 2026-10-23

Sahib 2026-10-23: köhnə sistemdə cutover-dən sonra yaranan/dəyişən BÜTÜN datanı yeni sistemə köçürmək.
Alətlər: `legacy_delta_extract` (lokal, MariaDB → şifrələnəcək paket) və `legacy_delta_apply`
(hədəfdə, dry-run default). Kod: `apps/legacy_import/services/delta/`.

## 1. Ölçülən fakt (dump-ların müqayisəsi)

* Cutover mənbəyi `myedudb.sql` **2026-08-17** snapshotudur (31 may DEYİL) — 17 avqusta qədərki data
  artıq yeni sistemdədir. Delta = 2026-08-17 → 2026-10-21 (yeni dump) fərqi.
* 1–13-cü semestrlərin jurnalları dəyişməyib (12 sətirdə yalnız `active`). Delta:

| Nə | Say |
|---|---:|
| 2026/2027 Payız jurnalları (semestr 14) | 1 590 (24 fake) |
| Dərs tarixləri | 12 955 |
| Xanalar (ie 176k, qb 33k, bal ~16k) | 228 110 |
| Köhnə semestrlərə təkrar imtahan / imtahan (im2 / im) | 1 263 / 87 |
| Yeni tələbə (1 713-ü 2026 qəbulu) / dəyişən | 1 724 / 291 |
| Yeni işçi / qrup / fənn / sillabus | 101 / 100 / 41 / 752 |
| `yekun`, `imthngrscxsblr` | dəyişməyib |

* Prod-da (22 okt nüsxəsi) Payız 2026/2027: 580 açılış, cəmi 55 dərs / 834 xana — müəllimlər
  payızda faktiki köhnə sistemdə işləyib.

## 2. Qaydalar (sahibin «tövsiyə olunan variant» qaydası ilə)

1. **Yeni sistem qalibdir**: mövcud xana / dərs / açılış müəllimi / sillabus / yekun bal ÜZƏRİNƏ YAZILMIR,
   yalnız boş doldurulur; fərq `*.conflict_kept` kimi sayılır.
2. Açılış = (fənn, semestr, qrup); varsa ona bağlanılır (eyni adlı fənnin açılışı da tapılır), yoxdursa
   yaradılır. Müəllim yalnız BOŞ açılışa yazılır.
3. Qeydiyyat: jurnal siyahısı + xanası olan tələbələr. Eyni fənn+semestrdə hər hansı açılışda qeydiyyatı
   varsa ikinci sətir açılmır; başqa qrupdan/alt qrupdan olan tələbə `source_group` ilə (alt qrupdan əlavə).
4. Dərs: tarix + saat; legacy-nin eyni gün iki parası ayrı dərsdir; yeni sistemdə əvvəlcədən açılmış eyni
   gün + eyni növ dərs bir legacy slotunu udur (ikiqat qayıb saatı olmasın). Gələcək tarixlər (`--lessons-until`)
   atılır. Növ: cutover J3 səsverməsi. 1 dərs = 2 saat.
5. Xana: `ie` → iştirak, `qb` → qayıb (`excusable`/üzrlü pəncərə → üzrlü), 0–10 → bal. Boş yazılmır.
6. Təkrar imtahan `im2` → `ResitRecord` (completed), `im` → `FinalGrade.exam_score` — yalnız boşsa.
7. Çatışmayan müəllim → **FİN-siz** hesab («Dərs yükü faylı»nın ad tutuşdurması, parolsuz,
   `roster.<ad>@placeholder.invalid`). Bloklanmış müəllimin bloku AÇILMIR.
8. Çatışmayan tələbə (azad edilməyib) → RİM-in `create_account` yolu, parolsuz,
   `legacy.<ad>@placeholder.invalid`, `institutional_identifier` = legacy id. Tutuşdurma: ledger →
   identifikator → FİN → (paket daxili eyni FİN) → ad + soyad (ata adı / doğum tarixi / qrup; ziddiyyətli
   FİN və ya ata adı = başqa adam). Ambiqü hal YARADILMIR və bağlanmır — siyahıda qalır.
9. Çatışmayan qrup → cutover forması (`myedu-grp-<id>`, ixtisas altında), alt qrupa `parent_group` izi.
10. Sillabus → açılışa **APPROVED** (`approval_source=migration`), açılışın sillabusu yoxdursa;
    müəllimə iş yaranmır. Baza sillabus — (fənn, müəllim) üçün yoxdursa.
11. **Dərs yükü** («Mənim dərs yüküm» `TeacherAssignment`-dən qurulur): müəllimi olan, amma heç bir tapşırıq
    sətrinin əhatə etmədiyi legacy jurnalı tədris şöbəsinin rəsmi «Dərs yükü faylı» axınından keçir (kafedra
    tapşırığı → sətir → bölgü → təsdiq). Saat = `fenn_saati`, fəaliyyətlərə sillabus payı ilə. Yalnız tapşırığı
    OLMAYAN və ya bölgüsü TƏSDİQLƏNMİŞ kafedralar; hər sətir əvvəlcədən yoxlanılır (fənn/qrup/müəllim mətni başqa
    sətrə düşürsə və ya oxşar mövcud sətir varsa — ötürülür); kafedra savepoint-dədir və mövcud bölgü / açılış
    müəllimi / qeydiyyat statusu dəyişərsə və ya eyni fənnin ikinci açılışı yaranarsa — kafedra geri qaytarılır.
12. Tapılmış tələbənin profilində yalnız BOŞ ata adı / doğum tarixi / cins doldurulur.
13. Bütün fazalar BİR tranzaksiyadadır; idempotentdir (təkrar qaçış = 0 yazı). Audit: bir sətir
    `resource_type=legacy_import.delta_batch` (saylar + yaradılan qrup/fənn/açılış/hesab/sillabus id-ləri).

### Sahib qərarı gözləyən (alət YAZMIR, yalnız sayır)

| Mövzu | Say | Tövsiyə |
|---|---:|---|
| Legacy-də qrupu dəyişən tələbələr | 194 | RİM qrup reyestrində rəsmi köçürmə ilə (yeni sistemdə dəyişiklik ola bilər) |
| Legacy-də azad edilənlər | 8 | RİM rəsmi əməli ilə |
| Kollokvium/sərbəst iş xanaları (k1–k3, si) | 307 | Köçürülməsin — 2026/2027 qaydasında yoxdur (Midterm 30) |
| Açılışın müəllimi legacy-dən fərqli | 185 | Yeni sistemdəki (tədris şöbəsinin bölgüsü) qalsın |
| Bloklanmış müəllim legacy-də dərs deyir | 31 | Kadrlar/RİM baxsın; blok avtomatik açılmır |
| Ad ilə ambiqü tələbə | ~150 | RİM `--names-out` siyahısı ilə əl ilə |

## 3. Nəticələr

### QA klonu (`emsarena_rehearsal_a0d170000901`, `emsarena_app` rolu, RLS aktiv) — TƏTBİQ OLUNUB

Əvvəl: klonun ehtiyat nüsxəsi `~/EMSArena-backups/legacy-delta-2026-10/qa_clone_pre_delta_20261023.dump`.

| | Say |
|---|---:|
| Yaradılan açılış / qrup / fənn | 1 401 / 57 / 3 |
| FİN-siz müəllim / tələbə hesabı | 81 / 642 |
| Qeydiyyat / dərs / xana | 25 774 / 13 325 / 217 654 |
| Təkrar imtahan / imtahan balı | 1 191 / 19 |
| Təsdiqlənmiş sillabus versiyası | 1 297 |
| Dərs yükü: kafedra / yeni yük sətri (bölgü ilə) | 14 / 733 (4 kafedra bölgü üzərində işləyir — toxunulmadı) |
| **İkinci qaçış** | **0 yazı** |

Dry-run sayları tətbiqlə EYNİDİR (dry-run eyni kodu işlədib geri qaytarır). İdxal olunmuş jurnal
səhifəsi 200 ilə açılır.

### Prod nüsxəsi (22 okt backup, təmiz bərpa → tətbiq; ikinci qaçış 0 yazı)

| | Say |
|---|---:|
| Jurnal → açılış (yaradılan / mövcud / eyni adlı) | 1 099 / 730 / 24 |
| FİN-siz müəllim / tələbə hesabı | 39 / 643 |
| Yeni qrup | 57 |
| Qeydiyyat / dərs / xana | 19 767 / 13 546 / 217 834 |
| Təkrar imtahan / imtahan balı | 1 191 / 19 |
| Sillabus (açılışa / baza) | 1 239 / 75 |
| Dərs yükü: kafedra / yeni yük sətri (bölgü ilə) | 20 / 783 (ehtiyatla ötürülən 144, kafedrası tapılmayan 14) |
| Üzərinə yazılmayan fərq (xana / müəllim / yekun) | 88 / 185 / 6 |
| Həll olunmayan xana (tələbə tapılmadı / gələcək tarix) | 6 083 / 714 |

Müddət ~8 dəqiqə (tək tranzaksiya; dərs yükü fazası ~4 dəq).

### PROD — TƏTBİQ OLUNUB (2026-10-24 03:29, sahibin «hə»sı ilə)

`prod-data-ops` → `legacy_delta_apply`, run 40039680313, paket sha256 `54886afa…4fbde9`, `--lessons-until 2026-10-23`,
tag `delta-20261024-032938-7b58`. Əvvəl backup: `/backups/last/emsarena-20261024-032640.sql.gz`.

| | Say |
|---|---:|
| Jurnal → açılış (yaradılan / mövcud / eyni adlı) | 1 099 / 730 / 24 |
| FİN-siz müəllim / tələbə hesabı / qrup | 40 / 644 / 57 |
| Qeydiyyat / dərs / xana | 19 774 / 13 548 / 217 903 |
| Təkrar imtahan / imtahan balı | 1 191 / 19 |
| Sillabus (açılışa APPROVED / baza) | 1 235 / 75 |
| Dərs yükü: kafedra / yeni yük sətri | 20 / 765 |
| Toxunulmayan fərq (xana / açılış müəllimi / yekun) | 89 / 185 / 6 |
| Müəllimi DB qapısından keçmədi (müəllimsiz açılış) | 17 |

**Tamamlayıcı tətbiq (05:34, run 40050138608, backup `emsarena-20261024-053110`):** dərs yükü axını 273 tələbəni
eyni fənnin öz qrup jurnalına da yazmışdı (legacy xanaları alt qrup jurnalındadır). `dedupe` fazası boş öz-qrup
sətirlərini rəsmi «alt qrup birləşməsi» ilə tarixçəyə keçirdi (**238**; `restore_source` ilə geri qaytarıla bilər),
**520** xana alt qrup jurnalında tamamlandı; hər iki jurnalda xanası olan **35** tələbəyə toxunulmadı (hesabat).
**Yoxlama dry-run-u (run 40050567621): 0 yazı.** Release, `STAFF_PLAN_KEY` sirri, artifaktlar silinib.

Adlı siyahı (yaradılan hesablar, ambiqü tələbələr, legacy qrup/azad fərqləri) yalnız lokal:
`~/EMSArena-backups/legacy-delta-2026-10/prod-apply-20261024/` (0600).

## 4. Prod addımları (HƏR BİRİ sahibin açıq «hə»sı ilə)

1. Kodu prod-a çatdır: Develop → Staging → main (`legacy_delta_*` əmrləri + `prod-data-ops` addımı).
2. Paket: `legacy_delta_extract` (bax §5) → `~/EMSArena-backups/legacy-delta-2026-10/delta-20261021.json.gz`
   (sha256 `54886afaeaf7474c42e4da6206984149c088876ce4cc208333bf047beb4fbde9`). Prod-a yaxın tarixdə köhnə
   sistemdən TƏZƏ dump alınsa, paketi yenidən qurun (köhnə sistem hələ də işləyir).
3. Şifrələ və draft release-ə yüklə (repo private):
   ```bash
   openssl enc -aes-256-cbc -md sha256 -pbkdf2 -iter 200000 -salt -pass env:STAFF_PLAN_KEY \
     -in delta-20261021.json.gz -out delta.json.gz.enc
   gh release create legacy-delta-20261021 delta.json.gz.enc --draft --title legacy-delta-20261021
   ```
4. `prod-data-ops` → `legacy_delta_apply`, `roster_tag=legacy-delta-20261021`, `batch=<sha256>`,
   `date_to=<prod tarixi>` — əvvəl **dry-run**; saylar §3 cədvəli ilə müqayisə olunur.
5. Sahibin «hə»sından sonra eyni girişlərlə `apply=true`, `confirm=APPLY` (addım əvvəlcə backup alır).
6. Yoxlama: eyni girişlərlə yenidən dry-run → `written.*` sətirləri olmamalıdır.
7. Release asset-i və artifaktı sil; RİM-ə: yaradılan tələbə/müəllim hesablarına parol (RİM «Parol təyin et»),
   ambiqü siyahı (şifrəli artifaktdakı `legacy_delta_names_*.csv`).

### Geri qaytarma

Tək tranzaksiya olduğundan yarımçıq vəziyyət yaranmır. Tətbiqdən sonra geri qaytarmaq lazım olsa:
addımın aldığı backup-dan bərpa (`prod-legacy-restore`/restore drill qaydası) və ya audit sətrindəki
id-lərlə hədəfli təmizlik (yaradılan açılışlar silinəndə onların dərs/xana/qeydiyyatı da gedir).

## 5. Lokal paket qurma

```bash
docker run -d --name ems-legacy-delta-src -e MARIADB_ROOT_PASSWORD=… -p 127.0.0.1:50330:3306 \
  -v ems-legacy-delta-src-data:/var/lib/mysql mariadb:10.6 --innodb-buffer-pool-size=3G --skip-log-bin
# myedu_new ← yeni dump, myedu_old ← cutover dump (myedudb.sql, 2026-08-17)
python manage.py legacy_delta_extract --password-file <fayl> --source myedu_new --baseline myedu_old \
  --since 2026-08-01 --snapshot-file "<yeni dump>" --out ~/EMSArena-backups/legacy-delta-2026-10/delta.json.gz
python manage.py legacy_delta_apply --bundle <paket> --organization qku --lessons-until <tarix>   # dry-run
```

## 6. Dərs mövzuları və tədris rolu bərpası (2026-10-25)

Sahibin sualı: «Mövzu yazılmayıb olan yerlərdə sənmi mövzu tapmamısan, həqiqətən mövzumu yox idi?» — köhnə
sistemdə **mövzu var idi**: hər dərs tarixi (`journals_dates_rooms.sillabus`) sillabusun həftəlik mövzu sətrinə
(`sillabus_sem_muh.movzu`) bağlıdır (2026/2027 payız: 11 214 tarix). Nə cutover, nə ilk delta bunu gətirmişdi.

* **`topics` fazası** (`services/delta/topics.py`): paketin `lesson_topics` bölməsi → dərs (eyni ay + gün + saat;
  saat tutmursa günün TƏK dərsi). Yalnız BOŞ mövzu doldurulur, bağlı açılış ötürülür. `syllabus_week` bağlantısı
  ayrıca — mövzu mətninin sillabus planı ilə dəqiq tutuşdurulması ilə.
* **Paket öz fazalarını daşıyır:** `legacy_delta_extract --phases offerings topics` → `snapshot.phases`;
  `legacy_delta_apply` `--phase` verilməyəndə onları götürür. Belə paket dərs/xana fazasını İŞLƏTMİR — bu vacibdir,
  çünki `legacy_repair_empty_lessons` sildiyi «yalnız qb» sütunlarını lessons fazası yenidən yaradardı.
* **Tədris rolu bərpası** (`legacy_loads.restore_teacher_role`): müəllim bu semestr köhnə jurnal yazıb, amma
  aktiv müəllim üzvlüyü yoxdur (köhnə «İngilis dili mərkəzi (Kafedra)» üzvlüyü sönülü) → açılışa yazıla bilmirdi
  (`offering.instructor_blocked` 17). Ən son sönülü üzvlük AKTİV kafedradadırsa `join_chair_as_teacher` ilə bərpa
  (audit), sonra müəllim yazılır.
* **Sıra (prod):** deploy → `legacy_repair_empty_lessons` (dry-run → apply) → `legacy_delta_apply` mövzu paketi
  (dry-run → apply) → `syllabus_week` backfill.

Prod kopyasında (2026-10-24 22:06 export): boş sütun silinməsi 26 300 (köçürülmüş tam boş 23 498 + yalnız «qb»
2 801 + müəllimin tam boş 1; 7 490 «qb» xanası / 14 980 qayıb saatı, 4 137 qeydiyyatın qayıbı yenidən hesablandı),
sonra mövzu 11 926 dərsə, rolu bərpa olunan 3 müəllim, 16 açılışa müəllim.

## 7. Alt qrup tələbələrinə rəsmi işarə (2026-10-25)

Sahib: «Alt qrup tələbələrini tapsan işarələ — yeni sistemdə işarələyərək göndər, görünsün ki alt qrupdur.»

Köhnə sistemdə alt qrup ayrıca qrupdur («536 MU1», «135 Si-1», «3/336F2»; `groups`-da ana qrup sütunu yoxdur, yalnız
ad naxışı), tələbənin `students.group_id`-si alt qrupa baxır. Yeni sistemdə həmin tələbə çox vaxt ANA qrupdadır,
delta isə onu alt qrupun jurnalına «alt qrupdan əlavə» (`Enrollment.source_group`) kimi yazıb — jurnal çipi var idi,
amma «Alt qrupa yerləşdir» tarixçəsi (`SubgroupPlacementEvent`) boş idi, bəzi alt qrupların ana qrup izi yox idi
(«Bi» ↔ «Bİ»: `casefold("İ")` nöqtəli «i̇» verir, ad naxışı tutmurdu).

* **`subgroups` fazası** (`services/delta/subgroups.py`, `PHASES`-də `dedupe`-dan sonra): (1) paket tələbələrinin
  legacy qrup vahidinin izi yoxdursa, EYNİ ixtisasda ad ailəsinə uyğun TƏK ana qrupa `settings.parent_group` yazılır
  (audit); (2) legacy-də alt qrupda (S), yeni sistemdə başqa qrupda olan tələbənin S jurnalındakı canlı «alt
  qrupdan əlavə» qeydiyyatına rəsmi `place` sətri — `registrar.public.record_imported_placement`, səbəb «Köhnə
  sistemdən köçürmə: alt qrup», `details.via=import` (qeydiyyata/bala toxunulmur, bildiriş yoxdur; alətin «geri
  götür» axını işləyir). Dövr = `snapshot.full_semesters`. İdempotent.
* **Yalnız sayılır:** legacy qrupu alt qrup deyil, amma fərqlidir (`group_differs_report_only`); alt qrup fənnini
  ana qrupun jurnalında keçir (`subject_in_other_journal` — xanalar oradadır, köçürmək balları gizlədərdi);
  alt qrup jurnalında qeydiyyatı yoxdur (`student_without_subgroup_journal`). Adlar yalnız `--names-out`-da.
* **UI:** jurnal çipi (mövcud) + tələbə reyestrində «Proqram · qrup» xanasında «alt qrup: <qrup>» nişanı (cari
  semestr, jurnal çipi ilə eyni predikat) + reyestr kartında yerləşdirmə tarixçəsi + qrup reyestrində ana qrup.
* **Prod kopyası (ems_prodlive_1025):** 12 alt qrup ana qrupa bağlandı (21 artıq bağlı idi), 277 tələbə üzrə
  1 365 «Alt qrupa yerləşdirildi» sətri; 52 tələbənin alt qrup jurnalında qeydiyyatı yoxdur, 482 tələbə×fənn ana
  qrup jurnalındadır, 139 tələbənin legacy qrupu fərqlidir (alt qrup deyil). İkinci qaçış: 0 yazı.
* **Prod:** paket yalnız bu fazanı daşıyır (`snapshot.phases = ["subgroups"]`; `legacy_delta_extract --phases
  subgroups` və ya mövcud delta2 paketinin yenidən yığılması) → şifrəli asset `legacy-delta-subgroups-…` →
  `prod-data-ops` `legacy_delta_apply` (dry-run → apply, `batch` = sha256).
