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
