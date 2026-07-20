"""Acciones del workflow de ordenes de compra.

Cada archivo contiene una accion del workflow:
- crear.py           : crear OC (BORRADOR)
- actualizar.py      : actualizar OC (solo BORRADOR)
- enviar.py          : enviar OC al supervisor (BORRADOR -> ENVIADO_A_SUPERVISOR)
- aprobar.py         : aprobar OC desde la app + aprobar_con_token (HMAC publico)
- rechazar.py        : rechazar OC desde la app
- marcar_comprada.py : marcar OC como comprada (APROBADO -> COMPRADO)

`_common.py` contiene los helpers compartidos (OrdenCompraView, require_oc,
to_view, ESTADOS_TERMINALES).
"""
