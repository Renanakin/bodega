"""
Validador de codigos de barras para la recepcion con escaneo (Fase 5).

Modulo independiente de BD (codigo puro), pensado para integrarse con
``SolicitudService.receive()`` y mantener el principio de "validator sin
side effects".

Reglas de la fase:
- EAN-13 / EAN-8: validar checksum modulo 10.
- Code 128 / Code 39: solo normalizar (sin checksum).
- QR / DataMatrix: solo normalizar.
- Producto sin codigo_barras: skip (no validar).
- Producto con codigo_barras: validar formato del escaneado y comparar.

NOTA: existe otro modulo similar en ``app/shared/barcode.py`` (Fase 7,
pensado para catalogos y printing de etiquetas). Esa API es distinta
(``validate_barcode`` retorna tupla de 2). Aqui mantenemos una API
especifica para el flujo de recepcion:
    - ``validate(raw) -> (is_valid, normalized, format)``
    - ``match_product(scanned, product_codigo_barras) -> bool``
para que ``SolicitudService._apply_receive`` no necesite ``try/except``
y mantenga la logica de negocio legible.
"""
from app.modules.barcode.validator import (
    BarcodeFormat,
    detect_format,
    match_product,
    normalize,
    validate,
)

__all__ = [
    "BarcodeFormat",
    "detect_format",
    "match_product",
    "normalize",
    "validate",
]
