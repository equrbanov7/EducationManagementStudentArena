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
        --run-id 137331f4-0d64-4a0b-b6bd-482a27624f60 \\
        --organization-id a8a1a0f5-aeb7-43c5-848d-fcff008f7273 \\
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
yazılış, dərs slotu tapılmadı, hədəf açarı toqquşması) mənbədən MÜSTƏQİL
yenidən hesablayır.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.legacy_reconcile.collect import (  # noqa: E402
    build_ladders,
    collect_source_facts,
    collect_target_facts,
    collect_write_replay,
    compare_finals,
)
from scripts.legacy_reconcile.grade_artifacts import reconcile_grade_artifacts  # noqa: E402
from scripts.legacy_reconcile.grade_facts import reconcile_grade_facts  # noqa: E402
from scripts.legacy_reconcile.grade_replay_facts import (  # noqa: E402
    replay_grade_fact_keys,
    replay_grade_fact_rows,
)
from scripts.legacy_reconcile.grade_source_hashes import collect_source_grade_hashes  # noqa: E402
from scripts.legacy_reconcile.render import render_report  # noqa: E402
from scripts.legacy_reconcile.sampling import SAMPLE_SEED, SAMPLE_SIZE, collect_sample  # noqa: E402
from scripts.legacy_reconcile.transport import SourceReader, TargetReader, Timer, target_dsn  # noqa: E402

DEFAULT_CONTAINER = "emsarena-legacy-source-rehearsal"
DEFAULT_SOURCE_DB = "myedudb"
DEFAULT_TARGET_HOST = "127.0.0.1"
DEFAULT_TARGET_PORT = 55433
DEFAULT_TARGET_USER = "emsarena_app"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="legacy_reconcile_report",
        description="Mənbə MariaDB ilə köçürülmüş PostgreSQL bazasını tutuşduran OXU-ONLY hesabat.",
    )
    parser.add_argument("--db", required=True, help="Hədəf PostgreSQL baza adı (məs. emsarena_rehearsal_…).")
    parser.add_argument("--run-id", required=True, help="Yalnız bu uğurlu repetisiya UUID-si uzlaşdırılır.")
    parser.add_argument(
        "--organization-id",
        required=True,
        type=UUID,
        help="RLS üçün repetisiya təşkilatının UUID-si (yalnız həmin tenant oxunur).",
    )
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
        default=None,
        help="TCP rejimində məcburi host portu; dinamik Docker portunu açıq verin.",
    )
    parser.add_argument("--source-user", default="root")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--sample-seed", type=int, default=SAMPLE_SEED)
    parser.add_argument(
        "--skip-deep",
        action="store_true",
        help="Ən ağır addımı (xana-xana yazı təkrar-icrası) buraxır; nərdivan qalığı böyük görünür.",
    )
    return parser


def _source_tcp(args) -> dict | None:
    if not args.source_host:
        return None
    if args.source_port is None:
        raise SystemExit("TCP rejimi üçün --source-port açıq verilməlidir.")
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
        organization_id=args.organization_id,
    )
    try:
        print("→ hədəf sayları və ledger körpüləri oxunur…", file=sys.stderr)
        target_facts = collect_target_facts(target, run_id=args.run_id)
        if not target_facts["run"]:
            raise RuntimeError("legacy_reconcile_run_not_found")
        print("→ mənbə aqreqatları hesablanır (ən ağır addım bir neçə dəqiqə çəkə bilər)…", file=sys.stderr)
        source_facts = collect_source_facts(source)
        replay = None
        if not args.skip_deep:
            print("→ yazı qərarı xana-xana təkrar icra olunur (ən ağır addım)…", file=sys.stderr)
            replay = collect_write_replay(source, target, target_facts, source_facts)
        print("→ nərdivan və yekun müqayisəsi qurulur…", file=sys.stderr)
        print("→ immutable legacy qiymət faktları sətir-səviyyəsində tutuşdurulur…", file=sys.stderr)
        extra_grade_rows = replay_grade_fact_rows(replay)
        source_grade_hashes = collect_source_grade_hashes(
            source,
            extra_keys=replay_grade_fact_keys(replay),
        )
        grade_facts = reconcile_grade_facts(
            source,
            target,
            run_id=args.run_id,
            source_hashes=source_grade_hashes,
            extra_source_rows=extra_grade_rows,
        )
        print("→ çap olunmuş bal-vərəqi arxivi hash və sıxılma üzrə tutuşdurulur…", file=sys.stderr)
        grade_artifacts = reconcile_grade_artifacts(source, target, run_id=args.run_id)
        ladders = build_ladders(source_facts, target_facts, replay)
        context = {
            "source": source_facts,
            "target": target_facts,
            "ladders": ladders,
            "replay": replay,
            "finals": compare_finals(source_facts, target_facts, target),
            "grade_facts": grade_facts,
            "grade_artifacts": grade_artifacts,
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
    run_succeeded = target_facts["run"][1] == "succeeded"
    ladders_balanced = all(ladder.unexplained == 0 for ladder in ladders.values())
    all_gates_passed = grade_facts.passed and grade_artifacts.passed and run_succeeded and ladders_balanced
    if not all_gates_passed:
        print("✖ Uzlaşdırmanın ən azı bir fail-closed qapısı keçmədi.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
