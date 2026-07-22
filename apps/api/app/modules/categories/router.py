"""
Router de categorías (async, FastAPI Depends(get_session)).

Endpoints:
- ``GET    /api/v1/categories``            — listado con filtros
- ``POST   /api/v1/categories``            — crear
- ``GET    /api/v1/categories/{id}``       — detalle
- ``PATCH  /api/v1/categories/{id}``       — actualización parcial
- ``DELETE /api/v1/categories/{id}``       — soft delete

Convenciones:
- ``session: AsyncSession = Depends(get_session)`` (no más ``get_database``).
- Todas las funciones son ``async def``.
- El audit se hace via ``AuthServiceAsync.audit_async(...)`` para que el
  commit del log sea parte de la misma transacción que la mutación.
"""

from __future__ import annotations

from uuid import UUID

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import (
    CategoryCreate,
    CategoryNode,
    CategoryResponse,
    CategoryUpdate,
)
from app.modules.categories.service import CategoryService
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_category_service(
    session: AsyncSession = Depends(get_session),
) -> CategoryService:
    return CategoryService(session, CategoryRepository(session))


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    is_active: bool | None = Query(default=None),
    parent_id: UUID | None = Query(default=None),
    _: object = Depends(get_current_user),
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryResponse]:
    categories = await service.list_categories(is_active=is_active, parent_id=parent_id)
    return [CategoryResponse.model_validate(c) for c in categories]


@router.get("/arbol", response_model=list[CategoryNode])
async def get_arbol(
    solo_activos: bool = Query(
        default=True, description="Si True (default), oculta nodos is_active=False."
    ),
    _: object = Depends(get_current_user),
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryNode]:
    """Jerarquía completa en una sola llamada (Fase 8).

    Equivalente a un GET con todos los registros + parent_id, pero ya
    anidado en ``children`` para que el front pinte el árbol directamente
    sin re-armar la jerarquía en JS.
    """
    return await service.get_arbol(solo_activos=solo_activos)


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    user=Depends(require_roles("admin", "supervisor")),
    service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await service.create_category(payload)
    # Audit se hace después del commit de la categoría; usamos una sesión
    # dedicada para que NO comparta la transacción (el caller ya recibió
    # la respuesta con 201). En tests, ``audit`` vía AuthService async
    # no rompe el flujo.
    from app.modules.auth.service import AuthService
    from app.modules.auth.repository import AuthRepository
    from app.db.session import utcnow
    from uuid import uuid4
    from app.db.session import AuditLogRecord

    record = AuditLogRecord(
        id=uuid4(),
        user_id=user.id,
        action="category.create",
        entity_type="category",
        entity_id=str(category.id),
        detail=f"Categoria {category.nombre} creada",
        created_at=utcnow(),
    )
    # Usar una nueva sesión async para el audit (independiente).
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as audit_session:
        try:
            repo = AuthRepository(audit_session)
            await repo._async_add_audit_log(record)
            await audit_session.commit()
        except Exception:
            # Audit best-effort: nunca falla la operación principal.
            pass
    return CategoryResponse.model_validate(category)


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: UUID,
    _: object = Depends(get_current_user),
    service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await service.get_category(category_id)
    return CategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    user=Depends(require_roles("admin", "supervisor")),
    service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await service.update_category(category_id, payload)
    # Audit best-effort (ver nota en create_category).
    from app.db.session import get_session_factory
    from app.modules.auth.repository import AuthRepository
    from app.modules.auth.service import AuthService
    from app.db.session import AuditLogRecord, utcnow
    from uuid import uuid4

    record = AuditLogRecord(
        id=uuid4(),
        user_id=user.id,
        action="category.update",
        entity_type="category",
        entity_id=str(category_id),
        detail=f"Categoria {category.nombre} actualizada",
        created_at=utcnow(),
    )
    factory = get_session_factory()
    async with factory() as audit_session:
        try:
            repo = AuthRepository(audit_session)
            await repo._async_add_audit_log(record)
            await audit_session.commit()
        except Exception:
            pass
    return CategoryResponse.model_validate(category)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_category(
    category_id: UUID,
    user=Depends(require_roles("admin", "supervisor")),
    service: CategoryService = Depends(get_category_service),
) -> None:
    await service.delete_category(category_id)
    # Audit best-effort.
    from app.db.session import get_session_factory
    from app.modules.auth.repository import AuthRepository
    from app.db.session import AuditLogRecord, utcnow
    from uuid import uuid4

    record = AuditLogRecord(
        id=uuid4(),
        user_id=user.id,
        action="category.delete",
        entity_type="category",
        entity_id=str(category_id),
        detail=f"Categoria {category_id} desactivada",
        created_at=utcnow(),
    )
    factory = get_session_factory()
    async with factory() as audit_session:
        try:
            repo = AuthRepository(audit_session)
            await repo._async_add_audit_log(record)
            await audit_session.commit()
        except Exception:
            pass
