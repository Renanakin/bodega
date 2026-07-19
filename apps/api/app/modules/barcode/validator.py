"""
Validador puro de codigos de barras (Fase 5: recepcion con escaneo).

Soporta:
- EAN-13 (13 digitos, checksum modulo 10).
- EAN-8  (8 digitos, checksum modulo 10).
- Code 128 (alfanumerico, sin checksum).
- Code 39 (alfanumerico + simbolos, sin checksum).
- QR / DataMatrix (string libre).

NO tiene dependencias externas (no SQLAlchemy, no Pydantic) para ser
100% unit-testable en aislamiento y reusable en cualquier capa (service,
worker, future CLI de catalogos).

API publica:
    normalize(raw)        -> str           (trim, sin espacios/guiones, upper)
    detect_format(bc)     -> BarcodeFormat (clasifica por longitud y charset)
    _ean_checksum_is_valid(digits) -> bool  (algoritmo modulo 10)
    validate(raw)         -> tuple[bool, str, BarcodeFormat]
                             (valida formato + checksum; raises BarcodeFormatError)
    match_product(scanned, product_codigo_barras) -> bool
                             (True si coincide, o si el producto no tiene barcode)

El error de dominio ``BarcodeFormatError`` se importa de ``app.core.errors``
para mantener consistencia con el resto del proyecto (ver errors.py).
"""
from __future__ import annotations

import re
from enum import Enum

from app.core.errors import BarcodeFormatError


class BarcodeFormat(str, Enum):
    """Formatos de codigo de barras soportados."""

    EAN_13 = "ean_13"
    EAN_8 = "ean_8"
    CODE_128 = "code_128"
    CODE_39 = "code_39"
    QR = "qr"
    DATAMATRIX = "datamatrix"
    UNKNOWN = "unknown"


# Patrones para detectar el formato segun el barcode normalizado.
# IMPORTANTE: el orden de chequeo importa. Los formatos mas especificos
# van primero para evitar que Code 128 (ASCII imprimible generico) capture
# todo. Code 39 se chequea antes que Code 128 porque su charset es mas
# restringido.
_RE_EAN_13 = re.compile(r"^\d{13}$")
_RE_EAN_8 = re.compile(r"^\d{8}$")
# Code 39: alfanumerico + simbolos especificos (.-$/+% espacio). Es un
# subset estricto de Code 128.
_RE_CODE_39 = re.compile(r"^[A-Z0-9\-. $/+%]{1,48}$")
# Code 128: ASCII imprimible (rango 32-126) sin espacios significativos
# tras normalizar. Es el "catch-all" para cualquier string valido.
_RE_CODE_128 = re.compile(r"^[\x21-\x7E]{1,48}$")
# QR / DataMatrix: cualquier string hasta 100 chars (largo razonable
# para bodega). Si llegamos aca es porque Code 128 ya rechazo (o el
# barcode tiene espacios o es muy largo).
_RE_QR = re.compile(r"^[\x20-\x7E]{1,100}$")


def normalize(raw: str) -> str:
    """Quita espacios, guiones, y normaliza a uppercase ASCII.

    Args:
        raw: barcode leido del scanner (o tipeado manualmente).

    Returns:
        String normalizado (trim, sin ' ' ni '-', uppercase).

    Raises:
        BarcodeFormatError: si el barcode es vacio o None.
    """
    if raw is None:
        raise BarcodeFormatError("Barcode es None")
    cleaned = re.sub(r"[\s\-]", "", str(raw).strip()).upper()
    if not cleaned:
        raise BarcodeFormatError("Barcode vacio")
    return cleaned


def detect_format(barcode: str) -> BarcodeFormat:
    """Detecta el formato del barcode normalizado.

    La deteccion es POR FORMATO, no por checksum: un EAN-13 con checksum
    malo sigue siendo "ean_13" a nivel formato; el caller decide si
    acepta o rechaza segun ``_ean_checksum_is_valid``.

    Orden de chequeo: especifico -> generico. EAN (13/8) son inequivocos
    (solo digitos); Code 39 es un subset estricto de Code 128 (su charset
    es mas limitado) asi que va antes; Code 128 captura ASCII imprimible;
    QR/DataMatrix es el catch-all final.

    Args:
        barcode: barcode ya normalizado (ver ``normalize``).

    Returns:
        ``BarcodeFormat`` correspondiente, o ``UNKNOWN`` si no matchea
        ningun patron conocido.
    """
    if _RE_EAN_13.fullmatch(barcode):
        return BarcodeFormat.EAN_13
    if _RE_EAN_8.fullmatch(barcode):
        return BarcodeFormat.EAN_8
    if _RE_CODE_39.fullmatch(barcode):
        return BarcodeFormat.CODE_39
    if _RE_CODE_128.fullmatch(barcode):
        return BarcodeFormat.CODE_128
    if _RE_QR.fullmatch(barcode):
        # Distinguir QR vs DataMatrix es imposible sin metadatos;
        # devolvemos QR como el caso comun en bodega (etiquetas en caja).
        return BarcodeFormat.QR
    return BarcodeFormat.UNKNOWN


