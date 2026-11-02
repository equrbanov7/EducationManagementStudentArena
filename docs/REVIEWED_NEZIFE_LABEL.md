# Nəzifə —336F2 üçün yanlış «cədvəldən kənar» nişanı

**Tətbiq edilməyib.** Yalnız8420`nezife.asirova` / Nəzifə Aşırova Vilayət,
QKU1022«Öyrənilən əsas dil-1»,336F2,2026/2027payız üçün sabit əməliyyatdır.

Mənbə yoxlaması: `nezife336F2-stale-label-proof-20261102.json` (RİM private proof).
21oktyabr2026,çərşənbə,11:50–13:20,seminar,2saat,379nömrəli otaq qeydi(otaqadı53)
mövcud `c7b0d9bc-03fa-4398-a676-4a9747b73b1d` həftəlik slotla tam uyğun gəlir.
Müəllimin səbəbi **«Cədvələ aiddir bu dərs»** olub; cari forma bu köhnə nişanı dəyişmir.

`force_schedule_exception` UI sorğusunun parametridir, ayrıca DB bayrağı deyil.
Saxlanmış nişan `Lesson.off_schedule_reason` sahəsindən hesablanır. Buna görə yalnız
`6a2f801f-a770-48c2-aa3c-73043c461865` dərsində bu səbəb boşaldılır. Tarix, saat,
növ, müəllim, mövzu, otaq,21bal/davamiyyət xanası və cədvəl dəyişmir.

Əməliyyat MR116/117`request_schedule_labels` pattern-ində metadata-only işləyir;
əlavə olaraq sabit canlı cədvəl/otaq/tenant/müəllim tamlığı, fullSQLacademicreversegraph,
yeni dry-run baseline, idempotent audit receipt və tam geri qaytarma var.
Sonradan dəyişmiş21xana,roster,başqa dərs və ya cədvəl baseline-i pozur. Room/slotdəyişibsə,
park/silinmə və başqa səbəb varsa əməl dayanır. Başqa dərslərin səbəbləri saxlanır.

Workflow: **Reviewed Nezife fixed scheduled lesson label**. Növbəti bundle CI/deploy-dan
sonra əvvəl dry-run, sonra freshbaseline+`apply=true`+`confirm=APPLY`. Deploy HEAD uyğunluğu
və ortaq production-deploy kilidi tələb olunur. Açıq məlumat və parol çıxışı yoxdur.

```sh
python manage.py repair_reviewed_nezife_label --actor OPERATOR
python manage.py repair_reviewed_nezife_label --actor OPERATOR --apply --expected-baseline FRESH_SHA
python manage.py repair_reviewed_nezife_label --actor OPERATOR --undo RECEIPT_UUID
python manage.py repair_reviewed_nezife_label --actor OPERATOR --undo RECEIPT_UUID --apply --expected-baseline FRESH_UNDO_SHA
```
