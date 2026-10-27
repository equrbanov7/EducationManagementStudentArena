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

## 8. Aktiv tələbə reyestrinin nizamlanması — `registry_sync` fazası (2026-10-25)

Sahib: «yeni jurnal datalarında analiz çıxardarsa, aktiv tələbə sayında nizamlamağa çalış». Köhnə sistemin
2026-10-21 snapshot-u qrup üzvlüyü və azad edilmə üçün cari vəziyyətdir. Faza (`services/delta/registry_sync.py`)
**yalnız açıq seçiləndə** işləyir (`DEFAULT_PHASES`-də yoxdur; paket `--phases registry_sync` ilə qurulur) və
fərqləri YALNIZ rəsmi reyestr əmrləri ilə tətbiq edir (`registrar.movements.create_movement`):

* **qrup** — köhnə sistemdə qrup cutover-DƏN SONRA dəyişibsə (`baseline` fərqi) və ya tələbə yenidirsə → `group_transfer`
  (əmr `KS-SINX-20261021`, səbəb «Köhnə sistemdən sinxron: 2026-10-21 vəziyyəti»); jurnal qeydiyyatları rəsmi
  köçürmə qaydası ilə yeni qrupun açılışına keçir (lazım olsa açılış yaranır);
* **azad edilmə** — `azadedildi=1` → `expulsion` (köhnə `order_no` / `order_date`; gələcək/boş tarix → snapshot
  tarixi). Paketin yeni `expelled_students` bölməsi cari semestrdə OLMAYAN azad edilmişləri də daşıyır (yalnız güclü
  sübutla — ledger / identifikator / FİN; eyni FİN-in azad edilməmiş sətri varsa, yəni yenidən qəbul — toxunulmur).

Toxunulmur (sayılır, adlı siyahıda): yeni sistemdə cutover-dən sonra əl ilə hərəkət/köçürmə/status izi; köhnə
qrup dəyişməyib (yeni sistem qalibdir); alt qrup ↔ ana qrup (`parent_group` izi və ya ad şablonu, I/İ eyniləşdirilir);
başqa ixtisasın qrupu (proqram köçürməsi qərarıdır); legacy-də eyni adamın iki sətri fərqli qrupda; hədəf «silinməli».

Prod nüsxəsində (`ems_prodlive_1025` kopyası): 141 köçürmə (48 köhnə sistemdə köçürülmüş + 93 yeni tələbənin
yerləşdirilməsi), 200 xaric (9 cari semestrdən + 191 cutover-dən əvvəl azad edilmiş, statusu «enrolled» qalmışdı),
aktiv qeyd 9 333 → 9 133; ikinci qaçış 0 yazı. Sahib qərarı gözləyən: 235 alt qrup yerləşdirməsi, 67 başqa ixtisas,
21 dublikat sətir və **~4 250 aktiv qeyd köhnə sistemin cari semestr jurnallarında yoxdur** (əsasən məzun kohortlar —
§8a `graduation` fazası).

```bash
python manage.py legacy_delta_extract --password-file <fayl> --source myedu_new --baseline myedu_old \
  --full-semester 14 --since 2026-08-01 --phases registry_sync --snapshot-file "<yeni dump>" \
  --out ~/EMSArena-backups/legacy-delta-2026-10/delta3-registry-20261025.json.gz
python manage.py legacy_delta_apply --bundle <paket> --organization qku   # dry-run; --apply ilə yazır
```

## 8a. Məzun etmə — `graduation` fazası (2026-10-25)

Sahib: «Əgər bu ilin jurnalında onların adı yoxdursa — MƏZUN ET; yoxsa ola bilər kimsə kəsilib, bitirməyib — onu
məzun etmə.» Reyestrə yeni hərəkət növü əlavə olundu: **«Məzun etmə»** (`graduation`, `enrolled → graduated`; cari/
gələcək dövrün açıq qeydiyyatları dondurulur, giriş bağlanır — eyni adamın başqa aktiv qeydi varsa toxunulmur;
«Bərpa» əmri `graduated`-dən də qaytarır). RİM/tələbə şöbəsi «Tələbə reyestri» → «Hərəkət» dialoqunda tək tələbə üçün
seçir; qrup çekmecəsində məzunlar «qrupdan çıxanlar» siyahısındadır («Bərpa et» ilə geri).

