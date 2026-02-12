# Database Reset Təlimatı (Azərbaycan dilində)

## Problem
Sizin aldığınız xəta:
```
psycopg2.errors.DuplicateTable: relation "uniq_player_per_session_client" already exists
```

## Həll (Test mühiti üçün ən yaxşı yol)

Siz dediyiniz kimi bu test mühitidir, ona görə də ən asan və təmiz yol database-i tam silmək və yenidən yaratmaqdır.

### Addım 1: PostgreSQL Database-i Silmək və Yenidən Yaratmaq

Terminal-da bu əmrləri icra edin:

```bash
# PostgreSQL-ə qoşulun
psql -U postgres

# Database-i silin (emsarena öz database adınızdır)
DROP DATABASE emsarena;

# Yenidən yaradın
CREATE DATABASE emsarena;

# Çıxın
\q
```

### Addım 2: Migration-ları Yenidən İcra Edin

```bash
# Virtual environment aktivləşdirin (əgər aktivləşməyibsə)
source venv/bin/activate  # Mac/Linux
# və ya
venv\Scripts\activate  # Windows

# Migration-ları icra edin
python manage.py migrate
```

## Nə Düzəldildi?

Migration faylında **təkrar constraint** var idi:
- Eyni field-lər üçün həm `AddConstraint`, həm də `AlterUniqueTogether` istifadə olunurdu
- Bu constraint-i iki dəfə yaradırdı və konflikt yaradırdı

İndi bu problem həll olunub və migration düzgün işləyəcək.

## Yoxlama

Hər şeyin düzgün işlədiyini yoxlayın:

```bash
# Django konfiqurasiyasını yoxlayın
python manage.py check

# Migration-ların vəziyyətini görün
python manage.py showmigrations

# live_exam model-lərini test edin
python manage.py shell
>>> from apps.live_exam.models import LiveSession, LivePlayer
>>> LivePlayer.objects.all()
>>> exit()
```

## Tez Reset Script-i

Daha rahat olmaq üçün bir script yarada bilərsiniz:

`reset_db.sh` faylı yaradın:
```bash
#!/bin/bash
echo "Database silinir..."
psql -U postgres -c "DROP DATABASE IF EXISTS emsarena;"
echo "Database yaradılır..."
psql -U postgres -c "CREATE DATABASE emsarena;"
echo "Migration-lar icra olunur..."
python manage.py migrate
echo "Hazırdır!"
```

İstifadə edin:
```bash
chmod +x reset_db.sh
./reset_db.sh
```

## Qeyd

- ✅ Bu həll test mühiti üçün idealdır
- ✅ Bütün migration problemlərini həll edir
- ✅ Təmiz database ilə başlamaq imkanı verir
- ⚠️ Production-da heç vaxt bu yolu istifadə etməyin!

## Sualınız varsa?

1. PostgreSQL işləyir? → `psql --version`
2. Database credentials düzgündür? → `.env` faylına baxın
3. Migration-lar düzgün apply oldu? → `python manage.py showmigrations`

Uğurlar! 🚀
