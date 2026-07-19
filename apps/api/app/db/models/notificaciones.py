"""Modelo SQLAlchemy para notificaciones in-app (Fase 8).

Complementa al ``email_outbox`` (Fase 7) que sigue siendo el transporte
async de emails. Esta tabla es el "inbox" del usuario dentro de la app web:
cada vez que el sistema detecta un evento relevante para un usuario
(ej. una solicitud que requiere su atencion), se inserta una fila aqui.

Tipos soportados (campo ``tipo``):
    - ``solicitud.created``         (Operador de origen)
    - ``solicitud.approved``        (Operador de origen)
    - ``solicitud.dispatched``      (Operador de destino)
    - ``solicitud.received``        (Operador de origen)
    - ``orden_compra.enviada``      (Supervisor)
    - ``orden_compra.aprobada``     (Bodeguero central)
    - ``stock.bajo_minimo``         (Bodeguero central)

El campo ``payload`` (JSON serializado) lleva contexto extra: id de la
solicitud, id de la OC, etc. La UI lo usa para armar el link directo al
detalle (e.g. ``/solicitudes/{id}``).
"""
import enum
import uuid

from app.db.base import GUID, Base, created_at_column
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class NotificationType(str, enum.Enum):
    """Tipos de notificacion que el sistema puede emitir."""

    SOLICITUD_CREATED = "solicitud.created"
    SOLICITUD_APPROVED = "solicitud.approved"
    SOLICITUD_DISPATCHED = "solicitud.dispatched"
    SOLICITUD_RECEIVED = "solicitud.received"
    SOLICITUD_REJECTED = "solicitud.rejected"
    SOLICITUD_CANCELLED = "solicitud.cancelled"
    ORDEN_COMPRA_ENVIADA = "orden_compra.enviada"
    ORDEN_COMPRA_APROBADA = "orden_compra.aprobada"
    ORDEN_COMPRA_RECHAZADA = "orden_compra.rechazada"
    ORDEN_COMPRA_RECIBIDA = "orden_compra.recibida"
    STOCK_BAJO_MINIMO = "stock.bajo_minimo"


class Notificacion(Base):
    """Notificacion in-app para un usuario especifico."""

    __tablename__ = "notificaciones"
    __table_args__ = (
        CheckConstraint("length(tipo) > 0", name="tipo_not_blank"),
        CheckConstraint("length(titulo) > 0", name="titulo_not_blank"),
        Index("ix_notificaciones_user_leida_created", "user_id", "leida", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensaje: Mapped[str] = mapped_column(String(1000), nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=True)
    leida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at = created_at_column()
    read_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
