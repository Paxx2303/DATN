"""Tests cho module ALPR (chuẩn hoá biển số VN + graceful degradation)."""
import pytest

from alpr import normalize_vn_plate, PlateRecognizer, plate_recognizer


@pytest.mark.parametrize("raw, expected", [
    ("51F12345", "51F-123.45"),     # ô tô: 1 chữ + 5 số
    ("51F-123.45", "51F-123.45"),   # đã đúng định dạng
    ("30A1234", "30A-1234"),        # ô tô đời cũ: 1 chữ + 4 số
    ("99-LD-567.89", "99LD-567.89"),# 2 chữ seri
    ("60B400.99", "60B-400.99"),
    ("  51 F 123 45 ", "51F-123.45"),
])
def test_normalize_valid(raw, expected):
    assert normalize_vn_plate(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "abc", "12", "30A123456789", "XYZ-123"])
def test_normalize_invalid(raw):
    assert normalize_vn_plate(raw) is None


def test_moto_ambiguity_defaults_to_car_grouping():
    # Chuỗi 8 ký tự không tách được seri xe máy → mặc định ưu tiên ô tô.
    assert normalize_vn_plate("29X12345") == "29X-123.45"


def test_recognizer_graceful_without_easyocr():
    # recognize(None) luôn trả [] dù easyocr có hay không (degrade gracefully).
    r = PlateRecognizer()
    assert r.recognize(None) == []
    assert plate_recognizer.recognize(None) == []
    # Khi easyocr CHƯA cài, is_available() phải là False (không ném lỗi).
    try:
        import easyocr  # noqa: F401
        easyocr_installed = True
    except ImportError:
        easyocr_installed = False
    if not easyocr_installed:
        assert r.is_available() is False
