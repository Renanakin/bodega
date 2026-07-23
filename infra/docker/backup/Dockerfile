# backup/Dockerfile - Servicio de backup para Postgres.
#
# Imagen minima basada en postgres:17-alpine (ya trae pg_dump) + supercronic
# (cron binario single-binary) para programar la corrida diaria a las 03:00 UTC.
#
# Por que no usar el cron del host:
# - Portabilidad: si llevas la pila a otro equipo, los crons van con la pila.
# - Aislamiento: el script corre en un entorno controlado.
# - Logs: stdout del contenedor, accesibles via `docker logs bodegaje-backup`.
#
# Por que supercronic y no cron de alpine:
# - supercronic es un solo binario, sin daemon, sin PAM, sin /etc/crontab.
# - Lee crontab de archivo, log a stdout -> ideal para contenedores.
# - Reinicia automaticamente si falla una corrida (con timestamp).

FROM postgres:17-alpine

# supercronic: https://github.com/aptible/supercronic (binario estatico)
ARG SUPERCRONIC_VERSION=v0.2.33
RUN apk add --no-cache curl bash \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
       -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && apk del curl

# Copiar script de backup
COPY scripts/backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh

# Crontab: 03:00 UTC todos los dias
# Formato: min hora dia-mes mes dia-semana comando
COPY crontab /etc/crontab.backup

# Healthcheck: verifica que el backup del dia existe y no es stale.
# - interval=12h: corre 2 veces al dia (suficiente para detectar fallos
#   sin gastar recursos).
# - start_period=10m: da tiempo a que la primera corrida automatica
#   (a las 03:00 UTC) o una corrida manual cree un backup. Antes de eso
#   el contenedor queda en "starting", que es el estado esperado.
# - retries=2: tolera un fallo aislado antes de marcar unhealthy.
COPY healthcheck.sh /usr/local/bin/healthcheck.sh
RUN chmod +x /usr/local/bin/healthcheck.sh
HEALTHCHECK --interval=12h --timeout=5s --start-period=10m --retries=2 \
    CMD /usr/local/bin/healthcheck.sh

# Entrypoint: supercronic en foreground, log a stdout
# -prometheus : expone metricas (no lo necesitamos aca)
# -split-logs : un log line por corrida
ENTRYPOINT ["/usr/local/bin/supercronic", "-split-logs", "/etc/crontab.backup"]
