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
    def __init__(self) -> None:
        super().__init__(
            code="invalid_transfer_quantity",
            message="Quantity is invalid for this transfer operation.",
            status_code=409,
        )


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_payload()})
