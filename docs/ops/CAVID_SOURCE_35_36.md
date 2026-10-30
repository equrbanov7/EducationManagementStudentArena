# Rəsmi Maliyyə source35/36 bərpası

24Oktyabr Maliyyə sənədinin SHA256-sı
`3c87f7f625b57360522c0f3eb31a29dc464dea52edba0e0dc8b9137c5019f32f`.
İki mənbə sətri birlikdə, bir tranzaksiyada tətbiq edilir:

- Source35: Cavid Xəlilov Murad11586,533MU, Vergitutmanın auditi30M30S.
  Mövcud `8390e6fd-e457-479b-ac27-bd519116be76` jurnalına çatışmayan yük sətri əlavə olunur.
  Source tələbə sayı6dır, jurnaldakı7 enrollment dəyişmir.
- Source36:403/5MN Tədqiqat analitikası30M15S. Müəllim Murad11586dır,
  hazırkı Bəxtiyar8258lə ayrı şəxsdir. Əsas Maliyyə üzvlüyü qalır, Təbiətdə
  canonical əlavə `is_primary=False` müəllim üzvlüyü yaranır. Mövcud45saatlı
  `f0555a39-ac5e-4c0c-89d8-a272bbcda281` jurnalı canonicalhandover ilə təhvil verilir.
  Köhnə sahib yalnızoxu müşahidəçisi olur, tarixçə qalır. Hesablar birləşdirilmir.

`repair_cavid_source_batch` defoltda bütün əməli yazıb sonda rollback edir.
Apply üçün əvvəlki dry-run-un exact baselineSHA-sı məcburidir. Tenant, IDs,
tam ad/ata adı, əsas üzvlük, fiziki qrup və semestr allowlist-lə sabitdir.
B jurnalı2enrollment,0dərs/qiymət/sillabus olmalıdır; aktiv manual pay varsa bloklanır.
A-nın ən az12dərs/84xanası və hər iki jurnalın bütün məzmunu fingerprint-lə qorunur.
Mövcud mühazirə assignmentID-si saxlanır. Yeni sətir, assignment və membershipID-ləri
auditreceipt-ə yazılır. Final sync yalnız bu iki sətirlə `create=False` çağırılır,
yeni və ya yenilənən jurnal/enrollment sayı sıfır olmalıdır.

PostgreSQL full-rowhash-ləri bütün tenantın akademik qeydlərini, qruplarını,
rollarını və manual üzvlüklərini müqayisə edir. Yalnız B sahibinin dəyişməsi,
bir canonicalhandover və konkret əlavə Təbiət üzvlüyü istisnadır. Tam qiymət və
tələbə məlumatları auditə çıxmır, yalnız say/fingerprint saxlanır.

```sh
python manage.py repair_cavid_source_batch --actor USER --org qku \
  --source-sha256 3c87f7f625b57360522c0f3eb31a29dc464dea52edba0e0dc8b9137c5019f32f
```

Apply: yuxarıdakı əmrə `--expected-baseline SHA --apply` əlavə edin.
Undo preview:`--undo cavid3536-YYYYMMDD-HHMMSS-xxxx`; undoapply də həmin preview-in
baseline-ını tələb edir. Undo source-createdArow/assignments-i canonical yollarla
götürür, B-nin originalassignment-ni bərpa edir, təhvili canonicalrevert edir.
Əlavə üzvlük silinmir, əvvəlki inactive vəziyyətə qaytarılır. Əsas üzvlük qalmış olur.
Sonrakı workload/access dəyişikliyi və ya B-də yeni dərs/qiymət undo-nu bloklayır.
A-da sonradan yazılmış qiymətlər qorunur. Amendment/audit/təhvil tarixçəsi qalır.

ProdDataOps route helper:`scripts/ops/cavid_source_batch_args.sh`.
Sabitcommand:`repair_cavid_source_batch`; batchblank=dryrun, baselineSHA=apply,
undoID=undopreview, undoID:baselineSHA=undoapply; roster_tagboş olmalıdır.
Stdoutprefix:`cavid3536:`. Workflow özü backup və apply/confirm=APPLY qaydasını saxlamalıdır.
