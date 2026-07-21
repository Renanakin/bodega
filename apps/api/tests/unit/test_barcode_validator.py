"""
Tests del validador de codigos de barras (Fase 5, modulo ``app.modules.barcode``).

Cubre:
- normalizacion (trim, sin espacios/guiones, upper).
- deteccion de formato (EAN-13, EAN-8, Code 128, Code 39, QR, UNKNOWN).
- checksum EAN-13/8 modulo 10.
- validacion combinada (formato + checksum).
- match_product() con y sin codigo_barras en el producto.
- BarcodeFormatError en entradas invalidas (None, vacio).

Los tests son sincronos y NO requieren BD: el modulo ``barcode`` es
codigo puro (sin dependencias de SQLAlchemy / Pydantic).
"""

from __future__ import annotations

import pytest
from app.core.errors import BarcodeFormatError
from app.modules.barcode import (
    BarcodeFormat,
    detect_format,
    match_product,
    normalize,
    validate,
)

pytestmark = pytest.mark.unit


# ============================================================== normalize()


class TestNormalize:
    def test_normalizar_quita_espacios_y_guiones(self) -> None:
        assert normalize("  789-1234  ") == "7891234"

    def test_normalizar_uppercase(self) -> None:
        assert normalize("abc-123") == "ABC123"

    def test_normalizar_sin_espacios_internos(self) -> None:
        assert normalize("789 1234 5678") == "78912345678"

    def test_normalizar_none_lanza_error(self) -> None:
        with pytest.raises(BarcodeFormatError):
            normalize(None)  # type: ignore[arg-type]

    def test_normalizar_vacio_lanza_error(self) -> None:
        with pytest.raises(BarcodeFormatError):
            normalize("")
        with pytest.raises(BarcodeFormatError):
            normalize("   ")


# ============================================================ detect_format()


class TestDetectFormat:
    def test_detectar_formato_ean_13(self) -> None:
        # 5901234123457 es EAN-13 valido
        assert detect_format(normalize("5901234123457")) == BarcodeFormat.EAN_13

    def test_detectar_formato_ean_8(self) -> None:
        assert detect_format(normalize("73513537")) == BarcodeFormat.EAN_8

    def test_detectar_formato_code_39(self) -> None:
        # Code 39: alfanumerico + simbolos especificos (.-$/+% espacio)
        # "AB-12" usa solo el charset de Code 39, no el de Code 128 (que
        # es mas amplio y matchearia antes).
        assert detect_format(normalize("AB-12")) == BarcodeFormat.CODE_39

    def test_detectar_formato_code_128(self) -> None:
        # Code 128 admite cualquier ASCII imprimible (0x21-0x7E), incluyendo
        # caracteres que NO son validos en Code 39 (ej. ":", "=", "*").
        # Usamos ":" para forzar la deteccion de Code 128.
        assert detect_format(normalize("ABC:123")) == BarcodeFormat.CODE_128

    def test_detectar_formato_qr(self) -> None:
        # QR: string ASCII imprimible mas largo que el limite de Code 128
        # (48 chars). 50+ chars cae al catch-all de QR.
        qr_largo = "https://bodega.local/qr/abcdefghijklmnopqrstuvwxyz12345"
        assert len(qr_largo) > 48
        assert detect_format(qr_largo) == BarcodeFormat.QR

    def test_detectar_formato_unknown_por_caracteres_de_control(self) -> None:
        # String con tab (0x09) que sobrevive a normalize() y no matchea
        # ningun charset (Code 39/128 son 0x21-0x7E; QR es 0x20-0x7E).
        assert detect_format("AB\x09CD") == BarcodeFormat.UNKNOWN


# ======================================================= _ean_checksum_is_valid
# (cubierto indirectamente via validate; este test documenta la convencion)


class TestEanChecksumConvention:
    """Documenta que el algoritmo EAN-13/8 usa la convencion estandar:

    - Posicion 0 (primer digito desde la izquierda) -> peso 1.
    - Posicion 1 -> peso 3.
    - Alterna hasta el check digit (excluido).
    - Para EAN-8, los pesos se invierten (posicion 0 -> peso 3)
      para compensar los 4 digitos menos en el body.
    """

    def test_ean_13_peso_1_en_posicion_0(self) -> None:
        # 4006381333931: 4*1+0*3+0*1+6*3+3*1+8*3+1*1+3*3+3*1+3*3+9*1+3*3 = 89
        # 89 mod 10 = 9; (10-9) mod 10 = 1; check digit = 1.
        is_valid, normalized, fmt = validate("4006381333931")
        assert is_valid is True
        assert normalized == "4006381333931"
        assert fmt == BarcodeFormat.EAN_13

    def test_ean_8_peso_3_en_posicion_0(self) -> None:
        # 73513537 es EAN-8 valido
        is_valid, normalized, fmt = validate("73513537")
        assert is_valid is True
        assert normalized == "73513537"
        assert fmt == BarcodeFormat.EAN_8


