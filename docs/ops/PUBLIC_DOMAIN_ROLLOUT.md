# Publik domenə çıxış — təlimat (2026-09-21)

**Məqsəd (sahibin tələbi):** tələbə publik internetdən daxil ola bilsin; müəllim elektron jurnaldan
başqa özünə aid bütün bölmələrə kənardan girsin; elektron jurnal yalnız universitet daxilində
işləsin; inzibati işçilər (RİM, tədris şöbəsi, dekanlıq, kafedra müdiri, HR, rektorluq, superadmin)
yalnız və yalnız universitet daxilindən daxil olsun. Hamısı domen üzərindən, tam təhlükəsiz.

Tətbiq serveri: `10.0.1.120` (LAN). Bu sənəd üç qatı əhatə edir: **şəbəkə/DNS**, **server/.env**,
**tətbiq qaydası** (kodda hazırdır: `apps/accounts/network_zone.py`, nginx `geo $ems_zone`).

---

## 0. Necə işləyir (bir baxışda)

| Kim | Kənardan (internet) | Daxildən (universitet LAN/Wi-Fi) |
|---|---|---|
| Tələbə | ✅ hər şey | ✅ |
| Müəllim | ✅ hər şey, **/jurnal/ ✗ (403)** | ✅ hər şey |
| İnzibati hesab / superadmin | ✗ (403 «yalnız universitet şəbəkəsindən», yalnız çıxış açıqdır) | ✅ |
| Admin paneli `/manage/` | ✗ (nginx 403 + `ADMIN_ALLOWED_IPS`) | ✅ (LAN CIDR) |
| Anonim (giriş səhifəsi, statik) | ✅ | ✅ |

Zona real müştəri IP-sindən çıxır: nginx `geo $ems_zone` (10/8, 172.16/12, 192.168/16, 127/8 = internal)
→ Django-ya `X-EMS-Zone` başlığı (müştərinin göndərdiyi eyni başlıq **əzilir**). Django
`NetworkZoneMiddleware` qaydanı roluna görə tətbiq edir; nginx isə `/jurnal/` və `/manage/` üçün
external zonadan 403 qaytarır (ikiqat qapı).

> ⚠️ **Ən vacib şərt — split-horizon DNS.** Daxildən domenə gedən istifadəçi də serverə **LAN
> IP-si ilə** çatmalıdır. Əgər daxili istifadəçi NAT üzərindən dönüb (hairpin) publik IP ilə gəlirsə,
> nginx onu *external* görür və bütün inzibati işçilər + jurnal daxildə də kilidlənir.

---

## 1. Şəbəkə / DNS (IT şöbəsi)

1. **Publik DNS**: `ems.wcu.edu.az` (nümunə ad) → universitetin publik IP-si. **Proxy/CDN (Cloudflare
   «orange cloud») İŞLƏDİLMİR** — real müştəri IP-si itir, zona və rate-limit-lər pozulur. Yalnız DNS
   (grey cloud) və ya birbaşa A qeydi.
2. **Daxili DNS (split-horizon)**: eyni ad `ems.wcu.edu.az` → `10.0.1.120`. Daxili DNS serverində
   (AD DNS / pfSense / MikroTik «DNS static») qeyd əlavə edin və daxili klientlərin **məhz bu DNS-i**
   işlətdiyini yoxlayın (`nslookup ems.wcu.edu.az` daxildə `10.0.1.120` verməlidir).
3. **Firewall / NAT**: yalnız `443/tcp` (və `80/tcp` — HTTPS-ə 301 üçün) publik IP-dən
   `10.0.1.120`-yə port-forward. `22/tcp` PUBLİK AÇILMIR (SSH yalnız LAN/VPN). Başqa heç bir port yox.
4. **Hairpin NAT söndürülsün** (daxili klient publik IP-yə getməsin) — split DNS düzgün qurulubsa
   onsuz da lazım olmur.
5. Universitetin daxili şəbəkələri `10.0.0.0/8` daxilindədirsə əlavə iş yoxdur; başqa CIDR varsa
   (məs. `192.168.50.0/24` Wi-Fi) həm `docker/nginx/nginx.conf` → `geo $ems_zone`, həm `.env` →
   `INTERNAL_NETWORKS` siyahısına əlavə edin (ikisi eyni olmalıdır).

## 2. TLS sertifikatı

