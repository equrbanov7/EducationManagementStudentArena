# Development Dockerfile for EMS Arena
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/local.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Expose port
EXPOSE 8000

# Run entrypoint script
ENTRYPOINT ["/app/docker/entrypoint.sh"]
