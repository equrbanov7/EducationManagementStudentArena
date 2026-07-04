# Demo test istifadəçiləri — Qərbi Kaspi Universiteti

Bütün rolları test etmək üçün nümunə istifadəçilər. Hamısı bir tenant-də
("Qərbi Kaspi Universiteti") yaradılır, **eyni parolu** paylaşır (siz təyin
edirsiniz) və `seed_western_caspian` komandası ilə **idempotent** qurulur.

## Necə qurmalı

```bash
# Bütün rol istifadəçiləri (paylaşılan parol məcburidir):
python manage.py seed_western_caspian --password "DemoPass123!"

# Platform superadmin-i də əlavə et (is_superuser):
python manage.py seed_western_caspian --password "DemoPass123!" --with-superadmin

# İlk-giriş OTP addımını söndür (test rahatlığı üçün — birbaşa parolla gir):
python manage.py seed_western_caspian --password "DemoPass123!" --no-first-login-flow
```

> **İlk giriş:** default olaraq hər istifadəçi (rektordan başqa) ilk girişdə
> email təsdiqi + öz parolunu qurma addımından keçir (e-universitet provisioning
> modeli). Sürətli test üçün `--no-first-login-flow` işlədin — onda birbaşa
> `--password` ilə daxil olursunuz.

## İstifadəçilər (username → rol → scope)

| Username | Rol | Scope (səviyyə) |
|----------|-----|-----------------|
| `wcu_rector` | Rektor (org owner) | Bütün təşkilat |
| `wcu_vice_rector` | Prorektor | Bütün təşkilat |
| `wcu_exam_center` | İmtahan mərkəzi | Org (imtahan həyat dövrü) |
| `wcu_hr` | HR | Org (üzv/vəzifə) |
| `wcu_dean` | Dekan | Fakültə alt-ağacı |
| `wcu_department_head` | Kafedra müdürü | Kafedra alt-ağacı |
| `wcu_program_coordinator` | **Proqram koordinatoru** (tyutor-ekvivalent) | İxtisas |
| `wcu_teacher` | Müəllim | Kurs |
| `wcu_assistant` | Müəllim köməkçisi | Kurs |
| `wcu_lab_assistant` | **Laborant** | Kurs |
| `wcu_tutor` | Tyutor | Qrup (AZ bölməsi) |
| `wcu_lead_student_az` | Baş tələbə | Qrup (AZ bölməsi) |
| `wcu_student_az1` | Tələbə | Qrup (AZ bölməsi) |
| `wcu_student_az2` | Tələbə | Qrup (AZ bölməsi) |
| `wcu_lead_student_en` | Baş tələbə | Qrup (İngilis bölməsi) |
| `wcu_student_en1` | Tələbə | Qrup (İngilis bölməsi) |
| `wcu_student_en2` | Tələbə | Qrup (İngilis bölməsi) |
| `wcu_superadmin` | Platform superadmin | Platform (yalnız `--with-superadmin` ilə) |

Email pattern: `<username>@qku.edu.az`. Parol: `--password` ilə verdiyiniz dəyər.

## Akademik struktur (yaradılan iyerarxiya)

```
Mühəndislik və Tətbiqi Elmlər fakültəsi
 └─ Kompüter elmləri kafedrası
     └─ Kompüter elmləri (ixtisas)
         ├─ KE-101 (Azərbaycan bölməsi)      ← tutor, baş tələbə + 2 tələbə
         └─ KE-101E (İngilis bölməsi)         ← baş tələbə + 2 tələbə
```

## Bölmə (sektor) qeydi

Qrup **dil bölməsinə** (AZ / İngilis) aiddir. Bu struktur **universitetə görə
dəyişir** — bölmə adları, sayı və iyerarxiya dərinliyi hər tenant üçün fərqli
ola bilər (bax `docs/UNIVERSITY_SYSTEM_ROADMAP.md`). Ona görə bölmə qrup adında
kodlanır, sərt-kod enum deyil — model tenant-konfiqurasiya əsaslıdır.

## Test axını nümunəsi

1. Seed-i qur (`--no-first-login-flow` ilə test rahatlığı üçün).
2. `wcu_dean` ilə gir → dekan kabineti (fakültə scope).
3. `wcu_student_az1` ilə gir → tələbə kabineti (AZ bölməsi qrupu).
4. `wcu_program_coordinator` ilə gir → tyutor-ekvivalent görünüş (ixtisas scope).
5. `--with-superadmin` işlətmisinizsə `wcu_superadmin` ilə `/admin/`-ə gir.
