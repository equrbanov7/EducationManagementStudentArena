# Four/Source28: dörd sabit yük receipt-inin SQL proyeksiyası

İlkin canlı yalnız-oxu mənbə: `41304708522`, HEAD
`ad2134333cb8536bf4f4bbb173ea6bdf04869145`. Metadata Four üçün 118 audit /
8,889,779 bayt, Source28 üçün 53 audit / 8,320,475 bayt göstərirdi. Bu saylar
köhnə snapshot-a aiddir, yeni dry-nin nəticəsi kimi təqdim edilmir.

Yalnız `workload_audit_receipt_spec.PINS`-dəki dörd audit ID-si və tam DB-sətir
SHA-sı şərti namizəddir: üç `workload.reviewed_source_batch`, bir
`workload.owner_activity_batch`. Həmin mənbədə cəmi 7,297,160 bayt idi. Ayrı-ayrı
JSON sahələrinin SQL SHA-ları, resource-ID hashı və tam-sətir bayt sayı da eyni
autentifikasiyalı metadata-dan pinlənib. Prefix, müəllim, ad və ya kod oxşarlığı
əsasında başqa audit sətri azad edilmir.

## Şərti sübut

Böyük `before` / `new_values` Python-a seçilmir. SQL yalnız sabit resource,
reason, UPDATE, apply, NULL old_values/changes, dəqiq top/before/details açar
qapıları, manifest/selection/baseline hash formatları, before-selection uyğunluğu
və qapalı model/count/fingerprint xəritələrini yoxlayır. Reviewed-source xəritəsi
before.academic-in həmin qorunan model alt-dəsti ilə eyni olmalıdır. Owner
receipt-i yalnız kodun əvvəl/sonra bərabərliyi yoxladıqdan sonra yazdığı tək
`academic_before_after` xəritəsini saxlayır: bu, ikinci tarixi xəritənin müstəqil
canlı rekonstruksiyası kimi göstərilmir. Python baseline-i PostgreSQL JSONB text
SHA-sı ilə yenidən hesablanmış sayılmır.

Qorunan xəritənin unknown modeli, çatışmayan grade/lesson/enrollment fingerprinti,
səhv tip, fərqli source/row/field SHA, başqa action/kind/reason və ya dəyişmiş
struktur HOLD-dur. Mövcud DB helper-inin count=0/md5="" EmptyResultSet sentinel-i
ayrıca tanınır; hər hansı qeyri-sıfır count üçün boş hash qəbul edilmir.

Bu təsnifat yalnız **qiymətə toxunmayan receipt niyyəti** deməkdir. Köhnə
reviewed-source yolu ayrıca təsdiqlənmiş katalog/üzvlük/təhvil əlavələri də
edə bilirdi; burada hüquqların və ya sahibin tarixən heç dəyişmədiyi iddia edilmir.
Cari bərpa heç bir köhnə receipt-i, hüququ və ya böyük snapshot-u dəyişdirmir.

## Versiyalı, doğru hash mənası

Four ixracı `wcu-four-cell-history/2` qaytarır. Decoder köhnə `/1` formatını
öz əvvəlki sahələri ilə qəbul edir; v1-də yeni SQL-hash proyeksiyası gizlədilmir.

- `projection=parsed_audit`: əvvəlki xam kiçik audit parser-i və
  `python-json-ascii-sorted-compact-sha256/1` JSON hash siyasəti.
- `projection=verified_workload_receipt`: yalnız bütün canlı yoxlamalar keçəndə;
  `postgres-jsonb-text-utf8-sha256/1` JSON hash siyasəti və
  `postgres-row_to_json-text-utf8-sha256/1` tam-sətir siyasəti. `case_ids=[]`
  qalır; receipt qiymət dəyişikliyi və ya mənbə-grade claim kimi təqdim edilmir.

Ümumi audit sayından sətir itmir. Scope ilkin SQL raw-bayt cəmini,
raw-parser mənbə baytlarını, kiçik proyeksiya baytlarını və hər iki sətir sayını
ayrı göstərir. Mövcud 8 MiB raw-parser+thin büdcəsi, unknown sətir üçün 1 MiB,
1000 audit sətri, typed-ref node/depth və query/time limitləri artırılmır.
Yalnız dəqiq dörd receipt böyük raw-parser girişindən çıxır; bütün digər
`superseded_marks_batch`, `repeated_sections_repair`, `empty_lesson`,
group-transfer və naməlum/grade/clear/delete auditləri əvvəlki tam parserdə qalır.

## Şəxsi semantik önbaxış

`wcu-recovery-audit-diagnostic/2` eyni actor-only readonly əmrinə bounded
`receipt_semantic_previews` əlavə edir; v1 metadata decoder tərəfindən ayrıca
qəbul olunur. Preview yalnız finite məlum açarlar, JSON tip etiketləri,
kind/hash/count/booleans və qapalı qorunan-model fingerprintləri verir.
Unknown açarların mətni, body, kontakt, reason və grade JSON-u çıxmır.
Səhv xəritə olduqda onun dəyəri NULL göstərilir, yalnız məlum model açarları və
unknown açar sayı/hashları qalır. `semantic_checks_passed=false` olduqda
source guard HOLD edir; preview heç vaxt `grade_apply_authority` vermir.

Formal correction/reversal/hygiene/LegacyGradeFact/Artifact və immutable ledger
qapıları, unknown deletion və mövcud grade-clear niyyəti qorunur. Ordinary audit
best-effort olaraq qalır, auditin olmaması silinmənin riyazi yoxluq sübutu deyil.
Four/Source28 apply üçün təzə tam history və ayrıca operator review hələ tələb
olunur. Bu paket heç bir production dispatch və ya grade yazısı icra etmir.
