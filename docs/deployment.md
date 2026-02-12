# EMS Arena Deployment Guide

## Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Ubuntu 22.04 or similar Linux distribution

## Environment Setup

### 1. Clone Repository
```bash
git clone https://github.com/equrbanov7/EducationManagementStudentArena.git
cd EducationManagementStudentArena
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
# For production
pip install -r requirements/production.txt

# For development
pip install -r requirements/local.txt
```

### 4. Configure Environment Variables
Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
# Edit .env with your configuration
```

### 5. Run Migrations
```bash
python manage.py migrate
```

### 6. Collect Static Files
```bash
python manage.py collectstatic --noinput
```

### 7. Create Superuser
```bash
python manage.py createsuperuser
```

## Production Deployment

### Using Gunicorn
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Using Daphne (for WebSocket support)
```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

## Docker Deployment
TODO: Add Docker deployment instructions

## Nginx Configuration
TODO: Add Nginx configuration example
