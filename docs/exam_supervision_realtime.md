# İmtahan nəzarəti — real-time (canlı) işləməsi

Müəllimin "Müvəqqəti blokla" / "İmtahandan uzaqlaşdır" əməliyyatlarının tələbə
ekranında **dərhal** görünməsi iki kanaldan asılıdır:

## 1. WebSocket (ani — saniyənin hissəsi)

Tələbə brauzeri `ws://<host>/ws/exams/supervision/<attempt_id>/` ünvanına qoşulur.
Müəllim əməliyyat edəndə server `group_send` ilə bu qrupa mesaj göndərir.

WebSocket-in işləməsi üçün:

- Server **ASGI** rejimində işləməlidir. `python manage.py runserver` Channels +
  daphne `INSTALLED_APPS`-da olduğu üçün ASGI-ni avtomatik xidmət edir — yəni dev-də
  də işləməlidir. Tam etibarlı production üçün:
  `daphne -b 0.0.0.0 -p 8000 config.asgi:application` (artıq `prod-entrypoint.sh`-da var).
- **Channel layer** prosesslər arası mesaj çatdırmalıdır. Tək runserver prosesində
  `InMemoryChannelLayer` kifayətdir. Bir neçə işçi proses / production üçün **Redis**
  lazımdır:
  - `.env`-də: `USE_REDIS=true` və `REDIS_URL=redis://localhost:6379/0`
  - Redis işləməlidir (`docker-compose.yml`-də `redis` xidməti var).
- **CSP**: `connect-src` ws/wss-ə icazə verməlidir. Base policy yalnız
  `:8000` portuna icazə verir; local settings dev-də `ws:`/`wss:` əlavə edir
  (istənilən port). Başqa portda işlədirsinizsə bu vacibdir.

## 2. Fast polling fallback (≤3 saniyə — həmişə işləyir)

WebSocket hər hansı səbəbdən qoşulmasa (Redis yoxdur, proxy WS-i kəsir, port
uyğunsuzluğu), tələbə brauzeri **hər 3 saniyə** status API-ni yoxlayır və
müəllim bloku/dayandırmasını avtomatik tətbiq edir — **manual refresh
lazım deyil**. Bu, infrastrukturdan asılı olmayan etibarlı kanaldır.

Yəni: WebSocket varsa ani, yoxdursa ən çox 3 saniyəyə tələbə ekranı bloklanır
və ya nəticə səhifəsinə yönləndirilir.

## Dəyişiklikdən sonra

- `python manage.py migrate exams` (0013 + 0014).
- `python manage.py collectstatic` (JS/CSS yeniləndi; `exam_supervision.js`-də
  cache-busting versiya `?v=20260530-realtime`).
- Tələbə açıq imtahan səhifəsini bir dəfə yeniləsin ki, yeni JS yüklənsin.
