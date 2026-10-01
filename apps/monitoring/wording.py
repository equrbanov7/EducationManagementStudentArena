"""Monitorinq xülasəsinin İNSAN DİLİNDƏ mətnləri (2026-10-01, RİM rəhbəri üçün).

Sahib: «tam aydın formada olsun» — xülasə texniki olmayan oxucu üçündür. Buna
görə Alertmanager qayda adları (``HostDiskSpaceLow``), servis açarları və
təhlükəsizlik kateqoriyaları burada sadə cümlələrə çevrilir. Bütün mətnlər
``pgettext`` ilə kontekstlidir (``monitoring.summary`` / ``monitoring.alert``)
və sorğunun aktiv dilində qaytarılır — xülasə keşi dilə görə ayrıdır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

_ALERT = "monitoring.alert"
_S = "monitoring.summary"


def alert_title(rule: str, fallback: str = "") -> str:
    """Alertmanager qayda adı → sadə cümlə (naməlum qayda üçün ``fallback``)."""
    titles = {
        "TargetDown": pgettext(_ALERT, "Monitorinq hədəflərindən biri cavab vermir"),
        "PostgresDown": pgettext(_ALERT, "Verilənlər bazası (PostgreSQL) əlçatmaz olub"),
        "High5xxRate": pgettext(_ALERT, "Server xətalarının (5xx) sayı artıb"),
        "HighLatencyP95": pgettext(_ALERT, "Səhifələr gec açılır (cavab müddəti 2 saniyədən çox)"),
        "ExamAttemptServerErrors": pgettext(_ALERT, "İmtahan cavablarının yazılmasında server xətası"),
        "PgConnectionsHigh": pgettext(_ALERT, "Baza bağlantılarının sayı limitə yaxınlaşıb"),
        "HostDiskSpaceLow": pgettext(_ALERT, "Serverdə disk yeri azalır"),
        "HostDiskEmergency": pgettext(_ALERT, "Serverdə disk yeri demək olar ki, bitib"),
        "HostMemoryHigh": pgettext(_ALERT, "Serverin yaddaşı (RAM) çox dolub"),
        "HostHighCpu": pgettext(_ALERT, "Prosessor (CPU) yükü yüksəkdir"),
        "HostCpuCritical": pgettext(_ALERT, "Prosessor (CPU) yükü kritik həddədir"),
        "HostHighLoad": pgettext(_ALERT, "Server yükü prosessor nüvələrinin sayını aşıb"),
        "HostSwapHigh": pgettext(_ALERT, "Yaddaş çatışmır — swap istifadəsi artıb"),
        "HostInodeLow": pgettext(_ALERT, "Diskdə fayl indeksi (inode) ehtiyatı azalır"),
        "ContainerDown": pgettext(_ALERT, "Xidmət konteynerlərindən biri dayanıb"),
        "ContainerRestartLoop": pgettext(_ALERT, "Xidmət konteyneri təkrar-təkrar yenidən başlayır"),
        "ContainerOOMKilled": pgettext(_ALERT, "Xidmət yaddaş çatışmazlığından dayandırılıb (OOM)"),
        "ContainerMemoryNearLimit": pgettext(_ALERT, "Xidmətin yaddaşı limitə yaxındır"),
        "RedisDown": pgettext(_ALERT, "Keş və növbə serveri (Redis) əlçatmazdır"),
        "RedisMemoryHigh": pgettext(_ALERT, "Keş serverinin (Redis) yaddaşı dolur"),
        "RedisEvictedKeys": pgettext(_ALERT, "Keş serveri yer çatmadığı üçün məlumat silib"),
        "RedisBlockedClients": pgettext(_ALERT, "Keş serverində gözləyən (bloklanmış) bağlantılar var"),
        "NginxDown": pgettext(_ALERT, "Veb server (Nginx) əlçatmazdır"),
        "EndpointProbeFailed": pgettext(_ALERT, "Avtomatik yoxlama saytın açılmadığını göstərdi"),
        "EndpointSlowProbe": pgettext(_ALERT, "Avtomatik yoxlama saytın yavaş açıldığını göstərdi"),
        "TlsCertExpiringSoon": pgettext(_ALERT, "Təhlükəsizlik sertifikatının (TLS) bitməsinə 30 gündən az qalıb"),
        "TlsCertExpiryCritical": pgettext(_ALERT, "Təhlükəsizlik sertifikatının (TLS) bitməsinə 7 gündən az qalıb"),
        "CeleryWorkersDown": pgettext(_ALERT, "Fon tapşırıqlarını icra edən işçilər (Celery) dayanıb"),
        "CeleryBeatStale": pgettext(_ALERT, "Planlı fon tapşırıqları (Celery Beat) işləmir"),
        "CeleryQueueBacklog": pgettext(_ALERT, "Fon tapşırıqları növbədə yığılıb qalır"),
        "CeleryHeavyQueueBacklog": pgettext(_ALERT, "Ağır fon tapşırıqları (OCR/AI/ixrac) növbədə yığılır"),
        "CeleryHeavyWorkerDown": pgettext(_ALERT, "Ağır fon tapşırıqlarının işçisi dayanıb"),
        "BackupTooOld": pgettext(_ALERT, "Bazanın ehtiyat nüsxəsi 26 saatdan köhnədir"),
        "OffsiteBackupStale": pgettext(_ALERT, "Serverdən kənar ehtiyat nüsxə yenilənmir"),
        "OffsiteBackupMetricMissing": pgettext(_ALERT, "Serverdən kənar ehtiyat nüsxənin vəziyyəti bilinmir"),
        "OffsiteBackupLastRunFailed": pgettext(_ALERT, "Serverdən kənar ehtiyat nüsxənin son cəhdi uğursuz oldu"),
        "RestoreDrillOverdue": pgettext(_ALERT, "Ehtiyat nüsxədən bərpa məşqi vaxtında aparılmayıb"),
        "NodeTextfileCollectorError": pgettext(_ALERT, "Server göstəricilərinin bir hissəsi oxunmur"),
        "PgBouncerClientsWaiting": pgettext(_ALERT, "Bazaya qoşulmaq üçün növbədə gözləyən sorğular var"),
        "PgBouncerMaxWaitHigh": pgettext(_ALERT, "Bazaya qoşulma növbəsində gözləmə uzanıb"),
    }
    return titles.get(rule or "", "") or fallback or pgettext(_ALERT, "Naməlum xəbərdarlıq")


def health_title(level: str) -> str:
    return {
        "ok": pgettext(_S, "Hər şey qaydasındadır"),
        "warning": pgettext(_S, "Diqqət tələb edən məqamlar var"),
        "problem": pgettext(_S, "Problem aşkarlandı"),
    }.get(level, pgettext(_S, "Vəziyyət tam müəyyən edilə bilmir"))


def health_summary(level: str, warnings: int, problems: int) -> str:
    if level == "ok":
        return pgettext(_S, "Server, baza, keş və fon tapşırıqları normal işləyir; açıq problem yoxdur.")
    return pgettext(_S, "%(problems)s problem, %(warnings)s xəbərdarlıq") % {
        "problems": problems,
        "warnings": warnings,
    }


def service_label(key: str) -> str:
    return {
        "database": pgettext(_S, "Verilənlər bazası"),
        "pgbouncer": pgettext(_S, "Baza bağlantı hovuzu"),
        "cache": pgettext(_S, "Keş (Redis)"),
        "workers": pgettext(_S, "Fon tapşırıqları (Celery)"),
        "scheduler": pgettext(_S, "Planlı tapşırıqlar (Beat)"),
        "web": pgettext(_S, "Veb server (Nginx)"),
        "probes": pgettext(_S, "Saytın avtomatik yoxlaması"),
        "metrics": pgettext(_S, "Metrik sistemi (Prometheus)"),
        "tls": pgettext(_S, "TLS sertifikatı"),
    }.get(key, key)


def backup_label(key: str) -> str:
    return {
        "local": pgettext(_S, "Bazanın gündəlik ehtiyat nüsxəsi"),
        "offsite": pgettext(_S, "Serverdən kənar ehtiyat nüsxə"),
        "drill": pgettext(_S, "Bərpa məşqi (son uğurlu)"),
    }.get(key, key)


def security_label(key: str) -> str:
    return {
        "failed_logins": pgettext(_S, "Uğursuz giriş cəhdləri"),
        "brute_force": pgettext(_S, "Kobud güc cəhdləri (bir ünvandan 10+ uğursuz giriş)"),
        "superadmin_failed": pgettext(_S, "Superadmin hesabına uğursuz giriş"),
        "rate_limited": pgettext(_S, "Limitə düşən sorğular (429)"),
        "network_zone": pgettext(_S, "Şəbəkə zonası rəddləri (xaricdən bağlı səhifələr)"),
        "profanity": pgettext(_S, "Nalayiq söz filtri blokları"),
        "permission_denials": pgettext(_S, "İcazə rəddləri (audit)"),
        "http_forbidden": pgettext(_S, "Qadağan olunmuş sorğular (403)"),
        "admin_denials": pgettext(_S, "İdarə panelinə rədd edilən girişlər"),
        "unauthorized_monitoring": pgettext(_S, "Monitorinqə icazəsiz baxış cəhdləri"),
    }.get(key, key)


def reason_text(key: str, **values) -> tuple[str, str]:
    """Sağlamlıq səbəbi → (nə baş verir, nə etməli)."""
    texts = {
        "db_down": (
            pgettext(_S, "Verilənlər bazası cavab vermir."),
            pgettext(
                _S, "Baza konteynerini və disk yerini dərhal yoxlayın; imtahan varsa İmtahan Mərkəzini xəbərdar edin."
            ),
        ),
        "db_slow": (
            pgettext(_S, "Verilənlər bazası gec cavab verir (%(ms)s ms)."),
            pgettext(_S, "Yavaş sorğuları və server yükünü yoxlayın."),
        ),
        "cache_down": (
            pgettext(_S, "Keş serveri (Redis) cavab vermir."),
            pgettext(_S, "Redis konteynerini yoxlayın — sessiyalar və fon tapşırıqları təsirlənə bilər."),
        ),
        "metrics_down": (
            pgettext(_S, "Metrik sistemi (Prometheus) əlçatmazdır — server göstəriciləri görünmür."),
            pgettext(
                _S,
                "Prometheus konteynerini yoxlayın. Tətbiq işləyir; baza, imtahan və təhlükəsizlik göstəriciləri "
                "görünür, server/trafik/konteyner göstəriciləri isə «—» qalır.",
            ),
        ),
        "errors_high": (
            pgettext(_S, "Son 1 saatda sorğuların %(pct)s%%-i server xətası (5xx) ilə bitib."),
            pgettext(_S, "«Tətbiq» bölməsində ən çox xəta verən səhifələrə və «Loglar»a baxın."),
        ),
        "latency_high": (
            pgettext(_S, "Səhifələr gec açılır: sorğuların 95%%-i %(seconds)s saniyəyə qədər çəkir."),
            pgettext(_S, "Ən yavaş səhifələrə və baza yükünə baxın."),
        ),
        "cpu_high": (
            pgettext(_S, "Prosessor (CPU) yükü %(pct)s%%-dir."),
            pgettext(_S, "Hansı xidmətin yükləndiyini «Konteynerlər» bölməsində yoxlayın."),
        ),
        "memory_high": (
            pgettext(_S, "Serverin yaddaşı (RAM) %(pct)s%% doludur."),
            pgettext(_S, "Yaddaşı çox işlədən konteyneri tapın; lazım olsa yenidən başladın."),
        ),
        "disk_high": (
            pgettext(_S, "Server diskinin %(pct)s%%-i doludur."),
            pgettext(_S, "Köhnə log və ehtiyat nüsxələri təmizləyin və ya diski genişləndirin."),
        ),
        "service_down": (
            pgettext(_S, "%(service)s işləmir."),
            pgettext(_S, "Müvafiq konteyneri yoxlayın və yenidən başladın."),
        ),
        "targets_down": (
            pgettext(_S, "%(count)s monitorinq hədəfi cavab vermir."),
            pgettext(_S, "«Server» və «Konteynerlər» bölmələrində hansı xidmətin dayandığını yoxlayın."),
        ),
        "workers_down": (
            pgettext(_S, "Fon tapşırıqlarını icra edən işçi (Celery) onlayn deyil."),
            pgettext(_S, "Celery konteynerlərini yoxlayın — bildirişlər, ixrac və avtomatik təhvil gecikə bilər."),
        ),
        "workers_stale": (
            pgettext(_S, "Fon tapşırıqlarının statistikası %(minutes)s dəqiqədir yenilənmir."),
            pgettext(_S, "Planlı tapşırıqlar (Celery Beat) konteynerini yoxlayın."),
        ),
        "queue_backlog": (
            pgettext(_S, "Növbədə %(count)s fon tapşırığı gözləyir."),
            pgettext(_S, "İşçilərin sayını və ağır tapşırıqları yoxlayın."),
        ),
        "backup_old": (
            pgettext(_S, "Bazanın son ehtiyat nüsxəsi %(hours)s saat əvvəl alınıb."),
            pgettext(_S, "Ehtiyat nüsxə xidmətini dərhal yoxlayın — gündəlik cədvəl pozulub."),
        ),
        "offsite_old": (
            pgettext(_S, "Serverdən kənar ehtiyat nüsxə %(hours)s saatdır yenilənmir."),
            pgettext(_S, "Off-site backup xidmətinin loguna baxın (şəbəkə, parol və ya disk)."),
        ),
        "incidents_critical": (
            pgettext(_S, "%(count)s kritik insident açıqdır."),
            pgettext(_S, "«İnsidentlər» bölməsində açıq insidentlərə baxın."),
        ),
        "incidents_open": (
            pgettext(_S, "%(count)s insident hələ həll olunmayıb."),
            pgettext(_S, "«İnsidentlər» bölməsində açıq insidentlərə baxın."),
        ),
        "brute_force": (
            pgettext(_S, "Son 24 saatda %(count)s kobud güc (brute-force) giriş cəhdi qeydə alınıb."),
            pgettext(_S, "«Təhlükəsizlik» bölməsində mənbə ünvanlarına baxın; lazım olsa ünvanı bloklayın."),
        ),
        "failed_logins_high": (
            pgettext(_S, "Son 24 saatda %(count)s uğursuz giriş cəhdi olub."),
            pgettext(_S, "Kütləvi parol təxmini olub-olmadığını «Təhlükəsizlik» bölməsində yoxlayın."),
        ),
        "exam_autosave": (
            pgettext(_S, "Son 1 saatda imtahan cavablarının yazılmasında %(count)s xəta olub."),
            pgettext(_S, "İmtahan Mərkəzi ilə əlaqə saxlayın və «Loglar»da xəta mətnlərinə baxın."),
        ),
        "tls_expiring": (
            pgettext(_S, "TLS sertifikatının bitməsinə %(days)s gün qalıb."),
            pgettext(_S, "Sertifikatı vaxtında yeniləyin."),
        ),
        "restarts": (
            pgettext(_S, "Son 24 saatda xidmətlər %(count)s dəfə yenidən başlayıb."),
            pgettext(_S, "«Konteynerlər» bölməsində hansı xidmətin təkrar başladığını yoxlayın."),
        ),
        "oom": (
            pgettext(_S, "Son 24 saatda %(count)s dəfə yaddaş çatışmazlığı (OOM) olub."),
            pgettext(_S, "Yaddaş limitlərini və yaddaşı çox işlədən xidməti yoxlayın."),
        ),
        "pool_waiting": (
            pgettext(_S, "Bazaya qoşulmaq üçün %(count)s sorğu növbədə gözləyir."),
            pgettext(_S, "Baza yükünü və uzun sürən sorğuları yoxlayın."),
        ),
    }
    what, todo = texts[key]
    try:
        return what % values, todo
    except (KeyError, TypeError, ValueError):  # pragma: no cover - tərcümə formatı pozulubsa
        return what, todo


def window_label(key: str) -> str:
    return {
        "5m": pgettext(_S, "Son 5 dəqiqə"),
        "1h": pgettext(_S, "Son 1 saat"),
        "24h": pgettext(_S, "Son 24 saat"),
    }.get(key, key)


__all__ = [
    "alert_title",
    "backup_label",
    "health_summary",
    "health_title",
    "reason_text",
    "security_label",
    "service_label",
    "window_label",
]
