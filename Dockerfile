FROM python:3.12-slim

LABEL description="Bitcoin mempool watcher via WebSocket → Webhook IPN"

WORKDIR /

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watcher.py .
COPY manage.py .

VOLUME ["/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import websocket; print('ok')" || exit 1

CMD ["python", "-u", "watcher.py"]