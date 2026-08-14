FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python package dependencies
COPY pyproject.toml README.md ./
COPY scraper/ ./scraper/

RUN pip install --no-cache-dir -e .
RUN playwright install --with-deps chromium

EXPOSE 8080

CMD ["uvicorn", "scraper.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
