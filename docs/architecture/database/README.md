# EMSArena Database Architecture

Bu paket EMSArena kod bazasının Django model registry-si, migration-lar və tenant/RLS mənbələri əsasında yaradılıb.

Yaradılma vaxtı: `2026-07-08 14:49:12`

## Fayllar

- [database-overview.md](database-overview.md) — ümumi cədvəl və domen xəritəsi.
- [data-dictionary.md](data-dictionary.md) — bütün aşkar edilmiş model/cədvəl field-ləri.
- [relationship-report.md](relationship-report.md) — FK, OneToOne və M2M əlaqələri.
- [tenant-boundary-report.md](tenant-boundary-report.md) — tenant ownership və RLS sərhədləri.
- [database-issues.md](database-issues.md) — aşkar edilmiş memarlıq riskləri.
- [emsarena-global-erd.drawio](emsarena-global-erd.drawio) — diagrams.net üçün editable global ERD.
- [emsarena-global-erd.mmd](emsarena-global-erd.mmd) — Mermaid ERD alternativi.
- [emsarena-global-erd.svg](emsarena-global-erd.svg) — statik SVG baxış.
- [domains/](domains/) — domen üzrə detallı ERD faylları.
- [domains/organization-structure-hierarchy.drawio](domains/organization-structure-hierarchy.drawio) — fakültə/kafedra/ixtisas OrgUnit subtype-larını vizual ayıran diaqram.

## Saylar

- First-party concrete model: **91**
- First-party auto M2M through table: **14**
- Django system concrete model: **6**
- Bütün sənədləşdirilmiş table/model obyektləri: **114**
- Münasibət qeydləri: **279**
- RLS policy migration-larında görünən table: **66**