Toplu faza (`services/delta/graduation.py`, **yalnız açıq seçiləndə**, `registry_sync`-dən SONRA işləyir). Namizəd:
`enrolled` qeyd + yeni sistemdə cari/gələcək dövr qeydiyyatı YOX + köhnə sistemin cari semestr jurnallarında YOX
(paketin `journals`-ı; tutuşmayan legacy sətrinin FİN/adı eynidirsə — yoxlanmalı) + köhnə sistemdə azad edilməyib +
cutover-dən sonra əl ilə hərəkət izi yox + qrup «silinməli» qabı deyil + **müddət bitib** (qəbul ili + ceil(ECTS/60) ≤
cari tədris ili, 2026) + **son kurs jurnalı var** (yeni sistemdə son jurnal semestri proqramın son tədris ilindədir;
tarixçədən — 2021/2022 — əvvəl bitənlər bu yoxlamadan azaddır). Əmr `MZN-SINX-2026`, tarix `2026-07-01` (sabit),
səbəb «Köhnə sistemdən sinxron: məzun — …». Qalanlar adlı «yoxlanmalı» siyahısındadır: `period_not_ended`,
`year_unknown` (1950 sentineli / ≤2000), `left_before_final_year`, `no_journal_history`, `junk_group`,
`legacy_unresolved_match`, `system_changed`.

Prod nüsxəsində (registry_sync + graduation birlikdə, `delta4-graduation-20261025.json.gz`): 996 məzun (bakalavr
2017–2022, magistr 2018/2022–2024), yoxlanmalı: 446 müddəti bitməyib, 2 227 qəbul ili bilinmir, 209 son kursdan əvvəl
kəsilib, 24 jurnal tarixçəsi yoxdur, 40 «silinməli» qrup, 23 tutuşmayan legacy sətri ilə eyni FİN/ad; toxunulmaz:
5 155 cari jurnalda, 13 köhnə sistemin cari jurnalında. Aktiv qeyd 9 333 → 8 137; ikinci qaçış 0 yazı.

⚠️ `history` fazası alumni üçün `enrolled` SAR yaradır — graduation onlardan SONRA yenidən işlədilə bilər (idempotent).

### 8b. Sahibin ikinci qərarı — opt-in bayraqlar (2026-10-25)

Prod tətbiqindən (1 048 məzun, 201 xaric) sonra qalan «yoxlanmalı»lar üçün paketin `snapshot`-unda bayraqlar
(`services/delta/graduation_owner.py`; bayraqsız paket köhnə davranışdadır):

* `graduate_year_unknown` — `year_unknown` (köhnə «0000» qrupları, qəbul ili 1950/≤2000) → «Məzun etmə»
  (`MZN-SINX-2026`, 2026-07-01, səbəb «…qəbul ili məlum deyil — sahibin 2026-10-25 qərarı»); tutuşmayan legacy
  sətri ilə eyni FİN/ad olan yenə yoxlanmalı qalır.
* `leave_unfinished` — `period_not_ended`, `left_before_final_year`, `no_journal_history` → «Akademik məzuniyyət»
  (`AM-SINX-2026`, 2026-10-25, bitmə 2027-06-30; status `academic_leave`, aktiv sayda deyil, «Bərpa» ilə qayıdır;
  dekanlıq təsdiqləməlidir). Kateqoriyalar hesabatda ayrıca: `graduation.leave.<kateqoriya>`.
* `deactivate_emptied_groups` — yuxarıdakı məzunların qrupları arxivlənir (`is_active=False` +
  `settings.graduation_archived` + «groups: archived — …» audit sətri; reyestrdə «arxivdən qaytar») — yalnız qrupda
  `enrolled`/`academic_leave` qeyd, cari/gələcək dövr açılışı/qeydiyyatı və aktiv alt vahid yoxdursa.
* `junk_group` («Silinməlidir») toxunulmur.

Paket: `delta5-graduation-owner-20261025.json.gz` (delta4 + `phases=["graduation"]` + üç bayraq). Təzə prod
nüsxəsində: 2 304 məzun (bakalavr 2 131, magistr 173), 656 akademik məzuniyyət (446 / 190 / 20), 182 qrup arxivləndi,
24 qrup aktiv qeydə görə qaldı, 40 «silinməli» + 1 tutuşmayan legacy sətri toxunulmadı; ikinci qaçış 0 yazı.

## 9. Tarixi semestrlərin boşluqları — `history` / `history_topics` fazaları (2026-10-25)

Sahib: «Köçürülməmiş heç bir data problem yaratmasın, köhnə datadan nəyisə bərpa olunası bir şey varsa et.»
Audit (`legacy_gap_audit_20261025.md`, şəxsi): legacy semestr 1–13-də gəlməyən real xanaların HAMISI qeydiyyat
(`Enrollment`) yoxluğundandır — cutover-də hesabı açılmayan tələbələr, K9 qrup uyğunsuzluğu, karantin (qrupu
silinmiş) jurnallar, siyahıdankənar xanası olan tələbələr. Ortaq nişan: `(uniqid, tələbə)` cütünün cutover
ledger-ində (`journal_enrollment`) `migrated` sətri yoxdur. Repair əmrləri canlı MariaDB istədiyi üçün bərpa delta
PAKETİ ilə gedir (`services/delta/history*.py`); qaydalar mövcud repair qaydalarıdır (yeni paralel qayda yoxdur):

