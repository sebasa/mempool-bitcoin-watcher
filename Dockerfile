FROM python:3.12-slim

LABEL maintainer="mempool-watcher"
LABEL description="Bitcoin transaction watcher via Mempool API → Webhook IPN"

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY watcher.py .
COPY manage.py .

# Volumen para la base de datos SQLite
VOLUME ["/data"]

# Healthcheck: verifica que la API de mempool responde
HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf "${MEMPOOL_URL:-http://umbrel.local:3006}/api/v1/fees/recommended" || exit 1

CMD ["python", "-u", "watcher.py"]
