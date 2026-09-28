# Python dependency lock (Audit 2026-09-28 AD-06)

## Files

| File | Role | Edited by |
|---|---|---|
| `requirements/base.txt`, `production.txt`, `test.txt`, … | **Inputs** — direct dependencies, `==` pins, comments with the reason for security pins | humans / Dependabot |
| `requirements/production.lock` | Full, hashed lock for the Docker image (`production.txt`) | `scripts/deps/lock.sh` only |
| `requirements/test.lock` | Full, hashed lock for CI (unit, RLS, build, e2e, JS jobs) | `scripts/deps/lock.sh` only |
| `scripts/deps/overrides.txt` | uv overrides for platform splits we never run (PyPy/Windows) | humans, rarely |

Locks are **universal** (`uv pip compile --universal --python-version 3.11`):
one file works on Linux and macOS, Python 3.11 and 3.12, with environment
markers for the few conditional packages. Every pin carries the sha256 of every
published wheel and sdist, so `pip install --require-hashes -r …lock` works on
the Docker image (Linux/amd64, 3.12), the CI runners and developer Macs.
Verified on 2026-09-28: clean installs of both locks on macOS/arm64 py3.11 and
in a `python:3.12-slim-bookworm` (amd64) container, `pip check` clean.

## Everyday use

```bash
# after changing a pin in requirements/*.txt (or on a Dependabot PR):
scripts/deps/lock.sh              # keeps every other pin, resolves only what changed
git add requirements/*.txt requirements/*.lock

scripts/deps/lock.sh --upgrade    # deliberate refresh of ALL transitive pins
scripts/deps/lock.sh --check      # what CI runs (lint job): fails if a lock is stale
```

The script uses `uv` from `PATH`, or installs the pinned `uv` (`UV_VERSION`,
default 0.12.19) into a throw-away venv under `$TMPDIR`.

## Installing

```bash
pip install --require-hashes -r requirements/test.lock        # dev / CI
pip install --require-hashes -r requirements/production.lock  # Dockerfile.prod
```

`psycopg2` (production) is still built from its sdist, so the image keeps
`gcc`/`libpq-dev` during the install layer. `setuptools`/`pip`/`wheel` are
upgraded unpinned *before* the locked install (base image CVEs, P2-10) and the
lock then pins `setuptools` to the resolved version.

## Why

Before the lock, 73 of 141 installed packages (Celery's `kombu`/`billiard`/`amqp`,
`botocore`, `grpcio`, `protobuf`, …) floated: CI, the server's cached first build
and a fresh host could resolve different versions of the same commit. The
initial lock was seeded from the tested developer venv, so no installed version
changed.
