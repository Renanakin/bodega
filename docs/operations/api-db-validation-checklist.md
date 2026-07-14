# Checklist de validacion local para API y DB

**Fecha:** 17-03-2026  
**Estado:** validacion actual disponible

## 1. Alcance

Este documento concentra la validacion manual del trabajo en:

- `apps/api`
- `db`

No cubre `apps/web` ni `infra` en este ciclo.

## 2. Validacion disponible hoy

### Backend actual

1. Crear entorno virtual en `apps/api`.
2. Instalar dependencias desde `requirements.txt`.
3. Levantar FastAPI localmente.
4. Verificar endpoints base:
   - `/docs`
   - `/redoc`
   - `/api/v1/health`
   - `/api/v1/warehouses`
   - `/api/v1/products`
   - `/api/v1/inventory/stock`
   - `/api/v1/inventory/movements`
   - `/api/v1/inventory/summary`

### Comandos sugeridos en PowerShell

```powershell
Set-Location apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

En otra consola:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

## 3. Validacion actual del MVP

> La API hoy usa persistencia en memoria. La migracion y la seed SQL ya existen como artefactos de BD, pero aun no estan conectados al backend.

### API

- crear una bodega
- listar bodegas
- crear un producto
- listar productos
- registrar una entrada de inventario
- registrar una salida valida
- rechazar una salida sin saldo suficiente
- consultar stock actualizado
- consultar historial de movimientos

### DB

- confirmar unicidad de `warehouses.code`
- confirmar unicidad de `products.sku`
- confirmar unicidad de `(warehouse_id, product_id)` en `stock_levels`
- confirmar llaves foraneas entre stock, movimientos, productos y bodegas
- confirmar que el movimiento genera actualizacion consistente del stock

## 4. Evidencia minima esperada

- salida correcta de `/api/v1/health`
- ejemplos de respuesta para bodegas, productos y stock
- evidencia de error controlado para stock insuficiente
- archivos SQL de migracion y seed presentes y revisables
- notas de verificacion en el resumen final del trabajo
