# Backup automatico de Postgres (bodegaje)

Servicio: `bodegaje-backup` (en `docker-compose.yml`).
Imagen custom: `infra/docker/backup/Dockerfile` (postgres:17-alpine + supercronic).
Volumen: `postgres_backups` (persiste los `.dump.gz` entre reinicios del host).

## Cuando corre

Diario a las **03:00 UTC** (12 AM Chile verano, 11 PM Chile invierno).
La primera corrida se hace esperar ~24h desde el primer `docker compose up`,
asi que **dispara una corrida manual justo despues de levantar el stack** (ver abajo).

## Que hace

1. `pg_dump -Fc` de la BD `bodegaje` -> formato custom (permite restore selectivo).
2. Comprime con gzip (queda ~1/4 del dump plano).
3. Valida tamaño minimo (1KB) y que gzip descomprima OK.
4. Crea symlink `bodegaje-latest.dump.gz` -> el mas reciente.
5. Rota: borra archivos `.dump.gz` con `mtime > 7 dias`.

## Ver estado

```powershell
# Listar backups
docker exec bodegaje-backup ls -lh /backups

# Ultimo log de corrida
docker logs --tail 50 bodegaje-backup

# Healthcheck (debe ser "healthy" si el ultimo backup es < 25h)
docker inspect --format='{{.State.Health.Status}}' bodegaje-backup
```

## Forzar corrida manual

```powershell
docker exec bodegaje-backup /usr/local/bin/backup.sh
```

Veras en consola algo como:
```
[2026-07-23T03:00:01Z] Iniciando backup: bodegaje@db:5432 -> /backups/bodegaje-20260723T030001Z.dump.gz
[2026-07-23T03:00:08Z] Backup completado en 7s. Tamaño: 234567 bytes.
[2026-07-23T03:00:08Z] Estado final: 1 backup(s), 224K total en /backups
```

## Restaurar (DRP)

### Caso 1: la BD se rompio, quieres volver al ultimo backup

```powershell
# 1. Bajar la API y el worker para que no escriban mientras restauras
docker compose stop api worker

# 2. Copiar el backup al host (si lo quieres inspeccionar antes)
docker cp bodegaje-backup:/backups/bodegaje-latest.dump.gz ./restore.dump.gz
# o un backup especifico:
# docker cp bodegaje-backup:/backups/bodegaje-20260723T030001Z.dump.gz ./restore.dump.gz

# 3. Restaurar dentro del contenedor de la BD
#    pg_restore con --clean --if-exists dropea objetos antes de crear
#    --no-owner / --no-privileges porque el dump no incluye owners
gunzip -c restore.dump.gz | docker exec -i bodegaje-db pg_restore \
    -U bodegaje -d bodegaje --clean --if-exists --no-owner --no-privileges

# 4. Verificar
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "SELECT count(*) FROM solicitudes_recarga;"

# 5. Levantar API y worker
docker compose start api worker
```

### Caso 2: disaster recovery en un equipo nuevo

```powershell
# 1. Levantar SOLO la BD vacia
docker compose up -d db

# 2. Esperar a que este healthy
docker ps --format "{{.Names}} {{.Status}}" | Select-String "bodegaje-db"

# 3. Restaurar el dump
gunzip -c /path/al/backup.dump.gz | docker exec -i bodegaje-db pg_restore \
    -U bodegaje -d bodegaje --no-owner --no-privileges

# 4. Levantar el resto
docker compose up -d
```

## Configuracion

Variables de entorno (definidas en `docker-compose.yml`):
- `POSTGRES_HOST=db`
- `POSTGRES_DB=bodegaje`
- `POSTGRES_USER=bodegaje`
- `PGPASSWORD=bodegaje` (en prod: rotar y usar Docker secrets)
- `BACKUP_RETENTION_DAYS=7`
- `BACKUP_DIR=/backups`

## Diseno

- **Sin cron del host**: portable, va con la pila.
- **supercronic** (no cron de alpine): binario estatico, sin daemon, lee crontab de archivo, log a stdout.
- **Healthcheck propio**: valida que el ultimo backup no es stale (>25h).
- **Volumen dedicado**: separado del de la BD para que un `docker volume rm postgres_data` no se lleve los backups.
- **Restore verificado en tests E2E**: ver `auditoria-fase5/test_backup_restore.py` (si no existe, correrlo la primera vez).

## Que NO hace (y como lo harias en prod)

- **No cifra los backups**. Para prod: cifrar con `gpg` post-pg_dump, o usar S3 con SSE-KMS.
- **No envia a storage remoto**. Para prod: agregar `aws s3 cp` despues del dump, o usar `pgbackrest`/`wal-g`.
- **No hace backups incrementales (WAL)`. Para PITR (point-in-time recovery): agregar `wal-g` o configurar `archive_mode=on` en Postgres.
- **No notifica si falla**. Para prod: agregar webhook a Slack/email cuando exit != 0.
