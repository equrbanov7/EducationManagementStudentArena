# Development Dockerfile for EMS Arena
# Pin to Debian Bookworm (stable) for consistency with the production image.
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# Set work directory
WORKDIR /app

# Apply OS security patches; install postgresql-client for pg_isready in entrypoint.
# tesseract-ocr + aze: skan edilmiş (şəkil əsaslı) imtahan PDF-lərini OCR ilə oxumaq üçün.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        tesseract-ocr \
        tesseract-ocr-aze \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/local.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Expose port
EXPOSE 8000

# Run entrypoint script
ENTRYPOINT ["/app/docker/entrypoint.sh"]
