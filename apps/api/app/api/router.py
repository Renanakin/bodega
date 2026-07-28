"""
Router principal de la API v1.

Regla R3: este archivo solo ensambla routers; no define rutas inline.
Regla R5: orden de inclusion sigue el flujo: health -> auth -> recursos.
"""

from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.categories.router import router as categories_router
from app.modules.health.router import router as health_router
from app.modules.inventory.router import router as inventory_router
from app.modules.notificaciones.router import router as notificaciones_router
from app.modules.notifications.router import router as notifications_router
from app.modules.ordenes_compra.public_router import router as ordenes_public_router
from app.modules.ordenes_compra.router import router as ordenes_router
from app.modules.product_extension.router import router as product_extension_router
from app.modules.products.router import router as products_router
from app.modules.proveedores.router import router as proveedores_router
from app.modules.receipts.router import router as receipts_router
from app.modules.reports.router import router as reports_router
from app.modules.solicitudes.router import router as solicitudes_router
from app.modules.stock_real.router import router as stock_real_router
from app.modules.supervisores.router import router as supervisores_router
from app.modules.transfers.router import router as transfers_router
from app.modules.ubicaciones.router import router as ubicaciones_router
from app.modules.warehouses.router import router as warehouses_router
from fastapi import APIRouter

# BUG 13 (fix 2026-07-23): redirect_slashes=False.
# Ver apps/api/app/modules/ordenes_compra/router.py:38 para contexto.
# Es un safety net global: cuando un cliente olvida el trailing slash,
# Starlette responde 307 (redirect) que el cliente HTTP puede o no
# seguir correctamente, y el resultado es ambiguo. Con
# redirect_slashes=False, el 404 es limpio y el desarrollador sabe
# inmediatamente que la URL es incorrecta.
api_router = APIRouter(redirect_slashes=False)
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(audit_router, prefix="/audit", tags=["audit"])
api_router.include_router(warehouses_router, prefix="/warehouses", tags=["warehouses"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
# Sub-recurso de products (neumaticos). Comparte prefix con products_router;
# FastAPI los matchea por path pattern, no por prefijo.
api_router.include_router(product_extension_router, prefix="/products", tags=["products"])
api_router.include_router(categories_router, prefix="/categories", tags=["categories"])
# Ubicaciones tiene paths bajo /bodegas/.../ubicaciones y /ubicaciones/{id};
# se monta sin prefix para no romper la ruta raíz de bodegas.
api_router.include_router(ubicaciones_router, tags=["ubicaciones"])
api_router.include_router(stock_real_router, prefix="/inventario/real", tags=["stock_real"])
api_router.include_router(inventory_router, prefix="/inventory", tags=["inventory"])
api_router.include_router(solicitudes_router, prefix="/solicitudes", tags=["solicitudes"])
api_router.include_router(supervisores_router, prefix="/supervisores", tags=["supervisores"])
api_router.include_router(proveedores_router, prefix="/proveedores", tags=["proveedores"])
# Recepciones (FIX FASE POST-E2E) — modulo documentado en manual seccion 8.
api_router.include_router(receipts_router, prefix="/receipts", tags=["receipts"])
api_router.include_router(ordenes_router, prefix="/ordenes-compra", tags=["ordenes_compra"])
# Public router (sin auth, rate limited) - ADR-0005
# Path completo: /api/v1/public/ordenes-compra/{aprobar,rechazar}/{token}
api_router.include_router(ordenes_public_router, tags=["ordenes_compra_public"])
# Notificaciones SMTP outbox (legacy, Fase 7) — prefijo singular.
api_router.include_router(notifications_router, prefix="/notificaciones", tags=["notifications"])
# Notificaciones in-app (Fase 8) — mismo prefijo, paths distintos.
# Las rutas del modulo (/, /{id}/marcar-leida, /no-leidas/count, etc.) NO
# colisionan con /outbox del modulo legacy porque FastAPI matchea por path.
api_router.include_router(notificaciones_router, prefix="/notificaciones", tags=["notificaciones"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(transfers_router, prefix="/transfers", tags=["transfers"])