* **Paket** (`legacy_delta_extract --history-semester …`): Django bazası = prod NÜSXƏSİ (ledger yalnız OXUNUR) —
  ~4,9 mln tarixi xanadan yalnız köçməmiş cütlərin xanaları (~0,32 mln; J-V7 arxiv sətirləri daxil), karantin
  jurnallarının dərs tarixləri, boşluq tələbələrinin bütün üzrlü pəncərələri, FİN sayları və «fəaliyyət» (bütün
  jurnallardan, E2/E3 sübutu). Fake/`sonra_sil` jurnallar (sahib qərarı gözləyir, §2.3) paketə DÜŞMÜR.
* **Hesab** (`history_accounts`): delta `StudentMapper` (ledger → identifikator → FİN → ad); tapılmayan və
  *hazırda oxuyan* (E2/E3 — `repair_enrollments_select`; E4 — legacy qrupunun yeni sistemdəki tələbələrinin çoxu aktiv
  `student`) → delta yolu (`create_legacy_student`); qalanı (məzun / xaric / keçmiş) → `repair_accounts` formasında
  staged hesab (`myedu.student.<id>`, yer-tutucu e-poçt, parolsuz) → `alumni` arxivi (`archive_staged_account`:
  üzvlük aktiv, GİRİŞ BAĞLI) + SAR `repair_sar.materialise` ilə. Ambiqü ad heç vaxt təxmin edilmir.
* **Qeydiyyat** (`history_plan`): mövcud yazılış (jurnalın öz açılışında) → əkiz (eyni fənn/ad + dövr, başqa
  açılış) BƏRPA OLUNMUR → yalnız «qb» olan cüt yeni yazılış açmır → dilim `_choose_slice` (SAR qrupu → dövrün digər
  qrupu → ilk dilim; fərqli dilim = qonaq `source_group`) → karantin: `_evidence_slice` (dövrdəki TƏK qrup; açılış
  yoxdursa yaradılır və J7 kimi kilidlənir — `apply_lock`). DB qapısı: aktiv üzvlük (student/alumni).
* **Xana + yekun**: delta-nın öz kodu (`lessons`, `finals` → J6 `write_exam_score`/`write_resit_score`) adapterlə;
  bağlı (təhvil verilmiş) jurnala YALNIZ ƏLAVƏ — mövcud xana/bal dəyişmir (`trg_journal_mark_guard` yalnız
  UPDATE-dədir, `journal_unlock` lazım deyil). Komponentlər (k1–k3, si) köçmür (delta qaydası).
* **`history_topics`**: tarixi dərslərin BOŞ mövzu/otağı (`topics.apply_topics`), ledger açılışlarında, bağlı
  jurnallarda da (metadata).
* Audit: hər qaçış bir `legacy_import.delta_batch` sətri — saylar + yaradılmış yazılış/açılış/hesab id-ləri
  (`history_enrollments`, `history_offerings`, `students`) — geri qaytarmaq üçün. Adlar yalnız `--names-out`.

Yaddaş: əmr app konteynerində (limit 2 GB) işləyir — paketlər ayrıdır (pik RSS ≤ ~0,75 GB): boşluqlar `1-6` və
`7-13`, mövzular ayrıca. Hesab qərarı bölgüdən asılı deyil (fəaliyyət bütün jurnallardan; eyni adamın ikinci legacy
sətri artıq yaradılmış hesaba bağlanır).

Prod nüsxəsində (`ems_prodlive_1025` kopyası, migrate + 3 paket, sonra təkrar): 16 739 cüt → 6 590 yeni yazılış
(2 184 qonaq), 4 425 mövcud yazılışa xana; 147 133 xana (iştirak/bal 104 246, üzrlü 114, qayıb 42 773), 2 699 `im`
+ 176 `im2`; 85 hesab (79 arxiv + 6 cari), 56 kilidli karantin açılışı; mövzu 272 744, otaq 275 594. İkinci
qaçış: 0 yazı. Bərpa olunmayan (adlı siyahıda): əkiz 1 294 cüt, karantin sübutsuz/çoxqruplu 787, tələbə həll
olunmur 1 161 (legacy `students`-də sətri olmayan 100 id + 2 ambiqü + 1 qəbul ili), aktiv üzvlüyü yoxdur 22.

Auditin ölçmə skripti ilə (fənn adında HTML entity-si açılaraq — audit «Xarici dildə işg&amp;uuml;zar…» kimi adları
tutuşdura bilmədiyi üçün 09-25 K9 təmirinin artıq bərpa etdiyi ~43 min xana-günü də boşluq sayırdı): real boşluq
**104 172 → 24 790 xana-gün (79 382 bərpa, 76 %)**, bal xanası 8 502 → 2 130. Qalan: legacy tələbəsi ledger-də/
identifikatorla tapılmayan 11 129 (ölçmə FİN/ad tutuşdurmasını görmür), karantin sübutsuz 6 877, e-poçt kohortunun
ambiqü/qalan hissəsi 2 609, əkiz/siyahıdankənar 3 290, digər 885.

