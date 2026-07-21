"""Paquete principal de la API Bodegaje.

Este archivo existe para que mypy pueda resolver correctamente los modulos
con el mismo basename en distintos subpaquetes (ej. router.py en
app/api/ y app/modules/*/router.py). Sin __init__.py aqui, Python
trata `app` como namespace package y mypy colisiona los nombres.

Vacio a proposito: el setup de logging, settings, etc. se hace en modulos
especificos que se importan explicitamente.
"""
