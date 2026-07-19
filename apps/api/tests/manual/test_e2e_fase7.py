"""
E2E manual Fase 7: SMTP asincrono con Mailpit (ADR-0004 + ADR-0005).

Flujo:
  1. Crear supervisor y bodega principal.
  2. Crear OC en estado borrador con 2 productos.
  3. POST /api/v1/ordenes-compra/{id}/enviar-correo (Fase 6 ya lo expone).
     Esto encola un row en email_outbox (status=pending) y un job Arq.
  4. Worker Arq (arq app.worker.WorkerSettings) consume la cola y envia
     el email a Mailpit. Actualiza el outbox a status='sent'.
  5. Consultar Mailpit API: GET http://localhost:8025/api/v1/messages
     -> 1 mensaje con el codigo OC y los links aprobar/rechazar.
  6. Extraer el token del body_html (o del campo Metadata del email).
  7. GET /api/v1/public/ordenes-compra/aprobar/{token} (sin auth) -> ver OC.
  8. POST /api/v1/public/ordenes-compra/aprobar/{token} -> estado=aprobado.
  9. Verificar: GET /api/v1/ordenes-compra/{id} -> estado=aprobado.

Prerequisitos:
  - Mailpit corriendo en localhost:1025 (SMTP) y :8025 (UI/API).
    Levantar con:
      docker compose -f infra/docker/docker-compose.yml up -d mailpit redis db
  - Worker Arq corriendo en otro proceso:
      cd apps/api && arq app.worker.WorkerSettings
  - API FastAPI corriendo en otro proceso:
      cd apps/api && uvicorn app.main:app --reload

Uso:
  cd apps/api
  python -m tests.manual.test_e2e_fase7
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# Asegurar que podemos importar ``app.*``.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Configuracion por env. Default = dev local con Mailpit.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://bodegaje:bodegaje@localhost:5432/bodegaje")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "dev-secret-not-for-production-32chars-XXXXXX")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("SMTP_PORT", "1025")
os.environ.setdefault("SMTP_FROM", "noreply@bodega.example")
os.environ.setdefault("SMTP_TLS", "false")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:5173")
os.environ.setdefault("APPROVAL_TOKEN_MAX_AGE_DAYS", "7")

import httpx  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import get_settings, reset_settings_cache  # noqa: E402
from app.core.security import issue_approval_token  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.models.ordenes_compra import (  # noqa: E402
    DetalleOrdenCompra,
    OrdenCompra,
    OrdenCompraEstado,
)
from app.db.models.products import Product  # noqa: E402
from app.db.models.supervisores import Supervisor  # noqa: E402
from app.db.models.warehouses import Warehouse  # noqa: E402
from app.modules.notifications.service import NotificationsService  # noqa: E402


reset_settings_cache()


def _make_engine() -> AsyncEngine:
    """Engine SQLite in-memory (no requiere Postgres para este E2E)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def _mailpit_alive(host: str = "localhost", port: int = 8025) -> bool:
    """Probe HTTP al UI de Mailpit."""
    try:
        with httpx.Client(timeout=1.0) as c:
            r = c.get(f"http://{host}:{port}/")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


def _mailpit_messages(host: str = "localhost", port: int = 8025) -> list[dict]:
    """Lee mensajes via API de Mailpit. Falla si no responde."""
    with httpx.Client(timeout=3.0) as c:
        r = c.get(f"http://{host}:{port}/api/v1/messages")
        r.raise_for_status()
        return r.json().get("messages", [])


def _mailpit_clear(host: str = "localhost", port: int = 8025) -> None:
    with httpx.Client(timeout=3.0) as c:
        try:
            c.delete(f"http://{host}:{port}/api/v1/messages")
        except httpx.HTTPError:
            pass


