"""
Schemas Pydantic para solicitudes de recarga (Fase 3, ADR-0003).

Reglas:
- R4: schemas solo validan shape; la lógica vive en service.
- R5: schemas descriptivos sin sufijos v2/new/old.
- ADR-0003: namespace unificado de estados.
- ADR-0002: origen ∈ {auxiliar, mecanico_box}, destino = principal.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
# Namespace unificado de estados (alineado con la migración 0006).
# Aceptamos `partially_received` (snake_case del modelo) y `partial`
# (alias del spec del usuario). El servicio siempre emite el valor
# canónico del modelo (`partially_received`).
EstadoSolicitud = Literal[
    "pending",
    "approved",
    "in_transit",
    "partially_received",
    "received",
    "partial",
    "rejected",
    "cancelled",
]
Prioridad = Literal["normal", "alta", "urgente"]


# ============================================================ LINEAS CREATE


class SolicitudLineaCreate(BaseModel):
    """Una linea de producto dentro de la solicitud a crear."""

    producto_id: UUID
    cantidad_solicitada: Quantity
    notas: str | None = Field(default=None, max_length=500)


# ============================================================== SOLICITUD CREATE


class SolicitudCreate(BaseModel):
    """Payload para crear una solicitud de recarga (N productos)."""

    bodega_origen_id: UUID
    bodega_destino_id: UUID  # debe ser Principal (validado en service)
    prioridad: Prioridad = Field(default="normal")
    notas: str | None = Field(default=None, max_length=500)
    lineas: list[SolicitudLineaCreate] = Field(min_length=1, max_length=200)

    @field_validator("lineas")
    @classmethod
    def validate_unique_products(
        cls, value: list[SolicitudLineaCreate]
    ) -> list[SolicitudLineaCreate]:
        """No se permiten productos duplicados en la misma solicitud."""
        ids = [line.producto_id for line in value]
        if len(ids) != len(set(ids)):
            raise ValueError("No se permiten productos duplicados en la misma solicitud")
        return value


# ============================================================ LINEAS DESPACHO / RECEPCION


class SolicitudLineaDespacho(BaseModel):
    """Una linea en el payload de despacho.

    `cantidad_despachada` puede ser menor que `cantidad_solicitada`
    (despacho parcial) pero nunca 0 ni mayor que la cantidad solicitada.
    """

    producto_id: UUID
    cantidad_despachada: Quantity
    barcode: str | None = Field(default=None, max_length=100)
    notas: str | None = Field(default=None, max_length=500)


class SolicitudLineaRecepcion(BaseModel):
    """Una linea en el payload de recepcion.

    `barcode` se valida contra `products.codigo_barras` (BarcodeMismatch
    si no coincide). `incidencia` es texto libre que se persiste en
    la linea y se usa en notas del movimiento.
    """

    producto_id: UUID
    cantidad_recibida: Quantity
    barcode: str | None = Field(default=None, max_length=100)
    incidencia: str | None = Field(default=None, max_length=500)


# ============================================================ SCHEMAS DE ACCION


class SolicitudAprobacion(BaseModel):
    """Payload opcional para aprobar una solicitud."""

    notas: str | None = Field(default=None, max_length=500)


class SolicitudDespacho(BaseModel):
    """Payload de despacho: una o mas lineas con cantidad + barcode opcional."""

    lineas: list[SolicitudLineaDespacho] = Field(min_length=1)
    notas: str | None = Field(default=None, max_length=500)


class SolicitudRecepcion(BaseModel):
    """Payload de recepcion: una o mas lineas con cantidad + barcode + incidencia."""

    lineas: list[SolicitudLineaRecepcion] = Field(min_length=1)
    notas: str | None = Field(default=None, max_length=500)


class SolicitudRechazo(BaseModel):
    """Payload para rechazar una solicitud."""

    motivo: str = Field(min_length=5, max_length=500)


class SolicitudCancelacion(BaseModel):
    """Payload para cancelar una solicitud (solo si PENDING)."""

    motivo: str | None = Field(default=None, max_length=500)


# --- Aliases de compatibilidad (router legacy los usa) ---

# Antes la línea de recepción tenía `id_producto` y `cantidad_recibida`; ahora
# lo mismo en `SolicitudLineaRecepcion`. Mantenemos el alias para no romper
# routers externos.
SolicitudReceiveLinea = SolicitudLineaRecepcion


class SolicitudReceive(BaseModel):
    """Compat: payload de recepcion (alias de SolicitudRecepcion).

    Mantenido para no romper el router legacy; en nuevos handlers usar
    `SolicitudRecepcion` directamente.
    """

    lineas: list[SolicitudLineaRecepcion] = Field(min_length=1)
    notas: str | None = Field(default=None, max_length=500)


SolicitudReject = SolicitudRechazo
SolicitudDetalleCreate = SolicitudLineaCreate


class SolicitudDetalleResponse(BaseModel):
    """Compat: alias legacy del nuevo SolicitudLineaResponse."""

    id_solicitud: UUID
    id_producto: UUID
    product_sku: str | None = None
    product_name: str | None = None
    cantidad_solicitada: Decimal
    cantidad_despachada: Decimal
    cantidad_recibida: Decimal
    barcode_validado: str | None = None
    notas: str | None = None


# ============================================================ SCHEMAS DE RESPUESTA


class SolicitudLineaResponse(BaseModel):
    """Linea de detalle en la respuesta."""

    id: UUID  # (id_solicitud, id_producto) en realidad
    producto_id: UUID
    producto_sku: str
    producto_nombre: str
    cantidad_solicitada: Decimal
    cantidad_despachada: Decimal
    cantidad_recibida: Decimal
    barcode_validado: str | None
    notas: str | None

    @classmethod
    def from_detalle(
        cls,
        detalle: DetalleSolicitudRecarga,  # type: ignore[name-defined]  # noqa: F821
        producto: Product | None = None,  # type: ignore[name-defined]  # noqa: F821
    ) -> SolicitudLineaResponse:
        sku = getattr(producto, "sku", None) or ""
        nombre = getattr(producto, "name", None) or ""
        return cls(
            id=detalle.id_producto,
            producto_id=detalle.id_producto,
            producto_sku=sku,
            producto_nombre=nombre,
            cantidad_solicitada=detalle.cantidad_solicitada,
            cantidad_despachada=detalle.cantidad_despachada,
            cantidad_recibida=detalle.cantidad_recibida,
            barcode_validado=detalle.barcode_validado,
            notas=detalle.notas,
        )


class SolicitudResponse(BaseModel):
    """Solicitud de recarga (vista API)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    codigo: str
    bodega_origen_id: UUID
    bodega_origen_codigo: str
    bodega_origen_nombre: str
    bodega_origen_tipo: str
    bodega_destino_id: UUID
    bodega_destino_codigo: str
    bodega_destino_nombre: str
    estado: EstadoSolicitud
    prioridad: str
    notas: str | None
    motivo_rechazo: str | None
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None
    lineas: list[SolicitudLineaResponse] = Field(default_factory=list)
    total_productos: int
    total_unidades: Decimal


