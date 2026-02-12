#!/bin/bash

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! pg_isready -h ${DB_HOST:-db} -p ${DB_PORT:-5432} -U ${DB_USER:-postgres}; do
  sleep 1
done
echo "PostgreSQL is ready!"

# Run migrations
python manage.py migrate --noinput

# Start development server
python manage.py runserver 0.0.0.0:8000
