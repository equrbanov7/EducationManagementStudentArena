# WCU dərs yükünün məhdud ixracı

Bu əməliyyat tam DB dump deyil. Sabit təşkilat
`526cfa63-4f80-4bba-a7a7-61c8fbb3d918`, il `2026/2027`.
`export_wcu_workload_snapshot` yalnız aktiv Django superuser aktoru qəbul edir;
read-only repeatable-read tranzaksiya və bypass-sız tenant RLS konteksti qurur.
Bütün domain sorğularında ayrıca organization filter var. Tenantı, ili və ya
SQL-i workflow girişindən dəyişmək mümkün deyil. Empty fixed scope fail-closed-dur.

Task/sətir/təyinat, patok plan/cəm/çarpan sahələri, qrupun `parent_group` əlaqəsi,
fənn kataloqu, dövr, offering, minimal müəllim adı/ata adı/username/aktivlik,
minimal müəllim membership IDs, sillabus ID/author/current-approved version
metadata ixrac olunur. Enrollment, student academic record, lesson və mark üçün
fərdi tələbə məlumatı deyil, aqreqat saylar və opaque state fingerprints var.
Tarixi instructor/kind saatları ayrıca aqreqatdır; NULL müəllim uydurulmur.
Şifrə hash-i, FIN, telefon, e-poçt, sənəd, sessiya/token, tələbə adı və fərdi qiymət,
Lesson mövzusu və sillabus məzmunu ixrac olunmur. MD5 fingerprints sadəcə
change-detector-dur; ixracın bütövlüyünü AES-GCM təmin edir.

Envelope: AES256-GCM, təsadüfi açar+nonce, RSA-OAEP-SHA256 ilə wrapping.
Public key fingerprint sabitdir. Private key repoda/prod-da yoxdur.
Plaintext yalnız proses yaddaşındadır; diskə0600 encrypted envelope yazılır.
Mövcud output O_EXCL ilə əvəz edilmir. Stdout yalnız ciphertext hash və saylardır.

Manual `workload-scoped-export.yml` mövcud Prod Data Ops runner/container,
`production` environment, `production-deploy` concurrency naxışını saxlayır.
Deploy olunmuş command tələb olunur. Workflow yalnız `actor` qəbul edir,
checkout credential saxlamır və public key-dən başqa faylı containerə köçürmür.
Encrypted artifact private repoda1gün saxlanır, scratch həmişə təmizlənir.
Workflow hazırlanması və ya git push özü ixracı işə salmır.

Yerli download/decrypt (private key məzmununu terminala çıxarmayın):

```sh
python scripts/ops/decrypt_workload_snapshot.py \
  --input /private/download/snapshot.enc.json \
  --private-key /private/existing/private.pem \
  --output-dir /private/existing/reconciliation-directory
```

Script DB-yə qoşulmur. Yeni tarixli+UUID `wcu-workload-*.json`0600 yaradır;
`ems_prod_1027` bazasına və əvvəlki JSON-lara toxunmur. Açar fingerprint,
AES authentication və decrypt edilmiş tenant/year əvvəlcə yoxlanır.

Manifest `schema_fields` real exported column adlarını göstərir.
`coverage`-də14/18 yalnız29Oct rəsmi mənbə əhatəsinin xarici audit qeydidir;
canlı bütün sətirlərin, müəllim hüquqlarının və ya sillabusların uyğunluğu demək
 deyil. Cari distinct chair/task sayları ayrıca hesablanır. Snapshot vaxtı
`captured_at` ilə qeyd edilir; köhnə27Oct snapshot yalnız ayrıca sübutdur.

## Tələbə-tərkibi müqayisəsi (ad və identifikatorsuz)

`group_sar_students` hər dəqiq groupUUID/status üçün student token set-i verir.
`group_enrollment_students` cari ilin offering-lərindən dəqiq groupUUID/period/status
üzrə unikal set verir. Sorğuların hər biri tenant və group/offering tenantını filter edir.
Hər capture üçün yeni təsadüfi256bit secret yaradılır; secret ixrac edilmir.
Token=HMAC-SHA256(tenant+studentID). Bir tələbə həmin snapshot-un SAR və enrollment,
ana/alt qruplarında eyni opaque token alır. Snapshotlar arasında linklənmir.
Student ID, ad, FIN və tələbə membership-ləri əlavə edilmir. Token sayı sətir
sayını deyil, unikal tələbə sayını göstərir.233KE/233KEaz alias qərarı və234K
ana/1/2 legitim ayrılması məlumatın üzərində dəyişiklik etmir; ing ayrıca qalır.

Command üçün worker-atomic gate-də yalnız onun dəqiq yolu istisnadır: capture
öz fresh read-only repeatable-read transaction və fixed RLS kontekstini yaradır;
outer transaction SET TRANSACTION ardıcıllığını pozar. Bu, ümumi gate istisnası deyil.