# ============================================================ DISTRIBUCION MULTIBODEGA (spec §4.1)


class DistribucionBodegaItem(BaseModel):
    """Una fila de la grilla multibodega."""

    bodega_id: UUID
    bodega_codigo: str
    bodega_nombre: str
    bodega_tipo: str
    total_quantity: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    estado: Literal["normal", "alerta", "critico"]
    ubicacion_principal: str | None  # formato "P-XX/E-YY" (placeholder Fase 3+)


class DistribucionMultibodegaResponse(BaseModel):
    """Distribucion de un producto en todas las bodegas (spec §4.1)."""

    producto_id: UUID
    sku: str
    nombre: str
    total_global: Decimal
    bodegas: list[DistribucionBodegaItem] = Field(default_factory=list)


# ============================================================ REPLENISHMENT (Fase 4)


class ReplenishmentReportResponse(BaseModel):
    """Reporte de una corrida de ``ReplenishmentEvaluator``.

    Retornado por ``POST /solicitudes/auto-generar``. Refleja la
    estructura de ``ReplenishmentReport`` (dataclass interno) + un
    timestamp para trazabilidad.
    """

    bodegas_evaluadas: int
    skus_bajo_minimo: int
    solicitudes_creadas: int
    solicitudes_omitidas_pendientes: int
    errores: list[str] = Field(default_factory=list)
    dry_run: bool = False
    timestamp: datetime


class StockBajoMinimoResponse(BaseModel):
    """Una fila del catalogo de productos bajo minimo de stock.

    Consumido por el frontend (ReplenishmentPage) para mostrar al
    bodeguero que SKU deberia reponer y cuanto. La sugerencia sigue
    la misma regla que ``ReplenishmentEvaluator``:
    - Si ``stock_maximo`` esta definido: ``stock_maximo - stock_actual``.
    - Si no: ``stock_minimo * 2 - stock_actual``.
    """

    bodega_id: UUID
    bodega_codigo: str
    bodega_nombre: str
    producto_id: UUID
    producto_sku: str
    producto_nombre: str
    stock_actual: Decimal
    stock_minimo: Decimal
    stock_maximo: Decimal | None
    cantidad_sugerida: Decimal
    prioridad: Literal["normal", "alta", "urgente"]


# ============================================================ TRANSFERS LEGACY (derivada)


class TransferDerivedLinea(BaseModel):
    """Linea de la vista derivada (compat transfers legacy)."""

    producto_id: UUID
    producto_sku: str
    producto_nombre: str
    cantidad_solicitada: Decimal
    cantidad_despachada: Decimal
    cantidad_recibida: Decimal


class TransferDerivedResponse(BaseModel):
    """Vista derivada de una solicitud expuesta como Transfer (legacy).

    Permite a clientes que aún consumen `/api/v1/transfers/{id}` seguir
    funcionando sin cambios. Disponible 6 meses (ver ADR-0003).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    from_warehouse_id: UUID
    from_warehouse_code: str
    to_warehouse_id: UUID
    to_warehouse_code: str
    product_id: UUID  # primer producto de la solicitud
    product_sku: str
    product_name: str
    quantity: Decimal
    received_quantity: Decimal
    status: str  # mapping del estado de solicitud a estado de transfer
    priority: str | None
    notes: str | None
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None
    lineas: list[TransferDerivedLinea] = Field(default_factory=list)
    source: Literal["solicitud_recarga"] = "solicitud_recarga"
