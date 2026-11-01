# Əlavə məlumat gözləyən müraciətlər

`waiting_info` statusunda şöbənin cavab SLA-sı dayandırılır: bu müraciətlər gecikmiş
sayğacına və filtrinə düşmür. Mətn və bütün yazışma saxlanır.

Son əlavə məlumat sorğusundan üç təşkilat iş günü və sorğunun saatı tamam olduqda,
istifadəçi cavab verməyibsə müraciət `closed` olur. Həll edilmiş sayılmır:
`resolved_at=NULL` və bağlanma səbəbi zaman xəttində açıq göstərilir.
Təşkilatın bayramları və köçürülmüş iş günləri nəzərə alınır.

Sahibin əlavə məlumatı və ya adi qeydi müraciəti yenidən baxışa qaytarır və şöbəyə
yeni cavab müddəti verir. Əməkdaşın daxili qeydi üç günlük gözləməni uzatmır.
Təkrar əlavə məlumat sorğusu isə yeni gözləmə müddəti başladır.

Emalçıya yalnız bu statusda “Cavab yazmadan bağla” düyməsi verilir. Əvvəlki
şöbə/aidiyyət/tenant icazələri saxlanır. Yeni, cavablandırılmamış müraciət həmin
düymə ilə bağlana bilməz.

Saatlıq Celery işi: `applications.close_stale_waiting_info`.
Əl ilə: `python manage.py close_stale_waiting_info [--org qku]`.
Naməlum təşkilat kodu bütün təşkilatlarda əməliyyata çevrilmir, xəta qaytarır.
Təkrar icra, son anda gələn cavab və yeni sorğu təzə sətir kilidi ilə qorunur.