```bash
# LOKAL (MariaDB + prod nüsxəsi ledger üçün; yalnız oxu)
export DATABASE_URL=postgres://…/ems_prodlive_1025 PGOPTIONS="-c default_transaction_read_only=on"
for spec in "a 1-6 history" "b 7-13 history" "topics 1-13 history_topics"; do set -- $spec
  python manage.py legacy_delta_extract --password-file <fayl> --source myedu_new --organization qku \
    --history-semester $2 --phases $3 --out ~/EMSArena-backups/legacy-delta-2026-10/hist/delta-hist-$1-20261025.json.gz
done
# hər paket: şifrələ → release (asset adı MƏHZ delta.json.gz.enc) → prod-data-ops legacy_delta_apply
openssl enc -aes-256-cbc -md sha256 -pbkdf2 -iter 200000 -salt -pass env:STAFF_PLAN_KEY \
  -in delta-hist-a-20261025.json.gz -out delta.json.gz.enc
gh release create legacy-delta-hist-a-20261025 delta.json.gz.enc --draft --title legacy-delta-hist-a-20261025
# workflow: command=legacy_delta_apply, roster_tag=legacy-delta-hist-a-20261025, batch=<paketin sha256-sı>,
#           date_to boş; əvvəl dry-run, sonra apply=true + confirm=APPLY. Sıra: a → b → topics.
```

⚠️ Bu fazalar `legacy_repair_empty_lessons --include-locked`-dən ƏVVƏL işləməlidir (audit §2.6: tarixi «boş»
sütunların çoxu bərpa olunacaq xanaların dərsləridir).

## 10. Magistr auditi — fənn KODU toqquşması (`subject_collisions`) və magistr qrup adları (2026-10-26)

Sahib 2026-10-26: «Sillabus və s. — magistrda köçməyənlər var, onlara da bax; dərs cədvəli və s.». Ölçü prod nüsxəsində
(2026-10-26 səhər) və delta5 paketində (cari semestr 14, `bak_or_mag=mag` qrupları) aparılıb; adlı siyahı yalnız lokaldır.

### 10.1 Kök səbəblər

1. **Fənn kodu toqquşması.** Delta ledger-i olmayan legacy fənni `QKU-<lessons.id>` kodu ilə tapırdı; tapşırıq idxalı isə
   2026-09-19-dan yeni fənlərə ardıcıl `QKU-<n>` kodları verib. Köhnə sistemdə payızda açılan fənlər (id 2668+) beləcə
   BAŞQA fənnin kartına düşüb (məs. «Tədqiqat analitikası» jurnalı «Quru ərazilərin bioresursları» adı ilə). Cəmi
   **29 legacy fənn (14-ü magistr), 50 açılış** — hamısı delta-nın yaratdığı açılışlar; **25-i «əkiz»**: eyni qrupda
   düzgün fənn üzrə rəsmi (tapşırıq) açılış da var — cədvəl slotu və dərs yükü orada, legacy dərs/xana isə yanlış adlı
   açılışda (20-si magistr). Delta-nın dərs yükü fazası yanlış adla 14 sətir açıb (2-si magistr; 9-u düzəlir, 5 bakalavr
   sətri əkizdir).
2. **Magistr qrup adı dərs yükü axınında bölünürdü.** «Forma 1» qrup ayırıcısı `403/5 MN` adını `403 /5` + `403 MN`
   kimi iki saxta qrupa bölürdü (`group_tokens`) — legacy jurnalın dərs yükü sətri «qrup başqa yerə düşür» deyə ötürülürdü
   (magistr: 40 yazı). Eyni xəta tədris şöbəsinin «Dərs yükü faylı» / Forma 1 yükləməsində magistr qruplarına da təsir edirdi.
3. Kataloqda dublikat «Tədqiqat metodları» (iki kart) — 9 yazı «fənn başqa karta düşür» deyə ötürülür (sahib/RİM:
   `merge_subjects`).
4. Legacy-də müəllim jurnala BAŞQA fənnin sillabusunu bağlayıb (19 magistr jurnalı) — qayda üzrə köçürülmür; 10 jurnalın
   legacy sillabusu yoxdur.
5. Bütün magistr proqramlarının təsdiqlənmiş planları BOŞDUR (0 sətir; 2026 planları qaralama, 0 sətir) — plan məzmunu
   köhnə sistemdə yox idi, tədris şöbəsi yükləməlidir.

### 10.2 Düzəliş (kod)

* `Catalog.subject_for` kodu yalnız ADI da tutanda qəbul edir; tutmursa `code_collision` — jurnal ötürülür (təxmin yox),
  `subject_collisions` fazasının xəritəsi (audit `legacy_import.subject_collision`) varsa həmin karta bağlanır.