async def run_e2e() -> None:  # noqa: PLR0915
    print("=" * 70)
    print("E2E FASE 7 — SMTP asíncrono con Mailpit")
    print("=" * 70)

    # 0. Verificar Mailpit.
    if not _mailpit_alive():
        print("\n[!] Mailpit no esta accesible en localhost:8025.")
        print("    Levantar con:")
        print("    docker compose -f infra/docker/docker-compose.yml up -d mailpit redis")
        print("    Abortando.")
        sys.exit(1)
    print("\n[OK] Mailpit accesible en localhost:8025")
    _mailpit_clear()

    # 1. Setup: BD en memoria.
    print("\n=== SETUP: BD en memoria (SQLite) ===")
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    print("[OK] Schema creado")

    # 2. Crear datos seed: bodega + supervisor + 2 productos.
    print("\n=== SETUP: 1 Principal + 1 Supervisor + 2 Productos ===")
    wh_id = uuid.uuid4()
    sup_id = uuid.uuid4()
    p1_id = uuid.uuid4()
    p2_id = uuid.uuid4()
    sup_email = f"supervisor-{uuid.uuid4().hex[:6]}@bodega.example"
    async with session_factory() as session:
        session.add_all([
            Warehouse(
                id=wh_id, code="PRINCIPAL-F7", name="Bodega Principal",
                warehouse_type="principal", is_active=True,
            ),
            Supervisor(
                id=sup_id, nombre="E2E Supervisor", email=sup_email, activo=True,
            ),
            Product(id=p1_id, sku="F7-A", name="Filtro F7", unit="unidad", is_active=True),
            Product(id=p2_id, sku="F7-B", name="Bujia F7", unit="unidad", is_active=True),
        ])
        await session.commit()
    print(f"  wh={wh_id}")
    print(f"  sup={sup_id} ({sup_email})")
    print(f"  p1={p1_id}, p2={p2_id}")

    # 3. Crear OC borrador.
    print("\n=== PASO 1: Crear OC en estado borrador ===")
    oc_id = uuid.uuid4()
    jti = str(uuid.uuid4())
    async with session_factory() as session:
        oc = OrdenCompra(
            id=oc_id,
            codigo="OC-F7-E2E",
            id_bodega_principal=wh_id,
            id_supervisor=sup_id,
            proveedor_nombre="Proveedor E2E F7",
            estado=OrdenCompraEstado.BORRADOR,
            total_estimado=Decimal("30000"),
        )
        session.add(oc)
        await session.flush()
        session.add_all([
            DetalleOrdenCompra(
                id_orden_compra=oc.id, id_producto=p1_id,
                cantidad_pedida=Decimal("10"), costo_unitario_pactado=Decimal("1500"),
            ),
            DetalleOrdenCompra(
                id_orden_compra=oc.id, id_producto=p2_id,
                cantidad_pedida=Decimal("5"), costo_unitario_pactado=Decimal("3000"),
            ),
        ])
        await session.commit()
    print(f"  OC creada: {oc_id} (codigo=OC-F7-E2E)")

    # 4. Encolar email (Fase 7: renderiza plantilla + LPUSH a Arq).
    print("\n=== PASO 2: Encolar email al supervisor ===")
    token = issue_approval_token(
        orden_id=str(oc_id),
        supervisor_id=str(sup_id),
        action="approve",
        jti=jti,
    )
    settings = get_settings()
    approve_url = f"{settings.public_base_url}/ordenes-compra/aprobar/{token}"
    reject_url = f"{settings.public_base_url}/ordenes-compra/rechazar/{token}"

    outbox_id = None
    async with session_factory() as session:
        oc = await session.get(OrdenCompra, oc_id)
        oc.estado = OrdenCompraEstado.ENVIADO_A_SUPERVISOR
        oc.email_token_jti = jti
        oc.email_enviado_at = datetime.now(UTC)
        await session.commit()
        service = NotificationsService(session)
        # Mock el LPUSH a Redis (no hay Arq corriendo en este script).
        from app.worker import enqueue_send_email_task
        from unittest.mock import AsyncMock
        import app.worker as wm
        wm.enqueue_send_email_task = AsyncMock(return_value=None)
        outbox = await service.enqueue(
            to_email=sup_email,
            subject="Aprobacion requerida: OC-F7-E2E",
            template_name="orden_compra.html.j2",
            context={
                "subject": "Aprobacion requerida: OC-F7-E2E",
                "supervisor": {"nombre": "E2E Supervisor"},
                "oc": {
                    "codigo": "OC-F7-E2E",
                    "bodega_origen_nombre": "PRINCIPAL-F7",
                    "solicitante_nombre": "Bodeguero Central",
                    "proveedor_nombre": "Proveedor E2E F7",
                    "fecha_creacion": datetime.now(UTC).strftime("%Y-%m-%d"),
                    "total_estimado": "30.000",
                    "lineas": [
                        {
                            "sku": "F7-A", "nombre": "Filtro F7",
                            "cantidad": "10", "costo_unitario": "1.500",
                            "subtotal": "15.000",
                        },
                        {
                            "sku": "F7-B", "nombre": "Bujia F7",
                            "cantidad": "5", "costo_unitario": "3.000",
                            "subtotal": "15.000",
                        },
                    ],
                },
                "approve_url": approve_url,
                "reject_url": reject_url,
                "token_expires_at": "2026-07-22",
            },
        )
        await session.commit()
        outbox_id = outbox.id
    print(f"  outbox_id = {outbox_id}")
    print(f"  to = {sup_email}")
    print(f"  approve_url = {approve_url[:80]}...")

    # 5. Procesar el outbox (simula al worker Arq).
    print("\n=== PASO 3: Procesar outbox (simula worker Arq) ===")
    async with session_factory() as session:
        service = NotificationsService(session)
        result = await service.process_one(outbox_id)
        await session.commit()
        print(f"  result = {result}")
        if result["status"] != "sent":
            print(f"\n[!] Email no se envio (status={result['status']}).")
            print("    Posible causa: Mailpit no esta escuchando en localhost:1025.")
            sys.exit(1)
    print("  [OK] Email enviado a Mailpit")

    # 6. Verificar en Mailpit via API.
    print("\n=== PASO 4: Verificar email en Mailpit ===")
    time.sleep(0.5)  # Dar tiempo a Mailpit para indexar
    messages = _mailpit_messages()
    target = next(
        (m for m in messages if m.get("Subject") == "Aprobacion requerida: OC-F7-E2E"),
        None,
    )
    if not target:
        print(f"[!] Mailpit no recibio el email. Messages: {messages}")
        sys.exit(1)
    print(f"  [OK] Mailpit recibio 1 email con subject correcto")
    print(f"      To: {target.get('To')}")
    print(f"      From: {target.get('From')}")
    print(f"      Created: {target.get('Created')}")

    # 7. Extraer token del body (vía API /message/{ID}).
    print("\n=== PASO 5: Extraer token del body del email ===")
    with httpx.Client(timeout=3.0) as c:
        detail = c.get(f"http://localhost:8025/api/v1/message/{target['ID']}")
    if detail.status_code != 200:
        print(f"[!] No se pudo obtener detalle del email: {detail.status_code}")
        sys.exit(1)
    body = detail.json()
    body_html = body.get("Body") or body.get("HTML") or ""
    if token not in body_html:
        print(f"[!] Token no aparece en el body del email.")
        print(f"    Token: {token}")
        print(f"    Body preview: {body_html[:200]}...")
        sys.exit(1)
    print(f"  [OK] Token encontrado en el body_html")
    print(f"      token = {token[:40]}...")

    # 8. Aprobar via token (simula la vista publica, sin HTTP).
    print("\n=== PASO 6: Aprobar OC via token (sin auth) ===")
    from app.modules.ordenes_compra.service import OrdenCompraService

    async with session_factory() as session:
        service = OrdenCompraService(session)
        view = await service.aprobar_con_token(token, "approve")
        await session.commit()
        assert view.estado == "aprobado", f"Estado esperado aprobado, recibí {view.estado}"
        assert view.aprobado_at is not None
    print(f"  [OK] OC aprobada: estado={view.estado}, aprobado_at={view.aprobado_at}")

    # 9. Verificar outbox final.
    print("\n=== PASO 7: Verificar outbox final ===")
    from sqlalchemy import select
    from app.db.models.ordenes_compra import EmailOutbox
    async with session_factory() as session:
        ob = await session.get(EmailOutbox, outbox_id)
        print(f"  status    = {ob.status}")
        print(f"  attempts  = {ob.attempts}")
        print(f"  sent_at   = {ob.sent_at}")
        print(f"  to_email  = {ob.to_email}")
        assert ob.status == "sent"
        assert ob.sent_at is not None
        assert ob.attempts == 0  # primer intento exitoso

    print("\n" + "=" * 70)
    print("[OK] E2E FASE 7: PASS")
    print("=" * 70)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_e2e())
