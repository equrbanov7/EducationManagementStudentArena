# Sillabus mənbə dövrəsi: qoruma və ayrıca forensic məzmun auditi

`copy_adjust` mövcud DRAFT versiyasını eyni PK-də yeniləyə bilir. Buna görə
A→B kopyasından sonra B→A kopyası iki real əməliyyat olmaqla yanaşı dairəvi
`source_version_id` yarada bilər. Versiyanın `created_at` tarixi son yerində
kopyalama vaxtı deyil: daha köhnə versiyanın əlaqəsini səhv saymaq olmaz.
`approval_source=human` olan DRAFT insan tərəfindən təsdiqlənmiş məzmun demək deyil.

İki məlum qaralamanın məzmunu, statusu, təsdiq atributları, göstəriciləri və
əvvəlki əlaqələri dəyişdirilmir. Bu paket mövcud dövrəni “təmir” etmir.
Normal məzmun collector-u dövrəni əvvəlki kimi rədd edir; normal offline
validator da dövrəli məzmunu qəbul etmir.

## Yeni dövrələrin qarşısı

Kopyalama/bağlama/sinxron yazıları üçün tenant daxilində transaction advisory
lock alınır. Kilid gözlənilmir: paralel kopyalama təkrar cəhd üçün təhlükəsiz
səbəb kodu ilə dayanır. Mövcud versiyanın məzmunu və təsdiq statusu yazılmadan
əvvəl mənbənin ən çox 64 əcdadı təzə DB sətirlərindən yoxlanır/kilidlənir.
Özünə/qaralama hədəfinə qayıdış, mövcud dövrə, başqa tenant, itmiş mənbə və
limit aşılması yazını dayandırır. Bu qoruma kimlik/RBAC qaydalarını əvəz etmir.
Tarixi dövrədən yeni versiyaya məzmun köçürmək də qəbul edilmir.

## İki ayrıca, yalnız oxu kapsulu

Workflow: `syllabus-forensic-export.yml`; girişlər yalnız aktiv sabit tenant
superadmini `actor` və `chair-cells-027` / `chair-cells-029` seçimidir.
Hər iş ayrıca 20 sabit registry kökü üçündür. Birləşmiş 40-kök query və ya
25-kök limitinin artırılması yoxdur. Host `/app/build-info.json` SHA-sını
`GITHUB_SHA` ilə yoxlayır. Private quarantine-dən yalnız təsdiqlənmiş şifrəli
fayl və run/attempt/HEAD/registry/batch/SHA manifesti artifact-a keçir.
Uğursuz iş artifact dərc etmir; always-finalizer host/container qovluqlarını silir.

```text
export_wcu_syllabus_forensic --actor USER --batch chair-cells-027 --public-key FILE --output NEW_FILE
export_wcu_syllabus_forensic --actor USER --batch chair-cells-029 --public-key FILE --output NEW_FILE
decrypt_syllabus_forensic.py --input ENVELOPE --private-key KEY --output-dir PRIVATE_DIR
```

Format `wcu-syllabus-content-cycle-forensic/1`-dir. Normal resolver, seçilmiş/
öz/cari/təsdiqlənmiş/mənbə ancestry closure və mövcud section/topic/body SHA
proyeksiyaları təkrar istifadə olunur. Bütün statement/time/query/row/byte
limitləri saxlanır. İxrac təzə REPEATABLE READ READ ONLY transaction-dadır;
naməlum tenant/itmiş reference/owner mismatch/limit aşılması tam işi dayandırır.
Dövrə visited-set ilə sonlanır və tam ID əlaqələri açıq qaytarılır.

`lineage_edges`, `lineage_cycles`, `held_roots` hər kökün dövrədən təsirlənib-
təsirlənmədiyini göstərir. Bütün 20 kökün body/section/topic fingerprintləri
qorunur; dövrədən təsirlənməyənlər müqayisə edilə bilər, təsirlənənlər held qalır.
`closure_complete=false`, `lineage_visited_complete=true`,
`lineage_integrity=false`, `normal_content_export_usable=false`,
`eligible_for_apply=false` açıq saxlanır. Hash fərqi yanlış məzmun, metadata
boşluğu isə məzmunun yoxluğu kimi şərh olunmur.

Kapsulda xam mətn, kontakt, JSON bölmə datası, qiymət və tələbə siyahısı yoxdur.
AES-GCM/RSA envelope və ayrıca strict schema/registry/typed edge recomputation
validator-u saxlanır. Dövrə siyahısını, held flag-ları və normal istifadə flag-ını
saxtalaşdırmaq rədd edilir. Mənbə əlaqələrini dəyişmək üçün ayrıca sübut/review
lazımdır; burada heç bir production dispatch və ya pointer mutation yoxdur.
