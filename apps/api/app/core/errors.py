from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    status_code: int
    extra: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.extra:
            payload["extra"] = self.extra
        return payload


class WarehouseNotFoundError(DomainError):
    def __init__(self, warehouse_id: str) -> None:
        super().__init__(
            code="warehouse_not_found",
            message=f"Warehouse '{warehouse_id}' was not found.",
            status_code=404,
        )


class ProductNotFoundError(DomainError):
    def __init__(self, product_id: str) -> None:
        super().__init__(
            code="product_not_found",
            message=f"Product '{product_id}' was not found.",
            status_code=404,
        )


class DuplicateWarehouseCodeError(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__(
            code="duplicate_warehouse_code",
            message=f"Warehouse code '{code}' already exists.",
            status_code=409,
        )


class DuplicateSkuError(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(
            code="duplicate_sku",
            message=f"Product SKU '{sku}' already exists.",
            status_code=409,
        )


class InsufficientStockError(DomainError):
    def __init__(self, product_id: str, warehouse_id: str) -> None:
        super().__init__(
            code="insufficient_stock",
            message=(
                f"Insufficient stock for product '{product_id}' "
                f"in warehouse '{warehouse_id}'."
            ),
            status_code=409,
        )


class InvalidTransferError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_transfer",
            message="Origin and destination warehouses must be different.",
            status_code=409,
        )


class TransferNotFoundError(DomainError):
    def __init__(self, transfer_id: str) -> None:
        super().__init__(
            code="transfer_not_found",
            message=f"Transfer '{transfer_id}' was not found.",
            status_code=404,
        )


class InvalidTransferStatusError(DomainError):
    def __init__(self, current_status: str, expected_status: str) -> None:
        super().__init__(
            code="invalid_transfer_status",
            message=(
                f"Transfer status '{current_status}' is invalid for this action. "
                f"Expected '{expected_status}'."
            ),
            status_code=409,
            extra={"current_status": current_status, "expected_status": expected_status},
        )


class AuthenticationError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="authentication_required",
            message="Authentication is required.",
            status_code=401,
        )


class InvalidCredentialsError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_credentials",
            message="Invalid username or password.",
            status_code=401,
        )


class AuthorizationError(DomainError):
    def __init__(self, role: str) -> None:
        super().__init__(
            code="insufficient_permissions",
            message=f"Role '{role}' does not have permission for this action.",
            status_code=403,
        )


class InvalidTransferQuantityError(DomainError):
    def __init__(self, message: str = "Quantity is invalid for this transfer operation.") -> None:
        super().__init__(
            code="invalid_transfer_quantity",
            message=message,
            status_code=409,
        )


class SolicitudNotFoundError(DomainError):
    def __init__(self, solicitud_id: str) -> None:
        super().__init__(
            code="solicitud_not_found",
            message=f"Solicitud '{solicitud_id}' was not found.",
            status_code=404,
        )


class SolicitudInvalidStateError(DomainError):
    """Transición de estado no permitida para la solicitud."""

    def __init__(self, current: str, expected: str | list[str]) -> None:
        expected_list = expected if isinstance(expected, list) else [expected]
        super().__init__(
            code="solicitud_invalid_state",
            message=(
                f"Solicitud en estado '{current}' no puede ejecutar la acción. "
                f"Esperado uno de: {expected_list}."
            ),
            status_code=409,
            extra={"current": current, "expected": expected_list},
        )


class BarcodeMismatchError(DomainError):
    """El barcode del lector no corresponde al producto esperado."""

    def __init__(self, producto_id: str, expected: str, received: str) -> None:
        super().__init__(
            code="barcode_mismatch",
            message=(
                f"Barcode '{received}' no corresponde al producto '{producto_id}' "
                f"(esperado '{expected}')."
            ),
            status_code=409,
            extra={
                "producto_id": producto_id,
                "expected": expected,
                "received": received,
            },
        )


class BarcodeFormatError(DomainError):
    """El barcode no tiene un formato valido o su checksum es invalido.

    Usado por ``app.modules.barcode.validator`` cuando el barcode leido
    no se puede normalizar (vacio / None / solo espacios) o su formato
    no matchea ningun patron conocido. La validacion de checksum de
    EAN-13/8 NO levanta esta excepcion: retorna ``(False, ...)`` desde
    ``validate()`` para que el caller decida si elevar mismatch.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            code="barcode_format_invalid",
            message=message,
            status_code=422,
        )


class ProductNotActiveError(DomainError):
    """El producto está inactivo; no puede participar en solicitudes."""

    def __init__(self, producto_id: str, sku: str | None = None) -> None:
        identifier = sku or producto_id
        super().__init__(
            code="product_not_active",
            message=f"Producto '{identifier}' está inactivo.",
            status_code=409,
        )


class InvalidSolicitudDirectionError(DomainError):
    """ADR-0002: origen debe ser auxiliar, destino principal."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="invalid_solicitud_direction",
            message=message,
            status_code=409,
        )


