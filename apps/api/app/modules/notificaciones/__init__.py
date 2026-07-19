"""Notificaciones in-app (Fase 8).

Inbox de notificaciones dentro de la aplicacion web (complementa al
``email_outbox`` de Fase 7, que es el transporte async de emails via
SMTP). Cada usuario ve su lista de notificaciones en la campanita del
AppShell (no en este modulo; eso es front).

Endpoints:
- ``GET    /api/v1/notificaciones``                  — lista del usuario actual
- ``GET    /api/v1/notificaciones/no-leidas/count``  — contador para badge
- ``POST   /api/v1/notificaciones/{id}/marcar-leida`` — marca una como leida
- ``POST   /api/v1/notificaciones/marcar-todas-leidas`` — bulk
"""