* Yeni opt-in faza **`subject_collisions`** (`delta/collisions.py`): delta-nın yaratdığı yanlış açılışı düzgün karta
  keçirir (eyni adlı tək aktiv fənn, yoxdursa yeni `QKU-L<id>` kartı) — fənn birləşdirməsinin rəsmi DB icazəsi ilə; açılışın
  sillabusu və həmin qrupların delta dərs yükü sətri də keçir; əkiz, delta-ya aid olmayan, başqa modulda istinadı olan və
  bağlı jurnala toxunulmur (sayılır). Bütün qrupları həll olunan fənn üçün xəritə yazılır; əkiz qalan fənn növbəti delta
  qaçışlarında ötürülür (ikinci nüsxə yaranmır). İdempotent.
* `group_tokens`: `403/5 MN ing` bir qrupdur.

Prod nüsxəsində (iş nüsxəsi): faza 25 açılış (12 magistr) + 18 sillabus + 9 yük sətri keçirdi, 16 yeni kart, 17 xəritə;
ikinci qaçış 0 yazı. Sonra magistr dərs yükü paketi (`offerings` + `workload` + `dedupe`): 8 kafedra, 20 yeni sətir
(rəsmi axın); magistr açılışlarında yük sətri olmayan 69 → 45, müəllim bölgüsü olmayan 80 → 56.

### 10.3 Prod addımları (hər biri sahibin «hə»sı ilə; workflow dəyişmir — mövcud `legacy_delta_apply` addımı)

1. Kodu prod-a çatdır.
2. Paket A — toqquşma (şəxsi data YOXDUR: yalnız jurnal → fənn/qrup; `snapshot.phases = ["subject_collisions"]`);
   paket B — magistr dərs yükü (magistr jurnalları + müəllim adları + sillabus/dərs tarixləri, tələbə/xana yoxdur;
   `snapshot.phases = ["offerings", "workload", "dedupe"]`). Hər biri şifrələnib ayrıca draft release-ə (`legacy-delta-…`).
3. `prod-data-ops` → `legacy_delta_apply`, `roster_tag` = A-nın tag-ı, `batch` = sha256 — dry-run, saylar §10.2 ilə
   müqayisə; sonra `apply=true`, `confirm=APPLY` (addım backup alır); yoxlama dry-run-u: `written.*` olmamalıdır.
4. Eyni addım B paketi ilə (A-dan SONRA — B toqquşan jurnalları A-nın xəritəsi ilə görür).
5. `infer_timetable_from_lessons` (period «Payız 2026/2027») — dry-run, sonra apply (yeni açılış/ad üçün slot).
6. Release asset-ləri və artifaktları sil.

### 10.4 Sahib qərarı gözləyən

* **25 əkiz jurnal** (20 magistr): legacy dərs/xana yanlış adlı açılışda, rəsmi açılış (cədvəl, yük) boş. Unikal açar
  (fənn, dövr, qrup) birinin fənnini dəyişməyə imkan vermir. Tövsiyə: rəsmi açılışa dərs + xananı köçürən «jurnal
  birləşdirmə» əməli (ayrıca iş), sonra yanlış açılışın ləğvi; 5 bakalavr əkizinin yanlış yük sətri (saat ikiqat) silinsin.
* 19 jurnalın başqa fənn sillabusu (2-si eyni fənnin yazılış fərqidir — onlar köçürülə bilər), 10 sillabussuz jurnal.
* «Tədqiqat metodları» dublikat kartı; adı fərqli eyni fənn əkizləri (məs. «İnternet proqramlaşdırma» / «İnternetdə
  proqramlaşdırma») — `merge_subjects` əkiz qrupda bloklanır.
* Boş magistr planları (40 proqram).
* Cədvəl: əkiz olmayan 11 magistr açılışında dərs var, slot yox (axşam dərsləri seyrək: tək dərs, müəllim toqquşması,
  qarışıq axın) — cədvəl redaktorunda əl ilə.

## 11. RİM müraciətləri — əkiz jurnal, lab kodu, alt həftə (2026-10-27)

### 11.1 Kod düzəlişləri

* **Qeydiyyat seçimi** (`delta/home_journal.py`, `journals.py`, `lessons.py`): tələbənin fənn üzrə «ev» jurnalı — aktiv
  (`active != 0`), siyahıda, xanası/tarixi çox olan; passiv jurnal seçilmir; `JournalSlices.pick` reyestr qrupu tutmayanda
  legacy qrupuna baxır. Ev açılışı ilə eyni ailədən (eyni açılış, ana ↔ alt qrup — mühazirə + lab alt qrupu) olan
  jurnallar əvvəlki kimi birləşir; paralel qrupun («əkiz») və passiv jurnalın xanası ev açılışında YALNIZ mövcud dərsə
  düşür (`cell.cross_journal_skipped`), yeni «fantom dərs» açılmır.
* **Legacy `sem_muh=2` = laboratoriya** (`rehearsal_journal_lesson_kinds.cell_kind`); `3` (praktiki) qəsdən seminar.
* **Alt həftə** (`timetable_inference.decide_week_type`): ≥ 2 cüt ardıcıl həftədə dərs → hər həftə (bir buraxılmış
  həftə slotu «alt həftə» etmir).

### 11.2 Data əmrləri (hamısı defolt dry-run, `--apply`, idempotent, audit, stdout yalnız saylar)

