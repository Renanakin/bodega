"""Proveedores externos: catalogo, contacto, productos que vende, lead time (Fase 8).

Endpoints:
- ``GET    /api/v1/proveedores``            — listado con filtro opcional ``?activo=true|false``
- ``POST   /api/v1/proveedores``            — crear (admin only)
- ``GET    /api/v1/proveedores/{id}``       — detalle
- ``PATCH  /api/v1/proveedores/{id}``       — actualizacion parcial
- ``DELETE /api/v1/proveedores/{id}``       — soft delete (admin only)

Diferencia con `users.role='supervisor'` y con `supervisores`: ``proveedores``
es la **persona juridica o natural externa** que vende los productos (no el
operador interno del sistema, ni el supervisor de turno). La OC los
referencia por nombre libre (Fase 6) — esta entidad permite que el dropdown
de "proveedor" en `OrdenesCompraPage` use datos canonicos y enriquecer la
OC con RUT/email/direccion sin re-tipificar.
"""
