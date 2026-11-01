# Altı yük düzəlişi jurnalının mövcud hüquqları — yalnız oxuyan sübut

`source_teacher_manual_share_requires_separate_review` kodu hazırda
`source != workload` olan aktiv paylara aiddir. Bu, payın mütləq `manual`
olduğunu göstərmir: `legacy` də həmin guard-a düşür.

Adi şifrələnmiş workload snapshot-a aşağıdakı opsional bölmələr əlavə edilir:

- `repair_contact_rights_scope` və `repair_contact_sources`: dörd baxılmış
  case-in altı dəqiq offering UUID-si, təsirlənən müəllim ID-ləri, rəsmi mənbə
  SHA-ları və faktiki görünən root-lar. Bunlar tətbiq icazəsi vermir.
- `repair_contact_offerings` və `repair_contact_shares`: mövcud sahib, saat,
  period/group/subject; bütün aktiv və qeyri-aktiv payların mənbəyi, dəqiq
  növ siyahısı, müəllimi, authorizer-i, vaxtları və tam qeyd/rights SHA-ları.
- `repair_contact_share_rows` və `repair_contact_enrollments`: dəqiq M2M
  qeyd ID-ləri və aid olduqları enrollment/course/student ID-ləri. Başqa
  açılışın enrollment-i ilə əlaqə exportu saxlayır; seçilmiş jurnalların
  tələbə məhdudiyyətləri birləşdirilmir.
- `repair_contact_handovers`: köhnə/yeni müəllim ID-ləri, authorizer,
  revert vəziyyəti, vaxtlar, reason mövcudluğu və tam qeyd SHA-sı.
- `repair_contact_share_audits`: seçilmiş pay/təhvil və onların batch
  qeydlərinin actor/vaxtları, seçilmiş obyekt ID-ləri, yalnız əlaqəli share
  manifest ID-ləri və raw əvvəl/sonra JSON SHA-ları. Auditdən yalnız icazəli
  sütunlar seçilir; IP/user-agent çıxarılmır.

`legacy`, `manual` və `workload` ayrı saxlanılır. Batch yalnız tanınmış
maşın formatındadırsa kodla, başqa halda hash və mövcudluq bayrağı ilə verilir.
Raw note, reason mətni, adlar, contact və ixtiyari JSON export edilmir.
Auditdə həqiqətən saxlanmış source SHA yoxdursa `source_sha256s=[]` qalır;
rəsmi yük faylının SHA-sı legacy share importunun mənşə sübutu kimi istifadə
edilmir. Tam audit qeydi əvəzinə icazəli audit sütunlarının SHA-sı ayrıca
`selected_record_sha256` adlanır.

Boş növ siyahısının «bütün növlər», boş M2M-in «bütün tələbələr» mənası var.
Naməlum növ məlumatı hash ilə qorunur və `kinds_valid=False` işarələnir;
bu hal geniş hüquq verilməsi kimi şərh edilməməlidir. Root-un exportda
görünməməsi tarixi məlumatın yoxluğunu sübut etmir.

Mövcud workload share sync `legacy/manual` qeydlərini dəyişmədən saxlayır.
Contacts repair-in hazırkı `desired` meyarı isə yalnız `workload` mənbəli
payları sayır. Buna görə təzə hüquq/provenance sübutu ayrıca baxılmadan nə
guard, nə də `desired` yumşaldılır. Payı `workload`-a çevirmək, təkrarlamaq,
silərək yenidən yaratmaq və ya tələbə məhdudiyyətini genişləndirmək bu işin
əhatəsinə daxil deyil. Mövcud saat, qiymət, q/b, i/e və müəlliflik dəyişmir.