# ================================================================== validate()


class TestValidate:
    def test_validar_ean13_valido(self) -> None:
        # 5901234123457 es EAN-13 valido
        is_valid, normalized, fmt = validate("5901234123457")
        assert (is_valid, normalized, fmt) == (True, "5901234123457", BarcodeFormat.EAN_13)

    def test_validar_ean13_invalido_por_checksum(self) -> None:
        # Mismo codigo pero con check digit alterado (0 en vez de 7)
        is_valid, normalized, fmt = validate("5901234123450")
        assert is_valid is False
        assert normalized == "5901234123450"
        assert fmt == BarcodeFormat.EAN_13

    def test_validar_code128_sin_checksum(self) -> None:
        # Code 128 no tiene checksum; cualquier string valido pasa.
        # Usamos ":" para forzar la deteccion como Code 128 (Code 39
        # no admite ":").
        is_valid, normalized, fmt = validate("ABC:123")
        assert (is_valid, normalized, fmt) == (True, "ABC:123", BarcodeFormat.CODE_128)

    def test_validar_code39_tambien_pasa_sin_checksum(self) -> None:
        # "ABC123" matchea Code 39 (que es chequeado antes de Code 128).
        # El resultado importante es que es valido (sin checksum).
        is_valid, normalized, fmt = validate("ABC123")
        assert (is_valid, normalized, fmt) == (True, "ABC123", BarcodeFormat.CODE_39)

    def test_barcode_vacio_lanza_error(self) -> None:
        with pytest.raises(BarcodeFormatError):
            validate("")
        with pytest.raises(BarcodeFormatError):
            validate("   ")

    def test_barcode_solo_guiones_se_normaliza_a_vacio_y_lanza_error(self) -> None:
        with pytest.raises(BarcodeFormatError):
            validate("---")
        with pytest.raises(BarcodeFormatError):
            validate("  -  ")


# ============================================================== match_product()


class TestMatchProduct:
    def test_match_product_sin_codigo_retorna_true(self) -> None:
        """Producto sin codigo_barras: skip de la validacion."""
        assert match_product("5901234123457", None) is True
        assert match_product("cualquier-cosa", "") is True

    def test_match_product_con_codigos_iguales_retorna_true(self) -> None:
        """Match exacto con normalizacion (espacios, guiones, case)."""
        assert match_product("5901234123457", "5901234123457") is True
        assert match_product(" 590-1234-123457 ", "5901234123457") is True
        assert match_product("5901234123457", " 590-1234-123457 ") is True

    def test_match_product_con_codigos_diferentes_retorna_false(self) -> None:
        assert match_product("5901234123457", "4006381333931") is False

    def test_match_product_con_escaneado_invalido_retorna_false(self) -> None:
        """Escaneo con checksum EAN malo -> no matchea aunque el codigo
        del producto sea el mismo (porque no se puede normalizar)."""
        # Check digit 0 en lugar de 7 -> checksum invalido
        assert match_product("5901234123450", "5901234123457") is False

    def test_match_product_con_escaneado_vacio_retorna_false(self) -> None:
        # Producto con codigo, escaneo vacio -> no matchea
        assert match_product("", "5901234123457") is False
        assert match_product("   ", "5901234123457") is False

    def test_match_product_acepta_code128_sin_checksum(self) -> None:
        """Code 128 es valido sin checksum; el matching es por igualdad
        normalizada sin importar el formato detectado."""
        # "ABC:123" fuerza Code 128 (Code 39 no admite ":")
        assert match_product("ABC:123", "ABC:123") is True
        assert match_product("ABC:123", "ABC:999") is False
        # "ABC123" matchea Code 39; tambien pasa porque no requiere checksum
        assert match_product("ABC123", "ABC123") is True
        assert match_product("ABC123", "ABC999") is False