| Əmr | Nə edir | Giriş |
|---|---|---|
| `build_twin_repair_plans` (legacy_import, LOKAL) | köhnə sistem (MariaDB və ya paket) + prod nüsxəsi → 3 plan, yalnız id-lər | `--legacy-source myedu_new --full-semester 14 --out-dir …` |
| `fix_legacy_lesson_kinds` | kod-2 «seminar» dərsləri → lab (+ lab-only planda seminar slotları) | `lessonkinds.json` |
| `relocate_twin_enrollment` | fantom xanalar → tələbənin ev açılışı; boşalan fantom dərs silinir; W qeydiyyatı `dropped` (qayıb daşınmır) | `relocate.json` |
| `merge_twin_offerings` | yanlış fənn adlı əkiz açılış → rəsmi açılış (dərs, xana, sillabus; T cədvəli/yükü qalır), W ləğv | `merge.json` |
| `fix_slot_week_parity` | çıxarılmış üst/alt slot → hər həftə (ardıcıl həftə sübutu; toqquşma yoxdursa) | `period` |

### 11.3 Prod nüsxəsində (`ems_prod_1027`, təmiz nüsxə: dry-run → apply → dry-run)

| Əmr | Tətbiq | Yoxlama dry-run |
|---|---|---|
| Planlar | relocate 22 bənd / 16 tələbə / 15 mənbə açılış / 117 xana / 4 bərpa; merge 31 cüt; kinds 115 dərs | — |
| `fix_legacy_lesson_kinds` | 13 açılış / 70 dərs / 9 slot (lab-only); `--include-mixed` ilə +16 açılış / 37 dərs | 0 yazı |
| `relocate_twin_enrollment` | 117 xana, 4 qayıb bərpası, 57 fantom dərs silindi, 22 qeydiyyat yaradıldı / 22 düşürüldü | 0 yazı |
| `merge_twin_offerings` | 29 cüt birləşdi (204 dərs, 2 186 xana, 27 sillabus, 9 slot köçdü), 2 cüt «hər iki tərəfdə xana» — toxunulmadı; W adına 6 yük sətri qalır (hesabat) | 0 yazı |
| `fix_slot_week_parity` | 46 slot hər həftəyə; 13 toqquşma (qalır) | 0 yazı |

Diaqnozun 653 «fantom dərs» detektoru legacy sübutu olmadan sayırdı; legacy sübutlu əkiz (paralel qrup) halı 117 xanadır —
qalanı eyni ailədir (ana ↔ alt qrup), birgə dərs və ya bütöv jurnalın yanlış qrupda olmasıdır (məs. 635 «Mülki müdafiə»
ortaq jurnalı — sahib qərarı). Alt həftə: 673 çıxarılmış üst/alt slotdan yalnız 58-in ÖZ dərs tarixçəsində ≥2 ardıcıl
həftə var (diaqnozun 255-i başqa növ/saatdakı dərsləri də sayırdı — «üst həftə mühazirə, alt həftə seminar» əsl
növbələşmədir).

### 11.4 Prod addımları (hər biri sahibin «hə»sı ilə; canlı imtahan günü deyil)

1. Kodu prod-a çatdır.
2. Lokal: TƏZƏ prod nüsxəsi üzərində `build_twin_repair_plans` (köhnə sistemin cari dump-ı ilə) → `relocate.json`,
   `merge.json`, `lessonkinds.json` → hər birini `STAFF_PLAN_KEY` ilə şifrələ (`*.json.enc`) → bir draft release
   (`rim-fix-YYYYMMDD-…`).
3. `prod-data-ops`, ARDICIL (sıra vacibdir — birləşmə dərsləri yenidən yaradır):
   `fix_legacy_lesson_kinds` (`roster_tag`, dry-run → apply; `create_missing=true` ilə ikinci qaçış — qarışıq plan) →
   `relocate_twin_enrollment` → `merge_twin_offerings` → `fix_slot_week_parity` (`period`). Hər birindən sonra eyni
   girişlə yoxlama dry-run-u (yazı sayğacları olmamalıdır).
4. Release asset-lərini və lokal planları sil.

## 12. Müəllimin köhnə sillabusu — `syllabi_backfill` fazası (2026-10-27)

Sahib: «Köhnə sistemdə jurnalı olan müəllimlərin sillabusu burda görünmür — mövcud olanlara dəymədən köhnələri gətir.»
Səbəb: `syllabi` fazası sillabusu açılışa bağlayıb müəllifi **açılışın müəllimi** edir (birləşmiş jurnalların digər
müəllimləri öz sillabusunu itirib); cutover-in `syllabus_migration` fazası prod-da işləməyib. Ölçü: ~114 müəllim /
~194 (fənn, müəllim) cütü.

