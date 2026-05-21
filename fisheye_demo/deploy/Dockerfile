ARG BASE_IMAGE=python:3.10-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements-prod.txt

COPY . .

RUN mkdir -p /app/static/uploads /app/static/results /app/data /app/models

EXPOSE 5000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 4 --timeout 300 wsgi:app"]
