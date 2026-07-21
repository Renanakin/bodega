"""
SolicitudRepository: único punto de acceso a BD para solicitudes_recarga (Fase 3).

Reglas:
- R4: el repo es la única capa que toca SQL; el service NO escribe SQL directo.
- R7: queries parametrizadas (nunca string format / %).
- ADR-0001: en Postgres usar `SELECT ... FOR UPDATE`; en SQLite usar el
  RLock del engine (BEGIN IMMEDIATE) como análogo.
- ADR-0003: namespace unificado `pending/approved/in_transit/received/...`.

NOTA IMPORTANTE sobre el estado `partial`:
    El ADR-0003 define `received | partial` como estados terminales. La
    migracion 0006 ya crea el CHECK `estado IN (..., 'partially_received', ...)`.
    Mantenemos `partially_received` (snake_case del modelo) y exponemos
    `partial` en la API pública para alinear con el spec del usuario.
    El mapeo se hace en el servicio via `_ESTADO_API`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from app.db.models.solicitudes import (
    DetalleSolicitudRecarga,
    SolicitudEstado,
    SolicitudRecarga,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Estados del modelo (alineados con la migración 0006).
_ESTADOS_MODELO: frozenset[str] = frozenset(
    {"pending", "approved", "in_transit", "partially_received", "received", "rejected", "cancelled"}
)


def _validate_estado(estado: str) -> None:
    """Helper: rechaza valores fuera del namespace del modelo."""
    if estado not in _ESTADOS_MODELO:
        raise ValueError(f"Estado '{estado}' no permitido. Validos: {sorted(_ESTADOS_MODELO)}")


class SolicitudRepository:
    """Repositorio de solicitudes_recarga y detalle_solicitud_recarga.

    Encapsula todo el SQL del módulo. El service trabaja contra esta
    interface, no contra `AsyncSession` directamente.

    Thread/concurrency:
    - En Postgres, `get_by_id_with_lock` usa `with_for_update()` para
      lock pesimista. La transacción la maneja el caller.
    - En SQLite (tests), no hay FOR UPDATE real; el caller debe usar
      `Database.begin_immediate_transaction()` para writer-lock.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---------------------------------------------------------------- CREATE

    async def create_solicitud(
        self,
        *,
        codigo: str,
        id_bodega_origen: uuid.UUID,
        id_bodega_destino: uuid.UUID,
        prioridad: str | None = None,
        notas: str | None = None,
    ) -> SolicitudRecarga:
        """Inserta una solicitud en estado PENDING. No incluye lineas (usar add_linea)."""
        solicitud = SolicitudRecarga(
            id=uuid.uuid4(),
            codigo=codigo,
            id_bodega_origen=id_bodega_origen,
            id_bodega_destino=id_bodega_destino,
            estado=SolicitudEstado.PENDING,
            prioridad=prioridad,
            notas=notas,
        )
        self._session.add(solicitud)
        await self._session.flush()
        return solicitud

    async def add_linea(
        self,
        *,
        id_solicitud: uuid.UUID,
        id_producto: uuid.UUID,
        cantidad_solicitada: Decimal,
    ) -> DetalleSolicitudRecarga:
        """Inserta una linea de detalle (PK compuesta solicitud+producto)."""
        detalle = DetalleSolicitudRecarga(
            id_solicitud=id_solicitud,
            id_producto=id_producto,
            cantidad_solicitada=cantidad_solicitada,
        )
        self._session.add(detalle)
        await self._session.flush()
        return detalle

    # ------------------------------------------------------------------ READ

    async def get_by_id(self, solicitud_id: uuid.UUID) -> SolicitudRecarga | None:
        """Lee una solicitud SIN lock. Usar para GETs."""
        stmt = select(SolicitudRecarga).where(SolicitudRecarga.id == solicitud_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_lock(self, solicitud_id: uuid.UUID) -> SolicitudRecarga | None:
        """Lee una solicitud CON lock pesimista (Postgres: SELECT FOR UPDATE).

        En SQLite (tests) el lock lo da BEGIN IMMEDIATE del engine; el
        with_for_update() no tiene efecto, pero la fila queda dentro de
        la transaccion que el caller debe abrir.

        Raises:
            Exception: propaga errores de BD. El caller (service) es
                responsable de manejar el rollback.
        """
        stmt = select(SolicitudRecarga).where(SolicitudRecarga.id == solicitud_id).with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_details(self, solicitud_id: uuid.UUID) -> SolicitudRecarga | None:
        """Lee la solicitud. NO hace eager loading (modelo sin relationship).

        Las lineas y bodegas se cargan por separado via `list_detalles()` y
        `WarehouseRepository.get_by_id()`. El service es responsable de
        evitar N+1 cacheando por id.
        """
        return await self.get_by_id(solicitud_id)

    async def get_by_codigo(self, codigo: str) -> SolicitudRecarga | None:
        """Busca por codigo unico (ej: SOL-20260714-0001)."""
        stmt = select(SolicitudRecarga).where(SolicitudRecarga.codigo == codigo)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_detalles(self, solicitud_id: uuid.UUID) -> Sequence[DetalleSolicitudRecarga]:
        """Lista las lineas de detalle de una solicitud."""
        stmt = select(DetalleSolicitudRecarga).where(
            DetalleSolicitudRecarga.id_solicitud == solicitud_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self,
        *,
        estado: str | None = None,
        id_bodega_origen: uuid.UUID | None = None,
        id_bodega_destino: uuid.UUID | None = None,
        fecha_desde: datetime | None = None,
        fecha_hasta: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[SolicitudRecarga]:
        """Lista solicitudes con filtros. Orden: created_at DESC.

        NO hace eager loading de detalles (modelo sin relationship).
        El service hace una segunda query con `list_detalles()` por
        cada solicitud. Para N=50 con M=5 lineas = 51 queries; aceptable
        en UI. Si hace falta, agregar un endpoint dedicado y usar
        `selectinload` via una CTE cuando se migre a Postgres puro.
        """
        if estado is not None:
            _validate_estado(estado)
        conditions = []
        if estado is not None:
            conditions.append(SolicitudRecarga.estado == estado)
        if id_bodega_origen is not None:
            conditions.append(SolicitudRecarga.id_bodega_origen == id_bodega_origen)
        if id_bodega_destino is not None:
            conditions.append(SolicitudRecarga.id_bodega_destino == id_bodega_destino)
        if fecha_desde is not None:
            conditions.append(SolicitudRecarga.created_at >= fecha_desde)
        if fecha_hasta is not None:
            conditions.append(SolicitudRecarga.created_at <= fecha_hasta)

        stmt = (
            select(SolicitudRecarga)
            .order_by(SolicitudRecarga.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ---------------------------------------------------------------- UPDATE

    async def update_estado(
        self,
        solicitud_id: uuid.UUID,
        estado: str,
        **timestamps: datetime | None,
    ) -> None:
        """Actualiza el estado de una solicitud y opcionalmente timestamps.

        Args:
            solicitud_id: UUID de la solicitud (debe estar locked por caller).
            estado: nuevo estado (namespace modelo).
            **timestamps: pares `atributo=valor`, ej: approved_at=now().
        """
        _validate_estado(estado)
        solicitud = await self._session.get(SolicitudRecarga, solicitud_id)
        if solicitud is None:
            return
        solicitud.estado = SolicitudEstado(estado)
        for attr, value in timestamps.items():
            if value is not None and hasattr(solicitud, attr):
                setattr(solicitud, attr, value)
        await self._session.flush()

    async def update_linea_despacho(
        self,
        solicitud_id: uuid.UUID,
        producto_id: uuid.UUID,
        cantidad: Decimal,
    ) -> None:
        """Actualiza cantidad_despachada de una linea (incremento)."""
        stmt = select(DetalleSolicitudRecarga).where(
            DetalleSolicitudRecarga.id_solicitud == solicitud_id,
            DetalleSolicitudRecarga.id_producto == producto_id,
        )
        result = await self._session.execute(stmt)
        detalle = result.scalar_one_or_none()
        if detalle is None:
            return
        detalle.cantidad_despachada = detalle.cantidad_despachada + cantidad
        await self._session.flush()

    async def update_linea_recepcion(
        self,
        solicitud_id: uuid.UUID,
        producto_id: uuid.UUID,
        cantidad: Decimal,
        barcode: str | None = None,
    ) -> None:
        """Actualiza cantidad_recibida y opcionalmente barcode_validado."""
        stmt = select(DetalleSolicitudRecarga).where(
            DetalleSolicitudRecarga.id_solicitud == solicitud_id,
            DetalleSolicitudRecarga.id_producto == producto_id,
        )
        result = await self._session.execute(stmt)
        detalle = result.scalar_one_or_none()
        if detalle is None:
            return
        detalle.cantidad_recibida = detalle.cantidad_recibida + cantidad
        if barcode is not None:
            detalle.barcode_validado = barcode
        await self._session.flush()

    # --------------------------------------------------------- ESTADÍSTICAS

    async def count_by_estado(self) -> dict[str, int]:
        """Conteo de solicitudes agrupadas por estado (namespace modelo)."""
        stmt = select(SolicitudRecarga.estado, func.count(SolicitudRecarga.id)).group_by(
            SolicitudRecarga.estado
        )
        result = await self._session.execute(stmt)
        return dict(result.all())

    async def count_by_bodega_origen(self) -> dict[uuid.UUID, int]:
        """Conteo de solicitudes agrupadas por bodega origen."""
        stmt = select(SolicitudRecarga.id_bodega_origen, func.count(SolicitudRecarga.id)).group_by(
            SolicitudRecarga.id_bodega_origen
        )
        result = await self._session.execute(stmt)
        return dict(result.all())

    # -------------------------------------------------------------- UTIL

    async def generate_unique_codigo(self, prefix: str = "SOL") -> str:
        """Genera un codigo unico formato PREFIX-YYYYMMDD-NNNN.

        El sufijo numérico es el conteo total + 1. NO es estrictamente
        gapless (si una solicitud se borra el contador no retrocede), pero
        es suficiente para uso humano. Si la unicidad choca, retry con
        +1 en el sufijo hasta encontrar uno libre (max 10 intentos).
        """
        today = datetime.now(UTC).strftime("%Y%m%d")
        count_stmt = select(func.count(SolicitudRecarga.id))
        result = await self._session.execute(count_stmt)
        base = int(result.scalar() or 0) + 1
        for offset in range(10):
            candidate = f"{prefix}-{today}-{base + offset:04d}"
            existing = await self.get_by_codigo(candidate)
            if existing is None:
                return candidate
        # Fallback: sufijo aleatorio (casi imposible de chocar).
        return f"{prefix}-{today}-{uuid.uuid4().hex[:8].upper()}"


__all__ = ["SolicitudRepository"]
