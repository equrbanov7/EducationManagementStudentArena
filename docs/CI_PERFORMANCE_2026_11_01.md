# CI müddəti: 2026-11-01 ölçüsü

Mənbə: `gh run view <id> --json jobs,createdAt,updatedAt,headSha,status,conclusion`.
Müddətlər workflow yaradılmasından hesablanır; aşağıdakı iki run uğurludur.

| Ölçü | 41302277258 (`ad213433`) | 41311894565 (`6ed6f300`) |
| --- | ---: | ---: |
| İlk paralel job-ların başlanması | 3–4 s | 34–35 s |
| Ən gec unit shard-ın bitməsi | 13:57 | 14:22 |
| Coverage job müddəti | 1:02 | 1:05 |
| CI Success bitməsi | 15:09 | 15:36 |
| Deploy job müddəti | 5:26 | 5:27 |
| Workflow → deploy tamamlanması | 20:40 | 21:07 |
| Docker build job müddəti | 2:04 | 2:57 |
| E2E job-un workflow-dan bitmə vaxtı | 11:09 | 10:57 |

Kritik yol: unit shard → birləşdirilmiş coverage → CI Success → deploy.
İlk job-ların başlanmasına qədərki 3–35 saniyə workflow planlaşdırılması və
runner başlanğıcını birlikdə göstərir; bunu tamamilə runner növbəsi adlandırmaq
olmaz. Job-lar arası asılılıq gözləməsi testin icra müddətinə daxil edilməyib.

Unit shard-larda şablon bazanın miqrasiyası 123–245 saniyə, test mərhələsi
268–564 saniyə çəkib. Deploy job-un əsas skripti hər iki run-da 312 saniyədir.
Docker/E2E zənciri bu iki run-da unit/coverage-dən tez bitib; həmin zəncirin
qısaldılması hazırkı kritik yolu qısaltmaz. `remote_deploy.sh` image-i prod-da
ayrıca qurur, amma bu ölçü bütün 312 saniyəni build-ə aid etməyə imkan vermir:
backup, preflight, release və health yoxlamaları da həmin addımdadır.

## Tətbiq edilən dəyişikliklər

- `.test_durations` uğurlu `41311894565` run-ının `test-durations` artefaktından
  yenilənib. Əvvəlki 16,797 açarın hamısı qalır; 1,238 yeni ölçü əlavə olunub
  (cəmi 18,035). Bu fayl test seçimini məhdudlaşdırmır; naməlum testlər
  pytest-split tərəfindən orta müddətlə bölgüyə daxil edilir.
- Coverage mərhələsi əvvəl `coverage report --fail-under=68`, sonra
  `coverage xml` ilə eyni source-u iki dəfə analiz edirdi. İndi
  `coverage xml --fail-under=68 -o coverage.xml` həm eyni minimumu tətbiq edir,
  həm XML artefaktını yaradır. Səkkiz coverage faylı tələbi saxlanır.
  Aşağı coverage yenə uğursuz exit kodu verir; bütün digər release qapıları qalır.

Yeni ölçülərlə köhnə pytest-split bölgüsünün yükü 1,018–1,383 test-saniyədir;
yenilənmiş bölgünün hər shard-ı təxminən 1,200 test-saniyədir (maksimum −13.3%).
Bu, eyni 18,035 nodeID üzərində `least_duration` alqoritminin modelidir,
wall-clock nəticəsi deyil. Xdist-in fayl qruplaması, worker sayı, runner sürəti
və ağır miqrasiya testlərinin sona düşməsi faktiki nəticəni dəyişir.
İlk uğurlu CI-dən sonra yeni ölçünü əvvəlki 20:40–21:07 ilə müqayisə etmək lazımdır.
Yeni CI ölçülmədən konkret dəqiqə qənaəti vəd edilmir.

## Məlumat düzəlişlərini kafedra üzrə toplamaq

Kod dəyişməyən, artıq deploy olunmuş dəstəklənən əməliyyat üçün hər müəllimə
ayrıca CI/deploy başladılmır. Mövcud Prod Data Ops-un `reviewed_workload_batch`
əməliyyatı bir nəzərdən keçirilmiş kafedra paketi ilə işlədilir. Paketə eyni
scope-un müəllimləri birlikdə daxil edilir; mənbə artefaktı, actor, dəqiq deploy
HEAD-i, baseline, rollback və qorunmalı məlumat yoxlamaları saxlanır.
Dəstəklənməyən düzəliş növü yeni nəzərdən keçirilmiş kod tələb edirsə, həmin kod
bir dəfə ümumi CI-dən keçir; müəllim başına yeni deploy edilmir.

