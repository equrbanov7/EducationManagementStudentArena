# Sabit cari cədvəl sübutu

Bu ixrac cədvəl düzəlişi üçün məlumat toplayır; özü heç nə tətbiq etmir.
`cohort.json` 188 jurnal / 85 müəllimlik yoxlanmış mənbə hesabatına bağlanıb.
Hesabat SHA256: `cd14ea8f44a4d5710eaabdaaf9a89a742099d4523a88e663b0f347e7bc6c0a71`.
Manifest SHA256: `409eedde0772ccef514b501148666deef28d1fb85eae9ee30702239c3a0e6c2d`.

- Yalnız `timetable-review-001`…`008`; bir kapsulda maksimum 25 sabit kök jurnal.
- Aktiv tenant superadmini və təzə PostgreSQL `REPEATABLE READ READ ONLY` tranzaksiyası tələb olunur; RLS bypass söndürülür.
- Cari və park/arxiv edilmiş cədvəl sətirləri, faktiki dərs vaxtları və cədvəldənkənar qeyd mövcudluğu, dərs düzəlişləri, növə görə cari yük bölgüsü və bütün sətrin qrup əlaqələri götürülür.
- Heç bir tələbə, qiymət, davamiyyət xanası və parol götürülmür. Şəxs adları, sərbəst qeydlər, qrup qeydləri, səbəblər və audit JSON-u PostgreSQL-dən açıq mətn kimi çıxmır: yalnız mövcudluq/istinad və server SHA256 verilir.
- `raw_record_sha256`: PostgreSQL `row_to_json(table)::text` UTF-8 SHA256; xüsusi sahə hash-ləri `COALESCE(to_jsonb(field)::text,'null')` UTF-8 SHA256-dır. Bunları Python JSON hash-i ilə əvəz etməyin.
- Standart zənglər akademik saat çevirmə siyasətini sübut etmir. Açıq 40/45 dəqiqə siyasəti yoxdursa naməlum saxlanır; bitmə vaxtı uydurulmur.
- Yalnız eyni sabit kapsula aid cədvəl/dərs audit istinadları verilir; auditin olmaması keçmişdə redaktə edilməməsinin sübutu deyil. Kapsuldan kənar müəllim/otaq toqquşmaları tətbiq vaxtı semestr kilidi altında ayrıca yenidən yoxlanmalıdır.

Workflow: `.github/workflows/timetable-evidence-export.yml`. Yalnız `actor` və sabit `batch` seçimi var; sərbəst ID, təşkilat, SQL, apply və undo parametri yoxdur. Deployed HEAD workflow SHA ilə eyni olmalıdır. Çıxış sabit universitet açarı ilə AES-GCM/RSA-OAEP şifrələnir; artefakt bir gün saxlanır.

Lokal açma:

```sh
python scripts/ops/decrypt_timetable_evidence.py --input snapshot.enc.json --private-key PRIVATE_KEY --output-dir PRIVATE_0700_DIRECTORY
```

Açan alət autentifikasiyanı, manifesti, bütün cədvəl/sahə siyahılarını, kapsul sərhədlərini, sayı və əlaqələri yoxlayır. Yalnız yeni 0600 fayl yaradır.

## Adi inference üçün təhlükəsiz defolt

`infer_timetable_from_lessons` indi öz müəllifi göstərilmiş, sintez edilməmiş, real başlanğıc/bitmə vaxtı olan dərsləri istifadə edir. Cari eyni fənn/dövr/qrup/dərs tipi üçün təsdiqlənmiş və qeydsiz müsbət yük təyinatı da tələb edilir; sərbəst altqrup qeydi bütün qrup üçün təyinat sayılmır. Ən azı iki tarix tələb edilir; saatı zəngə çəkmə və tək son dərsdən həftəlik slot yaratma söndürülüb. Ziddiyyətli real bitmə vaxtı saxlanılır, başqa dərsdən otaq götürülmür. Mövcud rəsmi/əl ilə yazılmış cədvəl silinmir və dəyişdirilmir.

Köhnə davranış yalnız ayrıca yoxlanmış plan üçün açıq `--legacy-heuristics` seçimi ilə mümkündür. Bu seçim tarixi müəllif/saat sübutunu əvəz etmir. Kapsullar yalnız sübut toplamaq üçündür; hər gələcək düzəliş ayrıca mənbə uyğunluğu, təzə fingerprint, toqquşma, dry-run və geri qaytarma qoruması tələb edir.
