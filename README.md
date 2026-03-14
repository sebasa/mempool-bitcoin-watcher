# 🔍 Mempool Bitcoin Watcher

Monitor de transacciones Bitcoin que consulta la API local de tu nodo Mempool (Umbrel) y envía notificaciones IPN a un webhook cuando detecta nuevas transacciones en las direcciones configuradas.

---

## 📁 Estructura del proyecto

```
mempool-watcher/
├── app/
│   ├── watcher.py          # Servicio principal (polling + webhook)
│   ├── manage.py           # CLI para gestionar direcciones y ver logs
│   └── requirements.txt
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── .env.example
```

---

## 🚀 Instalación en Debian

### 1. Clonar/copiar el proyecto

```bash
mkdir -p /opt/mempool-watcher
# Copia los archivos aquí
```

### 2. Instalar Docker (si no está instalado)

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

### 3. Configurar entorno

```bash
cd /opt/mempool-watcher
cp .env.example .env
nano .env   # Ajusta MEMPOOL_URL, WEBHOOK_URL y WEBHOOK_SECRET
```

### 4. Verificar conectividad con tu Umbrel

```bash
# Prueba que puedes alcanzar la API de Mempool desde el servidor Debian
curl http://192.168.1.x:3006/api/v1/fees/recommended
```

### 5. Construir e iniciar el contenedor

```bash
cd docker/
docker compose up -d --build
```

### 6. Ver logs en tiempo real

```bash
docker compose logs -f
```

---

## 🗂 Gestión de direcciones

El CLI `manage.py` corre **dentro del contenedor**:

```bash
# Alias útil para no repetir el prefijo
alias watcher="docker exec mempool-watcher python manage.py"

# Agregar una dirección
watcher add bc1qxxx... --label "Cliente #42"

# Listar todas las direcciones
watcher list

# Ver transacciones detectadas
watcher txs --limit 50

# Estadísticas generales
watcher stats

# Desactivar temporalmente una dirección
watcher disable bc1qxxx...

# Eliminar una dirección
watcher remove bc1qxxx...
```

---

## 📨 Formato del payload IPN

Cuando se detecta una nueva transacción, se envía un `POST` al webhook con:

```json
{
  "event":          "new_transaction",
  "address":        "bc1qxxx...",
  "txid":           "a1b2c3d4...",
  "confirmed":      false,
  "block_height":   null,
  "block_time":     null,
  "fee":            1234,
  "size":           250,
  "weight":         892,
  "received_sats":  100000,
  "sent_sats":      0,
  "net_sats":       100000,
  "received_btc":   0.00100000,
  "sent_btc":       0.00000000,
  "net_btc":        0.00100000,
  "vin_count":      1,
  "vout_count":     2,
  "mempool_url":    "http://umbrel.local:3006/tx/a1b2c3d4...",
  "timestamp":      "2025-01-15T10:30:00+00:00"
}
```

**Headers enviados:**

```
Content-Type:   application/json
User-Agent:     mempool-watcher/1.0
X-Event-Type:   bitcoin_transaction
X-Address:      bc1qxxx...
X-TXID:         a1b2c3d4...
X-Signature:    sha256=<hmac-hex>   ← solo si WEBHOOK_SECRET está configurado
```

---

## 🔐 Verificar la firma en tu servidor receptor

```python
import hmac, hashlib

def verify_signature(payload_body: bytes, header_sig: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header_sig)
```

```php
// PHP
function verifySignature(string $payload, string $header, string $secret): bool {
    $expected = 'sha256=' . hash_hmac('sha256', $payload, $secret);
    return hash_equals($expected, $header);
}
```

---

## ⚙️ Variables de entorno

| Variable          | Default                        | Descripción                              |
|-------------------|--------------------------------|------------------------------------------|
| `MEMPOOL_URL`     | `http://umbrel.local:3006`     | URL base de tu instancia Mempool         |
| `WEBHOOK_URL`     | *(requerido)*                  | Endpoint IPN receptor                    |
| `WEBHOOK_SECRET`  | *(vacío)*                      | Secreto HMAC para firma de payloads      |
| `DB_PATH`         | `/data/watcher.db`             | Ruta SQLite (dentro del contenedor)      |
| `POLL_INTERVAL`   | `30`                           | Segundos entre ciclos de polling         |
| `REQUEST_TIMEOUT` | `10`                           | Timeout de requests HTTP (segundos)      |

---

## 🏗 Esquema de la base de datos

```sql
-- Direcciones a monitorear
addresses (id, address, label, active, created_at, last_checked)

-- TXs ya detectadas (evita duplicados y trackea reintentos)
seen_txs (txid, address, detected_at, notified, retries)

-- Log de cada llamada al webhook
webhook_log (id, txid, address, status_code, success, payload, response, sent_at)
```

---

## 🔁 Lógica de reintentos

- Si el webhook responde con un código fuera del rango `2xx`, la TX queda marcada como `notified=0`.
- Cada 5 ciclos de polling, el watcher reintenta las notificaciones fallidas.
- Máximo **5 reintentos** por transacción.

---

## 🩺 Health check

El contenedor tiene un healthcheck integrado que consulta el endpoint `/api/v1/fees/recommended` de Mempool cada 60 segundos.

```bash
docker inspect --format='{{.State.Health.Status}}' mempool-watcher
```

---

## 📝 Notas importantes

- El watcher detecta transacciones tanto en **mempool (sin confirmar)** como **confirmadas**.
- Una misma TX no generará notificación duplicada aunque aparezca en ambos endpoints.
- Se recomienda un `POLL_INTERVAL` de al menos 15 segundos para no saturar la API local.
- Si agregas muchas direcciones (>50), considera aumentar el intervalo.