Bu qeyd sərbəst SQL, shell və ya test qapılarını keçən ayrıca release yolu yaratmır.
CI image-in prod-a birbaşa daşınması ayrıca işdir: source SHA, digest,
architecture, build arqumentləri, provenance və rollback uyğunluğu əvvəlcə
bütöv yoxlanmalıdır.

## Sabit own-syllabi V2 üçün tək-job paket

`own-syllabi-v2-package.yml` əvvəlki 14 ayrı workflow dispatch-in işini bir
`production-deploy` concurrency lock-u daxilində ardıcıl aparır. Bir checkout,
bir source download/decrypt/UID yoxlaması və bir artefakt upload qalır.
Ümumi CI və ya deploy bu əməliyyatın daxilində işə salınmır; workflow və onun
çağırdığı biznes komandaları əvvəl bir dəfə normal CI/deploy-dan keçməlidir.
2–5 dəqiqə əməliyyat müddəti hədəfdir, production-da ölçülmüş nəticə deyil.

Dispatch yalnız `actor`, `apply` (defolt false), `confirm` qəbul edir. Batch,
komanda, source, müəllim və ya undo selector-u yoxdur. Scope V2-dəki eyni iki
mənbədir; kafedra ilə bağlı yeni hallar kod və source review tələb edir.

Fazalar: pre-standard, pre-raw-026, pre-raw-044, pre-syllabus-026,
pre-syllabus-044 → təzə dry → yalnız `apply=true` və `confirm=APPLY` olduqda
həmin dry baseline ilə apply → repeat-dry → apply rejimində eyni receipt ilə
sıfır yazılı repeat-apply → eyni beş post kapsul. Defolt dry paketdə heç bir
`--apply` çağırışı yoxdur. Mövcud bərpa öncədən tətbiq edilibsə paket avtomatik
retry etmir; receipt ayrıca nəzərdən keçirilir.

Hər fazadan əvvəl runtime `/app/build-info.json` SHA-sı yoxlanır. Tracked source
fayllarının hash-ləri checkout HEAD-i ilə tutuşdurulur və manifestdə saxlanır.
Mənbənin cipher və plaintext hash-ləri əvvəlki V2 sabitləri ilə eynidir;
plaintext artifact ağacına düşmür, konteynerə yalnız mövcud non-root UID helper-i
ilə ötürülür. Atomik app komandasının ownership/draft/context/grade yoxlamaları
öz yerində işləyir. Paket DB-də ümumi uzun transaction yaratmır: hər exporter
öz read-only transaction-ını, repair öz atomik transaction-ını saxlayır.

Artefakt quruluşu: `package-manifest.json` və `pre|post/<label>/snapshot.enc.json`.
Manifest hər kapsulun ciphertext hash-ini, scope registry hash-ini, saylarını,
runtime HEAD-ini və dry/apply/repeat nəticələrini SHA256 hadisə zəncirində saxlayır.
`--finalize` naməlum fayl, plaintext, symlink, dəyişmiş hash, status, phase sırası
və ya natamam "complete" iddiasında upload-a icazə vermir. Xəta fazanı dayandırır;
uğurla toplanmış kapsullar və etibarlı partial manifest qorunur. Avtomatik undo
və retry yoxdur. Workflow həm host, həm konteyner mənbə qovluqlarını təmizləyir.

**Bu artefakt təkbaşına uğur sübutu deyil.** Son status yalnız
`applied_PENDING_INDEPENDENT_VERIFICATION` və ya
`dry_run_PENDING_INDEPENDENT_VERIFICATION` olur. Root artefaktı endirdikdən
sonra exact HEAD/run/attempt, source pin-lər, chain və on ciphertext hash-ini
yoxlamalı, mövcud private RSA ilə kapsulları lokal decrypt etməlidir. Mövcud
müstəqil `compare_raw`, `compare_content`, `compare_standard` sübutları ayrıca
qalır: raw grade/QB/IE/roster/attribution dəyişməməli, iki human draft və bütün
köhnə versiya/content tarixçəsi qorunmalı, yeni approved body-lər exact own-source
olmalıdır. Private RSA key heç vaxt workflow-a verilmir. Bu müqayisə bitmədən
əməliyyat tam yoxlanmış sayılmır.
