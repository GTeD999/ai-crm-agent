import pytest

from app.utils.phone import normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+7 (999) 123-45-67", "+79991234567"),
        ("8 999 123 45 67", "+79991234567"),
        ("+7-999-123-45-67", "+79991234567"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


def test_invalid_phone() -> None:
    with pytest.raises(ValueError):
        normalize_phone("12345")

