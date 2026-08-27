#!/usr/bin/env python3
"""Legacy (MyEdu / MariaDB) ↔ EMS Arena (PostgreSQL) uzlaşdırma hesabatı.

╔══════════════════════════════════════════════════════════════════════════════╗
║  OXU-ONLY MÜQAVİLƏ                                                           ║
║                                                                              ║
║  Bu skript HEÇ BİR yazı əməliyyatı etmir.  Hər iki bazaya yalnız ``SELECT``  ║
║  gedir; hər sessiya ``SET TRANSACTION READ ONLY`` ilə açılır və PostgreSQL   ║
║  bağlantısı ``rollback`` ilə bağlanır.  Sorğular ``assert_read_only``        ║
║  qapısından keçir — sürüşüb düşən bir ``UPDATE`` belə icra olunmur.          ║
║                                                                              ║
║  Repetisiya (rehearsal) işləyərkən də təhlükəsizdir: Django konteksti        ║
║  qaldırılmır, ledger-ə heç nə yazılmır, mənbə konteynerinə yalnız oxu        ║
║  sorğusu göndərilir.                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

İSTİFADƏ
--------
    python scripts/legacy_reconcile_report.py \\
        --db emsarena_rehearsal_603f5e9f08e7 \\
        --output /tmp/RECONCILE.md

Hədəf baza parolu **arqumentlə deyil**, mühit dəyişəni ilə verilir::

    export PGPASSWORD=…      # və ya LEGACY_TARGET_PASSWORD

Mənbə MariaDB-yə defolt giriş ``docker exec``-lədir: parol konteynerin öz
``MARIADB_ROOT_PASSWORD`` dəyişənindən oxunur və host-a heç vaxt çıxmır.
TCP rejimi üçün ``--source-host`` + ``LEGACY_SOURCE_PASSWORD`` verin.

NƏ HESABLAYIR
-------------
J8 fazası (``apps/legacy_import/services/rehearsal_journal_reconcile_phase.py``)
say balansını LEDGER-ə möhürləyir; bu skript isə eyni sübutu İNSANA göstərir və
ledger-in saxlamadığı pillələri (orphan jurnal, dublikat, həll olunmayan
yazılış) mənbədən MÜSTƏQİL yenidən hesablayır.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.legacy_reconcile.collect import (  # noqa: E402
    build_ladders,
    collect_source_facts,
    collect_target_facts,
    compare_finals,
)
from scripts.legacy_reconcile.render import render_report  # noqa: E402
from scripts.legacy_reconcile.sampling import SAMPLE_SEED, SAMPLE_SIZE, collect_sample  # noqa: E402
from scripts.legacy_reconcile.transport import SourceReader, TargetReader, Timer, target_dsn  # noqa: E402

DEFAULT_CONTAINER = "emsarena-legacy-source-rehearsal"
DEFAULT_SOURCE_DB = "myedudb"
DEFAULT_SOURCE_PORT = 56970  # repetisiya konteynerinin host portu (yoxlanılıb)
DEFAULT_TARGET_HOST = "127.0.0.1"
DEFAULT_TARGET_PORT = 55433
DEFAULT_TARGET_USER = "emsarena_staging"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="legacy_reconcile_report",
        description="Mənbə MariaDB ilə köçürülmüş PostgreSQL bazasını tutuşduran OXU-ONLY hesabat.",
    )
    parser.add_argument("--db", required=True, help="Hədəf PostgreSQL baza adı (məs. emsarena_rehearsal_…).")
    parser.add_argument("--output", required=True, help="Markdown hesabatın yazılacağı fayl.")
    parser.add_argument("--target-host", default=DEFAULT_TARGET_HOST)
    parser.add_argument("--target-port", type=int, default=DEFAULT_TARGET_PORT)
    parser.add_argument("--target-user", default=DEFAULT_TARGET_USER)
    parser.add_argument(
        "--source-container", default=DEFAULT_CONTAINER, help="Mənbə MariaDB konteyneri (docker rejimi)."
    )
    parser.add_argument("--source-db", default=DEFAULT_SOURCE_DB)
    parser.add_argument("--source-host", default="", help="Verilsə TCP rejiminə keçir (PyMySQL tələb olunur).")
    parser.add_argument(
        "--source-port",
        type=int,
        default=DEFAULT_SOURCE_PORT,
        help="Mənbənin host portu (repetisiya konteyneri 127.0.0.1:56970-ə bağlıdır).",
    )
    parser.add_argument("--source-user", default="root")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--sample-seed", type=int, default=SAMPLE_SEED)
    parser.add_argument(
        "--skip-deep",
        action="store_true",
        help="Ən ağır sorğunu (xana → jurnal/tələbə aqreqatı) buraxır; nərdivan qalığı böyük görünür.",
    )
    return parser


def _source_tcp(args) -> dict | None:
    if not args.source_host:
        return None
    password = os.environ.get("LEGACY_SOURCE_PASSWORD")
    if not password:
        raise SystemExit("TCP rejimi üçün LEGACY_SOURCE_PASSWORD mühit dəyişəni lazımdır.")
    return {"host": args.source_host, "port": args.source_port, "user": args.source_user, "password": password}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    timer = Timer()
    source = SourceReader(
        container=args.source_container,
        database=args.source_db,
        timer=timer,
        tcp=_source_tcp(args),
    )
    target = TargetReader(
        dsn=target_dsn(
            host=args.target_host,
            port=args.target_port,
            user=args.target_user,
            database=args.db,
            password=None,
        ),
        timer=timer,
    )
    try:
        print("→ hədəf sayları və ledger körpüləri oxunur…", file=sys.stderr)
        target_facts = collect_target_facts(target)
        print("→ mənbə aqreqatları hesablanır (ən ağır addım bir neçə dəqiqə çəkə bilər)…", file=sys.stderr)
        source_facts = collect_source_facts(source, deep=not args.skip_deep)
        print("→ nərdivan və yekun müqayisəsi qurulur…", file=sys.stderr)
        context = {
            "source": source_facts,
            "target": target_facts,
            "ladders": build_ladders(source_facts, target_facts),
            "finals": compare_finals(source_facts, target_facts, target),
            "sample": collect_sample(source, target, target_facts, size=args.sample_size, seed=args.sample_seed),
            "sample_seed": args.sample_seed,
            "source_label": f"{args.source_container}:{args.source_db}",
            "target_label": f"{args.target_host}:{args.target_port}/{args.db}",
            "timer": timer,
        }
        markdown = render_report(context=context)
    finally:
        source.close()
        target.close()

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(markdown, encoding="utf-8")
    print(f"✔ Hesabat yazıldı: {destination}  ({len(markdown):,} bayt)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
