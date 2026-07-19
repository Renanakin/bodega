"""Tests del BarcodeValidator (Fase 7)."""
import pytest

from app.shared.barcode import (
    BarcodeFormat,
    BarcodeValidationError,
    detect_format,
    normalize_barcode,
    validate_barcode,
)


pytestmark = pytest.mark.unit


class TestNormalizeBarcode:
    def test_strips_whitespace(self) -> None:
        assert normalize_barcode("  12345  ") == "12345"

    def test_removes_dashes(self) -> None:
        assert normalize_barcode("123-456-789") == "123456789"

    def test_uppercase(self) -> None:
        assert normalize_barcode("abc-123") == "ABC123"

    def test_empty_raises(self) -> None:
        with pytest.raises(BarcodeValidationError):
            normalize_barcode("   ")

    def test_none_raises(self) -> None:
        with pytest.raises(BarcodeValidationError):
            normalize_barcode(None)  # type: ignore[arg-type]


class TestDetectFormat:
    def test_ean_13(self) -> None:
        assert detect_format("5901234123457") == BarcodeFormat.EAN_13

    def test_ean_8(self) -> None:
        assert detect_format("12345678") == BarcodeFormat.EAN_8

    def test_code_128(self) -> None:
        assert detect_format("ABC 1234") == BarcodeFormat.CODE_128

    def test_code_39(self) -> None:
        assert detect_format("ABC-123") == BarcodeFormat.CODE_39

    def test_unknown(self) -> None:
        assert detect_format("xyz") == BarcodeFormat.UNKNOWN


class TestValidateBarcode:
    def test_valid_ean_13(self) -> None:
        # 5901234123457 es EAN-13 valido (checksum)
        cleaned, fmt = validate_barcode("5901234123457")
        assert cleaned == "5901234123457"
        assert fmt == BarcodeFormat.EAN_13

    def test_invalid_ean_13_checksum(self) -> None:
        # Checksum incorrecto
        with pytest.raises(BarcodeValidationError):
            validate_barcode("5901234123450")  # ultimo digito mal

    def test_valid_code_128(self) -> None:
        cleaned, fmt = validate_barcode("ABC 1234")
        assert fmt == BarcodeFormat.CODE_128

    def test_short_code_rejected(self) -> None:
        with pytest.raises(BarcodeValidationError):
            validate_barcode("AB")

    def test_too_long_rejected(self) -> None:
        with pytest.raises(BarcodeValidationError):
            validate_barcode("X" * 200)