* **Paket** (`legacy_delta_extract --teacher-syllabi`, LOKAL, yalnız MariaDB oxunur, Django bazasına toxunmur): cari
  semestrin (`semestr_jurnal.is_current`, və ya bir `--full-semester`) saxta olmayan jurnal başlıqları (tələbə/qrup
  siyahısı boş) + hər (müəllim, fənn) cütü üçün müəllimin bütün köhnə sillabusları (eyni adlı dublikat fənn daxil) +
  jurnalların öz `sillabus_id`-si. `snapshot.phases = ["syllabi_backfill"]` — paket adi fazalarla RƏDD olunur
  (`legacy_delta_teacher_syllabi_bundle_phase_mismatch`); workflow-a yeni giriş lazım deyil.
* **Tətbiq** (`services/delta/syllabi_backfill.py`): müəllim — delta `TeacherMapper`, **hesab yaradılmır**
  (`teacher_unresolved`); fənn — `Catalog.subject_for` (`subject_unresolved`); müəllimin bu fəndə istənilən aktiv
  sillabusu varsa (müəllif və ya açılış müəllimi kimi) — **toxunulmur** (`skipped_existing`), eyni açarlı passiv baza
  dosye də (`skipped_inactive_base`); mənbə — jurnalın öz sillabusu (eyni fənn, boş deyil), yoxsa müəllim + fənnin ən
  yeni aktiv boş olmayan sillabusu (`empty` / `no_syllabus`); hədəf — semestrsiz **baza sillabus**
  (`import_migrated_version`, `approval_source=migration`, müəllif = köhnə müəllim, məzmun `syllabi` fazasının
  çeviricisi ilə). Jurnal onu `syllabus_for_offering`-in 3-cü pilləsi (fənn + açılışın müəllimi) ilə tapır; müəllimin
  «Sillabuslar» siyahısının cari il görünüşü semestrsiz baza dosyeni də göstərir. İdempotent (ikinci qaçış
  `created 0`). Stdout: `syllabi_backfill.<açar> <say>` sətirləri (pairs, created, skipped_existing,
  skipped_inactive_base, teacher_unresolved, subject_unresolved, empty, no_syllabus, duplicate_pair).

### 12.1 Prod addımları (hər biri sahibin «hə»sı ilə; canlı imtahan günü deyil)

```bash
# 1) LOKAL paket (MariaDB nüsxəsi — köhnə sistemin TƏZƏ dump-ı myedu_new-da)
python manage.py legacy_delta_extract --port 50330 --password-file <fayl> --source myedu_new --teacher-syllabi \
  --snapshot-file "<dump>" --out ~/EMSArena-backups/legacy-delta-2026-10/delta-syllabi-20261027.json.gz
# (ixtiyari) prod NÜSXƏSİNDƏ dry-run: python manage.py legacy_delta_apply --bundle <paket> --organization qku
# 2) şifrələ → draft release (asset adı MƏHZ delta.json.gz.enc)
openssl enc -aes-256-cbc -md sha256 -pbkdf2 -iter 200000 -salt -pass env:STAFF_PLAN_KEY \
  -in delta-syllabi-20261027.json.gz -out delta.json.gz.enc
gh release create legacy-delta-syllabi-20261027 delta.json.gz.enc --draft --title legacy-delta-syllabi-20261027
```

3. `prod-data-ops` → `command=legacy_delta_apply`, `roster_tag=legacy-delta-syllabi-20261027`, `batch=<paketin
   sha256-sı>`, `date_to`/`date_from` boş, `apply` işarəsiz → **dry-run**; xülasədə `syllabi_backfill.created` ≈ ölçü
   (~194 cüt), `written.*` / `teacher.created` sətri olmamalıdır.
4. Sahibin «hə»sından sonra eyni girişlərlə `apply=true`, `confirm=APPLY` (addım əvvəlcə backup alır).
5. Yoxlama: eyni girişlərlə dry-run → `syllabi_backfill.created 0`. Release asset-ini sil.

Geri qaytarma: audit sətrinin (`legacy_import.delta_batch`, `resource_id` = tag) `created.syllabus_versions`
id-ləri — həmin versiyaların baza dosyeləri (yalnız bu qaçışda yaranıb) silinə bilər.

## 13. Bir sillabus — bir neçə jurnal (`syllabi_share`, `SyllabusShare`, 2026-10-27)

Sahib: «müəllim köhnə jurnalda o sillabusu 2 qrup üçün istifadə edib; jurnalı aktivləşdirərkən indi o bir qrup üçün
görünür, 2-ci üçün yox … köhnədən gələndə elə olsun — bir sillabus» + «müəllim istəsə eynisini istifadə etsin eyni
qrupa öz yerində» + «müəllimin köhnə illərdəki sillabusları görünməsin».

* **Model** — `syllabus.SyllabusShare` (migrasiya `syllabus.0008`, RLS + eyni-təşkilat triggerləri): dosye öz açılışında
  qalır, əlavə açılış ona SURƏTSİZ bağlanır. Bir açılış ən çox bir paylaşıma; açılışın öz dosyesi üstündür (öz dosye
  yaradılanda paylaşım silinir). Paylaşım yalnız açılışın CARİ müəllimi dosyenin müəllifi / öz açılışının müəllimi
  olanda tətbiq olunur (təhvildən sonra yeni müəllim köhnə müəllimin sillabusunu görmür).
