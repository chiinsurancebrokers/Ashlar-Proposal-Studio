FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Noto Sans gives ReportLab reliable Greek + Latin Unicode support.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8080

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
