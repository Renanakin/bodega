"""
Router de categorías (Fase 2).

Endpoints:
- ``GET    /api/v1/categories``            — listado con filtros
- ``POST   /api/v1/categories``            — crear
- ``GET    /api/v1/categories/{id}``       — detalle
- ``PATCH  /api/v1/categories/{id}``       — actualización parcial
- ``DELETE /api/v1/categories/{id}``       — soft delete

El router es liviano (Regla de Oro): validacion de input via Pydantic,
logica en ``CategoryService``. Errores de dominio se traducen a HTTP
vía ``DomainError`` handler registrado en ``main.py``.
"""

from __future__ import annotations

from uuid import UUID

from app.db.session import SQLiteDatabase, get_database
from app.modules.auth.dependencies import require_roles
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import (
    CategoryCreate,
    CategoryNode,
    CategoryResponse,
    CategoryUpdate,
)
from app.modules.categories.service import CategoryService
from fastapi import APIRouter, Depends, Query, status

router = APIRouter()


def get_category_service(db: SQLiteDatabase = Depends(get_database)) -> CategoryService:
    return CategoryService(CategoryRepository(db))


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    is_active: bool | None = Query(default=None),
    parent_id: UUID | None = Query(default=None),
    _: object = Depends(get_current_user),
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryResponse]:
    return service.list_categories(is_active=is_active, parent_id=parent_id)


@router.get("/arbol", response_model=list[CategoryNode])
def get_arbol(
    solo_activos: bool = Query(
        default=True, description="Si True (default), oculta nodos is_active=False."
    ),
    _: object = Depends(get_current_user),
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryNode]:
    """Jerarquia completa en una sola llamada (Fase 8).

    Equivalente a un GET con todos los registros + parent_id, pero ya
    anidado en ``children`` para que el front pinte el arbol directamente
    sin re-armar la jerarquia en JS.
    """
    return service.get_arbol(solo_activos=solo_activos)


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    user=Depends(require_roles("admin", "supervisor")),
    service: CategoryService = Depends(get_category_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> CategoryResponse:
    category = service.create_category(payload)
    auth_service.audit(
        user_id=user.id,
        action="category.create",
        entity_type="category",
        entity_id=str(category.id),
        detail=f"Categoria {category.nombre} creada",
    )
    return category


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: UUID,
    _: object = Depends(get_current_user),
    service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    return service.get_category(category_id)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    user=Depends(require_roles("admin", "supervisor")),
    service: CategoryService = Depends(get_category_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> CategoryResponse:
    category = service.update_category(category_id, payload)
    auth_service.audit(
        user_id=user.id,
        action="category.update",
        entity_type="category",
        entity_id=str(category_id),
        detail=f"Categoria {category.nombre} actualizada",
    )
    return category


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # explicito: FastAPI >= 0.116 confunde -> None con NoneType
)
def delete_category(
    category_id: UUID,
    user=Depends(require_roles("admin", "supervisor")),
    service: CategoryService = Depends(get_category_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    service.delete_category(category_id)
    auth_service.audit(
        user_id=user.id,
        action="category.delete",
        entity_type="category",
        entity_id=str(category_id),
        detail=f"Categoria {category_id} desactivada",
    )
