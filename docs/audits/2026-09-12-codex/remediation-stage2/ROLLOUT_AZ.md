# DB rolu və runtime keçidi — hazırlıq sənədi

## Təsdiqlənmiş nəticə

Mövcud real baza dəyişdirilməyib. PostgreSQL 16 və repodakı eyni PgBouncer v1.25.1-p0 image-i ilə ayrıca loopback mühit quruldu. Yeni app hesabı NOSUPERUSER/NOBYPASSRLS/NOCREATEDB/NOCREATEROLE/NOREPLICATION atributları ilə yaradıldı. Birbaşa və session pooling üzərindən current_user eyni app hesabıdır. Scope-suz oxu sıfır, uyğun tenant oxusu/yazısı uğurlu, başqa tenant yazısı rədd edilir; yeni bağlantıya scope daşınmır.

Provision skripti owner, imtiyazlı, başqa rola üzv və obyekt sahibi mövcud hesabı dəyişməkdən imtina edir. Yoxlama ilə grant-lar bir tranzaksiyadadır. Təzə volume init yoluna da eyni qoruma əlavə edildi. App hesabının təkrar provision-u keçdi; account activation və group transfer evidence cədvəllərində yazı qadağaları qorundu.

Sərt Django rol check-i indi DB əlçatmaz olduqda da xəta verir; bağlantı xətasının mətni/logindəki məxfi dəyərlər cavaba daxil edilmir. Yanlış mode dəyəri rədd edilir. `off` yalnız planlı migration/test yolunda açıq seçimdir.

## Keçiddən əvvəl tələb olunan hədəf məlumatları

Dəqiq hədəf host, domen/TLS terminasiya nöqtəsi, təsdiqlənmiş image digest-i və deploy checkout-u müəyyən edilməlidir. Auditdə görünən lokal köhnə konteyner uzaq production-un sübutu deyil. Mövcud məlumatın dəyişdirilməməsi şərti altında bu sənəd canlı hesab yaratma və deploy əməliyyatının yerinə yetirildiyi mənasına gəlmir.

## Əməliyyat ardıcıllığı

1. Hədəfin yalnız oxu preflight-i: cari runtime/migration hesabları, RLS flags, image digest, proxy/TLS və backup bərpa sübutu. App hesabı üçün owner-dən ayrı yeni ad seçilir; mövcud superuser yerində demote edilmir.
2. Ayrıca staging-də eyni migrasiya zənciri və provision skripti ilə hazırlıq; synthetic tenant/worker yoxlamaları. Migration owner hesabında, runtime ayrıca app hesabında qalır.
3. Planlı hədəf keçidində yalnız həmin mühitə yönəldilmiş `POSTGRES_CONTAINER`, `APP_DATABASE_USER`, `APP_DATABASE_PASSWORD` ilə `scripts/provision-app-db-role.sh`. Parollar shell history/hesabata yazılmamalıdır; secret injection istifadə edilir. Skript özbaşına konteyner restart etmir.
4. Tətbiq/worker/beat üçün APP_DATABASE_USER/PASSWORD, EMS_DB_ROLE_ENFORCE=error; migration bağlantısı ayrıca qalır. PgBouncer hazırkı session pool rejimində saxlanır. Transaction pooling ayrıca suite keçmədən açılmır.
5. Hədəf image-dən `manage.py check --database default` strict rejimdə, app/worker tenant scope smoke və health yoxlamaları. Owner ilə runtime yoxlaması E011 verməlidir, app ilə keçməlidir. Konfiqurasiya düzəlsə də köhnə image avtomatik yenilənmir.
6. HTTPS/TLS təsdiqindən sonra redirect/Secure cookie parametrləri; HSTS yalnız işlək HTTPS sübutundan sonra. Redis maxmemory konteyner limitindən aşağı saxlanır və mövcud memory istifadəsi ilə tutuşdurulur. Mənbədəki təhlükəsiz default-lar işləyən köhnə mühiti dəyişdirmir.

## Geri dönüş və məhdudiyyət

Migration owner saxlanır; app rolunu yaratmaq mövcud məlumatı silmir və schema migration tələb etmir. Yeni image problemli olarsa uyğun əvvəlki image/config snapshot-ı ilə planlı geri dönüş hazırlanmalıdır. Köhnə superuser runtime-a qayıtmaq təhlükəsizlik problemini yenidən açır; uğurlu təhlükəsizlik rollback-i kimi göstərilmir. Yeni hesabın silinməsi və grant revoke-u avtomatik edilmir.

Sınaq real PgBouncer session pooling-i əhatə edir; bütün async worker və WS axınları, uzaq TLS, transaction pooling, real backup-dan restore və canlı rollout hələ təsdiqlənməyib. Sintetik restore nəticəsi real backup sertifikatı deyil.
