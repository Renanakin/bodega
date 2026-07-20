"""Acciones del workflow de solicitudes de recarga.

Cada archivo contiene una accion del workflow:
- crear.py     : crear solicitud (PENDING)
- aprobar.py   : aprobar solicitud (PENDING -> APPROVED)
- despachar.py : despachar solicitud (APPROVED -> IN_TRANSIT)
- recibir.py   : recibir solicitud (IN_TRANSIT -> RECEIVED o PARTIALLY_RECEIVED)
- rechazar.py  : rechazar solicitud (PENDING o APPROVED -> REJECTED)
- cancelar.py  : cancelar solicitud (PENDING -> CANCELLED)

`_common.py` contiene los helpers compartidos (SolicitudView, lock_or_404,
to_view, validate_direction, utcnow, api_estado).
"""
