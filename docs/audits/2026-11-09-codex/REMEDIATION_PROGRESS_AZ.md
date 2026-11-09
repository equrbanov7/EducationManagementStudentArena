# Mərhələ 2 — tətbiq və yenidən yoxlama

Sahib 9 noyabrda Mərhələ 1 hesabatından sonra düzəlişləri, production tətbiqini
və yoxlamalar bitdikdən sonra deploy-u açıq şəkildə tapşırıb. Mərhələ 1-in
yalnız hesabat məhdudiyyəti bu yeni işə aid deyil; əvvəlki hesabat dəyişdirilmir.

## Qaydalar

- 21 oktyabr 2026 daxil legacy balları, sıfır daxil, dəqiq mənbə əlaqəsi ilə bərpa edilir.
- Daha yeni müəllim balı, rəsmi düzəliş və apellyasiya qorunur.
- Mənbə balı uzlaşdırıldıqdan sonra aidiyyəti boş xana sahibin qərarı kimi
  `owner_assigned_present` olur. Şübhəli xana üçün QB yaradılmır.
- Cari sillabuslar məzmun, fənn, dil və saat uyğunluğu ilə tamamlanıb real
  operatorun adı ilə təsdiqlənir. Süni məzmun və saxta müəlliflik yaradılmır.
- Dəyişikliklər əvvəl dry-run, sonra təzə baseline, qəbz və qorunan undo ilə aparılır.
- Claude-un checkout-u dəyişdirilmir. Cari CI/CD və canlı imtahan yoxlanır.

## Vəziyyət — 9 noyabr, 02:03 UTC

- İş branch-i `codex/reaudit-20261109`; audit checkpoint `4357d8ec0`.
- Main #277 və #183 birləşdirilib. Claude-un #183 CI+deploy-u `42546620951` uğurludur.
- Mənbə balı / davamiyyət bərpası hazırdır: 16 authentic PostgreSQL testi keçib.
  Sonrakı müəllim redaktəsi və rəsmi correction qorunur; native import/copy receipt
  müəllifliyi saxlayır. Missing source grade həll olunmadan həmin offering-in
  şübhəli boş xanaları sadəcə i/ə ilə örtülmür.
- Sillabus content restore/approve, canonical mapping adapter və source plan
  generatoru hazırdır; 104 əsas, son 32 ayrıca regression testi keçib.
- PR #204 final/apellyasiya düzəlişləri seçilərək inteqrasiya edilib; 300 fərqli
  PostgreSQL testi keçib. Native final read-only auditorun 11 testi də uğurludur.
- Şifrəli tam snapshot və əməliyyat ötürülməsi: son 24 test keçib. READ ONLY
  capture sabit tenant/dövr, native deploy SHA, row/byte/time limitləri ilə işləyir.
- Anar authorship, yarım cüt saatları, cache və cədvəl əməliyyatları mənbə hash,
  təzə baseline, backup və receipt ilə qorunur. Tətbiq edilməyib.
- 24 çatışmayan dərs vaxtının source authority-si və 6 duplicate QB namizədi
  dərinləşdirilir. 8 inactive slot üçün dar park əməliyyatı hazırlanır.
- Böyük generated audit JSON-ları məxfi lokal arxivdə saxlanır; SHA inventarı
  `evidence/large-evidence-index.json`-dadır. Hesabatlar və kod Git-də qalır.
- **Bizim production data tətbiqimiz və deploy-umuz hələ olmayıb.**

İlk auditin 212 jurnal və final/credit əhatə boşluğu yeni tam snapshot alınmadan
bağlanmış hesab edilmir. Cari tətbiq sayları, qəbzlər və təkrar yoxlama aşağıda
hər real əməliyyatdan sonra əlavə ediləcək. Davam ardıcıllığı
`CLAUDE_CONTINUE_PHASE2_AZ.md` faylındadır.

## Əlavə yoxlama — 02:15 UTC

- Sillabus üçün əsas385 və açıq seçimlə əvvəl audit edilmiş1700jurnal əhatəsi
  qoruyucularla ayrılıb; paylaşılan dosyenin bütün targetları birlikdə yoxlanır.
- Final legacy qeydlərinin hamısı əvvəlki semesterlərdədir; buna görə tarixi
  final və rəsmi vərəq metadata əhatəsi əlavə edilir. Cari semestr yoxlamasını
  bütün final nəticələrin təsdiqi kimi təqdim etmirik.
- TəkrarQB üçün bütöv predecessor unlink hazır deyil; mənbədə qalmalı köhnə
  xanalar var. Əvvəl source-specific düzəliş və cari credit/maska auditi gəlir.
- Public repoya akademik row-level data daxil edilməməsi üçün bütün detallı
  hesabat vəJSONlar məxfi arxivdədir; lokal iş qovluğunda nüsxələri saxlanır.
- Farida native dry-run cari assignment graph dəyişdiyi üçün dayandı.
  Bu nəticə data düzəlişi deyil; yeni capture ilə səbəb araşdırılacaq.
