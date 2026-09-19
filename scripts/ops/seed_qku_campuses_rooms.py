"""Sahib qərarı 2026-09-20: QKU korpus xəritəsi + legacy otaq reyestri.

1. ``Organization.settings["campuses"]`` — korpus → struktur vahidləri xəritəsi
   (universitetin 01.09.2026 rəsmi elanı: Korpus A / B / C / İ). Dərs modalında
   qrupun ixtisasına görə korpus ƏVVƏLCƏDƏN seçilir (bax apps/registrar/campus.py).
2. ``exams.ExamRoom`` — köhnə sistemin (myedu) 158 otağı, korpus adı ilə.
   Mənbə: scripts/data/qku_legacy_rooms.csv (myedudb dump, cədvəl ``rooms``).
   Kod ``myedu-room-<legacy id>`` — legacy_rooms fazası ilə EYNİ açar, yəni faza
   sonradan işləsə də dublikat yaranmır; mövcud otağın adı/korpusu ÜSTÜNDƏN
   YAZILMIR (insan düzəlişi qorunur), yalnız boş korpus doldurulur.

Legacy ``bina`` → korpus (köhnə sistemin canlı «Auditoriya» başlıqları ilə
tutuşdurulub, 2026-09-20): 1 İçərişəhər → Korpus İ (İstiqlaliyyət 31), 2 Biznes
məktəbi → Korpus A (Ə. Rəcəbli 17A), 3 Yüksək texnologiyalar → Korpus B (Ə. Rəcəbli
21), 6 «C binası» → Korpus C (Ə. Rəcəbli 207; otaqlar 11–60, dump-dan sonra
yaradılıb), 5 «Filologiya və Tərcümə» köhnə bina kimi saxlanılır (heç bir
ixtisasın defoltu deyil). İmtahan mərkəzi ``ExamRoomForm`` ilə dəyişə bilər.

İstehsalda: docker exec -i <app> python manage.py shell < scripts/ops/seed_qku_campuses_rooms.py
Yalnız oxumaq: DRY=1 docker exec -i -e DRY=1 <app> python manage.py shell < …
"""

import csv
import os
from pathlib import Path

from django.apps import apps as django_apps
from django.db import transaction

from apps.organizations.models import Organization
from core.rls import bypass_rls

DRY = os.environ.get("DRY") == "1"
ORG_SLUG = os.environ.get("ORG_SLUG", "qku")
CSV_PATH = Path(os.environ.get("ROOMS_CSV", "scripts/data/qku_legacy_rooms.csv"))

CAMPUSES = [
    {
        "building": "Korpus A (Biznes məktəbi)",
        "address": "Əhməd Rəcəbli küç., III Paralel, 17A",
        "units": [
            # Biznes və idarəetmə Məktəbi
            "Biznes və idarəetmə məktəbi",
            "Biznesin idarə edilməsi",
            "Dövlət və bələdiyyə idarəetməsi",
            "Marketinq",
            "Turizm bələdçiliyi",
            "Turizm işinin təşkili",
            "Turizm və otelçilik",
            "Menecment",
            # İqtisadiyyat Məktəbi
            "İqtisadiyyat və biznes məktəbi",
            "İqtisadiyyat",
            "Maliyyə",
            "Mühasibat",
            "Mühasibat uçotu və audit",
            "Beynəlxalq ticarət və logistika",
            "Dünya iqtisadiyyatı",
            "Sənayenin təşkili və idarə edilməsi",
            "İstehlak mallarının ekspertizası və marketinqi",
            "Davamlı inkişafın idarə edilməsi",
            # Ekologiya Məktəbi
            "Ekologiya",
            "Ekologiya mühəndisliyi",
            "Meşəçilik",
        ],
    },
    {
        "building": "Korpus B (Yüksək texnologiyalar)",
        "address": "Əhməd Rəcəbli küç., III Paralel, 21",
        "units": [
            # Yüksək Texnologiyalar Məktəbi
            "Yüksək texnologiyalar və innovativ mühəndislik",
            "İnformasiya təhlükəsizliyi",
            "Kompüter mühəndisliyi",
            "İnformasiya texnologiyaları",
            "Kompüter elmləri",
            "Proqramlaşdırma və informasiya təhlükəsizliyi",
            # İnnovativ Mühəndislik və Təbiət Elmləri Məktəbi
            "Biologiya",
            "Su bioehtiyyatları və akvakultura",
            "Cihaz mühəndisliyi",
            "Cihazqayırma mühəndisliyi",
            "Mexatronika və robototexnika mühəndisliyi",
            "Mexanika mühəndisliyi",
            "Qida mühəndisliyi",
            "Biotexnologiya",
            "Yerquruluşu və daşınmaz əmlakın kadastrı",
            "Meşə materiallarının və ağac emalının texnologiyası mühəndisliyi",
            "Poliqrafiya mühəndisliyi",
        ],
    },
    {
        "building": "Korpus C",
        "address": "Əhməd Rəcəbli küç., 207",
        "units": [
            # Psixologiya Məktəbi
            "Psixologiya",
            "Sosial iş",
            "Təhsildə sosial-psixoloji xidmət",
            "Təhsildə sosial psixoloji xidmət",
            # Filologiya və Tərcümə Məktəbi
            "Filologiya və Tərcümə",
            "Filologiya (Azərbaycan dili və ədəbiyyatı)",
            "Filologiya (İngilis dili və ədəbiyyatı)",
            "Azərbaycan dili və ədəbiyyatı",
            "Azərbaycan dili və ədəbiyyatı müəllimliyi",
            "İngilis dili və ədəbiyyatı müəllimliyi",
            "Tərcümə",
            "Tərcümə (Dillər üzrə)",
            "Tərcümə (İngilis dili)",
        ],
    },
    {
        "building": "Korpus İ (İçərişəhər)",
        "address": "İstiqlaliyyət küçəsi, 31",
        "units": [
            # Siyasi və İctimai Elmlər Məktəbi
            "Siyasi və ictimai elmlər məktəbi",
            "Beynəlxalq münasibətlər",
            "Beynəlxalq Münasibətlər (Tədris Ingilis Dilində)",
            "Fəlsəfə",
            "Politologiya",
            "Politologiya (Tədris Ingilis Dilində)",
            "Regionşünaslıq",
            "Tarix",
            "Tarix (Tədris Ingilis Dilində)",
            "Tarix müəllimliyi",
            # Dizayn Məktəbi
            "Dizayn",
            "Dizayn Məktəbi",
            "Dizayn (Qrafik)",
            "Dizayn (İnteryer)",
        ],
    },
]

