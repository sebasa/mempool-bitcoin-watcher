# 🔍 Mempool Bitcoin Watcher

Monitor de transacciones Bitcoin que se conecta via **WebSocket** a tu nodo Mempool (Umbrel) usando `track-addresses` — el propio nodo filtra y empuja solo las TXs relevantes. Cuando detecta una transacción en una dirección vigilada, dispara un webhook IPN hacia el endpoint configurado por **categoría**.

---

## 📁 Estructura del proyecto

```
mempool-watcher/
├── app/
│   ├── watcher.py          # Servicio principal (WebSocket + webhook IPN)
│   ├── manage.py           # CLI para gestionar categorías, direcciones y logs
│   └── requirements.txt
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🚀 Instalación en Debian

### 1. Instalar Docker (si no está instalado)

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

### 2. Configurar entorno

```bash
cd /opt/mempool-watcher
cp .env.example .env
nano .env   # Ajusta MEMPOOL_URL y opcionalmente WEBHOOK_URL de fallback
```

### 3. Verificar conectividad con tu Umbrel

```bash
curl http://192.168.1.x:3006/api/v1/fees/recommended
```

### 4. Construir e iniciar el contenedor

```bash
cd docker/
docker compose up -d --build
docker compose logs -f
```

---

## 🗂 Gestión con manage.py

Todas las operaciones se ejecutan dentro del contenedor:

```bash
# Alias recomendado
alias watcher="docker exec mempool-watcher python manage.py"
```

### Categorías

Cada categoría define su propio webhook. Primero crea las categorías, luego asigna direcciones.

```bash
# Crear categoría con webhook propio
watcher category add tienda      https://miapp.com/ipn/tienda      --secret abc123
watcher category add donaciones  https://miapp.com/ipn/donaciones  --secret xyz789
watcher category add exchange    https://miapp.com/ipn/exchange

# Listar categorías
watcher category list

# Editar webhook o secreto de una categoría
watcher category edit tienda --webhook https://nuevo-endpoint.com/ipn

# Eliminar categoría (las dirs quedan sin categoría)
watcher category remove tienda --force
```

### Direcciones

```bash
# Agregar dirección asignada a una categoría
watcher address add bc1qxxx... --category tienda     --label "Orden #42"
watcher address add bc1qyyy... --category donaciones --label "Campaña 2025"

# Listar todas las direcciones (agrupadas por categoría)
watcher address list

# Listar solo las de una categoría
watcher address list --category tienda

# Cambiar categoría o label de una dirección
watcher address edit bc1qxxx... --category donaciones
watcher address edit bc1qxxx... --label "Orden #99"

# Activar / desactivar sin eliminar
watcher address disable bc1qxxx...
watcher address enable  bc1qxxx...

# Eliminar
watcher address remove bc1qxxx...
```

### Logs y estadísticas

```bash
# Ver últimas transacciones detectadas
watcher txs
watcher txs --limit 50
watcher txs --category tienda

# Estadísticas generales + TXs por categoría
watcher stats
```

---

## 📨 Formato del payload IPN

Cuando se detecta una nueva transacción se envía un `POST` al webhook de la categoría correspondiente:

```json
{
  "event":         "mempool_transaction",
  "address":       "bc1qxxx...",
  "category":      "tienda",
  "txid":          "a1b2c3d4...",
  "confirmed":     false,
  "block_height":  null,
  "block_time":    null,
  "fee":           1234,
  "size":          250,
  "weight":        892,
  "received_sats": 100000,
  "sent_sats":     0,
  "net_sats":      100000,
  "received_btc":  0.00100000,
  "sent_btc":      0.00000000,
  "net_btc":       0.00100000,
  "vin_count":     1,
  "vout_count":    2,
  "mempool_url":   "http://umbrel.local:3006/tx/a1b2c3d4...",
  "timestamp":     "2025-01-15T10:30:00+00:00"
}
```

El campo `event` puede ser:
- `mempool_transaction` → TX recién detectada en la mempool (sin confirmar)
- `confirmed_transaction` → TX de esa dirección incluida en un bloque

**Headers enviados en cada request:**

```
Content-Type:   application/json
User-Agent:     mempool-watcher/3.0
X-Event-Type:   mempool_transaction
X-Address:      bc1qxxx...
X-Category:     tienda
X-TXID:         a1b2c3d4...
X-Signature:    sha256=<hmac-hex>   ← solo si la categoría tiene webhook_secret
```

---

## 🔐 Verificar la firma HMAC en tu receptor

```python
# Python
import hmac, hashlib

def verify(body: bytes, header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)

# Uso
ok = verify(request.body, request.headers["X-Signature"], "tu-secreto")
```

```php
// PHP
function verify(string $body, string $header, string $secret): bool {
    return hash_equals('sha256=' . hash_hmac('sha256', $body, $secret), $header);
}
```

---

## ⚙️ Variables de entorno

| Variable          | Default                    | Descripción                                                  |
|-------------------|----------------------------|--------------------------------------------------------------|
| `MEMPOOL_URL`     | `http://umbrel.local:3006` | URL base de tu instancia Mempool                             |
| `WEBHOOK_URL`     | *(vacío)*                  | Webhook de **fallback** para dirs sin categoría              |
| `WEBHOOK_SECRET`  | *(vacío)*                  | Secreto HMAC de fallback                                     |
| `DB_PATH`         | `/data/watcher.db`         | Ruta SQLite dentro del contenedor                            |
| `RECONNECT_DELAY` | `10`                       | Segundos entre reintentos de reconexión WebSocket            |
| `WATCHLIST_SYNC`  | `60`                       | Segundos entre re-sincronizaciones de la watchlist con la BD |
| `REQUEST_TIMEOUT` | `10`                       | Timeout de requests HTTP al webhook (segundos)               |

> `WEBHOOK_URL` y `WEBHOOK_SECRET` solo se usan como fallback. Lo recomendado es configurar el webhook directamente en cada categoría con `manage.py category add`.

---

## 🏗 Esquema de la base de datos

```sql
-- Categorías: cada una con su propio webhook
categories (id, name, webhook_url, webhook_secret, description, active, created_at)

-- Direcciones vigiladas, asignadas a una categoría
addresses (id, address, label, category_id → categories, active, created_at, last_match)

-- Registro de TXs detectadas (evita duplicados y trackea reintentos)
seen_txs (txid, address, detected_at, notified, retries)

-- Log de cada llamada al webhook
webhook_log (id, txid, address, category, webhook_url, status_code, success, payload, response, sent_at)
```

---

## 🔁 Cómo funciona el WebSocket

Al conectar, el watcher envía:

```json
{"track-addresses": ["bc1qxxx...", "bc1qyyy...", "bc1qzzz..."]}
```

El nodo Mempool se encarga de filtrar toda la mempool y empuja únicamente las TXs que involucran esas direcciones. Cada vez que se agrega o elimina una dirección, se reenvía el mensaje con la lista actualizada (sin reconectar).

La watchlist se re-sincroniza con la BD cada `WATCHLIST_SYNC` segundos, por lo que los cambios hechos con `manage.py` se aplican automáticamente sin reiniciar el contenedor.

---

## 📝 Notas

- Una misma TX nunca genera notificación duplicada por dirección.
- Si el webhook de una categoría falla, la TX queda marcada como `notified=0` en la BD para diagnóstico.
- Si una dirección no tiene categoría asignada, se usa el `WEBHOOK_URL` del `.env` como fallback. Si tampoco está configurado, se loguea una advertencia y se omite la notificación.