class SupervisorNotFoundError(DomainError):
    def __init__(self, supervisor_id: str) -> None:
        super().__init__(
            code="supervisor_not_found",
            message=f"Supervisor '{supervisor_id}' was not found.",
            status_code=404,
        )


class DuplicateSupervisorEmailError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(
            code="duplicate_supervisor_email",
            message=f"Supervisor email '{email}' already exists.",
            status_code=409,
        )


class OrdenCompraNotFoundError(DomainError):
    def __init__(self, oc_id: str) -> None:
        super().__init__(
            code="orden_compra_not_found",
            message=f"Orden de compra '{oc_id}' was not found.",
            status_code=404,
        )


class InvalidOrdenCompraStatusError(DomainError):
    def __init__(self, current: str, expected: str) -> None:
        super().__init__(
            code="invalid_orden_compra_status",
            message=f"OC status '{current}' is invalid for this action. Expected '{expected}'.",
            status_code=409,
        )


class InvalidApprovalTokenError(DomainError):
    def __init__(self, message: str = "Token de aprobacion invalido.") -> None:
        super().__init__(
            code="invalid_approval_token",
            message=message,
            status_code=401,
        )


class ExpiredApprovalTokenError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="approval_token_expired",
            message="El token de aprobacion ha expirado.",
            status_code=410,
        )


# --- Categorías (Fase 2) ---


class CategoryNotFoundError(DomainError):
    def __init__(self, category_id: str) -> None:
        super().__init__(
            code="category_not_found",
            message=f"Category '{category_id}' was not found.",
            status_code=404,
        )


class DuplicateCategoryNameError(DomainError):
    def __init__(self, name: str) -> None:
        super().__init__(
            code="duplicate_category_name",
            message=f"Category name '{name}' already exists.",
            status_code=409,
        )


class CategoryCircularReferenceError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="category_circular_reference",
            message="A category cannot be its own parent (direct or transitive).",
            status_code=409,
        )


# --- Ubicaciones (Fase 2) ---


class UbicacionNotFoundError(DomainError):
    def __init__(self, ubicacion_id: str) -> None:
        super().__init__(
            code="ubicacion_not_found",
            message=f"Ubicacion '{ubicacion_id}' was not found.",
            status_code=404,
        )


class DuplicateUbicacionError(DomainError):
    def __init__(self, detalle: str) -> None:
        super().__init__(
            code="duplicate_ubicacion",
            message=detalle,
            status_code=409,
        )


# --- Productos extendidos (Fase 2) ---


class DetalleNeumaticoNotFoundError(DomainError):
    def __init__(self, product_id: str) -> None:
        super().__init__(
            code="detalle_neumatico_not_found",
            message=f"Detalle neumatico for product '{product_id}' was not found.",
            status_code=404,
        )


class DuplicateDetalleNeumaticoError(DomainError):
    def __init__(self, product_id: str) -> None:
        super().__init__(
            code="duplicate_detalle_neumatico",
            message=f"Detalle neumatico for product '{product_id}' already exists.",
            status_code=409,
        )


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_payload()})


# --- Proveedores (Fase 8) ---


class ProveedorNotFoundError(DomainError):
    def __init__(self, proveedor_id: str) -> None:
        super().__init__(
            code="proveedor_not_found",
            message=f"Proveedor '{proveedor_id}' was not found.",
            status_code=404,
        )


class DuplicateProveedorNombreError(DomainError):
    def __init__(self, nombre: str) -> None:
        super().__init__(
            code="duplicate_proveedor_nombre",
            message=f"Proveedor nombre '{nombre}' already exists.",
            status_code=409,
        )


class DuplicateProveedorRutError(DomainError):
    def __init__(self, rut: str) -> None:
        super().__init__(
            code="duplicate_proveedor_rut",
            message=f"Proveedor RUT '{rut}' already exists.",
            status_code=409,
        )


# --- Notificaciones in-app (Fase 8) ---


class NotificationNotFoundError(DomainError):
    def __init__(self, notification_id: str) -> None:
        super().__init__(
            code="notification_not_found",
            message=f"Notification '{notification_id}' was not found.",
            status_code=404,
        )


# --- Inventario / parámetros (Fase 8) ---


class InvalidStockParameterError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="invalid_stock_parameter",
            message=message,
            status_code=422,
        )
