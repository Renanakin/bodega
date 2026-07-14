from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.db.session import SQLiteDatabase, get_database
from app.modules.auth.dependencies import require_roles
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate, ProductResponse
from app.modules.products.service import ProductService

router = APIRouter()


def get_product_service(db: SQLiteDatabase = Depends(get_database)) -> ProductService:
    return ProductService(ProductRepository(db))


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


@router.get("", response_model=list[ProductResponse])
def list_products(
    _: object = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> list[ProductResponse]:
    return service.list_products()


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    user=Depends(require_roles("admin", "supervisor")),
    service: ProductService = Depends(get_product_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> ProductResponse:
    product = service.create_product(payload)
    auth_service.audit(
        user_id=user.id,
        action="product.create",
        entity_type="product",
        entity_id=str(product.id),
        detail=f"Producto {product.sku} creado",
    )
    return product


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: UUID,
    _: object = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return service.get_product(product_id)
