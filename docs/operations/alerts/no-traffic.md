# Alerta: NoTraffic

**Severidad:** ⚠️ warning
**Origen:** Prometheus
**SLA respuesta:** 30 min
**Componente:** `bodegaje-api`

---

## ¿Qué significa?

La API no ha recibido requests HTTP en 10+ minutos. Esto **no siempre
es un problema** (sistema nuevo sin usuarios), pero suele indicar algo
roto.

## Diagnóstico

### 1. ¿Es horario de operación?

- **Sí** (L-V 9-18): es un problema. Actúa.
- **No** (madrugada, feriado, finde): probablemente sea normal. Silencia
  la alerta con `silence` en Alertmanager.

### 2. Verificar Nginx y load balancer

```bash
# Nginx esta vivo?
docker ps | grep nginx
docker logs bodegaje-nginx --tail 20

# Hay requests llegando a Nginx?
docker logs bodegaje-nginx 2>&1 | grep -c "GET\|POST"
```

### 3. Verificar DNS

```bash
# Ping al dominio
nslookup bodega.example.com

# Test desde fuera
curl -v https://bodega.example.com/health
```

### 4. Verificar la app

```bash
# La app responde si le pego directo?
docker ps | grep bodegaje-api
docker logs bodegaje-api --tail 20

# Test directo al puerto 8000
docker exec bodegaje-api curl -s http://localhost:8000/api/v1/health/live
```

## Causas probables

1. **Nginx caído o restart loop** → `docker logs bodegaje-nginx`
2. **DNS no resuelve** → cambiar DNS o usar IP
3. **Cert TLS expirado** → `certbot renew`
4. **App crasheó en silencio** → `docker logs bodegaje-api`
5. **Balanceador (cloud) en mal estado** → consola del proveedor

## Acción

Si Nginx está caído pero la app vive:
```bash
docker compose -f infra/docker/docker-compose.yml restart nginx
```

Si la app está caída:
```bash
docker logs bodegaje-api --tail 100
# Si es OOM o crash, ver disaster-recovery §"Escenario 3"
```

Si es problema de cloud (balanceador, DNS, TLS), escalar a soporte del
proveedor.
