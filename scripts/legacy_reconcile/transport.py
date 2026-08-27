"""Hər iki bazaya OXU-ONLY nəqliyyat qatı + sorğu vaxtı ölçmə.

⚠️ TƏHLÜKƏSİZLİK MÜQAVİLƏSİ
    * Bu modul YALNIZ ``SELECT``/``SHOW`` icra edir.  Hər sessiya
      ``SET SESSION TRANSACTION READ ONLY`` (MariaDB) və
      ``SET TRANSACTION READ ONLY`` (PostgreSQL) ilə başlayır — sürüşüb düşən
      bir ``UPDATE`` belə baza tərəfindən rədd ediləcək.
    * Mənbə MariaDB-yə DEFOLT giriş ``docker exec``-ledir: parol konteynerin öz
      mühit dəyişənindən (``MARIADB_ROOT_PASSWORD``) oxunur, host-a heç vaxt
      çıxmır və koda yazılmır.
    * TCP rejimi yalnız açıq şəkildə seçildikdə işə düşür və parolu ARQUMENTDƏN
      yox, mühit dəyişənindən götürür.

PostgreSQL bağlantısı bir uzunömürlü READ ONLY tranzaksiya saxlayır — bütün
bölmələr EYNİ snapshot-ı görsün deyə (uzlaşdırma hesabatı üçün vacibdir: yarısı
köhnə, yarısı yeni say olmasın).  Repetisiya İŞLƏYƏRKƏN də təhlükəsizdir, sadəcə
hesabatı repetisiya bitəndən sonra işlətmək daha dəqiq mənzərə verir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from .analysis import unescape_batch_field

_FORBIDDEN = ("insert", "update", "delete", "drop", "truncate", "alter", "create", "grant", "replace")
_MARIADB_PREAMBLE = "SET SESSION TRANSACTION READ ONLY;\n"
_NULL_SENTINEL = "NULL"


class ReadOnlyViolation(RuntimeError):
    """Skript yazı əməliyyatına bənzər SQL göndərməyə çalışdı."""


def assert_read_only(sql: str) -> None:
    """Fail-closed qapı: hər sorğu icradan ƏVVƏL burada süzülür."""

    lowered = sql.lower()
    for keyword in _FORBIDDEN:
        if f" {keyword} " in f" {lowered} " or lowered.lstrip().startswith(keyword):
            raise ReadOnlyViolation(f"Yazı əməliyyatı bloklandı: {keyword}")


@dataclass
class QueryTiming:
    """Hesabatın «sorğu vaxtları» əlavəsi üçün ölçmə qeydi."""

    label: str
    seconds: float
    rows: int


@dataclass
class Timer:
    entries: list[QueryTiming] = field(default_factory=list)

    def record(self, label: str, seconds: float, rows: int) -> None:
        self.entries.append(QueryTiming(label=label, seconds=seconds, rows=rows))

    @property
    def total_seconds(self) -> float:
        return sum(entry.seconds for entry in self.entries)


# ── MariaDB (mənbə) ──────────────────────────────────────────────────────────


class SourceReader:
    """MariaDB mənbəsindən OXU — ``docker exec`` və ya PyMySQL üzərindən."""

    def __init__(self, *, container: str, database: str, timer: Timer, tcp: dict | None = None) -> None:
        self.container = container
        self.database = database
        self.timer = timer
        self.tcp = tcp
        self._connection = None
        if tcp is None and shutil.which("docker") is None:
            raise RuntimeError("`docker` tapılmadı — TCP rejimi üçün --source-host/--source-port verin.")

    def query(self, label: str, sql: str) -> list[list[str]]:
        """Sorğunu icra et; nəticəni sətir-sətir mətn siyahısı kimi qaytar."""

        assert_read_only(sql)
        started = time.monotonic()
        rows = self._run_tcp(sql) if self.tcp else self._run_docker(sql)
        self.timer.record(f"mənbə · {label}", time.monotonic() - started, len(rows))
        return rows

    def scalar(self, label: str, sql: str, default: str = "0") -> str:
        rows = self.query(label, sql)
        return rows[0][0] if rows and rows[0] else default

    # -- nəqliyyat variantları ------------------------------------------------

    def _run_docker(self, sql: str) -> list[list[str]]:
        command = [
            "docker",
            "exec",
            "-i",
            self.container,
            "sh",
            "-c",
            # Parol konteynerin öz mühitindədir; host-da heç vaxt görünmür.
            f'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" {self.database} -N -B',
        ]
        completed = subprocess.run(
            command,
            input=_MARIADB_PREAMBLE + sql,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = "\n".join(line for line in completed.stderr.splitlines() if "Using a password" not in line)
            raise RuntimeError(f"MariaDB sorğusu uğursuz oldu: {stderr.strip()[:400]}")
        return _parse_batch(completed.stdout)

    def _run_tcp(self, sql: str) -> list[list[str]]:
        cursor = self._tcp_connection().cursor()
        cursor.execute(sql)
        rows = [[_stringify(value) for value in row] for row in cursor.fetchall()]
        cursor.close()
        return rows

    def _tcp_connection(self):
        if self._connection is None:
            import pymysql  # yalnız TCP rejimində lazımdır

            self._connection = pymysql.connect(
                host=self.tcp["host"],
                port=self.tcp["port"],
                user=self.tcp["user"],
                password=self.tcp["password"],
                database=self.database,
                charset="utf8mb4",
                autocommit=True,
            )
            with self._connection.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def _parse_batch(stdout: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in stdout.split("\n"):
        if line == "":
            continue
        rows.append([unescape_batch_field(field_text) for field_text in line.split("\t")])
    return rows


def _stringify(value) -> str:
    if value is None:
        return _NULL_SENTINEL
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# ── PostgreSQL (hədəf) ───────────────────────────────────────────────────────


class TargetReader:
    """Köçürülmüş PostgreSQL bazasından OXU (psycopg2, read-only tranzaksiya)."""

    def __init__(self, *, dsn: dict, timer: Timer) -> None:
        import psycopg2

        self.timer = timer
        self.connection = psycopg2.connect(**dsn)
        self.connection.set_session(readonly=True, autocommit=False)
        with self.connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET statement_timeout = '600s'")

    def query(self, label: str, sql: str, params=None) -> list[tuple]:
        assert_read_only(sql)
        started = time.monotonic()
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        self.timer.record(f"hədəf · {label}", time.monotonic() - started, len(rows))
        return rows

    def scalar(self, label: str, sql: str, params=None, default=0):
        rows = self.query(label, sql, params)
        return rows[0][0] if rows and rows[0][0] is not None else default

    def close(self) -> None:
        # Read-only tranzaksiya — commit yox, rollback: heç bir iz qalmır.
        self.connection.rollback()
        self.connection.close()


def target_dsn(*, host: str, port: int, user: str, database: str, password: str | None) -> dict:
    """Parolu arqumentdən YOX, mühit dəyişənindən oxu (fallback: arqument)."""

    resolved = password or os.environ.get("PGPASSWORD") or os.environ.get("LEGACY_TARGET_PASSWORD")
    if not resolved:
        raise RuntimeError("Hədəf baza parolu yoxdur: PGPASSWORD mühit dəyişənini təyin edin.")
    return {"host": host, "port": port, "user": user, "dbname": database, "password": resolved}
