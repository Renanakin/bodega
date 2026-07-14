# API/DB Inventory MVP Design

Date: 2026-03-17
Scope: `apps/api` first, then `db`
Status: Approved design pending written-spec review

## 1. Goal
Build the first real backend MVP for the multi-warehouse system with clean domain boundaries and without shortcut CRUD that would later rot into inconsistent stock logic.

The MVP must support:
- warehouse catalog
- product catalog
- current stock by warehouse/product
- auditable inventory movements
- stock changes only through domain services
- prevention of invalid stock outputs

## 2. Delivery Order
1. API design and implementation scaffolding
2. Database schema and versioned migration alignment
3. Verification with focused tests

## 3. Domain Scope
### Included
- Warehouses
- Products
- Inventory stock queries
- Inventory movement registration
- Inventory movement history
- Stock summary endpoint

### Deferred
- Transfers between warehouses
- Replenishment workflows
- Purchasing
- Chat/notifications
- Reports beyond simple summary
- Auth and permissions

## 4. Architectural Principles
- Modules grow by domain, not by technical layer across the whole app.
- Routers stay thin.
- Business rules live in services.
- Persistence stays in repositories.
- Stock is never modified directly from routes.
- Critical inventory operations must be transactional.
- Avoid unnecessary abstractions and avoid over-engineering for the MVP.

## 5. API Module Structure
Under `apps/api/app/modules/`:

### `warehouses/`
- `router.py`
- `schemas.py`
- `service.py`
- `repository.py`

### `products/`
- `router.py`
- `schemas.py`
- `service.py`
- `repository.py`

### `inventory/`
- `router.py`
- `schemas.py`
- `service.py`
- `repository.py`

Shared backend support kept minimal:
- `app/core/config.py`
- `app/core/errors.py`
- `app/db/session.py`
- optional lightweight model helpers only if they reduce duplication without hiding business rules

## 6. Data Model
### `warehouses`
Fields:
- `id`
- `code` unique
- `name`
- `warehouse_type`
- `is_active`
- `created_at`
- `updated_at`

### `products`
Fields:
- `id`
- `sku` unique
- `name`
- `unit`
- `is_active`
- `created_at`
- `updated_at`

### `inventory_movements`
Auditable movement ledger.
Fields:
- `id`
- `warehouse_id`
- `product_id`
- `movement_type`
- `quantity`
- `reference_type`
- `reference_id`
- `notes`
- `created_at`

Allowed movement types in the MVP:
- `in`
- `out`
- `adjustment_in`
- `adjustment_out`

### `stock_levels`
Current projection for fast reads.
Fields:
- `id`
- `warehouse_id`
- `product_id`
- `quantity`
- `min_quantity`
- `updated_at`

Constraints:
- unique `(warehouse_id, product_id)`
- foreign keys to warehouses/products

## 7. Transaction Model
When registering a movement:
1. validate warehouse exists
2. validate product exists
3. validate movement type and positive quantity
4. lock/read current stock row for `(warehouse_id, product_id)`
5. compute resulting stock
6. reject insufficient stock for outgoing movements
7. insert movement into `inventory_movements`
8. update or create `stock_levels`
9. commit transaction

## 8. Invariants
- `stock_levels` changes only through inventory domain service.
- `inventory_movements` is the audit source of truth.
- `stock_levels` is a fast-read projection, not an independently edited source.
- Outgoing movements cannot leave negative stock.
- `code` and `sku` remain unique.

## 9. API Contracts
Base prefix: `/api/v1`

### Warehouses
- `GET /warehouses`
- `POST /warehouses`
- optional immediate addition: `GET /warehouses/{warehouse_id}`

Create payload:
```json
{
  "code": "CENTRAL",
  "name": "Bodega Central",
  "warehouse_type": "central"
}
```

### Products
- `GET /products`
- `POST /products`
- optional immediate addition: `GET /products/{product_id}`

Create payload:
```json
{
  "sku": "SKU-001",
  "name": "Producto Inicial",
  "unit": "unit"
}
```

### Inventory
- `GET /inventory/stock`
- `GET /inventory/movements`
- `POST /inventory/movements`
- `GET /inventory/summary`

Movement payload:
```json
{
  "warehouse_id": "uuid",
  "product_id": "uuid",
  "movement_type": "in",
  "quantity": 10,
  "reference_type": "manual",
  "reference_id": "ajuste-001",
  "notes": "Carga inicial"
}
```

Suggested filters:
- stock: `warehouse_id`, `product_id`, `sku`
- movements: `warehouse_id`, `product_id`, `movement_type`, date range

## 10. Error Model
Stable domain errors mapped to HTTP:
- `warehouse_not_found` -> 404
- `product_not_found` -> 404
- `duplicate_warehouse_code` -> 409
- `duplicate_sku` -> 409
- `insufficient_stock` -> 409
- invalid payload / invalid movement type -> 422

## 11. Testing Strategy
### API tests
- healthcheck returns ok
- create/list warehouses
- create/list products
- register incoming movement
- register outgoing movement
- reject outgoing movement with insufficient stock
- query updated stock
- list movements

### DB validation
- unique warehouse code
- unique product sku
- unique `(warehouse_id, product_id)` in stock
- foreign keys intact
- quantity numeric constraints where appropriate

## 12. Implementation Order
### Phase 1: API
1. define pydantic schemas
2. implement repositories
3. implement services
4. wire real routers
5. normalize domain errors
6. add focused tests

### Phase 2: DB
1. finalize schema for warehouses/products/inventory movements/stock levels
2. add versioned initial migration
3. add minimal seeds only if they help local verification
4. align naming and constraints with API contracts

### Phase 3: Verification
1. run backend tests
2. validate schema/migration files
3. smoke test core endpoints
4. confirm stock cannot be changed outside movement service flow

## 13. Acceptance Criteria
The first increment is done when:
- warehouse/product catalogs have real create/list behavior
- inventory movements are persisted through a dedicated service path
- stock reads reflect movement writes
- outgoing movements fail when stock is insufficient
- schema is versioned and consistent with backend logic
- tests protect the main invariants

## 14. Intended File Scope
Primary implementation targets:
- `apps/api/**`
- `db/**`

This spec was written under `.omx/plans/` instead of `docs/` to respect the user's instruction to limit work to API and DB areas.