"""
Modelos SQLAlchemy del dominio (Fase 4: modelo completo).

Reglas aplicadas:
- R3: cada dominio tiene su archivo; ninguno vive en db/ suelto.
- R5: el nombre del archivo coincide con el módulo de dominio.

Importar este archivo desde alembic/env.py para que todos los modelos
sean visibles al autogenerate.
"""
from __future__ import annotations

# Catalogo
from app.db.models.categorias import Category

# Inventario
from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.notificaciones import Notificacion, NotificationType
from app.db.models.ordenes_compra import (
    DetalleOrdenCompra,
    EmailOutbox,
    OrdenCompra,
    OrdenCompraEstado,
)
from app.db.models.product_extension import DetalleNeumatico
from app.db.models.products import Product

# Proveedores
from app.db.models.proveedores import Proveedor

# Solicitudes
from app.db.models.solicitudes import (
    DetalleSolicitudRecarga,
    SolicitudEstado,
    SolicitudRecarga,
)
from app.db.models.stock_real import InventarioStockReal

# Compras
from app.db.models.supervisores import Supervisor
from app.db.models.transfers import Transfer

# Operacion
from app.db.models.ubicaciones import UbicacionEstanteria
from app.db.models.users import AuditLog, User, UserSession

# Core
from app.db.models.warehouses import Warehouse

__all__ = [
    # Core
    "Warehouse",
    "Product",
    "User",
    "UserSession",
    "AuditLog",
    "Transfer",
    # Inventario
    "StockLevel",
    "InventoryMovement",
    "MovementType",
    # Catalogo
    "Category",
    "DetalleNeumatico",
    # Operacion
    "UbicacionEstanteria",
    "InventarioStockReal",
    # Solicitudes
    "SolicitudRecarga",
    "DetalleSolicitudRecarga",
    "SolicitudEstado",
    # Compras
    "Supervisor",
    "OrdenCompra",
    "DetalleOrdenCompra",
    "OrdenCompraEstado",
    "EmailOutbox",
    # Proveedores
    "Proveedor",
    # Notificaciones in-app (Fase 8)
    "Notificacion",
    "NotificationType",
]