# Köhnə sistemin «Auditoriya» siyahısındakı başlıqlar (canlı, 2026-09-20): 1 İçərişəhər,
# 2 Biznes məktəbi, 3 Yüksək texnologiyalar, 4 Azadlıq (boş), 5 Filologiya və Tərcümə,
# 6 C binası (id 216–255, dump-dan SONRA yaradılıb — CSV-yə əl ilə əlavə olunub).
LEGACY_BUILDING = {
    "1": "Korpus İ (İçərişəhər)",
    "2": "Korpus A (Biznes məktəbi)",
    "3": "Korpus B (Yüksək texnologiyalar)",
    "5": "Filologiya və Tərcümə (köhnə bina)",
    "6": "Korpus C",
}
ROOM_TYPES = {"1": "Auditoriya", "2": "Laboratoriya", "3": "Emalatxana", "4": "Digər"}
ROOM_CODE_PREFIX = "myedu-room-"


def _rooms_from_csv():
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row["name"] or "").strip()
            if not name:
                continue
            try:
                capacity = int(row["capacity"] or 0)
            except ValueError:
                capacity = 0
            yield {
                "code": f"{ROOM_CODE_PREFIX}{row['legacy_id']}",
                "name": name[:120],
                "building": LEGACY_BUILDING.get((row["building"] or "").strip(), ""),
                "capacity": max(0, min(capacity, 999)),
                "notes": ROOM_TYPES.get((row["room_type"] or "").strip(), ""),
            }


class _DryRunRollback(Exception):
    """DRY rejimi: bütün yazılar atomic blokun sonunda geri alınır."""


def main():
    ExamRoom = django_apps.get_model("exams", "ExamRoom")
    with bypass_rls():
        org = Organization.objects.get(slug=ORG_SLUG)
        settings = dict(org.settings or {})
        settings["campuses"] = CAMPUSES
        try:
            _apply(ExamRoom, org, settings)
        except _DryRunRollback:
            print("[DRY] heç nə yazılmadı (geri alındı).")


def _apply(ExamRoom, org, settings):
    created = updated_building = kept = 0
    with transaction.atomic():
        org.settings = settings
        org.save(update_fields=["settings"])
        for room in _rooms_from_csv():
            existing = ExamRoom.objects.filter(organization=org, code=room["code"]).first()
            if existing is None:
                ExamRoom.objects.create(organization=org, is_active=True, **room)
                created += 1
            elif not (existing.building or "").strip() and room["building"]:
                existing.building = room["building"]
                existing.save(update_fields=["building", "updated_at"])
                updated_building += 1
            else:
                kept += 1
        by_building = {}
        for b in ExamRoom.objects.filter(organization=org, is_active=True).values_list("building", flat=True):
            by_building[b or "—"] = by_building.get(b or "—", 0) + 1
        print(
            f"[{'DRY' if DRY else 'APPLY'}] campuses={len(CAMPUSES)} rooms: created={created} "
            f"building_filled={updated_building} kept={kept} total_by_building={by_building}"
        )
        if DRY:
            raise _DryRunRollback


main()
