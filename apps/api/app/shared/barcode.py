"""
BarcodeValidator: normaliza y valida codigos de barras (Fase 7).

Soporta:
- EAN-13 (13 digitos, checksum valido)
- EAN-8 (8 digitos, checksum valido)
- Code 128 (alfanumerico)
- Code 39 (alfanumerico + algunos simbolos)
- QR / DataMatrix (cualquier string, sin validacion de checksum)
"""

from __future__ import annotations

import re
from enum import StrEnum


class BarcodeFormat(StrEnum):
    EAN_13 = "ean_13"
    EAN_8 = "ean_8"
    CODE_128 = "code_128"
    CODE_39 = "code_39"
    QR = "qr"
    DATAMATRIX = "datamatrix"
    UNKNOWN = "unknown"


class BarcodeValidationError(ValueError):
    """El codigo es invalido (checksum, formato o vacio)."""


def normalize_barcode(raw: str) -> str:
    """Normaliza: trim, uppercase, sin espacios ni guiones."""
    if raw is None:
        raise BarcodeValidationError("barcode is None")
    cleaned = raw.strip().replace(" ", "").replace("-", "").upper()
    if not cleaned:
        raise BarcodeValidationError("barcode is empty")
    return cleaned


def detect_format(barcode: str) -> BarcodeFormat:
    """Detecta el formato del barcode."""
    if re.fullmatch(r"\d{13}", barcode):
        return BarcodeFormat.EAN_13
    if re.fullmatch(r"\d{8}", barcode):
        return BarcodeFormat.EAN_8
    if re.fullmatch(r"[A-Z0-9\-./ ]{1,48}", barcode) and " " in barcode:
        return BarcodeFormat.CODE_128
    if re.fullmatch(r"[A-Z0-9\-. $/+%]{1,48}", barcode):
        return BarcodeFormat.CODE_39
    return BarcodeFormat.UNKNOWN


def _ean_checksum_ok(code: str) -> bool:
    """Valida el checksum EAN-13/8 modulo 10."""
    if not code.isdigit() or len(code) not in (8, 13):
        return False
    digits = [int(c) for c in code]
    check_digit = digits[-1]
    body = digits[:-1]
    # EAN-13: posiciones pares (0,2,4...) peso 1, impares peso 3
    # EAN-8: similar pero empieza con peso 3
    total = 0
    for i, d in enumerate(body):
        weight = (1 if i % 2 == 0 else 3) if len(code) == 13 else 3 if i % 2 == 0 else 1
        total += d * weight
    expected = (10 - (total % 10)) % 10
    return check_digit == expected


def validate_barcode(raw: str) -> tuple[str, BarcodeFormat]:
    """Valida y normaliza un barcode.

    Raises:
        BarcodeValidationError: si el formato no es valido o el checksum falla.

    Returns:
        Tupla (barcode_normalizado, formato_detectado).
    """
    if raw is None:
        raise BarcodeValidationError("barcode is None")
    # Detectar formato ANTES de normalizar (espacios significativos en Code 128)
    fmt = detect_format(raw.strip())
    cleaned = normalize_barcode(raw)

    if fmt in (BarcodeFormat.EAN_13, BarcodeFormat.EAN_8):
        if not _ean_checksum_ok(cleaned):
            raise BarcodeValidationError(f"EAN checksum invalido: {cleaned}")
    elif fmt == BarcodeFormat.CODE_128:
        if len(raw.strip()) < 4:
            raise BarcodeValidationError(f"Code 128 demasiado corto: {raw}")
    elif fmt == BarcodeFormat.CODE_39 and len(cleaned) < 4:
        raise BarcodeValidationError(f"Code 39 demasiado corto: {cleaned}")
    # QR / DataMatrix / UNKNOWN: no validamos checksum, solo formato basico
    if len(cleaned) > 100:
        raise BarcodeValidationError(f"Barcode demasiado largo: {len(cleaned)} chars")

    return cleaned, fmt
