# Farida: yalnız sonradan inferensiya ilə yaradılmış həftəlik slotun parkı

Bu sabit əməliyyat yalnız AZ1 `68f5682e-7326-4c13-9fb3-2cd88f013808`
slotunu mövcud `park_slot` xidməti ilə park edir. Silmə və yeni slot yaratma yoxdur.
İlkin DOCX-in beş slotu, o cümlədən hər iki AZ qrupunun 15:15 seminarı və
English açılışının 16:55 seminarı saxlanır. English-in AZ1 jurnalında saxlanan
28 tarixi qiymət/davamiyyət sətri dəyişmir; AZ2-yə dərs və ya qiymət köçürülmür.
Park planlaşdırma görünüşünə təsir edir, tarixi fiziki dərsləri gizlətmir.

## Mənbə və şərti aktuallıq

Şəxsi `az-seminar-schedule-review.json` faylının SHA256-sı:
`037d18ad93ea111a34de0ca6699afddabc4a16f73b2d5a70743b226251cea397`.
Fayl symlink olmamalı, adi fayl və yalnız sahibi üçün oxuna bilən olmalıdır.
Bu sənədin əvvəlki klon məlumatı canlı təsdiq deyil. İlk dry canlı bazada bütün
altı tam slot sətrinin pinlərini və iki yaradılma auditinin SHA-sını yoxlayır.
Uyğunsuzluq olduqda əməliyyat dayanır; baseline mənbə sübutunu əvəz etmir.

Cari tenant/dövr/müəllim/fənn/qruplar, sektor/valideyn/alias ailəsi,
iki kəsişən yük sətri, S15/M30/subgroup1/union1 və tam assignment qrafı yoxlanır.
Yeni paylaşım/təhvil, bölgü qeydi, slot istinadı və əlaqəli planlaşdırma override-ı
ayrıca review tələb edir. İki məlum 16:55 tarixçə dərsi və səkkiz mark istinadının
ID-ləri saxlanır. Sonradan yaranmış bağlı dərs/mark və xarici cədvəl konflikti
baseline-i etibarsız edir.

## CLI

```text
repair_reviewed_farida_slot --org qku --actor USER --file PRIVATE_JSON --sha256 SOURCE_SHA
repair_reviewed_farida_slot --org qku --actor USER --file PRIVATE_JSON --sha256 SOURCE_SHA --baseline DRY_BASELINE --apply
repair_reviewed_farida_slot --org qku --actor USER --file PRIVATE_JSON --sha256 SOURCE_SHA
repair_reviewed_farida_slot --org qku --actor USER --file PRIVATE_JSON --sha256 SOURCE_SHA --undo APPLY_RECEIPT_UUID
repair_reviewed_farida_slot --org qku --actor USER --file PRIVATE_JSON --sha256 SOURCE_SHA --undo APPLY_RECEIPT_UUID --baseline UNDO_DRY_BASELINE --apply
```

Tək sabit tenantda aktiv profilli, aktiv üzvlüyü olan superuser tələb olunur;
mərkəzi cədvəl RBAC və dövr/konflikt yoxlamaları saxlanır. Dry PostgreSQL
REPEATABLE READ / READ ONLY transaction-da işləyir. Apply eyni cədvəl advisory
lock-u və kilidli təzə baseline ilə işləyir. Undo yalnız bu əməliyyatın dəqiq
receipt-i üzrə mövcud `restore_alias_slot` vasitəsilə mümkündür. Başqa şəxsin
park etdiyi və ya əvvəlcədən dəyişmiş slot qəbul edilmir.

Təhlükəsiz JSON çıxışı `reviewed_farida_slot: ` prefiksi ilədir:
`status`, `baseline`, `receipt`, `slots_changed`, `slots_created`, `slots_deleted`,
`lessons_changed`, `marks_changed`, `credits_changed`,
`original_docx_slots_preserved`; dry əlavə `planned_slots=1`, yazı isə
`after_baseline` qaytarır. Statuslar: `dry_run`, `parked`, `already_parked`,
`undone`, `already_undone`. İlk apply/undo yalnız `slots_changed=1`; qalan
bütün dəyişiklik sayları sıfır, `original_docx_slots_preserved=5` olmalıdır.
Xəta çıxışı yalnız sabit guard və qapalı diaqnostika sahələridir; SQL, xam
istisna mətni və mənbə sənədi çıxışa yazılmır.

## Qoruma və təkrar icra

Slotun yalnız park atributları və `updated_at` dəyişir. Undo zaman möhürünü geri
tarixləmir. Hər yazıdan dərhal əvvəl/sonra bütün üç açılışın akademik sətirləri,
syllabus versiyaları və AbsenceCredit-ləri tam-sahə fingerprint ilə müqayisə olunur;
fərq bütün transaction-u geri qaytarır. Köhnə qiymət dəyəri/saat düzəlişləri
kontrol baseline-inə dondurulmur, lakin həmin yazı anında toxunulmaz qalır.
Yeni bağlı istinadlar və scheduling authority dəyişiklikləri hold yaradır.
Bütün bunlar yeni müəllim hüququ və ya patok iddiası yaratmır.

Avtomatik dispatch/push bu paketə daxil deyil. Əvvəl təzə dry nəticəsi və
receipt review edilməli, sonra ayrıca səlahiyyətli operator apply etməlidir.
