# Asəf Qəribov — rəsmi patokun saat düzəlişi

Mənbə: Ümumi iqtisadiyyatın 2026/2027 Excel sənədi, `Dərs yükü` vərəqi, 9-cu sətir. Orijinal SHA256: `37557f086dd1b3a1d31c53d76e755ed65302b6cb326ebe7856a71db21c5cc2da`.

`536 MRK, 536 Bİ` üçün eyni sətirdə 30 mühazirə və 30 seminar yazılıb. Cari sistemdə bu yük səhvən MRK üçün 23+22, Bİ2 üçün 8+7 bölünüb. Bİ1-in mövcud jurnalı da vahid yükə bağlanmalıdır. Qeydiyyatdakı Bİ1/Bİ2 ana qrup əlaqələri ayrıca yoxlanılır.

Düzəliş iki mövcud yük sətrindən birini 30+30 vahid patok sətrinə çevirir, digərinin bölgüsünü sıfırlayır. Üç qrup vahid sətrə bağlanır; üç mövcud jurnalın hər birində kontakt həddi 60 olur. Müəllimin bu fənn üzrə yükü 60 saat olaraq qalır, 180 saata çoxaldılmır. Üç təsdiqlənmiş, öz mənbə sillabusunun həftəlik məzmunu artıq 30+30-dur; yalnız səhv `plan_hours` metadatası düzəlir.

30 dərs, 432 xana və 75 qeydiyyat; ballar (0 daxil), q/b, i/e, üzrlü qeydlər, müəlliflər, tarixlər, imtahanlar, sillabus mətni və təsdiq məlumatları dəyişdirilmir. Mövcud 4 kredit və saat hesabı bayraqları saxlanılır; Excel-dəki 6 kredit / saat hesabı fərqi bu əməliyyata daxil deyil. Yeni jurnal yaradılmır, mövcud jurnal görünüşləri birləşdirilmir.

## İcra

Yalnız deploy tamamlandıqdan sonra `Reviewed Asəf official 60h shared stream` workflow-u çağırılır. Default dry-run-dır. Operator deploy olunmuş HEAD-i yoxlayır və yalnız bu sabit native əmri işlədir.

```bash
python manage.py repair_reviewed_asef_stream --actor OPERATOR
python manage.py repair_reviewed_asef_stream --actor OPERATOR --apply --expected-baseline DRY_RUN_SHA256
```

Workflow üçün tətbiq parametrləri: `actor`, təzə `baseline`, `apply=true`, `confirm=APPLY`. Təkrar icra dəyişiklik etmir. Geri alma ayrıca təzə dry-run, tətbiq receipt UUID-si və cari vəziyyətin tam uyğunluğunu tələb edir:

```bash
python manage.py repair_reviewed_asef_stream --actor OPERATOR --undo RECEIPT_UUID
python manage.py repair_reviewed_asef_stream --actor OPERATOR --undo RECEIPT_UUID --apply --expected-baseline DRY_RUN_SHA256
```

İstənilən cari qeyd/sətir/mənbə/sillabus uyğunsuzluğu əməliyyatı dayandırır. Yeni yazılmış xana varsa, köhnə receipt ilə geri alma qəbul edilmir. Atomik əməliyyatın sonunda akademik əlaqələrin tam qapanma hash-i yoxlanılır; fərq olsa hər şey geri qaytarılır.
