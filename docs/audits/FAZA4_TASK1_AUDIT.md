# FAZA 4 / Task 1 — request-external DB path audit

**Tarix:** 2026-07-04
**Nəticə:** ✅ Bütün request-external DB yolları `rls_worker_atomic()` ilə sarınıb.

## Metodologiya

Aşağıdakı grep ilə DB-yə potensial toxunan bütün request-xarici entry-point-lər axtarıldı:

```bash
grep -rlE "database_sync_to_async|@shared_task|@app\.task|BaseCommand|@receiver" \
  --include="*.py" apps core | sort > candidates.txt
```

Cəmi **17 fayl** candidate. Sonra `rls_worker_atomic` istifadəsi ilə müqayisə edildi.

## Statik audit tapıntıları (fayl-fayl)

### Celery/task-lar

| Fayl | Vəziyyət | Qeyd |
|------|-----|------|
| `core/tasks.py` | ✅ Wrapped | Bütün task-lar `with rls_worker_atomic()` daxilində |
| `core/email_tasks.py` | ✅ Wrapped | Bütün email task-ları wrapped |
| `apps/exams/tasks.py` | ✅ Wrapped | Sweep/export task-ları wrapped |

### Signal handler-lər (post/pre_save, connect)

| Fayl | Receiver | Wrap? | Səbəb |
|------|----------|-------|-------|
| `apps/accounts/signals.py` | 1 | ✅ | Yeganə DB-yaz receiver wrapped |
| `apps/audit/signals.py` | 3 | ✅ | Hər 3 receiver DB yazır və hamısı wrapped |
| `apps/blog/signals.py` | 9 | ✅ | 4 DB-yaz receiver wrapped; 5 cache-only receiver (wrap lazım deyil) |
| `apps/courses/signals.py` | 3 | ✅ | Hamısı wrapped |
| `apps/notifications/signals.py` | 8 | ✅ | 4 post_save + 4 pre_save; pre_save-lər `_cache_previous_state` helper-ini çağırır ki, o da wrapped |
| `apps/organizations/signals.py` | 4 | ✅ | 1 DB-yaz receiver wrapped; 3 cache-invalidation receiver (wrap lazım deyil) |

### Management command-ları

| Fayl | Wrap? | Qeyd |
|------|-------|------|
| `apps/exams/management/commands/seed_group_demo_data.py` | ✅ | Wrapped |
| `apps/notifications/management/commands/purge_notifications.py` | ✅ | Wrapped |
| `apps/organizations/management/commands/backfill_admin_memberships.py` | ✅ | Wrapped |
| `apps/organizations/management/commands/create_sample_orgs.py` | ✅ | Wrapped |
| `apps/organizations/management/commands/seed_ci_e2e_scenario.py` | ✅ | Wrapped |
| `apps/organizations/management/commands/seed_ci_e2e_user.py` | ✅ | Wrapped |
| `apps/accounts/management/commands/create_roles.py` | ⚪ N/A | Deprecated no-op — DB-yə toxunmur (yalnız `self.stdout.write`) |

### WebSocket consumer-ləri

| Fayl | Wrap? | Qeyd |
|------|-------|------|
| `apps/live_exam/consumers.py` | ✅ | Bütün `database_sync_to_async` blokları wrapped |
| `apps/live_exam/auth.py` | ✅ | Wrapped |
| `apps/live_exam/cache.py` | ✅ | Wrapped |
| `apps/exams/consumers.py` | ⚪ N/A | Yalnız channel-layer group send/discard; DB toxunmur (`ExamSupervisionConsumer` `scope["user"]` + settings oxuyur, `database_sync_to_async` yoxdur) |

## Regressiya qarşısını almaq

Bu invarianti qorumaq üçün `scripts/check_worker_atomic_coverage.py` (növbəti bölmə) əlavə oluna bilər — hər yeni DB-yə toxunan request-external entry-point-in `rls_worker_atomic()` istifadə etməsini yoxlayır.

## Nəticə

- **Cəmi 15 aktiv request-external DB entry-point tam wrapped.**
- **2 exception:** ikisi də DB-yə toxunmayan komponentlərdir (deprecated no-op command + no-DB consumer).
- **Yeni gap yoxdur.**

Task 1 üzrə əlavə kod dəyişikliyi lazım deyil. Növbəti addım: Task 2 (izolyasiya testlərini transaction-pooling üçün gücləndir).
