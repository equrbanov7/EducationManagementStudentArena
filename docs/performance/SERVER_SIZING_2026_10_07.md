# Server gücü kifayət edirmi? — 2026-10-07

Mənbə: prod-audit (2026-10-07 18:02 UTC, reboot-dan 4 saat 42 dəq sonra), Prometheus-un 7 günlük tarixçəsi,
tutum testləri ([CAPACITY_TEST_2026_10_05_NIGHT.md](CAPACITY_TEST_2026_10_05_NIGHT.md)).

## Hazırkı server

- **VM:** «WEST», ESXi 10.0.1.240.
- **Resurs:** 10 vCPU, 31 GB RAM. Reboot-dan sonra da eyni ölçüdədir, böyüdülməyib.
- **Disk:** 29 % dolu.
- **DB:** 3,0 GB. Tamamilə yaddaşa sığır, keş isabəti 99,8 %.

## Real istifadə (7 gün, yük testləri çıxılmaqla)

| Göstərici | Dəyər | Qiymət |
|---|---|---|
| HTTP sorğu | pik 3,1 sorğu/s (5 dəq), həftədə 65 min sorğu | çox aşağı |
| Gecikmə p95 | 25 ms | əla |
| RAM | 16–22 % | böyük ehtiyat |
| PostgreSQL bağlantıları | maks. 23 / 200 | böyük ehtiyat |
| PgBouncer gözləmə | 0 s | darboğaz yoxdur |
| 5xx (7 gün) | 1 | — |
| Disk I/O | orta 0,5 %, maks. 7,9 % | böyük ehtiyat |

CPU-nun 7 günlük 95 % pikləri yük testlərinin gecə qaçışlarıdır, real istifadə deyil.

## Tutum (ölçülmüş və təxmini)

- **Ölçülən (sıxılmış test stack-i: app 4 nüvə + DB 2 nüvə):**
  - 500 eyni-anlı giriş və kabinet — 0 xəta;
  - 1000 eyni-anlı imtahan (sərt temp, 8–20 s düşünmə) — ~3 % səliqəli 503.
- **Canlı server:** app və DB eyni 10 nüvəni bölür, üstəlik real tələbə sual başına 1–3 dəqiqə düşünür. Buna görə real tutum təxminən:
  - **3000–5000 eyni-anlı imtahan iştirakçısı**;
  - **gündəlik istifadədə 10 000+ qeydiyyatlı istifadəçi**.
- **Darboğaz yalnız CPU-dur** və yalnız kütləvi eyni anlı hadisələrdə görünür: hamı eyni dəqiqədə girir, ya da 1000+ tələbə eyni imtahandadır. RAM-a ehtiyac yoxdur.

## Nəticə

**Bu gün və yaxın semestr üçün 10 vCPU / 31 GB kifayətdir.** VM-i 24 vCPU / 64 GB-a böyütmək indi vacib deyil. O, yalnız bu hallarda lazımdır:
- bir imtahan pəncərəsində 2000–3000-dən çox tələbə eyni anda yazacaqsa;
- və ya təşkilat sayı / tələbə sayı bir neçə dəfə artacaqsa.

Böyütmə lazım olsa, **RAM-ı yox, vCPU-nu artırın** (16–24 vCPU kifayətdir, 32 GB RAM qalsın). Ondan sonra `APP_REPLICAS` nüvə sayına uyğun artırılır, məs. 16 vCPU → 12 replika. Hovuz yenidən hesablanır (bax `remote_deploy.sh` env preflight).

## 2026-10-07-də tətbiq olunan tənzimləmə

Yaddaş tavanına yaxınlaşan konteynerlər üçün (7 günlük maks. working set / limit):

| Konteyner | Əvvəl | İndi | Səbəb |
|---|---|---|---|
| celery-beat | 256 MB | 512 MB | 124 % (limitdən yuxarı — reclaim/OOM riski) |
| celery_worker ×2 | 1024 MB | 1536 MB | 82 % |
| prometheus | 512 MB | 1024 MB | 83 % (TSDB 1,1 GB, 11 min seriya) |
| cadvisor | 512 MB | 768 MB | 78 % |

Bunlardan başqa:
- `EMS_DB_ROLE_ENFORCE=error` (təhlükəsizlik auditi): RLS-i yan keçən DB rolu ilə deploy bloklanır.
- **Qəsdən dəyişdirilməyənlər:**
  - `APP_REPLICAS=8`, `MAX_INFLIGHT_REQUESTS=24`, PgBouncer 110+50. Tutum testində optimal çıxıb. PgBouncer növbəsi doyma anında admission control rolunu oynayır.
  - Postgres parametrləri. DB yaddaşa sığır, dəyişiklik restart tələb edir, faydası yoxdur.
- **Gözləyən:** host-da `reboot-required` (avtomatik quraşdırılmış təhlükəsizlik yeniləmələri, kernel). Planlı reboot `prod-host-maint.yml` → `reboot` ilə edilir, yalnız sahibin icazəsi ilə.
