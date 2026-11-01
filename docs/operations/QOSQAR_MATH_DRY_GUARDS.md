# Qoşqar və Math dry-run guard-larının məhdud dəqiqləşdirilməsi

41269266620 dry-run `alternate_workload_requires_review` ilə dayandı.
Səbəb `e2ed0137-c68e-4c8f-ba1c-437565990724` seçim bloku idi:
plan M45/S45, faktiki cəmlər 0/0, union/subgroup 0/0, təyinat yoxdur.
Bu sətir silinmir və saatlandırılmır. Yalnız onun pinlənmiş tenant, task,
dövr, fənn, qrup və sıfır yük forması qəbul edilir. Başqa alternate sətir,
müsbət cəm, yeni təyinat və ya kimlik dəyişikliyi əməliyyatı saxlayır.
Sətir əvvəl/sonra qorunan qrafda qalır.

Əvvəl təsdiqlənmiş 1487 dublikat yükünün çıxarılması yalnız
`b56648eb-fa8c-4e58-8054-e7f88bab9cff` sətrinin iki mövcud təyinatını əhatə
edir: `005e01da-7983-48c1-9c5f-3cdae4682055` və
`bd83bf34-d06f-4e97-b748-4816a84f3a08`. Hər ikisinin mövcud
`is_hourly_paid=True` dəyəri pinlənir. Bu payroll yoxlaması deyil.
Bayraqlar False edilmir; silinən qeydlərin tam provenance-i receipt-də
qalır və strict undo zamanı eyni UUID və bayraqlarla bərpa edilir.
Saxlanan canonical təyinatların False bayraqları dəyişmir.

41269324364 Math dry-run `wrong_row_has_prior_amendment` ilə dayandı.
Bu guard saxlanır. Cari amendment məzmunu əvvəlki snapshot-da yox idi;
oldclone-da sıfır qeyd olması cari production tarixçəsinin yoxluğunu sübut etmir.

Növbəti adi şifrələnmiş workload snapshot-a iki əlavə bölmə daxil edilir:

- `repair_math_history_scope`: sabit task/row, iki gözlənilən assignment UUID-si,
  faktiki assignment UUID-ləri, root-un görünməsi və bounded closure sayı.
- `repair_math_history`: həmin row və onun reverse descendant qeydləri;
  generic-target amendments ayrıca daxil edilir. Model/UUID, tipli FK əlaqələri,
  actor ID-ləri, tarixlər, reason/status kodları, tipli material əvvəl/sonra
  dəyərləri, raw JSON və tam qeyd üçün SHA-256, note/document mövcudluğu verilir.

Sabit Math row: `eb41b840-05b1-4637-8c2c-03fb8b36c0c3`.
Gözlənilən təyinatlar `45e4d53b-e6b0-4891-afc4-d387ee6307ec` və
`4db00940-f2a3-4d54-97ff-6f7730bd0af1`.
Raw note, text, contact, sənəd yolu və ixtiyari raw JSON çıxarılmır.
2500 qeyd büdcəsi aşılarsa export kəsilmir, tamamilə dayanır.

Bu bölmələr tətbiq icazəsi vermir. Yeni sübut gələndən sonra amendment və
əlaqəli tarixçə ayrıca qiymətləndirilməlidir. Math guard-unu avtomatik açan
allowlist yoxdur. Köhnə workload snapshot-larda bu iki bölmə opsionaldır;
mövcud journal-cell formatının decoder yolu dəyişmir.
