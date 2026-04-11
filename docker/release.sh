#!/bin/sh
set -eu

# Keep database schema and collected static assets in sync with the latest
# image/code before the web container starts serving traffic.
python manage.py migrate --noinput
python manage.py collectstatic --noinput
