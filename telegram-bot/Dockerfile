FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates openssl procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

RUN groupadd -g 988 docker && useradd -m botuser -G docker && chown -R botuser:botuser /app
USER botuser

ENTRYPOINT ["python3", "bot.py"]
