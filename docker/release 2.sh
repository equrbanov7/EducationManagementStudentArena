#!/bin/sh
set -eu

# Run this once during deployment before starting web workers.
python manage.py migrate --noinput