* Publik CA sertifikatı lazımdır (self-signed publikdə qəbul olunmur). Variantlar:
  * **Let's Encrypt (DNS-01)** — universitetin DNS provayderində TXT qeydi ilə (`certbot --manual
    --preferred-challenges dns` və ya `acme.sh`), 90 günlük, avtomatlaşdırılmalıdır;
  * **Universitetin öz CA / satın alınmış sertifikat** (1 illik) — ən sadə.
* Fayllar serverdə: `docker/nginx/certs/origin.crt` (full chain) və `origin.key` (icazə 600).
  Deploy skripti (`scripts/deploy/remote_deploy.sh`) sertifikatı yoxlayır (`validate_origin_cert`).
* HSTS artıq açıqdır (`max-age=31536000; includeSubDomains; preload`) — domen bir dəfə HTTPS-lə
  açılandan sonra HTTP-yə qayıtmaq olmaz; bunu bilərək keçin.

## 3. Server `.env` dəyişiklikləri (`/home/wcu/EducationManagementStudentArena/.env`)

```env
EDGE_PROXY_MODE=direct                       # publik domen birbaşa bu serverə baxır
TLS_ALLOW_SELF_SIGNED_LOCAL=false
ALLOWED_HOSTS=ems.wcu.edu.az,10.0.1.120,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://ems.wcu.edu.az,https://10.0.1.120
SITE_URL=https://ems.wcu.edu.az
HEALTHCHECK_HOST=ems.wcu.edu.az
INTERNAL_NETWORKS=10.0.0.0/8,127.0.0.0/8,::1/128
NETWORK_ZONE_ENFORCED=True                   # jurnal + inzibati hesablar yalnız daxildən
NETWORK_ZONE_TRUST_HEADER=True               # nginx-in X-EMS-Zone başlığına inan
ADMIN_ALLOWED_IPS=10.0.0.0/19,127.0.0.1      # admin paneli yalnız LAN-dan (CIDR dəstəklənir)
FINAL_EXAM_ALLOWED_IPS=10.0.0.0/19           # imtahan zalı — mövcud qayda
```
`.env`-i dəyişəndən sonra: `docker compose -f docker-compose.prod.yml up -d --force-recreate app
celery_worker celery_worker_heavy celery_beat nginx` (və ya növbəti deploy). `ADMIN_ALLOWED_IPS`
GitHub-dan `prod-harden.yml` workflow-u ilə də yazıla bilər.

## 4. Sıra ilə keçid (checklist)

1. [ ] Daxili DNS-də `ems.wcu.edu.az → 10.0.1.120` (split-horizon) — daxildən `nslookup` ilə yoxla.
2. [ ] Sertifikat `docker/nginx/certs/` — `openssl x509 -in origin.crt -noout -subject -dates`.
3. [ ] `.env` yuxarıdakı kimi; `NETWORK_ZONE_ENFORCED=True` **ən sonda** açılsın.
4. [ ] `docker compose ... up -d --force-recreate nginx app …`; `curl -kI https://10.0.1.120 -H "Host: ems.wcu.edu.az"` → 200.
5. [ ] Daxildən brauzerlə `https://ems.wcu.edu.az` — sertifikat etibarlı, giriş işləyir.
6. [ ] Firewall NAT 443/80 açılsın; kənardan (mobil internet) `https://ems.wcu.edu.az` — giriş səhifəsi.
7. [ ] Test matrisi (bölmə 5).
8. [ ] `gh workflow run prod-audit.yml` — başlıqlar/portlar/TLS hesabatı yaşıl.

## 5. Test matrisi (keçiddən sonra mütləq)

| Test | Kənardan (mobil internet) | Daxildən |
|---|---|---|
| Tələbə hesabı ilə giriş, «Mənə təyin edilmiş imtahanlar», nəticələr | 200 | 200 |
| Müəllim: kabinet, fənlər, sillabus, imtahan yaratma | 200 | 200 |
| Müəllim: `https://ems.wcu.edu.az/jurnal/` | **403** «Elektron jurnal yalnız universitet şəbəkəsində» | 200 |
| İnzibati (RİM/dekanlıq) hesabı ilə giriş | giriş sonrası **403** səhifəsi, yalnız «Çıxış» | 200 |
| `https://ems.wcu.edu.az/manage/` | **403** (nginx) | 302 → 2FA login |
| `curl -H "X-EMS-Zone: internal" https://ems.wcu.edu.az/jurnal/` (saxta başlıq) | **403** (başlıq əzilir) | — |
| `curl -I http://ems.wcu.edu.az` | 301 → https | 301 |
| `https://ems.wcu.edu.az/.env`, `/.git/config`, `/admin/` | 404 | 404 |

Bloklanan sorğular audit jurnalında `network_zone_deny` kimi görünür (RİM → Audit).

## 6. Geri qayıtma (rollback)

`.env`-də `NETWORK_ZONE_ENFORCED=False` → `docker compose ... up -d --force-recreate app` — tətbiq
qaydası dərhal sönür; nginx qapısı (`/jurnal/`, `/manage/` external 403) `geo` ilə qalır — onu da
söndürmək lazımdırsa `docker/nginx/nginx.conf`-da `if ($ems_zone_path …) { return 403; }` sətrini
şərhə alıb `nginx -s reload`. Domen/NAT-ı bağlamaq üçün firewall qaydasını söndürmək kifayətdir.

## 7. Bilinən məhdudiyyətlər / tövsiyələr

* VPN ilə evdən qoşulan inzibati işçi VPN-in LAN CIDR-ində olduğu üçün *internal* sayılır — bu,
  nəzərdə tutulan davranışdır (VPN = universitet şəbəkəsi).
* Cloudflare/CDN lazım olarsa `EDGE_PROXY_MODE` və `TRUSTED_PROXY_HOPS`/realip dəstəyi ayrıca iş
  tələb edir — hazırkı deploy skripti qəsdən rədd edir.
* SSH üçün `fail2ban` + `ufw` (yalnız 22/80/443) hostda sahib tərəfindən qurulmalıdır (runner-də
  sudo yoxdur).
* `SESSION_COOKIE_AGE` 24 saatdır; kənardan girən tələbə/müəllim üçün yetərlidir.
