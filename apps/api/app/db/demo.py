from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.db.session import create_database, utcnow
from app.modules.auth.security import hash_password
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import InventoryMovementCreate, MovementType
from app.modules.inventory.service import InventoryService
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate
from app.modules.products.service import ProductService
from app.modules.transfers.repository import TransferRepository
from app.modules.transfers.schemas import TransferCreate, TransferReceive
from app.modules.transfers.service import TransferService
from app.modules.warehouses.repository import WarehouseRepository
from app.modules.warehouses.schemas import WarehouseCreate
from app.modules.warehouses.service import WarehouseService


def reset_demo_database(db_path: str | Path | None = None) -> Path:
    resolved_path = Path(db_path or settings.resolved_database_path)
    if resolved_path.exists():
        resolved_path.unlink()

    database = create_database(resolved_path)
    warehouse_repository = WarehouseRepository(database)
    product_repository = ProductRepository(database)
    inventory_repository = InventoryRepository(database)
    transfer_repository = TransferRepository(database)

    warehouse_service = WarehouseService(warehouse_repository)
    product_service = ProductService(product_repository)
    inventory_service = InventoryService(
        inventory_repository=inventory_repository,
        warehouse_repository=warehouse_repository,
        product_repository=product_repository,
    )
    transfer_service = TransferService(
        transfer_repository=transfer_repository,
        inventory_repository=inventory_repository,
        warehouse_repository=warehouse_repository,
        product_repository=product_repository,
    )

    now = utcnow()
    for username, full_name, role, password in [
        ("admin", "Administrador Demo", "admin", "demo123"),
        ("supervisor", "Supervisor Demo", "supervisor", "demo123"),
        ("origen", "Operador Origen Demo", "origin_operator", "demo123"),
        ("destino", "Operador Destino Demo", "destination_operator", "demo123"),
    ]:
        database.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                username,
                full_name,
                role,
                hash_password(password),
                1,
                now.isoformat(),
            ),
        )

    central = warehouse_service.create_warehouse(
        WarehouseCreate(code="CENTRAL", name="Bodega Central", warehouse_type="central")
    )
    north = warehouse_service.create_warehouse(
        WarehouseCreate(code="NORTE", name="Sucursal Norte", warehouse_type="sucursal")
    )
    south = warehouse_service.create_warehouse(
        WarehouseCreate(code="SUR", name="Sucursal Sur", warehouse_type="sucursal")
    )

    aceite = product_service.create_product(
        ProductCreate(sku="ACE-001", name="Aceite Hidraulico 20L", unit="unidad")
    )
    filtro = product_service.create_product(
        ProductCreate(sku="FIL-004", name="Filtro Industrial 4P", unit="unidad")
    )
    kit = product_service.create_product(
        ProductCreate(sku="KIT-010", name="Kit Mantenimiento M3", unit="kit")
    )

    for warehouse_id, product_id, movement_type, quantity, reference_id, notes in [
        (central.id, aceite.id, MovementType.IN, 72, "seed-001", "Carga inicial"),
        (central.id, filtro.id, MovementType.IN, 24, "seed-002", "Carga inicial"),
        (central.id, kit.id, MovementType.IN, 18, "seed-003", "Carga inicial"),
        (south.id, filtro.id, MovementType.IN, 8, "seed-004", "Stock base sur"),
    ]:
        inventory_service.register_movement(
            InventoryMovementCreate(
                warehouse_id=warehouse_id,
                product_id=product_id,
                movement_type=movement_type,
                quantity=quantity,
                reference_type="seed",
                reference_id=reference_id,
                notes=notes,
            )
        )

    database.execute(
        "UPDATE stock_levels SET min_quantity = ? WHERE warehouse_id = ? AND product_id = ?",
        ("12", str(south.id), str(filtro.id)),
    )
    database.execute(
        "UPDATE stock_levels SET min_quantity = ? WHERE warehouse_id = ? AND product_id = ?",
        ("10", str(central.id), str(kit.id)),
    )

    transfer_service.create_transfer(
        TransferCreate(
            from_warehouse_id=central.id,
            to_warehouse_id=north.id,
            product_id=filtro.id,
            quantity=4,
            priority="Alta",
            notes="Transferencia demo solicitada",
        )
    )
    approved = transfer_service.create_transfer(
        TransferCreate(
            from_warehouse_id=central.id,
            to_warehouse_id=south.id,
            product_id=aceite.id,
            quantity=6,
            priority="Media",
            notes="Transferencia demo aprobada",
        )
    )
    transfer_service.approve_transfer(approved.id)

    dispatched = transfer_service.create_transfer(
        TransferCreate(
            from_warehouse_id=central.id,
            to_warehouse_id=north.id,
            product_id=kit.id,
            quantity=3,
            priority="Alta",
            notes="Transferencia demo despachada",
        )
    )
    transfer_service.approve_transfer(dispatched.id)
    transfer_service.dispatch_transfer(dispatched.id, None)

    received = transfer_service.create_transfer(
        TransferCreate(
            from_warehouse_id=central.id,
            to_warehouse_id=north.id,
            product_id=filtro.id,
            quantity=2,
            priority="Baja",
            notes="Transferencia demo recibida",
        )
    )
    transfer_service.approve_transfer(received.id)
    transfer_service.dispatch_transfer(received.id, None)
    transfer_service.receive_transfer(
        received.id,
        TransferReceive(quantity=2, notes="Recepcion completa demo"),
    )

    database.close()
    return resolved_path


if __name__ == "__main__":
    path = reset_demo_database()
    print(f"Demo database reset at: {path}")
