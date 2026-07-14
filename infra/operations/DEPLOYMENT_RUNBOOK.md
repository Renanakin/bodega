# Deployment Runbook

## Objetivo

Dejar una ruta clara para desplegar y recuperar `web` e `infra` sin tocar `db` ni `api`.

## Pre-checklist

- validar imagenes o artefactos actualizados
- verificar variables de entorno por ambiente
- confirmar que el proxy apunta a los servicios correctos
- asegurar respaldo vigente de base de datos por parte del responsable backend/db
- comunicar ventana de despliegue

## Local

```powershell
./infra/scripts/start-local.ps1
```

## Staging

```powershell
./infra/scripts/start-staging.ps1
```

## Production

```powershell
./infra/scripts/start-production.ps1
```

## Validaciones posteriores

- abrir `/`
- abrir `/api/v1/health`
- abrir `/docs`
- revisar logs de `nginx`
- revisar que frontend cargue rutas internas

## Rollback

1. detener stack actual
2. volver a la version previa de imagenes o codigo
3. levantar compose anterior
4. validar frontend, proxy y healthcheck

## Notas

- no exponer `db` ni `redis` en produccion
- documentar cada cambio de proxy o puertos
- si se agregan certificados TLS, hacerlo en el proxy frontal