def _ean_checksum_is_valid(digits: str) -> bool:
    """Valida checksum EAN (modulo 10).

    Algoritmo estandar EAN-13/8 (desde la izquierda, 0-indexed):
    - Posicion 0: peso 1
    - Posicion 1: peso 3
    - Posicion 2: peso 1
    - Posicion 3: peso 3
    - ...
    Para EAN-8, los pesos se invierten (la primera posicion desde la
    izquierda tiene peso 3) para alinear con el algoritmo original que
    cuenta desde la derecha (donde el check digit ocupa la posicion 1).

    Suma de (digito * peso) sobre los primeros N-1 digitos + check_digit
    debe ser congruente a 0 modulo 10.

    Args:
        digits: barcode completo de 8 o 13 digitos.

    Returns:
        True si el checksum es valido, False en caso contrario.
    """
    if not digits.isdigit() or len(digits) not in (8, 13):
        return False
    digits_list = [int(d) for d in digits]
    check_digit = digits_list[-1]
    body = digits_list[:-1]

    # Pesos segun el estandar: EAN-13 empieza con peso 1 (idx 0);
    # EAN-8 empieza con peso 3 (idx 0) para compensar que tiene 4 digitos
    # menos en el body.
    if len(digits) == 13:
        weights = [1 if i % 2 == 0 else 3 for i in range(12)]
    else:  # 8
        weights = [3 if i % 2 == 0 else 1 for i in range(7)]
    total = sum(d * w for d, w in zip(body, weights))
    expected = (10 - (total % 10)) % 10
    return check_digit == expected


def validate(barcode: str) -> tuple[bool, str, BarcodeFormat]:
    """Valida formato Y (cuando aplica) checksum del barcode.

    Args:
        barcode: barcode leido del scanner (raw, sin normalizar).

    Returns:
        Tupla ``(is_valid, normalized, format)`` donde:
        - ``is_valid``: True si el formato es valido y (si aplica) el
          checksum es correcto. False para EAN con checksum malo o
          formatos desconocidos.
        - ``normalized``: el barcode ya normalizado (trim, sin espacios
          ni guiones, uppercase).
        - ``format``: ``BarcodeFormat`` detectado.

    Raises:
        BarcodeFormatError: si el barcode es None o vacio tras trim.
    """
    if not barcode:
        raise BarcodeFormatError("Barcode vacio")
    normalized = normalize(barcode)
    fmt = detect_format(normalized)

    if fmt in (BarcodeFormat.EAN_13, BarcodeFormat.EAN_8):
        if not _ean_checksum_is_valid(normalized):
            return False, normalized, fmt
    if fmt == BarcodeFormat.UNKNOWN:
        return False, normalized, fmt
    return True, normalized, fmt


def match_product(barcode: str, product_codigo_barras: str | None) -> bool:
    """Compara barcode escaneado contra el codigo registrado del producto.

    Reglas (Fase 5):
    - Si el producto NO tiene ``codigo_barras`` registrado, retorna True
      (skip de la validacion; muchos productos no tienen codigo fisico).
    - Si el producto tiene ``codigo_barras``:
        1. Normalizar y validar formato/checksum del escaneado.
        2. Comparar normalizado contra el codigo del producto.
    - Si el barcode escaneado no es normalizable, retorna False
      (sin raise: el caller decide si elevar BarcodeMismatchError).

    Args:
        barcode: barcode leido del scanner (puede tener espacios/guiones).
        product_codigo_barras: barcode registrado en ``products.codigo_barras``,
            o None si el producto no tiene.

    Returns:
        True si el barcode escaneado corresponde al producto o si el
        producto no tiene barcode. False en caso contrario.
    """
    if not product_codigo_barras:
        return True  # producto sin barcode registrado: skip
    try:
        is_valid, normalized, _ = validate(barcode)
    except BarcodeFormatError:
        return False
    if not is_valid:
        return False
    return normalize(product_codigo_barras) == normalized