* **Həll** — `syllabus_for_offering` (öz → paylaşım → fənn+semestr → baza), `student_syllabus_map`,
  `approved_week_rows_for_offerings` (`link_lesson_syllabus_weeks`), `semester_readiness` eyni pilləni görür. Təsdiq,
  versiya, tamamlanma faizi BİRDİR.
* **UI** — təkrar istifadə dialoqunda «Eyni sillabusu bu qrupda da istifadə et (bir sillabus)» (yalnız öz sillabusu,
  eyni fənn + semestr, sillabussuz qrup); redaktorda «Bir sillabus — bir neçə jurnal» bloku: paylaşılan qruplar
  («Ayır») + sillabussuz öz qruplarınız (seçim komponenti, «Bu qrupda da istifadə et»); siyahıda «Həmçinin bu
  qruplarda istifadə olunur». Müəllim (geniş baxış əhatəsi YOX) mənbə kimi yalnız CARİ tədris ilinin və semestrsiz
  baza dosyenin sillabusunu görür / işlədir (`reuse.source_old_year`).
* **Delta** — `syllabi` fazası eyni köhnə sillabusu eyni müəllimin qruplarına BİR dəfə köçürür, qalanlarını paylaşır;
  `syllabi_backfill` fazası ilə birgə həmişə `syllabi_share` də işləyir; `--teacher-syllabi` paketi indi jurnalların
  `groups_id`-sini və `groups` bölməsini saxlayır.
* **Təmir** — `share_legacy_syllabi --bundle <paket> --organization qku [--teacher ad.soyad] [--expected-sha256 …]`
  (defolt dry-run; `--apply`). Eyni köhnə sillabusu işlədən qruplardan birinin köçmüş dosyesi (məzmun izi: həftəlik
  mövzular + təsvir + nəticələr) lövbərdir; sillabusu OLMAYAN qruplar ona bağlanır. FILL-ONLY, idempotent.
  Stdout: bir `syllabi_share: açar=say …` sətri.

### 13.1 Prod nüsxəsində (`ems_prod_1027`, klon, `delta5-graduation-owner-20261025` paketi)

* 869 köhnə sillabus; 252-si eyni müəllimin 2+ qrupunda (665 açılış); 223-ünün lövbəri var, qalan **372 qrupun ÖZ
  surəti artıq var** (`own_copy` — fill-only qaydası ilə toxunulmur), 26 dəstdə heç bir qrupa köçməyib (`no_anchor`).
  Nəticə: `linked=0` — bu paketlə cari prod-da paylaşılacaq boş qrup YOXDUR.
* Prod-un «sillabussuz» 51 açılışı (eyni müəllimin eyni fəndə başqa qrupunda sillabus var) köhnə sistemdə həmin
  sillabusu işlədən jurnala bağlı deyil (əkiz fənn kartı, tapşırıq idxalı ilə açılan qrup və s.) — onları müəllim
  dialoqda «Eyni sillabusu bu qrupda da istifadə et» ilə özü bağlayır.
* Simulyasiya (klonda 341 toxunulmamış surət passiv edildi — «köhnə idxal bir dəfə köçürsəydi» vəziyyəti):
  dry-run `linked=314` → apply `linked=314` → dry-run `linked=0, covered=340`; sillabussuz açılış 731 → 417;
  314 paylaşılan açılışın hamısında jurnal, tələbə, həftəlik plan və «Semestr hazırlığı» lövbəri görür.

### 13.2 Prod addımları (hər biri sahibin «hə»sı ilə; canlı imtahan günü deyil)

1. Deploy (`syllabus.0008` migrasiyası).
2. TƏZƏ paket: `legacy_delta_extract … --teacher-syllabi` (indi qruplarla) → şifrələ → draft release
   `legacy-delta-syllabi-<tarix>` (asset `delta.json.gz.enc`), §12.1 ilə eyni.
3. `prod-data-ops` → `command=share_legacy_syllabi`, `roster_tag=legacy-delta-syllabi-<tarix>`, `batch=<sha256>`,
   `teacher` boş, `apply` işarəsiz → dry-run; `syllabi_share: … linked=N` sətrinə bax.
4. «Hə»dan sonra eyni girişlər + `apply=true`, `confirm=APPLY` (əvvəl backup). Yoxlama: təkrar dry-run → `linked=0`.
5. (§12) `legacy_delta_apply` eyni paketlə `syllabi_backfill` — artıq `syllabi_share` də daxildir.

Geri qaytarma: audit sətri (`legacy_import.delta_batch`, tag) `created.syllabus_shares` = bağlanan açılışların id-ləri
→ həmin açılışların `SyllabusShare` sətirləri silinir (və ya müəllim redaktorda «Ayır»).
