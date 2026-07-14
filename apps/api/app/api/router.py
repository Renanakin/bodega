from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.inventory.router import router as inventory_router
from app.modules.products.router import router as products_router
from app.modules.transfers.router import router as transfers_router
from app.modules.warehouses.router import router as warehouses_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(audit_router, prefix="/audit", tags=["audit"])
api_router.include_router(warehouses_router, prefix="/warehouses", tags=["warehouses"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(inventory_router, prefix="/inventory", tags=["inventory"])
api_router.include_router(transfers_router, prefix="/transfers", tags=["transfers"])
