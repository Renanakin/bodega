# Alerta: DiskSpaceLow

**Severidad:** ⚠️ warning
**Origen:** Prometheus
**SLA respuesta:** 1 hora
**Componente:** `host`

---

## ¿Qué significa?

El volumen raíz tiene menos del 10% libre por 30+ minutos. Riesgo
inminente de que el SO no pueda escribir (logs, temp files) o de que
Postgres colapse.

## ¿Qué hacer?

### 1. Ver el estado del disco (1 min)

```bash
df -h /
df -h /var/lib/docker
df -h /var/lib/postgresql  # volumen de datos de Postgres
```

### 2. Identificar qué ocupa espacio (5 min)

```bash
# Top 10 directorios
du -h / --max-depth=1 2>/dev/null | sort -hr | head -10

# Top 10 archivos grandes
find / -type f -size +100M 2>/dev/null | head -10

# Logs viejos
du -sh /var/log/* 2>/dev/null | sort -hr | head -5
```

### 3. Liberar espacio (rápido)

#### Limpiar logs viejos
```bash
# Logs de Docker
docker system prune -a --volumes  # ⚠️ borra imágenes y volumenes no usados
docker image prune -a  # solo imagenes

# Logs de syslog
journalctl --vacuum-time=7d  # mantener solo 7 dias
```

#### Limpiar backups viejos
```bash
# Backups de Postgres > 7 dias
find /var/backups/bodegaje -name "*.sql.gz" -mtime +7 -delete

# Logs rotados de Nginx
find /var/log/nginx -name "*.gz" -mtime +30 -delete
```

#### Comprimir logs activos
```bash
# Log de la app (si esta fuera de Docker)
gzip /var/log/bodegaje/api.log
```

### 4. Si el problema es el volumen de Postgres (1 min)

```bash
# Ver tamaño de las tablas
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT schemaname, tablename,
         pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
  LIMIT 10;
"
```

Tablas candidatas a limpieza:
- `audit_logs`: rotar cada 90 días.
- `inventory_movements`: archivar > 1 año.
- `email_outbox`: purgar `status IN ('sent', 'dead')` > 30 días.

### 5. Si nada de lo anterior alcanza, expandir el disco

- En cloud: expandir el volumen (5-10 min de downtime).
- En VPS: agregar disco nuevo y mover `/var/lib/postgresql`.

## Mitigación duradera

1. **Monitoreo proactivo:** la alerta al 10% es tardía. Configurar
   una segunda al 20% para tener tiempo.
2. **Rotación automática:** cron que limpia logs >7 días y `audit_logs`
   >90 días.
3. **Almacenamiento externo:** mover backups a S3 para no llenar el
   disco local.

## Referencias

- [disaster-recovery.md](../disaster-recovery.md)
